import flask
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import os
from werkzeug.security import generate_password_hash, check_password_hash # Added for password hashing
import uuid # Moved import to top
import llm_handler # Import the LLM handler
from datetime import datetime # To format timestamp
from urllib.parse import unquote  # Add this import for URL decoding


# Initialize Flask app
app = Flask(__name__)
# Enable CORS with all origins
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
# Configure the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///default.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Recommended to disable to save resources

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False) # Increased length for hash
    # A unique link_id will be generated for each user to share
    link_id = db.Column(db.String(80), unique=True, nullable=False)
    feedbacks = db.relationship('Feedback', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>' # Changed to username for better representation

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # How the anonymous user knows the person (e.g., classmate, colleague)
    anon_identifier = db.Column(db.String(200), nullable=True)
    feedback_text = db.Column(db.Text, nullable=False)
    context_text = db.Column(db.Text, nullable=True)
    # Optional email from the anonymous user
    anon_email = db.Column(db.String(120), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    # Cached LLM output (populated on submit, or lazily on first read of older rows)
    llm_sentiment = db.Column(db.String(100), nullable=True)
    llm_summary = db.Column(db.Text, nullable=True)
    llm_constructive_criticism = db.Column(db.Text, nullable=True)
    llm_processed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<Feedback {self.id} for User {self.user_id}>'

# Helper function to generate a unique link_id (you might want a more robust solution)
# import uuid # Moved to top
def generate_unique_link_id():
    return str(uuid.uuid4())[:8] # Example: first 8 chars of a UUID

def process_and_cache_feedback(fb_item):
    """
    Runs the feedback through the LLM, writes the result onto the Feedback row's
    llm_* cache columns, commits, and returns the (sentiment, summary, constructiveCriticism)
    tuple ready for the API response. Never raises - falls back to placeholder text
    and leaves llm_processed_at unset on failure, so it will be retried on next read.
    """
    feedback_input_dict = {
        'anon_identifier': fb_item.anon_identifier or 'Tidak disebutkan',
        'context_text': fb_item.context_text or 'Tidak disebutkan',
        'feedback_text': fb_item.feedback_text
    }

    # Default values for LLM processed fields
    parsed_sentiment = "Netral Aja 😐"
    parsed_summary = "Tidak dapat memproses ringkasan saat ini."
    parsed_constructive_criticism = "Tidak ada saran spesifik saat ini."

    try:
        llm_response_dict = llm_handler.summarize_text_with_llm(
            item_to_summarise=feedback_input_dict,
            model_provider="anthropic" # Or get from os.getenv('MODEL_TYPE', "anthropic")
        )

        raw_sentiment = llm_response_dict.get("sentiment", "Netral Aja")
        if "error" in raw_sentiment.lower() or "could not process" in llm_response_dict.get("summary", "").lower():
            # Keep default error messages if LLM indicated an issue; don't cache a failure.
            return parsed_sentiment, parsed_summary, parsed_constructive_criticism

        parsed_summary = llm_response_dict.get("summary", parsed_summary)
        parsed_constructive_criticism = llm_response_dict.get("constructiveCriticism", parsed_constructive_criticism)

        # Add emoji to sentiment
        if "positif" in raw_sentiment.lower():
            parsed_sentiment = f"{raw_sentiment} 👍"
        elif "negatif" in raw_sentiment.lower():
            parsed_sentiment = f"{raw_sentiment} 😟"
        else: # Netral or other
            parsed_sentiment = f"{raw_sentiment} 😐"

        fb_item.llm_sentiment = parsed_sentiment
        fb_item.llm_summary = parsed_summary
        fb_item.llm_constructive_criticism = parsed_constructive_criticism
        fb_item.llm_processed_at = datetime.utcnow()
        db.session.commit()

    except (ValueError, NotImplementedError) as e:
        print(f"LLM configuration error for feedback ID {fb_item.id}: {e}")
        # Fallback values are already set (parsed_sentiment, parsed_summary, etc.)
    except Exception as e:
        print(f"Error processing feedback ID {fb_item.id} with LLM: {e}")
        # Fallback values are already set

    return parsed_sentiment, parsed_summary, parsed_constructive_criticism

# Create database tables if they don't exist
with app.app_context():
    db.create_all()
    # db.create_all() only creates missing tables, it never alters existing ones.
    # Since this project has no migration framework (Alembic/Flask-Migrate), backfill
    # the new LLM-cache columns on an already-existing `feedback` table by hand.
    # Idempotent (IF NOT EXISTS) so it's safe to run on every startup.
    if db.engine.dialect.name == 'postgresql':
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS llm_sentiment VARCHAR(100)"))
            conn.execute(text("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS llm_summary TEXT"))
            conn.execute(text("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS llm_constructive_criticism TEXT"))
            conn.execute(text("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS llm_processed_at TIMESTAMP"))

@app.route('/api/auth/register', methods=['POST'])
def register_user():
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No input data provided'}), 400

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'message': 'Username, email, and password are required'}), 400

    if User.query.filter_by(username=username).first() is not None:
        return jsonify({'message': 'Username already exists'}), 409 # 409 Conflict
    
    if User.query.filter_by(email=email).first() is not None:
        return jsonify({'message': 'Email already registered'}), 409

    hashed_password = generate_password_hash(password)
    new_link_id = generate_unique_link_id()
    # Ensure link_id is unique (though collision is highly unlikely with UUIDs)
    while User.query.filter_by(link_id=new_link_id).first() is not None:
        new_link_id = generate_unique_link_id()

    new_user = User(
        username=username,
        email=email,
        password_hash=hashed_password,
        link_id=new_link_id
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        'message': 'User registered successfully', 
        'user_id': new_user.id,
        'username': new_user.username,
        'email': new_user.email, # Added email to response
        'link_id': new_user.link_id
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def login_user():
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No input data provided'}), 400

    identifier = data.get('identifier') # Changed from 'email' to 'identifier'
    password = data.get('password')

    if not identifier or not password:
        return jsonify({'message': 'Identifier (email/username) and password are required'}), 400

    # Try to find user by email or username
    user = User.query.filter((User.email == identifier) | (User.username == identifier)).first()

    if user and check_password_hash(user.password_hash, password):
        # Login successful - In a real app, generate and return a token (e.g., JWT) here
        return jsonify({
            'message': 'Login successful',
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'link_id': user.link_id
            # Add token here in a real app: 'token': generated_token
        }), 200
    else:
        # Invalid credentials
        return jsonify({'message': 'Invalid credentials'}), 401

@app.route('/api/user/lookup/<identifier>', methods=['GET'])
def lookup_user(identifier):
    # Try to find user by username or link_id or email
    # user_username = User.query.filter((User.username == identifier)).first()
    # user_link_id = User.query.filter((User.link_id == identifier)).first()
    # user_email = User.query.filter((User.email == identifier)).first()
    user_username = User.query.filter_by(username=identifier).first()
    user_link_id = User.query.filter_by(link_id=identifier).first()
    user_email = User.query.filter_by(email=identifier).first()
    if user_username:
        return jsonify({'user_identifier': user_username.username}), 200
        # legacy format:
        # return jsonify({'link_id': user.link_id}), 200
    elif user_link_id:
        return jsonify({'user_identifier': user_link_id.link_id}), 200
    elif user_email:
        return jsonify({'user_identifier': user_email.email}), 200
    else:
        # If no user found by username, link_id, or email
        return jsonify({'message': 'Pengguna tidak ditemukan atau ID tidak valid'}), 404

@app.route('/api/users', methods=['POST'])
def create_user():
    # This endpoint might be deprecated or re-purposed if all user creation goes through /api/auth/register
    # For now, it remains as a simple way to create a user with just a link_id,
    # but it doesn't set username, email, or password.
    # Consider if this is still needed or how it should interact with the new registration flow.
    new_link_id = generate_unique_link_id()
    # Ensure link_id is unique
    while User.query.filter_by(link_id=new_link_id).first() is not None:
        new_link_id = generate_unique_link_id()
    
    new_user = User(link_id=new_link_id)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created successfully', 'link_id': new_link_id, 'user_id': new_user.id}), 201

@app.route('/api/feedback/<identifier>', methods=['POST'])
def submit_feedback(identifier):
    decoded_identifier = unquote(identifier)
    print(f"Attempting to find user with identifier: {decoded_identifier}")
    
    user = User.query.filter_by(username=decoded_identifier).first()
    if user:
        print(f"Found user by username: {user.username}")
    else:
        print("No user found by username")
        user = User.query.filter_by(link_id=decoded_identifier).first()
        if user:
            print(f"Found user by link_id: {user.link_id}")
        else:
            print("No user found by link_id")
            user = User.query.filter_by(email=decoded_identifier).first()
            if user:
                print(f"Found user by email: {user.email}")
            else:
                print("No user found by email")
    
    if not user:
        return jsonify({'message': 'User not found for the provided identifier'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'message': 'No input data provided'}), 400

    feedback_text = data.get('feedback_text')
    if not feedback_text:
        return jsonify({'message': 'Feedback text is required'}), 400

    anon_identifier = data.get('anon_identifier')
    context_text = data.get('context_text')
    anon_email = data.get('anon_email')

    new_feedback = Feedback(
        user_id=user.id,
        anon_identifier=anon_identifier,
        feedback_text=feedback_text,
        context_text=context_text,
        anon_email=anon_email
    )
    db.session.add(new_feedback)
    db.session.commit()

    # Warm the LLM cache immediately so the dashboard's first read is already fast.
    # If this fails (LLM error/timeout), the feedback is still saved; get_user_feedbacks
    # will retry the LLM call lazily on first read.
    process_and_cache_feedback(new_feedback)

    return jsonify({'message': 'Feedback submitted successfully', 'feedback_id': new_feedback.id}), 201

@app.route('/api/users/<identifier>/feedbacks', methods=['GET'])
def get_user_feedbacks(identifier):
    # Try to find user by username, link_id, or email (same as lookup_user)
    user = User.query.filter_by(username=identifier).first()
    if not user:
        user = User.query.filter_by(link_id=identifier).first()
    if not user:
        user = User.query.filter_by(email=identifier).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404

    feedbacks_from_db = Feedback.query.filter_by(user_id=user.id).order_by(Feedback.created_at.desc()).all()
    
    processed_feedbacks = []

    for fb_item in feedbacks_from_db:
        if fb_item.llm_processed_at is not None:
            # Already cached (either from submit-time processing or a previous read) - no LLM call.
            parsed_sentiment = fb_item.llm_sentiment
            parsed_summary = fb_item.llm_summary
            parsed_constructive_criticism = fb_item.llm_constructive_criticism
        else:
            # Not cached yet (older row from before this feature, or submit-time call failed) - compute once and persist.
            parsed_sentiment, parsed_summary, parsed_constructive_criticism = process_and_cache_feedback(fb_item)

        # Determine context for display
        item_context_display = fb_item.context_text if fb_item.context_text and fb_item.context_text.strip() != '-' else \
                               (fb_item.anon_identifier if fb_item.anon_identifier and fb_item.anon_identifier.strip() != '-' else "-")
        
        # If context is still minimal, use a snippet of the original feedback text as a last resort.
        if not item_context_display.strip() or item_context_display.strip() == '-':
            item_context_display = (fb_item.feedback_text[:75] + '...') if fb_item.feedback_text and len(fb_item.feedback_text) > 75 else (fb_item.feedback_text or "Feedback diterima")


        processed_feedbacks.append({
            "id": fb_item.id,
            "timestamp": fb_item.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'), # ISO 8601 format
            "sender": fb_item.anon_identifier,
            "context": item_context_display,
            "sentiment": parsed_sentiment,
            "summary": parsed_summary,
            "constructiveCriticism": parsed_constructive_criticism
        })

    return jsonify(processed_feedbacks), 200

if __name__ == '__main__':
    # Note: For development only. Use a proper WSGI server for production.
    app.run(host="0.0.0.0", debug=False, port=os.getenv('PORT', 5001))


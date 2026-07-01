from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from app.model import User
from app import db
from app.utils.uuid import generate_unique_link_id

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@auth_bp.route('/register', methods=['POST'])
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

@auth_bp.route('/login', methods=['POST'])
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
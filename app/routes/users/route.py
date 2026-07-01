from flask import Blueprint, request, jsonify
from urllib.parse import unquote
from app.model import User, Feedback
from app import db
from app.utils.uuid import generate_unique_link_id
from app.utils.feedback_processor import process_feedback_with_llm, format_sentiment_for_display

users_bp = Blueprint('users', __name__, url_prefix='/api/users')

@users_bp.route('/', methods=['POST'])
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

@users_bp.route('/<identifier>/feedbacks', methods=['GET'])
def get_user_feedbacks(identifier):

    decoded_identifier = unquote(identifier)
    user = User.query.filter_by(username=decoded_identifier).first()
    if not user:
        user = User.query.filter_by(link_id=decoded_identifier).first()
    if not user:
        user = User.query.filter_by(email=decoded_identifier).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404

    feedbacks = Feedback.query.filter_by(user_id=user.id).order_by(Feedback.created_at.desc()).all()

    processed_feedbacks = []
    for fb in feedbacks:
        if fb.summary is not None:
            # Already cached (from submit-time processing or a previous read) - no LLM call.
            sentiment, summary, constructive_criticism = fb.sentiment, fb.summary, fb.constructive_criticism
        else:
            # Not cached yet (older row, or submit-time call failed) - compute once and persist.
            sentiment, summary, constructive_criticism = process_feedback_with_llm(fb)

        # Determine context for display: prefer explicit context, fall back to who-they-are,
        # then to a snippet of the feedback text itself.
        context_display = fb.context_text if fb.context_text and fb.context_text.strip() != '-' else \
            (fb.anon_identifier if fb.anon_identifier and fb.anon_identifier.strip() != '-' else "-")
        if not context_display.strip() or context_display.strip() == '-':
            context_display = (fb.feedback_text[:75] + '...') if fb.feedback_text and len(fb.feedback_text) > 75 else (fb.feedback_text or "Feedback diterima")

        processed_feedbacks.append({
            "id": fb.id,
            "timestamp": fb.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "sender": fb.anon_identifier,
            "context": context_display,
            "sentiment": format_sentiment_for_display(sentiment),
            "summary": summary or "Tidak dapat memproses ringkasan saat ini.",
            "constructiveCriticism": constructive_criticism or "Tidak ada saran spesifik saat ini."
        })

    return jsonify(processed_feedbacks), 200
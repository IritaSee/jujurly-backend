from flask import Blueprint, request, jsonify
from urllib.parse import unquote
from app.model import User, Feedback
from app import db
from app.utils.feedback_processor import process_feedback_with_llm

feedback_bp = Blueprint('feedback', __name__, url_prefix='/api/feedback')

@feedback_bp.route('/<identifier>', methods=['POST'])
def submit_feedback(identifier):
    decoded_identifier = unquote(identifier)
    user = User.query.filter_by(username=decoded_identifier).first()
    if not user:
        user = User.query.filter_by(link_id=decoded_identifier).first()
    if not user:
        user = User.query.filter_by(email=decoded_identifier).first()
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

    # Warm the cache immediately so the dashboard's first read is already fast.
    # If this fails (LLM error/timeout), the feedback is still saved; get_user_feedbacks
    # will retry the LLM call lazily on first read.
    process_feedback_with_llm(new_feedback)

    return jsonify({
        'message': 'Feedback submitted successfully',
        'feedback_id': new_feedback.id,
    }), 201


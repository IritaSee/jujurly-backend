from flask import Blueprint, request, jsonify
from urllib.parse import unquote
from app.model import User, Feedback
from app import db
from app.utils.llm_handler import summarize_text_with_llm

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

    # Default values jika LLM gagal
    default_sentiment = "Netral Aja"
    default_summary = "Tidak dapat memproses ringkasan saat ini"
    default_criticism = "Tidak ada saran spesifik saat ini"

    # Prepare data for LLM processing
    feedback_input_dict = {
        'anon_identifier': anon_identifier or 'Tidak disebutkan',
        'context_text': context_text or 'Tidak disebutkan',
        'feedback_text': feedback_text
    }

    # Initialize variables for LLM results
    llm_sentiment = default_sentiment
    llm_summary = default_summary
    llm_criticism = default_criticism

    # Process with LLM
    try:
        llm_response_dict = summarize_text_with_llm(
            item_to_summarise=feedback_input_dict,
            model_provider="anthropic"  # Or get from environment variable
        )
        
        # Extract values from response with proper fallbacks
        llm_sentiment = llm_response_dict.get("sentiment", default_sentiment)
        llm_summary = llm_response_dict.get("summary", default_summary)
        llm_criticism = llm_response_dict.get("constructiveCriticism", default_criticism)
        
        # Ensure we have non-empty values
        if not llm_sentiment or llm_sentiment.strip() == "":
            llm_sentiment = default_sentiment
        if not llm_summary or llm_summary.strip() == "":
            llm_summary = default_summary
        if not llm_criticism or llm_criticism.strip() == "":
            llm_criticism = default_criticism
            
    except Exception as e:
        print(f"LLM processing error: {e}")
        # Keep the default values we already set

    # Create feedback with LLM results
    new_feedback = Feedback(
        user_id=user.id,
        anon_identifier=anon_identifier,
        feedback_text=feedback_text,
        context_text=context_text,
        anon_email=anon_email,
        sentiment=llm_sentiment,
        summary=llm_summary,
        constructive_criticism=llm_criticism
    )

    db.session.add(new_feedback)
    db.session.commit()

    return jsonify({
        'message': 'Feedback submitted successfully', 
        'feedback_id': new_feedback.id,
    }), 201



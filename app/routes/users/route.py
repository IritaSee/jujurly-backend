from flask import Blueprint, request, jsonify
from urllib.parse import unquote
from app.model import User, Feedback
from app import db
from app.utils.uuid import generate_unique_link_id

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

    feedbacks = Feedback.query.filter_by(user_id=user.id).all()
    processed_feedbacks = [
        {
            'user_id': fb.user_id,
            'sentiment': fb.sentiment,
            'constructive_criticism': fb.constructive_criticism,
            'summary': fb.summary
        }
        for fb in feedbacks
    ]

    return jsonify(processed_feedbacks), 200
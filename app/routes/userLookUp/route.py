from flask import Blueprint, request, jsonify
from app.model import User

userLookUp = Blueprint('lookup', __name__ , url_prefix='/api/user/')

@userLookUp.route('/<identifier>', methods=['GET'])
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
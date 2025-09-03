import os
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Inisialisasi ekstensi global
db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    # Enable CORS untuk semua origin hanya pada /api/*
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })

    # Konfigurasi database
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///default.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Init ekstensi
    db.init_app(app)
    migrate.init_app(app, db)

    # Import model agar Alembic tahu
    from app import model

    # Import dan register semua blueprint
    from app.routes.auth.route import auth_bp
    from app.routes.feedback.route import feedback_bp
    from app.routes.userLookUp.route import userLookUp
    from app.routes.users.route import users_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(feedback_bp, url_prefix="/api/feedback")
    app.register_blueprint(userLookUp, url_prefix="/api/userlookup")
    app.register_blueprint(users_bp, url_prefix="/api/users")

    return app

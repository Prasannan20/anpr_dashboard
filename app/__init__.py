import os
from flask import Flask
from .config import Config
from .extensions import db, login_manager, socketio, csrf
from .models import User
from .auth import auth_bp
from .routes import main_bp

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config())
    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")
    csrf.init_app(app)
    with app.app_context():
        db.create_all()
        _ensure_admin()
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    return app

def _ensure_admin():
    from werkzeug.security import generate_password_hash
    from .models import User
    from .extensions import db
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin123")
    if not User.query.filter_by(username=username).first():
        u = User(username=username, role="admin", password_hash=generate_password_hash(password))
        db.session.add(u); db.session.commit()

from .extensions import socketio

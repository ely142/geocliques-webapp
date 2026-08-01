import os

from dotenv import load_dotenv
from flask import Flask

from app.extensions import db, login_manager


def create_app(test_config=None):
    load_dotenv()

    app = Flask(__name__)

    os.makedirs(app.instance_path, exist_ok=True)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "fallback-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///users.db")

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    from app.auth import auth_bp
    from app.event import event_bp
    from app.map import map_bp
    from app.master import master_bp
    from app.notif import notif_bp
    from app.routes import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(master_bp)
    app.register_blueprint(notif_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(event_bp)
    app.register_blueprint(main_bp)

    return app

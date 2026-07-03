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

    login_manager.login_view = "main.login"
    login_manager.login_message_category = "info"

    from app.routes import main_bp

    app.register_blueprint(main_bp)

    return app

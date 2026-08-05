import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Clique, CliqueUser, User


@pytest.fixture
def app():
    app = create_app(
        test_config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,  # Disable security tokens so tests can submit forms easily
        }
    )

    with app.app_context():
        db.create_all()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def base_db_setup(app):
    """Fixture to set up a valid User and Clique environment."""

    with app.app_context():
        fake_user = User(name="Test", email="user@test.com", password=generate_password_hash("Password123!"))
        db.session.add(fake_user)
        db.session.flush()

        fake_clique = Clique(
            name="Test Clique",
            description="Description",
            visibility="private",
            admin_id=fake_user.id,
            icon="bi-star",
        )

        db.session.add(fake_clique)
        db.session.flush()

        fake_clique_user = CliqueUser(user_id=fake_user.id, clique_id=fake_clique.id)

        db.session.add(fake_clique_user)
        db.session.commit()

        return {
            "user_id": fake_user.id,
            "clique_id": fake_clique.id,
            "email": "user@test.com",
            "password": "Password123!",
        }

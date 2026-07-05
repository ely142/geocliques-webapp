import pytest

from app.extensions import db
from app.models import Notification


@pytest.fixture
def notif_db_setup(app, base_db_setup):
    """Adds a Notification on top of the base db enviroment."""

    with app.app_context():
        fake_notif = Notification(type="invitation", user_id=base_db_setup["user_id"], clique_id=base_db_setup["clique_id"])
        db.session.add(fake_notif)
        db.session.commit()

        setup_data = base_db_setup.copy()
        setup_data["notif_id"] = fake_notif.id
        setup_data["notif_type"] = fake_notif.type
        return setup_data


def test_get_notifications_unauthenticated(client):
    """Test that a logged-out user cannot view notifications."""
    response = client.get("/api/notif/get_notifications")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_get_notifications_authenticated(client, notif_db_setup):
    """Test that a logged-in user gets a successful JSON response."""

    client.post("/auth/login", data={"email": notif_db_setup["email"], "password": notif_db_setup["password"]})

    response = client.get("/api/notif/get_notifications")

    assert response.status_code == 200

    data = response.json

    assert "notifications" in data
    assert len(data["notifications"]) == 1
    assert data["notifications"][0]["type"] == notif_db_setup["notif_type"]


def test_delete_notification(client, app, notif_db_setup):
    """Test that an authenticated user can delete a notification."""

    client.post("/auth/login", data={"email": notif_db_setup["email"], "password": notif_db_setup["password"]})

    response = client.post(f"/api/notif/delete_notification/{notif_db_setup['notif_id']}")

    assert response.status_code == 200

    with app.app_context():
        deleted_notif = db.session.get(Notification, notif_db_setup["notif_id"])

        assert deleted_notif is None

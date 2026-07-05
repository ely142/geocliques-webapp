import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Event, Marker, Review, User

SAFE_GET_ROUTES = [
    "/",
    "/auth/login",
    "/auth/register",
    "/select-layer",
    "/user_guide",
    "/user_edit_user",
    "/change_password",
    "/manage_account",
    "/feed",
    "/settings",
    "/create-clique",
    "/users",
    "/cliques",
    "/master/reports",
    "/maptest",
    "/auth/logout",
    "/search_cliques",
    "/master/reports",
]


@pytest.mark.parametrize("route", SAFE_GET_ROUTES)
def test_all_safe_routes_render_without_url_errors(client, route):
    """Smoke test to ensure no Jinja BuildErrors exist in the templates."""
    response = client.get(route)

    assert response.status_code in [200, 302]


def test_unauthenticated_user_is_redirected(client):
    """Verify origin tracking and redirection logic for protected routes."""
    response = client.get("/maptest")

    assert response.status_code == 302  # Redirect code
    assert "/auth/login" in response.headers["Location"]


@pytest.mark.parametrize("origin_route, expected_redirect_url", [("main.settings", "/settings"), ("main.maptest", "/maptest")])
@pytest.mark.parametrize("form_action", ["save", "delete"])
def test_update_review_dynamic_redirect(app, client, origin_route, expected_redirect_url, form_action):
    """Verify that updating a review dynamically redirects back to the origin page."""

    with app.app_context():
        fake_user = User(id=1, name="Test", email="test@test.com", password=generate_password_hash("Password123!"))
        fake_marker = Marker(id=1, lat=34, long=35, total_reviews=1, average_review=5)
        fake_review = Review(id=1, marker_id=1, user_id=1, stars=5, commentary="Review")

        db.session.add(fake_user)
        db.session.add(fake_marker)
        db.session.add(fake_review)
        db.session.commit()

    client.post("/auth/login", data={"email": "test@test.com", "password": "Password123!"})

    response = client.post(
        "/update-review/1",  # The dynamic route using marker id 1
        data={
            "action": form_action,
            "stars": "4",
            "commentary": "New text",
            "next": origin_route,
        },
    )

    assert response.status_code == 302
    assert expected_redirect_url in response.headers["Location"]


@pytest.mark.parametrize("origin_route, expected_redirect_url", [("main.settings", "/settings"), ("", "/edit-events/1/1")])
@pytest.mark.parametrize("form_action", ["edit", "delete"])
def test_update_event_dynamic_redirect(app, client, origin_route, expected_redirect_url, form_action):
    """Verify updating/deleting an event correctly routes back to the specific origin page."""

    with app.app_context():
        fake_user = User(id=1, name="Test", email="user@test.com", password=generate_password_hash("Password123!"))
        fake_event = Event(id=1, date="2026-07-03", time="10:00", description="Test Event", marker_id=1, user_id=1, clique_id=1)

        db.session.add(fake_user)
        db.session.add(fake_event)
        db.session.commit()

    client.post("/auth/login", data={"email": "user@test.com", "password": "Password123!"})

    response = client.post(
        "/update-event/1",
        data={"action": form_action, "next": origin_route, "date": "2026-07-04", "time": "12:00", "description": "Updated event description"},
    )

    assert response.status_code == 302
    assert expected_redirect_url in response.headers["Location"]

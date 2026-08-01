import pytest

from app.extensions import db
from app.models import Event, Marker, Review, UserMarker

SAFE_GET_ROUTES = [
    "/",
    "/auth/login",
    "/auth/register",
    "/map/select-layer",
    "/user_guide",
    "/user/edit",
    "/user/change_password",
    "/user/manage_account",
    "/feed",
    "/user/settings",
    "/create-clique",
    "/master/users",
    "/master/cliques",
    "/master/reports",
    "/map/maptest",
    "/auth/logout",
    "/search_cliques",
]


@pytest.fixture
def map_db_setup(app, base_db_setup):
    """Adds Marker, Review and UserMarker instances on top of the base db environment."""

    with app.app_context():
        fake_marker = Marker(lat=31.6, long=34.7, description="Test Marker", total_reviews=1, average_review=5.0)  # Match to Review attributes
        db.session.add(fake_marker)
        db.session.flush()

        fake_review = Review(marker_id=fake_marker.id, user_id=base_db_setup["user_id"], stars=5, commentary="Review")
        db.session.add(fake_review)

        fake_user_marker = UserMarker(user_id=base_db_setup["user_id"], marker_id=fake_marker.id, clique_id=base_db_setup["clique_id"])
        db.session.add(fake_user_marker)
        db.session.commit()

        setup_data = base_db_setup.copy()
        setup_data["marker_id"] = fake_marker.id
        setup_data["review_id"] = fake_review.id
        return setup_data


@pytest.mark.parametrize("route", SAFE_GET_ROUTES)
def test_all_safe_routes_render_without_url_errors(client, route):
    """Smoke test to ensure no Jinja BuildErrors exist in the templates."""
    response = client.get(route)

    assert response.status_code in [200, 302]


def test_unauthenticated_user_is_redirected(client):
    """Verify origin tracking and redirection logic for protected routes."""
    response = client.get("/map/maptest")

    assert response.status_code == 302  # Redirect code
    assert "/auth/login" in response.headers["Location"]


@pytest.mark.parametrize("origin_route, expected_redirect_url", [("user.settings", "/settings"), ("map.maptest", "/maptest")])
@pytest.mark.parametrize("form_action", ["save", "delete"])
def test_update_review_dynamic_redirect(client, map_db_setup, origin_route, expected_redirect_url, form_action):
    """Verify that updating a review dynamically redirects back to the origin page."""

    client.post("/auth/login", data={"email": map_db_setup["email"], "password": map_db_setup["password"]})

    response = client.post(
        f"/map/update-review/{map_db_setup['marker_id']}",
        data={
            "action": form_action,
            "stars": "4",
            "commentary": "New text",
            "next": origin_route,
        },
    )

    assert response.status_code == 302
    assert expected_redirect_url in response.headers["Location"]


@pytest.mark.parametrize("origin_route, expected_redirect_url", [("user.settings", "/settings"), ("", "/event/edit-events/1/1")])
@pytest.mark.parametrize("form_action", ["edit", "delete"])
def test_update_event_dynamic_redirect(app, client, map_db_setup, origin_route, expected_redirect_url, form_action):
    """Verify updating/deleting an event correctly routes back to the specific origin page."""

    with app.app_context():
        fake_event = Event(
            date="2026-07-03",
            time="10:00",
            description="Test Event",
            marker_id=map_db_setup["marker_id"],
            user_id=map_db_setup["user_id"],
            clique_id=map_db_setup["clique_id"],
        )
        db.session.add(fake_event)
        db.session.commit()

        event_id = fake_event.id

    client.post("/auth/login", data={"email": map_db_setup["email"], "password": map_db_setup["password"]})

    response = client.post(
        f"/event/update/{event_id}",
        data={"action": form_action, "next": origin_route, "date": "2026-07-04", "time": "12:00", "description": "Updated event description"},
    )

    assert response.status_code == 302
    assert expected_redirect_url in response.headers["Location"]

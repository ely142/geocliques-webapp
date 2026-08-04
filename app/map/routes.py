import os
from datetime import datetime

from flask import jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.map import map_bp
from app.models import (
    Clique,
    Event,
    Marker,
    Review,
    User,
    UserMarker,
)
from app.utils import (
    assign_clique_colors,
    delete_review_and_update_marker,
)


@map_bp.route("/map_keys.js")
def map_keys():
    key = os.getenv("MAP_THUNDERFOREST_KEY", "")
    return (
        f"window.MAP_KEYS = {{ thunderforest: '{key}' }};",
        200,
        {"Content-Type": "application/javascript"},
    )


@map_bp.route("/maptest")
@login_required
def maptest():
    if current_user.email == "adminadmin@gmail.com":
        return render_template("layouts/masterbase.html", name=current_user.name, logged_in=True)
    selected_layer = session.get("selected_layer", "default")
    return render_template("map/maptest.html", name=current_user.name, logged_in=True, selected_layer=selected_layer)


@map_bp.route("/geojson-features", methods=["GET"])
@login_required
def get_user_markers():
    # Extract current user markers and setup colors
    user_clique_ids = {cu.clique_id for cu in current_user.cliques}
    user_markers = UserMarker.query.filter(UserMarker.clique_id.in_(user_clique_ids)).all()
    clique_ids = sorted(user_clique_ids)
    clique_color_map = assign_clique_colors(clique_ids)

    features = []
    for um in user_markers:
        marker = um.marker
        clique = db.session.get(Clique, um.clique_id)

        # Current user reviews
        review = Review.query.filter_by(marker_id=marker.id, user_id=current_user.id).first()
        user_review = None
        if review:
            user_review = {"stars": review.stars, "commentary": review.commentary}

        # Peer reviews
        all_reviews = Review.query.filter(Review.marker_id == marker.id, Review.user_id != current_user.id).all()
        other_reviews = [
            {
                "stars": r.stars,
                "commentary": r.commentary,
                "user": db.session.get(User, r.user_id).name,
                "user_pic": db.session.get(User, r.user_id).picture,
            }
            for r in all_reviews
        ]

        # Current user events
        all_user_events = Event.query.filter_by(marker_id=marker.id, user_id=current_user.id).all()
        user_events = [
            {"date": e.date.isoformat(), "time": e.time.strftime("%H:%M"), "description": e.description, "is_own_event": True}
            for e in all_user_events
        ]

        # Peer events
        all_events = Event.query.filter(Event.marker_id == marker.id, Event.user_id != current_user.id).all()
        other_events = [
            {
                "date": e.date.isoformat(),
                "time": e.time.strftime("%H:%M"),
                "description": e.description,
                "user": db.session.get(User, e.user_id).name,
                "user_pic": db.session.get(User, e.user_id).picture,
                "is_own_event": False,
            }
            for e in all_events
        ]

        # Construct GeoJSON feature
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [marker.long, marker.lat]},
                "properties": {
                    "description": marker.description or "No description",
                    "marker_id": marker.id,
                    "average_review": marker.average_review,
                    "total_reviews": marker.total_reviews,
                    "user_review": user_review,
                    "reviews": other_reviews,
                    "user_events": user_events,
                    "events": other_events,
                    "clique_id": um.clique_id,
                    "clique_name": clique.name,
                    "clique_color": clique_color_map[um.clique_id],
                    "icon": clique.icon,
                },
            }
        )

    return jsonify(features)


@map_bp.route("/add-marker", methods=["POST"])
@login_required
def add_marker():
    try:
        data = request.get_json()
        latitude = data["latitude"]
        longitude = data["longitude"]
        title = data.get("title", "")
        commentary = data.get("commentary", "")
        rating = int(data.get("rating"))
        if not title or not (1 <= rating <= 5):
            return jsonify({"success": False, "message": "Fields (title, rating) are required."}), 400

        clique_id = int(data.get("clique_id"))

        rating = int(data.get("rating"))
        if rating < 1 or rating > 5:
            return jsonify({"success": False, "message": "Invalid rating value."}), 400

        user_clique_ids = [cu.clique_id for cu in current_user.cliques]
        if clique_id not in user_clique_ids:
            return jsonify({"success": False, "message": "You are not a member of this clique."}), 403

        new_marker = Marker(
            lat=latitude,
            long=longitude,
            description=title,
            total_reviews=1,
            average_review=float(rating),
        )

        db.session.add(new_marker)
        db.session.flush()

        user_marker = UserMarker(
            user_id=current_user.id,
            marker_id=new_marker.id,
            clique_id=clique_id,
        )
        db.session.add(user_marker)

        new_review = Review(
            stars=rating,
            commentary=commentary,
            marker_id=new_marker.id,
            user_id=current_user.id,
        )
        db.session.add(new_review)

        db.session.commit()

        return jsonify({"success": True, "message": "Marker added successfully!"}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@map_bp.route("/rate-marker/<int:marker_id>", methods=["POST"])
@login_required
def rate_marker(marker_id):
    marker = db.get_or_404(Marker, marker_id)

    data = request.get_json()
    stars = int(data.get("rating"))
    commentary = data.get("commentary", "").strip()

    if not (1 <= stars <= 5):
        return jsonify({"success": False, "message": "Star rating is required."}), 400

    existing_review = Review.query.filter_by(marker_id=marker_id, user_id=current_user.id).first()
    if existing_review:
        return jsonify({"success": False, "message": "You have already reviewed this marker."}), 400

    new_avg = ((marker.average_review * marker.total_reviews) + stars) / (marker.total_reviews + 1)
    marker.total_reviews += 1
    marker.average_review = round(new_avg, 2)

    review = Review(
        stars=stars,
        commentary=commentary,
        marker_id=marker_id,
        user_id=current_user.id,
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({"success": True, "message": "Review added!"})


@map_bp.route("/edit-review/<int:marker_id>", methods=["GET"])
@login_required
def edit_review(marker_id):
    review = Review.query.filter_by(marker_id=marker_id, user_id=current_user.id).first_or_404()
    marker = review.marker
    is_only_review = marker.total_reviews == 1
    next = request.args.get("next", "map.maptest")
    return render_template(
        "map/edit_review.html",
        review=review,
        marker=marker,
        is_only_review=is_only_review,
        logged_in=True,
        name=current_user.name,
        next=next,
    )


@map_bp.route("/update-review/<int:marker_id>", methods=["POST"])
@login_required
def update_review(marker_id):
    review = Review.query.filter_by(marker_id=marker_id, user_id=current_user.id).first_or_404()
    marker = review.marker
    action = request.form.get("action")
    next = request.form.get("next", "map.maptest")

    if action == "delete":
        delete_review_and_update_marker(review.id)
        db.session.commit()
        return redirect(url_for(next))

    new_stars = int(request.form.get("stars"))
    new_comment = request.form.get("commentary", "").strip()

    total = marker.total_reviews
    new_avg = ((marker.average_review * total) - review.stars + new_stars) / total
    marker.average_review = round(new_avg, 2)

    review.stars = new_stars
    review.commentary = new_comment
    db.session.commit()
    return redirect(url_for(next))


@map_bp.route("/select-layer", methods=["GET", "POST"])
@login_required
def select_layer():
    if request.method == "POST":
        selected_layer = request.form.get("layer")
        session["selected_layer"] = selected_layer
        return redirect(url_for("map.maptest"))

    selected_layer = session.get("selected_layer", "default")

    layers = [
        ("default", "default"),
        ("OpenStreetMap.HOT", "alternative"),
        ("Esri.WorldImagery", "satellite"),
        ("Thunderforest.Transport", "public transport routes and lines"),
        ("Thunderforest.OpenCycleMap", "bicycle lanes"),
        ("Thunderforest.Outdoors", "Outdoors"),
    ]

    return render_template(
        "map/select_layer.html",
        layers=layers,
        selected_layer=selected_layer,
        name=current_user.name,
        logged_in=True,
    )

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.master import master_bp
from app.models import (
    BannedUser,
    Clique,
    Event,
    Marker,
    Notification,
    Review,
    User,
    UserMarker,
)
from app.utils import delete_marker_and_contents, delete_review_and_update_marker, delete_user


@master_bp.route("/users")
@login_required
def users():
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.home"))

    users_arr = User.query.all()

    banned_users = BannedUser.query.all()
    banned_info = []
    for b in banned_users:
        user = db.session.get(User, b.user_id)
        clique = db.session.get(Clique, b.clique_id)
        admin = db.session.get(User, clique.admin_id) if clique else None
        if user and clique and admin:
            banned_info.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "clique_id": clique.id,
                    "clique_name": clique.name,
                    "reason": b.reason,
                    "admin_name": admin.name,
                }
            )

    return render_template(
        "master/users.html",
        name=current_user.name,
        logged_in=True,
        usersList=users_arr,
        banned_users=banned_info,
    )


@master_bp.route("/unban_user_master/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def unban_user_master(clique_id, user_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.feed"))

    BannedUser.query.filter_by(user_id=user_id, clique_id=clique_id).delete()
    db.session.add(Notification(type="unban", user_id=user_id, clique_id=clique_id))
    db.session.commit()

    flash("User successfully unbanned.", "success")
    return redirect(url_for("master.users"))


@master_bp.route("/edit_user/<int:user_id>", methods=["POST"])
@login_required
def edit_user(user_id):
    if current_user.email != "adminadmin@gmail.com":
        return jsonify({"success": False, "message": "You do not have permission to edit users."})

    user = db.session.get(User, user_id)
    if user:
        data = request.get_json()
        new_email = data.get("email")
        new_name = data.get("name")

        if User.query.filter(User.email == new_email, User.id != user.id).first():
            return jsonify({"success": False, "message": "Email already exists!"})

        user.email = new_email
        user.name = new_name
        db.session.commit()

        return jsonify({"success": True, "message": "User updated successfully!"})

    return jsonify({"success": False, "message": "User not found."})


@master_bp.route("/cliques")
def cliques():
    all_cliques = Clique.query.all()
    admin_map = {clique.id: db.session.get(User, clique.admin_id) for clique in all_cliques}
    return render_template(
        "master/cliques.html",
        cliquesList=all_cliques,
        adminMap=admin_map,
        logged_in=current_user.is_authenticated,
    )


@master_bp.route("/clique-map/<int:clique_id>")
@login_required
def master_clique_map(clique_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.home"))

    clique = db.get_or_404(Clique, clique_id)
    return render_template("master/clique_map.html", clique=clique, logged_in=True)


@master_bp.route("/edit_clique/<int:clique_id>", methods=["GET"])
@login_required
def edit_clique(clique_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.feed"))

    clique = db.get_or_404(Clique, clique_id)
    all_users = User.query.all()

    member_ids = set(cu.user_id for cu in clique.users)

    marker_ids = [um.marker_id for um in UserMarker.query.filter_by(clique_id=clique_id).all()]
    reviews = Review.query.filter(Review.marker_id.in_(marker_ids)).all()

    for review in reviews:
        review.user = db.session.get(User, review.user_id)
        review.marker = db.session.get(Marker, review.marker_id)

    # Sort reviews by marker name alphabetically
    sorted_reviews = sorted(reviews, key=lambda r: (r.marker.description or "").lower())

    events = Event.query.filter_by(clique_id=clique_id)

    for event in events:
        event.user = db.session.get(User, event.user_id)
        event.marker = db.session.get(Marker, event.marker_id)
    sorted_events = sorted(events, key=lambda r: (r.marker.description or "").lower())

    return render_template(
        "master/edit_clique.html",
        clique=clique,
        all_users=all_users,
        member_ids=member_ids,
        sorted_reviews=sorted_reviews,
        sorted_events=sorted_events,
        logged_in=True,
    )


@master_bp.route("/clique-geojson/<int:clique_id>", methods=["GET"])
@login_required
def get_clique_markers(clique_id):
    if current_user.email != "adminadmin@gmail.com":
        return jsonify({"error": "Unauthorized"}), 403

    user_markers = UserMarker.query.filter_by(clique_id=clique_id).all()

    features = []
    for um in user_markers:
        marker = um.marker
        all_reviews = Review.query.filter_by(marker_id=marker.id).all()
        review_data = [
            {
                "user": db.session.get(User, r.user_id).name,
                "stars": r.stars,
                "commentary": r.commentary or "",
            }
            for r in all_reviews
        ]

        all_events = Event.query.filter_by(marker_id=marker.id).all()
        events_data = [
            {
                "user": db.session.get(User, e.user_id).name,
                "date": e.date,
                "time": e.time,
                "description": e.description,
            }
            for e in all_events
        ]

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [marker.long, marker.lat]},
                "properties": {
                    "marker_title": marker.description or "Untitled Marker",
                    "average_review": marker.average_review,
                    "total_reviews": marker.total_reviews,
                    "reviews": review_data,
                    "events": events_data,
                },
            }
        )

    return jsonify(features)


@master_bp.route("/remove_marker_from_clique/<int:clique_id>/<int:marker_id>", methods=["POST"])
@login_required
def remove_marker_from_clique(clique_id, marker_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.feed"))
    delete_marker_and_contents(marker_id)
    db.session.commit()
    return redirect(url_for("master.edit_clique", clique_id=clique_id))


@master_bp.route("/delete_review_from_clique/<int:review_id>/<int:clique_id>", methods=["POST"])
@login_required
def delete_review_from_clique(review_id, clique_id):
    delete_review_and_update_marker(review_id)
    db.session.commit()
    return redirect(url_for("master.edit_clique", clique_id=clique_id))


@master_bp.route("/reports")
@login_required
def master_reports():
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.home"))

    types = ["bot like report", "overwhelming bias report", "hurtful language report"]
    reports = Notification.query.filter(Notification.type.in_(types)).all()

    enriched = [
        {
            "id": r.id,
            "user": db.session.get(User, r.user_id),
            "clique": db.session.get(Clique, r.clique_id),
            "type": r.type,
        }
        for r in reports
    ]

    return render_template("master/reports.html", reports=enriched, name=current_user.name, logged_in=True)


@master_bp.route("/delete_user/<int:user_id>", methods=["POST"])
@login_required
def delete_user_route(user_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("user.settings"))

    delete_user(user_id)
    db.session.commit()
    flash("User and associated data deleted.", "success")
    return redirect(url_for("master.users"))

from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from rapidfuzz import fuzz

from app.extensions import db
from app.models import (
    BannedUser,
    Clique,
    CliqueUser,
    Event,
    Marker,
    Notification,
    Review,
    User,
    UserMarker,
)
from app.utils import (
    delete_clique_and_contents,
    delete_user_from_clique,
    perform_leave_clique,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/update-icon/<int:clique_id>", methods=["POST"])
@login_required
def update_icon(clique_id):
    clique = db.get_or_404(Clique, clique_id)

    if request.method == "POST":
        new_icon = request.form.get("selectedIcon")
        clique.icon = new_icon

        db.session.commit()

        return redirect(url_for("main.admin_control_room", clique_id=clique_id))
    return redirect(url_for("main.admin_control_room", clique_id=clique_id))


@main_bp.route("/update_clique_type/<int:clique_id>", methods=["POST"])
@login_required
def update_clique_type(clique_id):
    clique = db.get_or_404(Clique, clique_id)

    if request.method == "POST":
        new_visibility = request.form.get("visibility")

        if new_visibility in ["Private", "Public", "Protected"]:
            clique.visibility = new_visibility

            db.session.commit()

            return redirect(url_for("main.admin_control_room", clique_id=clique.id))
        return redirect(url_for("main.admin_control_room", clique_id=clique.id))


@main_bp.route("/")
def home():
    return render_template("index.html", logged_in=current_user.is_authenticated, show_auth_links=True)


@main_bp.route("/user_guide", methods=["GET"])
def user_guide():
    return render_template("user_guide.html", logged_in=False)


# CLIQUE FUNCTIONS
""" functions relating to creating, searching, joining, and leaving cliques"""


@main_bp.route("/feed")
@login_required
def feed():
    user_clique_links = CliqueUser.query.filter_by(user_id=current_user.id).all()
    user_clique_ids = [link.clique_id for link in user_clique_links]

    user_cliques = []
    for link in user_clique_links:
        clique = db.session.get(Clique, link.clique_id)
        user_cliques.append(
            {
                "id": clique.id,
                "name": clique.name,
                "description": clique.description,
                "status": "admin" if clique.admin_id == current_user.id else "user",
                "visibility": clique.visibility,
            }
        )

    week_ago = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    recent_markers = UserMarker.query.filter(UserMarker.clique_id.in_(user_clique_ids), UserMarker.creation_date >= week_ago).all()

    marker_updates = []
    for um in recent_markers:
        creator = db.session.get(User, um.user_id)
        marker_updates.append(
            {
                "type": "marker",
                "date": um.creation_date,
                "clique_name": db.session.get(Clique, um.clique_id).name,
                "marker_name": um.marker.description or "Unnamed Marker",
                "description": um.marker.description or "",
                "user_name": creator.name if creator else "Deleted User",
                "user_pic": creator.picture if creator else "default.jpg",
            }
        )

    marker_ids = [um.marker_id for um in UserMarker.query.filter(UserMarker.clique_id.in_(user_clique_ids)).all()]
    recent_reviews = Review.query.filter(Review.creation_date >= week_ago, Review.marker_id.in_(marker_ids)).all()

    review_updates = []
    for r in recent_reviews:
        marker = db.session.get(Marker, r.marker_id)
        any_link = UserMarker.query.filter_by(marker_id=r.marker_id).first()
        if not any_link:
            continue
        clique = db.session.get(Clique, any_link.clique_id)
        creator = db.session.get(User, r.user_id)

        review_updates.append(
            {
                "type": "review",
                "date": r.creation_date,
                "clique_name": clique.name,
                "marker_name": marker.description or "Unnamed Marker",
                "stars": r.stars,
                "commentary": r.commentary,
                "user_name": creator.name if creator else "Deleted User",
                "user_pic": creator.picture if creator else "default.jpg",
            }
        )

    all_updates = marker_updates + review_updates
    all_updates.sort(key=lambda x: x["date"], reverse=True)  # Most recent to oldest
    all_updates = all_updates[:20]

    scoreboard_data = []

    # Process scores for each clique the user belongs to
    for link in user_clique_links:
        clique_id = link.clique_id
        clique = db.session.get(Clique, clique_id)
        members = CliqueUser.query.filter_by(clique_id=clique_id).all()
        scores = {}

        for member in members:
            user = db.session.get(User, member.user_id)
            user_score = 0

            marker_ids = [um.marker_id for um in UserMarker.query.filter_by(clique_id=clique_id).all()]
            reviews = Review.query.filter(Review.user_id == user.id, Review.marker_id.in_(marker_ids)).all()

            # Award points for review quality (Goldilocks scoring: peak points for 16-25 words)
            for r in reviews:
                word_count = len(r.commentary.strip().split()) if r.commentary else 0
                if word_count <= 3 or word_count > 40:
                    user_score += 1
                elif word_count <= 7 or word_count > 35:
                    user_score += 2
                elif word_count <= 10 or word_count > 30:
                    user_score += 3
                elif word_count <= 15 or word_count > 25:
                    user_score += 4
                elif word_count <= 25:
                    user_score += 5

            # Award 2 points per marker contributed to the clique
            marker_count = UserMarker.query.filter_by(clique_id=clique_id, user_id=user.id).count()
            user_score += marker_count * 2

            scores[user.id] = (user_score, user.name)

        # Rank users by descending score
        sorted_users = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
        ranking = [{"rank": i + 1, "user_id": uid, "name": scores[uid][1]} for i, (uid, _) in enumerate(sorted_users)]

        scoreboard_data.append({"clique_name": clique.name, "ranking": ranking})

    return render_template(
        "user/feed.html",
        name=current_user.name,
        logged_in=True,
        cliques=user_cliques,
        updates=all_updates,
        scoreboards=scoreboard_data,
    )


@main_bp.route("/create-clique", methods=["GET", "POST"])
@login_required
def create_clique():
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        visibility = request.form.get("visibility")
        icon = request.form.get("selectedIcon")

        if not name:
            return redirect(url_for("main.create_clique"))

        new_clique = Clique(
            name=name,
            description=description,
            visibility=visibility,
            icon=icon,
            date_created=datetime.today().strftime("%Y-%m-%d"),
            admin_id=current_user.id,
        )
        db.session.add(new_clique)
        db.session.flush()

        membership = CliqueUser(
            user_id=current_user.id,
            clique_id=new_clique.id,
            joined_date=datetime.today().strftime("%Y-%m-%d"),
        )
        db.session.add(membership)
        db.session.commit()

        return redirect(url_for("map.maptest"))

    return render_template("user/create_clique.html", name=current_user.name, logged_in=True)


@main_bp.route("/send_invite", methods=["POST"])
@login_required
def send_invite():
    data = request.get_json()
    email = data.get("email")
    clique_id = int(data.get("clique_id"))

    if not email:
        return jsonify({"success": False, "message": "Email is required."}), 400

    invitee = User.query.filter_by(email=email).first()
    if not invitee:
        return jsonify({"success": False, "message": "No user found with that email."}), 404

    banned = BannedUser.query.filter_by(user_id=invitee.id, clique_id=clique_id).first()
    if banned:
        return jsonify(
            {
                "success": False,
                "message": "You cannot invite this user because they were banned from the clique.",
            }
        ), 400

    if invitee.id == current_user.id:
        return jsonify({"success": False, "message": "You cannot invite yourself."}), 400

    already_in_clique = CliqueUser.query.filter_by(user_id=invitee.id, clique_id=clique_id).first()
    if already_in_clique:
        return jsonify({"success": False, "message": "The user you invited is already in this clique."}), 400

    # Determine notification type
    clique = db.session.get(Clique, clique_id)

    if not clique:
        return jsonify({"success": False, "message": "Clique not found."}), 404

    is_admin = clique.admin_id == current_user.id
    is_protected = clique.visibility == "Protected"
    if is_admin and is_protected:
        notif_type = "invitation admin"
    elif is_protected:
        notif_type = "invitation protected"
    else:
        notif_type = "invitation"

    # Check for existing invite
    existing = Notification.query.filter_by(user_id=invitee.id, clique_id=clique_id).first()

    if existing:
        if existing.type == "invitation admin":
            return jsonify({"success": False, "message": "This user has already been invited by an admin."}), 400
        elif existing.type == "invitation" and notif_type == "invitation admin":
            # upgrade existing type to admin invitation
            existing.type = "invitation admin"
            db.session.commit()
            return jsonify({"success": True, "message": "Upgraded invitation to admin invitation."})
        elif existing.type == "invitation protected":
            return jsonify({"success": False, "message": "This user has already been invited to this clique."}), 400

    new_notification = Notification(type=notif_type, user_id=invitee.id, clique_id=clique_id)
    db.session.add(new_notification)
    db.session.commit()

    return jsonify({"success": True, "message": f"Invitation sent successfully as '{notif_type}'!"})


@main_bp.route("/join_clique/<int:clique_id>", methods=["POST"])
@login_required
def join_clique(clique_id):
    banned = db.session.query(BannedUser).filter_by(user_id=current_user.id, clique_id=clique_id).first()
    if banned:
        return jsonify({"success": False, "message": "You are banned from this clique and cannot rejoin."})

    existing = CliqueUser.query.filter_by(clique_id=clique_id, user_id=current_user.id).first()
    if existing:
        return jsonify({"success": False, "message": "You're already a member of this clique."})

    new_link = CliqueUser(
        user_id=current_user.id,
        clique_id=clique_id,
        joined_date=datetime.today().strftime("%Y-%m-%d"),
    )
    db.session.add(new_link)
    db.session.commit()

    return jsonify({"success": True, "message": "Successfully joined the clique!"})


@main_bp.route("/leave_clique/<int:clique_id>", methods=["POST"])
@login_required
def leave_clique(clique_id):
    success = perform_leave_clique(clique_id, current_user.id)
    if success:
        db.session.commit()
        flash("You have successfully left the clique.", "success")
    else:
        flash("Failed to leave the clique.", "danger")
    return redirect(url_for("user.settings"))


@main_bp.route("/search_cliques")
@login_required
def search_cliques():
    query = request.args.get("query", "").strip().lower()

    if not query:
        return redirect(url_for("main.feed"))

    visible_cliques = Clique.query.filter(Clique.visibility.in_(["Public", "Protected"])).all()
    matched = []

    for clique in visible_cliques:
        name_score = fuzz.partial_ratio(query, clique.name.lower())
        desc_score = fuzz.partial_ratio(query, clique.description.lower())

        if name_score >= 60 or desc_score >= 60:
            sort_score = name_score + (10 if name_score >= desc_score else 0)
            matched.append((sort_score, clique))

    matched.sort(key=lambda x: x[0], reverse=True)
    sorted_cliques = [item[1] for item in matched]

    admin_map = {clique.id: db.session.get(User, clique.admin_id) for clique in sorted_cliques}

    member_counts = {clique.id: len(clique.users) for clique in sorted_cliques}
    marker_counts = {clique.id: len(clique.markers) for clique in sorted_cliques}
    user_clique_ids = {cu.clique_id for cu in current_user.cliques}

    return render_template(
        "user/search_results.html",
        query=query,
        results=sorted_cliques,
        admin_map=admin_map,
        member_counts=member_counts,
        marker_counts=marker_counts,
        user_clique_ids=user_clique_ids,
        name=current_user.name,
        logged_in=True,
    )


@main_bp.route("/autocomplete")
@login_required
def autocomplete():
    term = request.args.get("term", "").lower()
    if not term:
        return jsonify([])

    cliques_list = Clique.query.filter(Clique.visibility.in_(["Public", "Protected"])).all()
    matches = []

    for clique in cliques_list:
        if term in clique.name.lower() or term in clique.description.lower():
            matches.append(clique.name)

    # Return unique names (limit to 10)
    return jsonify(list(set(matches))[:10])


@main_bp.route("/request_join_protected/<int:clique_id>", methods=["POST"])
@login_required
def request_join_protected(clique_id):
    if not db.session.get(Clique, clique_id):
        return jsonify({"success": False, "message": "Clique not found."}), 404

    banned = db.session.query(BannedUser).filter_by(user_id=current_user.id, clique_id=clique_id).first()
    if banned:
        return jsonify(
            {
                "success": False,
                "message": "You are banned from this clique and cannot request to join.",
            }
        )

    existing_request = Notification.query.filter_by(user_id=current_user.id, clique_id=clique_id, type="request to join protected").first()

    if existing_request:
        return jsonify({"success": False, "message": "You already requested to join this clique."}), 400

    new_note = Notification(user_id=current_user.id, clique_id=clique_id, type="request to join protected")
    db.session.add(new_note)
    db.session.commit()

    return jsonify({"success": True, "message": "Request sent to the clique admin."})


# CLIQUE ADMIN FUNCTIONS
""" functions used by the cliques' admins to manage the cliques"""


@main_bp.route("/accept_request/<int:note_id>/<int:clique_id>", methods=["POST"])
@login_required
def accept_request(note_id, clique_id):
    note = db.get_or_404(Notification, note_id)
    clique = db.get_or_404(Clique, clique_id)

    if current_user.id != clique.admin_id:
        return jsonify({"success": False, "message": "Only the admin can accept join requests."}), 403

    user = db.session.get(User, note.user_id)
    new_link = CliqueUser(user_id=user.id, clique_id=clique_id, joined_date=datetime.today().strftime("%Y-%m-%d"))
    db.session.add(new_link)
    db.session.delete(note)

    new_notif = Notification(  # Add notification to the user that his request has been approved
        type="accept invitation", user_id=user.id, clique_id=clique_id
    )
    db.session.add(new_notif)
    db.session.commit()

    return jsonify({"success": True, "message": f"{user.name} has been added to '{clique.name}'."})


@main_bp.route("/admin_control_room/<int:clique_id>", methods=["GET", "POST"])
@login_required
def admin_control_room(clique_id):
    clique = db.get_or_404(Clique, clique_id)

    if clique.admin_id != current_user.id:
        return redirect(url_for("main.feed"))

    admin_user = db.session.get(User, clique.admin_id)

    members = (
        db.session.query(User)
        .join(CliqueUser, CliqueUser.user_id == User.id)
        .filter(CliqueUser.clique_id == clique_id, User.id != clique.admin_id)
        .all()
    )

    # Prepare review stats per user
    clique_users = []
    for user in members:
        marker_ids_subq = db.session.query(UserMarker.marker_id).filter_by(clique_id=clique_id).distinct()
        user_reviews = Review.query.filter(Review.user_id == user.id, Review.marker_id.in_(marker_ids_subq)).all()

        review_count = len(user_reviews)
        avg_rating = round(sum(r.stars for r in user_reviews) / review_count, 2) if review_count > 0 else 0.0

        clique_users.append(
            {
                "id": user.id,
                "name": user.name,
                "reviews_added": review_count,
                "average_rating": avg_rating,
            }
        )

    # Admin stats (separate row at top)
    admin_marker_ids = [um.marker_id for um in UserMarker.query.filter_by(clique_id=clique_id).all()]
    admin_reviews = Review.query.filter(Review.user_id == admin_user.id, Review.marker_id.in_(admin_marker_ids)).all()
    admin_review_count = len(admin_reviews)
    admin_avg_rating = round(sum(r.stars for r in admin_reviews) / admin_review_count, 2) if admin_review_count > 0 else 0.0

    banned_users = BannedUser.query.filter_by(clique_id=clique_id).all()
    banned_info = []
    for b in banned_users:
        user = db.session.get(User, b.user_id)
        if user:
            banned_info.append(
                {
                    "user_id": b.user_id,
                    "name": user.name,
                    "ban_date": b.ban_date,
                    "reason": b.reason,
                }
            )

    time_window = request.args.get("range", "week")
    today = datetime.today()
    if time_window == "month":
        start_date = today - timedelta(days=30)
    elif time_window == "year":
        start_date = today - timedelta(days=365)
    else:
        start_date = today - timedelta(days=7)

    start_date_str = start_date.strftime("%Y-%m-%d")

    joined_count = CliqueUser.query.filter_by(clique_id=clique_id).filter(CliqueUser.joined_date >= start_date_str).count()

    marker_count = UserMarker.query.filter_by(clique_id=clique_id).filter(UserMarker.creation_date >= start_date_str).count()

    review_count = (
        db.session.query(Review)
        .filter(
            Review.creation_date >= start_date_str,
            Review.marker_id.in_(db.session.query(UserMarker.marker_id).filter_by(clique_id=clique_id).distinct()),
        )
        .count()
    )

    if time_window == "year":
        today = datetime.today()
        labels = [str(today.year - i) for i in range(2, -1, -1)]

        def extract(date_str):
            return date_str[:4]
    elif time_window == "month":
        today = datetime.today().replace(day=1)
        labels = [(today - timedelta(days=30 * i)).strftime("%Y-%m") for i in range(11, -1, -1)]

        def extract(date_str):
            return date_str[:7]
    else:
        today = datetime.today().date()
        labels = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

        def extract(date_str):
            return date_str

    members = CliqueUser.query.filter_by(clique_id=clique_id).all()
    markers = UserMarker.query.filter_by(clique_id=clique_id).all()
    marker_ids = [m.marker_id for m in markers]
    reviews = Review.query.filter(Review.marker_id.in_(marker_ids)).all()

    members_by = Counter(extract(m.joined_date) for m in members)
    markers_by = Counter(extract(m.creation_date) for m in markers)
    reviews_by = Counter(extract(r.creation_date) for r in reviews)

    members_series = [members_by.get(label, 0) for label in labels]
    markers_series = [markers_by.get(label, 0) for label in labels]
    reviews_series = [reviews_by.get(label, 0) for label in labels]

    return render_template(
        "user/admin_control_room.html",
        clique=clique,
        admin_user=admin_user,
        admin_review_count=admin_review_count,
        admin_avg_rating=admin_avg_rating,
        clique_users=clique_users,
        banned_users=banned_info,
        logged_in=True,
        name=current_user.name,
        joined_count=joined_count,
        marker_count=marker_count,
        review_count=review_count,
        time_range=time_window,
        week_days=labels,
        members_series=members_series,
        markers_series=markers_series,
        reviews_series=reviews_series,
    )


@main_bp.route("/kick_user/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def kick_user(clique_id, user_id):
    clique = db.get_or_404(Clique, clique_id)
    if current_user.id != clique.admin_id and current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.feed"))

    delete_user_from_clique(clique_id, user_id)
    db.session.add(Notification(type="kick", user_id=user_id, clique_id=clique_id))
    db.session.commit()

    if current_user.email == "adminadmin@gmail.com":
        return redirect(url_for("master.edit_clique", clique_id=clique_id))
    return redirect(url_for("main.admin_control_room", clique_id=clique_id))


@main_bp.route("/ban_user/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def ban_user(clique_id, user_id):
    reason = request.form.get("reason", "").strip()[:100]
    clique = db.get_or_404(Clique, clique_id)

    if current_user.id != clique.admin_id and current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.feed"))

    db.session.add(
        BannedUser(
            user_id=user_id,
            clique_id=clique_id,
            reason=reason,
            ban_date=datetime.today().strftime("%Y-%m-%d"),
        )
    )
    db.session.add(Notification(type="ban", user_id=user_id, clique_id=clique_id))
    delete_user_from_clique(clique_id, user_id)
    db.session.commit()

    if current_user.email == "adminadmin@gmail.com":
        return redirect(url_for("master.edit_clique", clique_id=clique_id))
    return redirect(url_for("main.admin_control_room", clique_id=clique_id))


@main_bp.route("/unban_user/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def unban_user(clique_id, user_id):
    clique = db.get_or_404(Clique, clique_id)

    if current_user.id != clique.admin_id:
        return redirect(url_for("main.feed"))

    BannedUser.query.filter_by(user_id=user_id, clique_id=clique_id).delete()
    db.session.add(Notification(type="unban", user_id=user_id, clique_id=clique_id))

    db.session.commit()

    return redirect(url_for("main.admin_control_room", clique_id=clique_id))


@main_bp.route("/transfer_admin/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def transfer_admin(clique_id, user_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("main.feed"))

    clique = db.get_or_404(Clique, clique_id)
    user = db.get_or_404(User, user_id)

    if user.id == clique.admin_id:
        return redirect(url_for("master.edit_clique", clique_id=clique_id))

    clique.admin_id = user.id
    db.session.commit()

    return redirect(url_for("master.edit_clique", clique_id=clique_id))


@main_bp.route("/user-reviews-map/<int:user_id>/<int:clique_id>")
@login_required
def user_reviews_map(user_id, clique_id):
    user = db.get_or_404(User, user_id)

    # Find markers belonging to the clique that the user has already reviewed
    reviewed_marker_ids = db.session.query(Review.marker_id).filter_by(user_id=user_id).all()
    reviewed_marker_ids = [mid[0] for mid in reviewed_marker_ids]

    clique_marker_ids = db.session.query(UserMarker.marker_id).filter_by(clique_id=clique_id).all()
    clique_marker_ids = [mid[0] for mid in clique_marker_ids]

    final_marker_ids = set(reviewed_marker_ids) & set(clique_marker_ids)
    markers = Marker.query.filter(Marker.id.in_(final_marker_ids)).all()

    features = []
    for marker in markers:
        review = Review.query.filter_by(user_id=user.id, marker_id=marker.id).first()
        if not review:
            continue

        is_creator = UserMarker.query.filter_by(user_id=user.id, marker_id=marker.id).first() is not None

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [marker.long, marker.lat]},
                "properties": {
                    "marker_title": marker.description or "Untitled Marker",
                    "stars": review.stars,
                    "commentary": review.commentary or "",
                    "is_creator": is_creator,
                },
            }
        )

    return render_template(
        "user/user_reviews_map.html",
        user=user,
        features=features,
        logged_in=True,
        name=current_user.name,
    )


@main_bp.route("/user-events-map/<int:user_id>/<int:clique_id>")
@login_required
def user_events_map(user_id, clique_id):
    user = db.get_or_404(User, user_id)

    evented_marker_ids = db.session.query(Event.marker_id).filter_by(user_id=user_id).all()
    evented_marker_ids = [mid[0] for mid in evented_marker_ids]

    clique_marker_ids = db.session.query(UserMarker.marker_id).filter_by(clique_id=clique_id).all()
    clique_marker_ids = [mid[0] for mid in clique_marker_ids]

    final_marker_ids = set(evented_marker_ids) & set(clique_marker_ids)

    markers = Marker.query.filter(Marker.id.in_(final_marker_ids)).all()

    features = []
    for marker in markers:
        events = Event.query.filter(Event.user_id == user.id, Event.marker_id == marker.id, Event.clique_id == clique_id).all()

        events_data = [
            {
                "date": e.date,
                "time": e.time,
                "description": e.description,
                "user": db.session.get(User, e.user_id).name,
            }
            for e in events
        ]

        is_creator = UserMarker.query.filter_by(user_id=user.id, marker_id=marker.id).first() is not None

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [marker.long, marker.lat]},
                "properties": {
                    "marker_title": marker.description or "Untitled Marker",
                    "events": events_data,
                    "is_creator": is_creator,
                },
            }
        )

    return render_template(
        "user/user_events_map.html",
        user=user,
        features=features,
        logged_in=True,
        name=current_user.name,
    )


@main_bp.route("/send_admin_invitation/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def send_admin_invitation(clique_id, user_id):
    clique = db.session.get(Clique, clique_id)
    if not clique or clique.admin_id != current_user.id:
        return redirect(url_for("main.feed"))

    existing = Notification.query.filter_by(user_id=user_id, clique_id=clique_id, type="invitation to become admin").first()

    if existing:
        return redirect(url_for("main.admin_control_room", clique_id=clique_id))

    db.session.add(Notification(user_id=user_id, clique_id=clique_id, type="invitation to become admin"))
    db.session.commit()
    return redirect(url_for("main.admin_control_room", clique_id=clique_id))


@main_bp.route("/accept_admin_invite/<int:note_id>/<int:clique_id>", methods=["POST"])
@login_required
def accept_admin_invite(note_id, clique_id):
    note = db.get_or_404(Notification, note_id)
    clique = db.get_or_404(Clique, clique_id)

    if note.user_id != current_user.id or note.type != "invitation to become admin":
        return redirect(url_for("map.maptest"))

    clique.admin_id = current_user.id
    db.session.delete(note)
    db.session.commit()

    return redirect(url_for("map.maptest"))


@main_bp.route("/decline_admin_invite/<int:note_id>", methods=["POST"])
@login_required
def decline_admin_invite(note_id):
    note = db.get_or_404(Notification, note_id)
    if note.user_id != current_user.id or note.type != "invitation to become admin":
        return redirect(url_for("map.maptest"))

    db.session.delete(note)
    db.session.commit()
    return redirect(url_for("map.maptest"))


@main_bp.route("/report_user", methods=["POST"])
@login_required
def report_user():
    user_id = int(request.form.get("user_id"))
    clique_id = int(request.form.get("clique_id"))
    reasons = request.form.getlist("reasons")

    if not reasons:
        return redirect(url_for("main.admin_control_room", clique_id=clique_id))

    for reason in reasons:
        db.session.add(Notification(type=reason, user_id=user_id, clique_id=clique_id))

    db.session.commit()
    return redirect(url_for("main.admin_control_room", clique_id=clique_id))


@main_bp.route("/delete_clique/<int:clique_id>", methods=["POST"])
@login_required
def delete_clique_route(clique_id):
    clique = db.get_or_404(Clique, clique_id)
    if current_user.id != clique.admin_id and current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("user.settings"))

    delete_clique_and_contents(clique_id)
    db.session.commit()
    return redirect(url_for("master.cliques"))

import os

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import (
    Clique,
    CliqueUser,
    Event,
    Marker,
    Review,
    User,
    UserMarker,
)
from app.user import user_bp
from app.utils import (
    delete_user,
    is_valid_email,
    is_valid_password,
)


@user_bp.route("/settings")
@login_required
def settings():
    user_clique_links = CliqueUser.query.filter_by(user_id=current_user.id).all()
    user_cliques = []

    for link in user_clique_links:
        clique = db.session.get(Clique, link.clique_id)
        status = "admin" if clique.admin_id == current_user.id else "user"

        marker_ids = [um.marker_id for um in UserMarker.query.filter_by(clique_id=clique.id).all()]
        total_markers = len(set(marker_ids))
        user_reviews_in_clique = Review.query.filter(Review.marker_id.in_(marker_ids), Review.user_id == current_user.id).count()

        user_cliques.append(
            {
                "id": clique.id,
                "name": clique.name,
                "description": clique.description,
                "status": status,
                "visibility": clique.visibility,
                "reviews_added": f"{user_reviews_in_clique}/{total_markers}",
            }
        )

    all_reviews = Review.query.filter_by(user_id=current_user.id).all()
    reviews_data = []
    for r in all_reviews:
        any_marker_link = UserMarker.query.filter_by(marker_id=r.marker_id).first()
        clique = db.session.get(Clique, any_marker_link.clique_id) if any_marker_link else None
        if clique:
            reviews_data.append(
                {
                    "review_id": r.id,
                    "marker_id": r.marker_id,
                    "clique_name": clique.name,
                    "marker_name": r.marker.description,
                    "commentary": r.commentary,
                    "stars": r.stars,
                }
            )

    all_events = Event.query.filter_by(user_id=current_user.id).all()
    events_data = []

    for e in all_events:
        e.marker = db.session.get(Marker, e.marker_id)
        e.clique = db.session.get(Clique, e.clique_id)

        events_data.append(
            {
                "event_id": e.id,
                "marker_id": e.marker_id,
                "clique_name": e.clique.name,
                "marker_name": e.marker.description,
                "date": e.date,
                "time": e.time,
                "description": e.description,
            }
        )

    show_avatars = os.environ.get("SHOW_PREMIUM_AVATARS", "False") == "True"

    return render_template(
        "user/settings.html",
        name=current_user.name,
        show_avatars=show_avatars,
        cliques=user_cliques,
        reviews=reviews_data,
        events=events_data,
        logged_in=True,
    )


@user_bp.route("/edit", methods=["GET"])
@login_required
def edit_user():
    return render_template("user/edit_user.html", name=current_user.name, logged_in=True)


@user_bp.route("/update_user", methods=["POST"])
@login_required
def update_user():
    new_name = request.form.get("name")
    new_email = request.form.get("email")

    if not is_valid_email(new_email):
        flash(
            "The email address you entered is not valid. Please enter a valid email address.",
            "danger",
        )
        return redirect(url_for("user.edit_user"))

    # Ensure email uniqueness
    existing_user = User.query.filter(User.email == new_email, User.id != current_user.id).first()
    if existing_user:
        flash(
            "The email address you entered is already in use. Please choose a different one.",
            "danger",
        )
        return redirect(url_for("user.edit_user"))

    current_user.name = new_name
    current_user.email = new_email
    db.session.commit()

    return redirect(url_for("user.settings"))


@user_bp.route("/change_password", methods=["GET"])
@login_required
def change_password():
    return render_template("user/change_password.html", name=current_user.name, logged_in=True)


@user_bp.route("/update_password", methods=["POST"])
@login_required
def update_password():
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    if not check_password_hash(current_user.password, current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("user.change_password"))

    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "danger")
        return redirect(url_for("user.change_password"))

    if not is_valid_password(new_password):
        flash(
            "Invalid password format! Password must be at least 8 characters long, include an uppercase letter, a digit, and a special character.",
            "danger",
        )
        return redirect(url_for("user.change_password"))

    if new_password == current_password:
        flash("Your new password must be different from your current password.", "danger")
        return redirect(url_for("user.change_password"))

    current_user.password = generate_password_hash(new_password, method="pbkdf2:sha256", salt_length=8)
    db.session.commit()

    return redirect(url_for("user.settings"))


@user_bp.route("/manage_account", methods=["GET"])
@login_required
def manage_account():
    return render_template(
        "user/manage_account.html",
        name=current_user.name,
        logged_in=True,
        user_password=current_user.password,
    )


@user_bp.route("/verify-password", methods=["POST"])
@login_required
def verify_password():
    data = request.get_json()
    password = data.get("password")

    if check_password_hash(current_user.password, password):
        return jsonify(valid=True)
    else:
        return jsonify(valid=False)


@user_bp.route("/update-profile-pic/<int:user_id>", methods=["POST"])
@login_required
def update_profile_pic(user_id):
    user = db.get_or_404(User, user_id)
    action = request.form.get("action")

    if action == "edit":
        avatar_filename = request.form.get("selected_avatar")

        user.picture = avatar_filename
        db.session.commit()

        return redirect(url_for("user.settings"))

    if action == "delete":
        user.picture = "default.jpg"
        db.session.commit()

        return redirect(url_for("user.settings"))


@user_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    if request.form.get("confirmed") != "true":
        flash("Account deletion not confirmed.", "danger")
        return redirect(url_for("user.manage_account"))

    delete_user(current_user.id)
    db.session.commit()
    logout_user()
    flash("Your account has been successfully deleted. We're sorry to see you go.", "info")
    return redirect(url_for("auth.login"))

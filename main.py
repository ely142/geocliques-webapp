import os
from collections import Counter
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from rapidfuzz import fuzz
from werkzeug.security import check_password_hash, generate_password_hash

from models import (
    BannedUser,
    Clique,
    CliqueUser,
    Event,
    Marker,
    Notification,
    Review,
    User,
    UserMarker,
    db,
)
from utils import (
    assign_clique_colors,
    delete_clique_and_contents,
    delete_marker_and_contents,
    delete_review_and_update_marker,
    delete_user,
    delete_user_from_clique,
    is_valid_email,
    is_valid_password,
    perform_leave_clique,
)

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "fallback-secret")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///users.db")
db.init_app(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


@app.before_request
def delete_expired_events():
    # Allowed endpoints represent views where users interact with map data
    if request.endpoint in ["maptest", "add_event", "get_user_markers", "edit_event"]:
        today = date.today()

        expired_events = Event.query.filter(Event.date < today).all()

        for event in expired_events:
            db.session.delete(event)

        db.session.commit()


@app.route("/map_keys.js")
def map_keys():
    key = os.getenv("MAP_THUNDERFOREST_KEY", "")
    return (
        f"window.MAP_KEYS = {{ thunderforest: '{key}' }};",
        200,
        {"Content-Type": "application/javascript"},
    )


# MAP FUNCTIONS
""" functions relating to displaying and interacting with the Leaflet map"""


@app.route("/maptest")
@login_required
def maptest():
    if current_user.email == "adminadmin@gmail.com":
        return render_template("master/masterbase.html", name=current_user.name, logged_in=True)
    selected_layer = session.get("selected_layer", "default")
    return render_template("user/maptest.html", name=current_user.name, logged_in=True, selected_layer=selected_layer)


@app.route("/geojson-features", methods=["GET"])
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
        user_events = [{"date": e.date, "time": e.time, "description": e.description, "is_own_event": True} for e in all_user_events]

        # Peer events
        all_events = Event.query.filter(Event.marker_id == marker.id, Event.user_id != current_user.id).all()
        other_events = [
            {
                "date": e.date,
                "time": e.time,
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


@app.route("/clique-geojson/<int:clique_id>", methods=["GET"])
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


@app.route("/add-marker", methods=["POST"])
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
            creation_date=datetime.today().strftime("%Y-%m-%d"),
        )
        db.session.add(user_marker)

        new_review = Review(
            stars=rating,
            commentary=commentary,
            marker_id=new_marker.id,
            user_id=current_user.id,
            creation_date=datetime.today().strftime("%Y-%m-%d"),
        )
        db.session.add(new_review)

        db.session.commit()

        return jsonify({"success": True, "message": "Marker added successfully!"}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/edit-review/<int:marker_id>", methods=["GET"])
@login_required
def edit_review(marker_id):
    review = Review.query.filter_by(marker_id=marker_id, user_id=current_user.id).first_or_404()
    marker = review.marker
    is_only_review = marker.total_reviews == 1
    next = request.args.get("next", "maptest")
    return render_template(
        "user/edit_review.html",
        review=review,
        marker=marker,
        is_only_review=is_only_review,
        logged_in=True,
        name=current_user.name,
        next=next,
    )


@app.route("/update-review/<int:marker_id>", methods=["POST"])
@login_required
def update_review(marker_id):
    review = Review.query.filter_by(marker_id=marker_id, user_id=current_user.id).first_or_404()
    marker = review.marker
    action = request.form.get("action")
    next = request.form.get("next", "maptest")

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


@app.route("/rate-marker/<int:marker_id>", methods=["POST"])
@login_required
def rate_marker(marker_id):
    marker = Marker.query.get_or_404(marker_id)
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
        creation_date=datetime.today().strftime("%Y-%m-%d"),
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({"success": True, "message": "Review added!"})


@app.route("/select-layer", methods=["GET", "POST"])
@login_required
def select_layer():
    if request.method == "POST":
        selected_layer = request.form.get("layer")
        session["selected_layer"] = selected_layer
        return redirect(url_for("maptest"))

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
        "user/select_layer.html",
        layers=layers,
        selected_layer=selected_layer,
        name=current_user.name,
        logged_in=True,
    )


@app.route("/add-event/<int:marker_id>/<int:clique_id>", methods=["GET", "POST"])
@login_required
def add_event(marker_id, clique_id):
    if request.method == "POST":
        date = request.form.get("date")
        time = request.form.get("time")
        description = request.form.get("description")

        if not date or not time or not description:
            return redirect(url_for("add_event"))

        new_event = Event(
            date=date,
            time=time,
            description=description,
            marker_id=marker_id,
            clique_id=clique_id,
            user_id=current_user.id,
        )

        db.session.add(new_event)
        db.session.commit()
        return redirect(url_for("maptest"))

    return render_template(
        "user/add_event.html",
        marker_id=marker_id,
        clique_id=clique_id,
        logged_in=True,
        name=current_user.name,
    )


@app.route("/edit-events/<int:marker_id>/<int:clique_id>", methods=["GET"])
@login_required
def edit_event(marker_id, clique_id):
    all_user_events = Event.query.filter(Event.marker_id == marker_id, Event.user_id == current_user.id, Event.clique_id == clique_id).all()
    marker = Marker.query.filter(Marker.id == marker_id).first()
    clique = Clique.query.filter(Clique.id == clique_id).first()
    return render_template(
        "user/edit_events.html",
        events=all_user_events,
        clique=clique,
        marker=marker,
        logged_in=True,
        name=current_user.name,
    )


@app.route("/update-event/<int:event_id>", methods=["POST"])
@login_required
def update_event(event_id):
    event = Event.query.get_or_404(event_id)
    action = request.form.get("action")
    next = request.form.get("next")  # maptest.html default route

    if request.method == "POST":
        if action == "delete":
            db.session.delete(event)
            db.session.commit()

            if current_user.email == "adminadmin@gmail.com":
                return redirect(url_for("edit_clique", clique_id=event.clique_id))

            if next == "settings":
                return redirect(url_for(next))
            else:
                return redirect(url_for("edit_event", marker_id=event.marker_id, clique_id=event.clique_id))

        else:
            event_date = request.form["date"]
            event_time = request.form["time"]
            event_description = request.form["description"]

            event.date = event_date
            event.time = event_time
            event.description = event_description

            db.session.commit()

            if next == "settings":
                return redirect(url_for(next))
            else:
                return redirect(url_for("edit_event", marker_id=event.marker_id, clique_id=event.clique_id))


@app.route("/update-icon/<int:clique_id>", methods=["POST"])
@login_required
def update_icon(clique_id):
    clique = Clique.query.get_or_404(clique_id)

    if request.method == "POST":
        new_icon = request.form.get("selectedIcon")
        clique.icon = new_icon

        db.session.commit()

        return redirect(url_for("admin_control_room", clique_id=clique_id))
    return redirect(url_for("admin_control_room", clique_id=clique_id))


@app.route("/update_clique_type/<int:clique_id>", methods=["POST"])
@login_required
def update_clique_type(clique_id):
    clique = Clique.query.get_or_404(clique_id)

    if request.method == "POST":
        new_visibility = request.form.get("visibility")

        if new_visibility in ["Private", "Public", "Protected"]:
            clique.visibility = new_visibility

            db.session.commit()

            return redirect(url_for("admin_control_room", clique_id=clique.id))
        return redirect(url_for("admin_control_room", clique_id=clique.id))


# USER FUNCTIONS
""" functions relating to registration, login, account, and user-specific actions"""


@app.route("/")
def home():
    return render_template("index.html", logged_in=current_user.is_authenticated, show_auth_links=True)


@app.route("/user_guide", methods=["GET"])
def user_guide():
    return render_template("user_guide.html", logged_in=False)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        name = request.form.get("name")

        if not is_valid_email(email):
            flash(
                "Please enter a valid email address.",
                "danger",
            )
            return redirect(url_for("register"))

        if not is_valid_password(password):
            flash(
                "Password must be at least 8 characters long, include an uppercase letter, a digit, and a special character.",
                "danger",
            )
            return redirect(url_for("register"))

        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if user:
            flash("You've already signed up with that email, log in instead!", "danger")
            return redirect(url_for("login"))

        hash_and_salted_password = generate_password_hash(password, method="pbkdf2:sha256", salt_length=8)
        new_user = User(email=email, password=hash_and_salted_password, name=name)

        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        if email == "adminadmin@gmail.com":
            return redirect(url_for("cliques"))
        return redirect(url_for("maptest"))

    return render_template("register.html", logged_in=current_user.is_authenticated)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if not user:
            flash("That email does not exist, please try again.", "danger")
            return redirect(url_for("login"))
        elif not check_password_hash(user.password, password):
            flash("Password incorrect, please try again.", "danger")
            return redirect(url_for("login"))
        else:
            login_user(user)
            if user.email == "adminadmin@gmail.com":
                return redirect(url_for("cliques"))
            return redirect(url_for("maptest"))

    return render_template("login.html", logged_in=current_user.is_authenticated)


@app.route("/logout")
@login_required
def logout():
    db.session.close()
    logout_user()
    return redirect(url_for("home"))


@app.route("/settings")
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


@app.route("/delete-review/<int:review_id>", methods=["POST"])
@login_required
def delete_review_route(review_id):
    review = db.session.get(Review, review_id)
    if not review or review.user_id != current_user.id:
        return redirect(url_for("settings"))

    delete_review_and_update_marker(review_id)
    db.session.commit()
    return redirect(url_for("settings"))


@app.route("/check_review_solo/<int:review_id>")
@login_required
def check_review_solo(review_id):
    review = Review.query.get_or_404(review_id)
    marker = review.marker
    return jsonify({"is_only": len(marker.reviews) == 1})


@app.route("/user_edit_user", methods=["GET"])
@login_required
def user_edit_user():
    return render_template("user/user_edit_user.html", name=current_user.name, logged_in=True)


@app.route("/update_user", methods=["POST"])
@login_required
def update_user():
    new_name = request.form.get("name")
    new_email = request.form.get("email")

    if not is_valid_email(new_email):
        flash(
            "The email address you entered is not valid. Please enter a valid email address.",
            "danger",
        )
        return redirect(url_for("user_edit_user"))

        # Ensure email uniqueness
    existing_user = User.query.filter(User.email == new_email, User.id != current_user.id).first()
    if existing_user:
        flash(
            "The email address you entered is already in use. Please choose a different one.",
            "danger",
        )
        return redirect(url_for("user_edit_user"))

    current_user.name = new_name
    current_user.email = new_email
    db.session.commit()

    return redirect(url_for("settings"))


@app.route("/change_password", methods=["GET"])
@login_required
def change_password():
    return render_template("user/change_password.html", name=current_user.name, logged_in=True)


@app.route("/update_password", methods=["POST"])
@login_required
def update_password():
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    if not check_password_hash(current_user.password, current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("change_password"))

    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "danger")
        return redirect(url_for("change_password"))

    if not is_valid_password(new_password):
        flash(
            "Invalid password format! Password must be at least 8 characters long, include an uppercase letter, a digit, and a special character.",
            "danger",
        )
        return redirect(url_for("change_password"))

    if new_password == current_password:
        flash("Your new password must be different from your current password.", "danger")
        return redirect(url_for("change_password"))

    current_user.password = generate_password_hash(new_password, method="pbkdf2:sha256", salt_length=8)
    db.session.commit()

    return redirect(url_for("settings"))


@app.route("/manage_account", methods=["GET"])
@login_required
def manage_account():
    return render_template(
        "user/manage_account.html",
        name=current_user.name,
        logged_in=True,
        user_password=current_user.password,
    )


@app.route("/verify-password", methods=["POST"])
@login_required
def verify_password():
    data = request.get_json()
    password = data.get("password")

    if check_password_hash(current_user.password, password):
        return jsonify(valid=True)
    else:
        return jsonify(valid=False)


@app.route("/update-profile-pic/<int:user_id>", methods=["POST"])
@login_required
def update_profile_pic(user_id):
    user = User.query.get_or_404(user_id)
    action = request.form.get("action")

    if action == "edit":
        avatar_filename = request.form.get("selected_avatar")

        user.picture = avatar_filename
        db.session.commit()

        return redirect(url_for("settings"))

    if action == "delete":
        user.picture = "default.jpg"
        db.session.commit()

        return redirect(url_for("settings"))


# CLIQUE FUNCTIONS
""" functions relating to creating, searching, joining, and leaving cliques"""


@app.route("/feed")
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


@app.route("/create-clique", methods=["GET", "POST"])
@login_required
def create_clique():
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        visibility = request.form.get("visibility")
        icon = request.form.get("selectedIcon")

        if not name:
            return redirect(url_for("create_clique"))

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

        return redirect(url_for("maptest"))

    return render_template("user/create_clique.html", name=current_user.name, logged_in=True)


@app.route("/send_invite", methods=["POST"])
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
    clique = Clique.query.get_or_404(clique_id)
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


@app.route("/join_clique/<int:clique_id>", methods=["POST"])
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


@app.route("/leave_clique/<int:clique_id>", methods=["POST"])
@login_required
def leave_clique(clique_id):
    success = perform_leave_clique(clique_id, current_user.id)
    if success:
        db.session.commit()
        flash("You have successfully left the clique.", "success")
    else:
        flash("Failed to leave the clique.", "danger")
    return redirect(url_for("settings"))


@app.route("/search_cliques")
@login_required
def search_cliques():
    query = request.args.get("query", "").strip().lower()

    if not query:
        return redirect(url_for("feed"))

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


@app.route("/autocomplete")
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


@app.route("/request_join_protected/<int:clique_id>", methods=["POST"])
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


@app.route("/get_notifications")
@login_required
def get_notifications():
    notifications = []

    personal_notes = Notification.query.filter(Notification.user_id == current_user.id).filter(Notification.type != "request to join protected").all()

    for note in personal_notes:
        clique = db.session.get(Clique, note.clique_id)
        clique_name = clique.name if clique else "Unknown"
        visibility = clique.visibility if clique else "Unknown"

        if note.type == "ban":
            notifications.append(
                {
                    "id": note.id,
                    "clique_id": note.clique_id,
                    "clique_name": clique_name,
                    "type": note.type,
                }
            )
        elif note.type == "unban":
            notifications.append(
                {
                    "id": note.id,
                    "clique_id": note.clique_id,
                    "clique_name": clique_name,
                    "type": note.type,
                }
            )
        elif note.type == "kick":
            notifications.append(
                {
                    "id": note.id,
                    "clique_id": note.clique_id,
                    "clique_name": clique_name,
                    "type": note.type,
                }
            )
        elif note.type == "invitation" or note.type == "invitation admin" or note.type == "invitation protected":
            notifications.append(
                {
                    "id": note.id,
                    "clique_id": note.clique_id,
                    "clique_name": clique_name,
                    "visibility": visibility,
                    "type": note.type,
                }
            )
        elif note.type == "invitation to become admin":
            notifications.append(
                {
                    "id": note.id,
                    "clique_id": note.clique_id,
                    "clique_name": clique_name,
                    "type": note.type,
                }
            )
        elif note.type == "admin replacement":
            notifications.append(
                {
                    "id": note.id,
                    "clique_id": note.clique_id,
                    "clique_name": clique_name,
                    "type": note.type,
                }
            )
        elif note.type == "accept invitation":
            notifications.append(
                {
                    "id": note.id,
                    "clique_id": note.clique_id,
                    "clique_name": clique_name,
                    "type": note.type,
                }
            )

    # Show "request to join protected" only if current user is the clique's admin
    join_requests = Notification.query.filter_by(type="request to join protected").all()

    for note in join_requests:
        clique = db.session.get(Clique, note.clique_id)
        if clique and clique.admin_id == current_user.id:
            requester = db.session.get(User, note.user_id)
            notifications.append(
                {
                    "id": note.id,
                    "clique_id": clique.id,
                    "clique_name": clique.name,
                    "visibility": clique.visibility,
                    "type": "request to join protected",
                    "requester_name": requester.name if requester else "Unknown",
                }
            )

    return jsonify({"notifications": notifications})


@app.route("/delete_notification/<int:id>", methods=["POST"])
@login_required
def delete_notification(id):
    note = db.session.get(Notification, id)

    report_types = {"bot like report", "overwhelming bias report", "hurtful language report"}
    if note and note.type in report_types:
        if current_user.email == "adminadmin@gmail.com":  # Only master can delete report-type notifications
            db.session.delete(note)
            db.session.commit()
            return redirect(url_for("master_reports"))
        else:
            return redirect(url_for("home"))

    # Normal user-related notifications (ban, kick, invites, etc.)
    if note and (note.user_id == current_user.id or (note.clique_id and db.session.get(Clique, note.clique_id).admin_id == current_user.id)):
        db.session.delete(note)
        db.session.commit()
        return jsonify({"success": True})

    return jsonify({"success": False, "message": "Notification not found or unauthorized"}), 404


# CLIQUE ADMIN FUNCTIONS
""" functions used by the cliques' admins to manage the cliques"""


@app.route("/accept_request/<int:note_id>/<int:clique_id>", methods=["POST"])
@login_required
def accept_request(note_id, clique_id):
    note = Notification.query.get_or_404(note_id)
    clique = Clique.query.get_or_404(clique_id)

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


@app.route("/admin_control_room/<int:clique_id>", methods=["GET", "POST"])
@login_required
def admin_control_room(clique_id):
    clique = Clique.query.get_or_404(clique_id)

    if clique.admin_id != current_user.id:
        return redirect(url_for("feed"))

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


@app.route("/kick_user/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def kick_user(clique_id, user_id):
    clique = Clique.query.get_or_404(clique_id)
    if current_user.id != clique.admin_id and current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("feed"))

    delete_user_from_clique(clique_id, user_id)
    db.session.add(Notification(type="kick", user_id=user_id, clique_id=clique_id))
    db.session.commit()

    if current_user.email == "adminadmin@gmail.com":
        return redirect(url_for("edit_clique", clique_id=clique_id))
    return redirect(url_for("admin_control_room", clique_id=clique_id))


@app.route("/ban_user/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def ban_user(clique_id, user_id):
    reason = request.form.get("reason", "").strip()[:100]
    clique = Clique.query.get_or_404(clique_id)

    if current_user.id != clique.admin_id and current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("feed"))

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
        return redirect(url_for("edit_clique", clique_id=clique_id))
    return redirect(url_for("admin_control_room", clique_id=clique_id))


@app.route("/unban_user/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def unban_user(clique_id, user_id):
    clique = Clique.query.get_or_404(clique_id)

    if current_user.id != clique.admin_id:
        return redirect(url_for("feed"))

    BannedUser.query.filter_by(user_id=user_id, clique_id=clique_id).delete()
    db.session.add(Notification(type="unban", user_id=user_id, clique_id=clique_id))

    db.session.commit()

    return redirect(url_for("admin_control_room", clique_id=clique_id))


@app.route("/transfer_admin/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def transfer_admin(clique_id, user_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("feed"))

    clique = Clique.query.get_or_404(clique_id)
    user = User.query.get_or_404(user_id)

    if user.id == clique.admin_id:
        return redirect(url_for("edit_clique", clique_id=clique_id))

    clique.admin_id = user.id
    db.session.commit()

    return redirect(url_for("edit_clique", clique_id=clique_id))


@app.route("/user-reviews-map/<int:user_id>/<int:clique_id>")
@login_required
def user_reviews_map(user_id, clique_id):
    user = User.query.get_or_404(user_id)

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


@app.route("/user-events-map/<int:user_id>/<int:clique_id>")
@login_required
def user_events_map(user_id, clique_id):
    user = User.query.get_or_404(user_id)

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


@app.route("/send_admin_invitation/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def send_admin_invitation(clique_id, user_id):
    clique = db.session.get(Clique, clique_id)
    if not clique or clique.admin_id != current_user.id:
        return redirect(url_for("feed"))

    existing = Notification.query.filter_by(user_id=user_id, clique_id=clique_id, type="invitation to become admin").first()

    if existing:
        return redirect(url_for("admin_control_room", clique_id=clique_id))

    db.session.add(Notification(user_id=user_id, clique_id=clique_id, type="invitation to become admin"))
    db.session.commit()
    return redirect(url_for("admin_control_room", clique_id=clique_id))


@app.route("/accept_admin_invite/<int:note_id>/<int:clique_id>", methods=["POST"])
@login_required
def accept_admin_invite(note_id, clique_id):
    note = Notification.query.get_or_404(note_id)
    clique = Clique.query.get_or_404(clique_id)

    if note.user_id != current_user.id or note.type != "invitation to become admin":
        return redirect(url_for("maptest"))

    clique.admin_id = current_user.id
    db.session.delete(note)
    db.session.commit()

    return redirect(url_for("maptest"))


@app.route("/decline_admin_invite/<int:note_id>", methods=["POST"])
@login_required
def decline_admin_invite(note_id):
    note = Notification.query.get_or_404(note_id)
    if note.user_id != current_user.id or note.type != "invitation to become admin":
        return redirect(url_for("maptest"))

    db.session.delete(note)
    db.session.commit()
    return redirect(url_for("maptest"))


@app.route("/report_user", methods=["POST"])
@login_required
def report_user():
    user_id = int(request.form.get("user_id"))
    clique_id = int(request.form.get("clique_id"))
    reasons = request.form.getlist("reasons")

    if not reasons:
        return redirect(url_for("admin_control_room", clique_id=clique_id))

    for reason in reasons:
        db.session.add(Notification(type=reason, user_id=user_id, clique_id=clique_id))

    db.session.commit()
    return redirect(url_for("admin_control_room", clique_id=clique_id))


# MASTER FUNCTIONS
""" functions accessible only to the master user """


@app.route("/users")
@login_required
def users():
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("home"))

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


@app.route("/unban_user_master/<int:clique_id>/<int:user_id>", methods=["POST"])
@login_required
def unban_user_master(clique_id, user_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("feed"))

    BannedUser.query.filter_by(user_id=user_id, clique_id=clique_id).delete()
    db.session.add(Notification(type="unban", user_id=user_id, clique_id=clique_id))
    db.session.commit()

    flash("User successfully unbanned.", "success")
    return redirect(url_for("users"))


@app.route("/edit_user/<int:user_id>", methods=["POST"])
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


@app.route("/cliques")
def cliques():
    all_cliques = Clique.query.all()
    admin_map = {clique.id: db.session.get(User, clique.admin_id) for clique in all_cliques}
    return render_template(
        "master/cliques.html",
        cliquesList=all_cliques,
        adminMap=admin_map,
        logged_in=current_user.is_authenticated,
    )


@app.route("/clique-map/<int:clique_id>")
@login_required
def master_clique_map(clique_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("home"))

    clique = Clique.query.get_or_404(clique_id)
    return render_template("master/clique_map.html", clique=clique, logged_in=True)


@app.route("/edit_clique/<int:clique_id>", methods=["GET"])
@login_required
def edit_clique(clique_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("feed"))

    clique = Clique.query.get_or_404(clique_id)
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


@app.route("/remove_marker_from_clique/<int:clique_id>/<int:marker_id>", methods=["POST"])
@login_required
def remove_marker_from_clique(clique_id, marker_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("feed"))
    delete_marker_and_contents(marker_id)
    db.session.commit()
    return redirect(url_for("edit_clique", clique_id=clique_id))


@app.route("/delete_review_from_clique/<int:review_id>/<int:clique_id>", methods=["POST"])
@login_required
def delete_review_from_clique(review_id, clique_id):
    delete_review_and_update_marker(review_id)
    db.session.commit()
    return redirect(url_for("edit_clique", clique_id=clique_id))


@app.route("/master/reports")
@login_required
def master_reports():
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("home"))

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


# DELETIONS / CLEANUPS FUNCTIONS
""" functions used for deletions"""


@app.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    if request.form.get("confirmed") != "true":
        flash("Account deletion not confirmed.", "danger")
        return redirect(url_for("manage_account"))

    delete_user(current_user.id)
    db.session.commit()
    logout_user()
    flash("Your account has been successfully deleted. We're sorry to see you go.", "info")
    return redirect(url_for("login"))


@app.route("/delete_user/<int:user_id>", methods=["POST"])
@login_required
def delete_user_route(user_id):
    if current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("settings"))

    delete_user(user_id)
    db.session.commit()
    flash("User and associated data deleted.", "success")
    return redirect(url_for("users"))


@app.route("/delete_clique/<int:clique_id>", methods=["POST"])
@login_required
def delete_clique_route(clique_id):
    clique = Clique.query.get_or_404(clique_id)
    if current_user.id != clique.admin_id and current_user.email != "adminadmin@gmail.com":
        return redirect(url_for("settings"))

    delete_clique_and_contents(clique_id)
    db.session.commit()
    return redirect(url_for("cliques"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()

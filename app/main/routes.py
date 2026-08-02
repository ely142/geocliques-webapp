from datetime import datetime, timedelta

from flask import jsonify, render_template, request
from flask_login import current_user, login_required

from app.extensions import db
from app.main import main_bp
from app.models import (
    Clique,
    CliqueUser,
    Marker,
    Review,
    User,
    UserMarker,
)


@main_bp.route("/")
def home():
    return render_template("index.html", logged_in=current_user.is_authenticated, show_auth_links=True)


@main_bp.route("/user_guide", methods=["GET"])
def user_guide():
    return render_template("user_guide.html", logged_in=False)


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

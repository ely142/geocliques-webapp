import random
import re

import numpy as np
from matplotlib.colors import to_rgb

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
    db,
)

PALETTE = [
    "#FE7743",
    "#273F4F",
    "#7C4585",
    "#E9A319",
    "#FFC6C6",
    "#46F0F0",
    "#C5172E",
    "#E9F5BE",
    "#000000",
    "#FBF8EF",
    "#A76545",
    "#FF8383",
    "#9AA6B2",
    "#FFF085",
    "#5F8B4C",
    "#8F87F1",
    "#410445",
    "#A59D84",
    "#E07B39",
]


# Auxiliary functions related to assigning unique colors to cliques' markers
def color_distance(c1, c2):
    rgb1 = np.array(to_rgb(c1))
    rgb2 = np.array(to_rgb(c2))
    return np.linalg.norm(rgb1 - rgb2)


def generate_safe_random_color(existing_colors, min_dist=0.3):
    tries = 1000
    for _ in range(tries):
        color = "#{:02x}{:02x}{:02x}".format(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        if all(color_distance(color, c) >= min_dist for c in existing_colors):
            return color
    return "#%06x" % random.randint(0, 0xFFFFFF)


def assign_clique_colors(clique_ids):
    assigned = {}
    used = []

    for idx, cid in enumerate(clique_ids):
        if idx < len(PALETTE):
            color = PALETTE[idx]
        else:
            color = generate_safe_random_color(used)
        assigned[cid] = color
        used.append(color)

    return assigned


# Auxiliary functions related to the registration process in the app
def is_valid_password(password):
    return (
        len(password) >= 8
        and any(c.isupper() for c in password)
        and any(c.isdigit() for c in password)
        and any(c in "!@#$%^&*()-_=+[]{}|;:'\",.<>?/" for c in password)
    )


def is_valid_email(email):
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z.]+$"
    return re.match(email_regex, email)


# Auxiliary functions related to deletions in the app
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return

    for review in list(user.reviews):
        delete_review_and_update_marker(review.id)

    created_links = UserMarker.query.filter_by(user_id=user.id).all()
    for link in created_links:
        link.user_id = -1

    admin_cliques = Clique.query.filter_by(admin_id=user.id).all()
    for clique in admin_cliques:
        other_members = (
            CliqueUser.query.filter(CliqueUser.clique_id == clique.id, CliqueUser.user_id != user.id).order_by(CliqueUser.joined_date).all()
        )
        if other_members:
            new_admin_id = other_members[0].user_id
            clique.admin_id = new_admin_id
            db.session.add(Notification(type="admin replacement", user_id=new_admin_id, clique_id=clique.id))
        else:
            delete_clique_and_contents(clique.id)

    non_admin_links = CliqueUser.query.filter_by(user_id=user.id).all()
    for link in non_admin_links:
        Event.query.filter_by(clique_id=link.clique_id, user_id=user.id).delete()
        db.session.delete(link)

    Event.query.filter_by(user_id=user.id).delete()

    UserMarker.query.filter_by(user_id=user.id).delete()
    Notification.query.filter_by(user_id=user.id).delete()
    BannedUser.query.filter_by(user_id=user.id).delete()

    db.session.delete(user)


def delete_user_from_clique(clique_id, user_id):
    CliqueUser.query.filter_by(user_id=user_id, clique_id=clique_id).delete()

    marker_ids = [um.marker_id for um in UserMarker.query.filter_by(clique_id=clique_id).all()]
    reviews = Review.query.filter(Review.user_id == user_id, Review.marker_id.in_(marker_ids)).all()

    for review in reviews:
        delete_review_and_update_marker(review.id)

    Event.query.filter_by(user_id=user_id, clique_id=clique_id).delete()


def perform_leave_clique(clique_id, user_id):
    clique = db.session.get(Clique, clique_id)
    if not clique:
        return False

    if clique.admin_id == user_id:
        other_members = (
            CliqueUser.query.filter(CliqueUser.clique_id == clique_id, CliqueUser.user_id != user_id).order_by(CliqueUser.joined_date).all()
        )

        if other_members:
            new_admin_id = other_members[0].user_id
            clique.admin_id = new_admin_id

            db.session.add(Notification(type="admin replacement", user_id=new_admin_id, clique_id=clique_id))
        else:
            delete_clique_and_contents(clique_id)
            return True

    delete_user_from_clique(clique_id, user_id)
    return True


def delete_clique_and_contents(clique_id):
    marker_ids = [um.marker_id for um in UserMarker.query.filter_by(clique_id=clique_id).all()]
    for mid in marker_ids:
        delete_marker_and_contents(mid)

    Notification.query.filter_by(clique_id=clique_id).delete()
    UserMarker.query.filter_by(clique_id=clique_id).delete()
    CliqueUser.query.filter_by(clique_id=clique_id).delete()
    BannedUser.query.filter_by(clique_id=clique_id).delete()

    clique = db.session.get(Clique, clique_id)
    if clique:
        db.session.delete(clique)


def delete_review_and_update_marker(review_id):
    review = db.session.get(Review, review_id)
    if not review:
        return

    marker = review.marker
    db.session.delete(review)

    remaining_reviews = [r for r in marker.reviews if r.id != review.id]
    marker.total_reviews = len(remaining_reviews)

    if remaining_reviews:
        marker.average_review = round(sum(r.stars for r in remaining_reviews) / len(remaining_reviews), 2)
    else:
        # Delete the marker and its associated data
        Event.query.filter_by(marker_id=marker.id).delete()
        UserMarker.query.filter_by(marker_id=marker.id).delete()
        db.session.delete(marker)


def delete_marker_and_contents(marker_id):
    Review.query.filter_by(marker_id=marker_id).delete()
    Event.query.filter_by(marker_id=marker_id).delete()
    UserMarker.query.filter_by(marker_id=marker_id).delete()
    marker = db.session.get(Marker, marker_id)
    if marker:
        db.session.delete(marker)

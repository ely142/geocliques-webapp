from flask import jsonify, redirect, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import (
    Clique,
    Notification,
    User,
)
from app.notif import notif_bp


@notif_bp.route("/get_notifications")
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


@notif_bp.route("/delete_notification/<int:id>", methods=["POST"])
@login_required
def delete_notification(id):
    note = db.session.get(Notification, id)

    report_types = {"bot like report", "overwhelming bias report", "hurtful language report"}
    if note and note.type in report_types:
        if current_user.email == "adminadmin@gmail.com":  # Only master can delete report-type notifications
            db.session.delete(note)
            db.session.commit()
            return redirect(url_for("master.master_reports"))
        else:
            return redirect(url_for("main.home"))

    # Normal user-related notifications (ban, kick, invites, etc.)
    if note and (note.user_id == current_user.id or (note.clique_id and db.session.get(Clique, note.clique_id).admin_id == current_user.id)):
        db.session.delete(note)
        db.session.commit()
        return jsonify({"success": True})

    return jsonify({"success": False, "message": "Notification not found or unauthorized"}), 404

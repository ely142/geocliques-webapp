from datetime import date

from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.event import event_bp
from app.extensions import db
from app.models import (
    Clique,
    Event,
    Marker,
)


@event_bp.before_app_request
def delete_expired_events():
    # Allowed endpoints represent views where users interact with map data
    if request.endpoint in ["map.maptest", "event.add_event", "map.get_user_markers", "event.edit_event"]:
        today = date.today()

        expired_events = Event.query.filter(Event.date < today).all()

        for event in expired_events:
            db.session.delete(event)

        db.session.commit()


@event_bp.route("/add/<int:marker_id>/<int:clique_id>", methods=["GET", "POST"])
@login_required
def add_event(marker_id, clique_id):
    if request.method == "POST":
        date = request.form.get("date")
        time = request.form.get("time")
        description = request.form.get("description")

        if not date or not time or not description:
            return redirect(url_for("event.add_event", marker_id=marker_id, clique_id=clique_id))

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
        return redirect(url_for("map.maptest"))

    return render_template(
        "event/add_event.html",
        marker_id=marker_id,
        clique_id=clique_id,
        logged_in=True,
        name=current_user.name,
    )


@event_bp.route("/edit-events/<int:marker_id>/<int:clique_id>", methods=["GET"])
@login_required
def edit_event(marker_id, clique_id):
    all_user_events = Event.query.filter(Event.marker_id == marker_id, Event.user_id == current_user.id, Event.clique_id == clique_id).all()
    marker = Marker.query.filter(Marker.id == marker_id).first()
    clique = Clique.query.filter(Clique.id == clique_id).first()
    return render_template(
        "event/edit_events.html",
        events=all_user_events,
        clique=clique,
        marker=marker,
        logged_in=True,
        name=current_user.name,
    )


@event_bp.route("/update/<int:event_id>", methods=["POST"])
@login_required
def update_event(event_id):
    event = db.get_or_404(Event, event_id)
    action = request.form.get("action")
    next = request.form.get("next")

    if request.method == "POST":
        if action == "delete":
            db.session.delete(event)
            db.session.commit()

            if current_user.email == "adminadmin@gmail.com":
                return redirect(url_for("master.edit_clique", clique_id=event.clique_id))

            if next == "main.settings":
                return redirect(url_for(next))
            else:
                return redirect(url_for("event.edit_event", marker_id=event.marker_id, clique_id=event.clique_id))

        else:
            event_date = request.form["date"]
            event_time = request.form["time"]
            event_description = request.form["description"]

            event.date = event_date
            event.time = event_time
            event.description = event_description

            db.session.commit()

            if next == "main.settings":
                return redirect(url_for(next))
            else:
                return redirect(url_for("event.edit_event", marker_id=event.marker_id, clique_id=event.clique_id))

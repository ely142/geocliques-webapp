from flask import Blueprint

event_bp = Blueprint("event", __name__, url_prefix="/event")

from app.event import routes

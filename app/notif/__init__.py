from flask import Blueprint

notif_bp = Blueprint("notif", __name__, url_prefix="/api/notif")

from app.notif import routes

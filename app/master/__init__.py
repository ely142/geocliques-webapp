from flask import Blueprint

master_bp = Blueprint("master", __name__, url_prefix="/master")

from app.master import routes

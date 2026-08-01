from flask import Blueprint

clique_bp = Blueprint("clique", __name__, url_prefix="/clique")

from app.clique import routes

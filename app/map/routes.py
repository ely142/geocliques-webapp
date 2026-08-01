from flask import render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.map import map_bp

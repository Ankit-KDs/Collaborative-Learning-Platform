from flask import Blueprint

learning_bp = Blueprint("learning", __name__, url_prefix="/learning-path")

from app.learning import routes  # noqa: E402, F401

"""
Doubts blueprint package initialization.
"""

from flask import Blueprint

doubts_bp = Blueprint("doubts", __name__, url_prefix="/doubts")

from app.doubts import routes  # noqa: E402, F401

"""
Teacher Moderation Review Queue Blueprint
=========================================
Provides faculty oversight tools for flagged chat messages, report resolution,
and student strike auditing.
"""

from flask import Blueprint

moderation_bp = Blueprint("moderation", __name__, url_prefix="/moderation")

from app.moderation import routes  # noqa: F401, E402

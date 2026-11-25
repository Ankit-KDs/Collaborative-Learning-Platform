"""
Admin Blueprint Initialization
==============================
Provides administrative portal, database browser, analytics, and audit log.
"""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

from app.admin import routes  # noqa: E402, F401

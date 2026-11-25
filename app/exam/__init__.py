"""
Exam Revision Mode Blueprint
============================
Delivers high-yield syllabus revision, semantic FAQ clusters, and verified answers.
"""

from flask import Blueprint

exam_bp = Blueprint("exam", __name__, url_prefix="/exam-mode")

from app.exam import routes  # noqa: F401, E402

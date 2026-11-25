"""
Exam Mode Controller Routes
===========================
Endpoints for curated high-yield exam revision, topic analysis,
semantic question clusters, and verified answers.
"""

from flask import render_template, request
from flask_login import login_required

from app.config import SUBJECTS
from app.exam import exam_bp
from app.services.exam_service import build_exam_revision_package


@exam_bp.route("", methods=["GET"])
@exam_bp.route("/", methods=["GET"])
@login_required
def index():
    """
    Exam Mode dashboard view.
    Accepts subject and time_range ('30', '90', 'all') query params.
    """
    subject = request.args.get("subject", "").strip()
    if not subject or subject not in SUBJECTS:
        subject = SUBJECTS[0]

    time_range = request.args.get("time_range", "30").strip().lower()
    if time_range not in {"30", "90", "all"}:
        time_range = "30"

    revision_data = build_exam_revision_package(subject=subject, time_range=time_range)

    return render_template(
        "exam/index.html",
        title=f"Exam Mode: {subject}",
        subjects=SUBJECTS,
        selected_subject=subject,
        selected_time_range=time_range,
        data=revision_data,
    )

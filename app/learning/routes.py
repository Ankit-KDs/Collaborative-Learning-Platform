"""
Routes for Personalized Learning Path & Weak-Topic Analytics.
============================================================
Provides student performance diagnostics computed locally without AI,
and delivers personalized study plans generated via Gemini.
"""

from datetime import timedelta
import json

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.learning import learning_bp
from app.models import LearningPath, utc_now
from app.services.ai_service import AIServiceError, check_and_record_usage, generate_learning_path
from app.services.learning_stats import compute_student_learning_stats


@learning_bp.route("", methods=["GET"])
@learning_bp.route("/", methods=["GET"])
@login_required
def dashboard():
    """
    Render weak-topic diagnostic dashboard and AI study plan.
    Students see their prioritized subjects, quiz chart, and cached or new learning plan.
    Teachers receive a faculty advisory notice.
    """
    if current_user.is_teacher:
        return render_template(
            "learning/dashboard.html",
            is_teacher=True,
            title="Personalized Learning Path",
        )

    # 1. Compute local learning diagnostics without AI
    stats = compute_student_learning_stats(current_user.id)
    ranked_subjects = stats["ranked_subjects"]
    chart_data = stats["chart_data"]
    current_hash = stats["profile_hash"]

    # 2. Fetch existing cached learning plan if any
    learning_path = LearningPath.query.filter_by(user_id=current_user.id).first()
    plan_data = None
    has_hash_mismatch = False
    can_regenerate = True
    cooldown_minutes_left = 0

    if learning_path:
        try:
            plan_data = json.loads(learning_path.content_json)
        except (ValueError, TypeError):
            plan_data = None

        # Compare profile hashes to detect skill or stat changes
        has_hash_mismatch = (learning_path.profile_hash != current_hash)

        # Enforce 1-hour cooldown between plan regenerations
        elapsed = utc_now() - learning_path.generated_at
        if elapsed < timedelta(hours=1):
            can_regenerate = False
            cooldown_minutes_left = max(1, int((timedelta(hours=1) - elapsed).total_seconds() // 60))

    return render_template(
        "learning/dashboard.html",
        is_teacher=False,
        ranked_subjects=ranked_subjects,
        top_subjects=ranked_subjects[:3],
        chart_data=chart_data,
        learning_path=learning_path,
        plan_data=plan_data,
        has_hash_mismatch=has_hash_mismatch,
        can_regenerate=can_regenerate,
        cooldown_minutes_left=cooldown_minutes_left,
        title="My Personalized Learning Path",
    )


@learning_bp.route("/generate", methods=["POST"])
@login_required
def generate_plan():
    """
    Generate or regenerate a personalized AI study plan based on weak-topic analytics.
    Enforces daily quota and 1-hour regeneration cooldown.
    """
    if current_user.is_teacher:
        flash("Faculty accounts cannot generate student study roadmaps.", "warning")
        return redirect(url_for("learning.dashboard"))

    # 1. Check 1-hour cooldown
    existing_path = LearningPath.query.filter_by(user_id=current_user.id).first()
    if existing_path:
        elapsed = utc_now() - existing_path.generated_at
        if elapsed < timedelta(hours=1):
            mins = max(1, int((timedelta(hours=1) - elapsed).total_seconds() // 60))
            flash(f"Study plan can only be regenerated once per hour. Please wait {mins} minute(s).", "warning")
            return redirect(url_for("learning.dashboard"))

    # 2. Compute diagnostics
    stats = compute_student_learning_stats(current_user.id)
    top_3 = stats["ranked_subjects"][:3]
    current_hash = stats["profile_hash"]

    # 3. Anonymized profile summary (NO student names or emails!)
    profile_summary = {
        "priority_subjects": [
            {
                "subject": s["subject"],
                "level": s["level"],
                "open_doubts": s["open_doubts"],
                "total_doubts": s["total_doubts"],
                "quiz_average_pct": s["quiz_avg"],
                "priority_score": s["priority_score"],
            }
            for s in top_3
        ]
    }

    try:
        # 4. Check and record AI usage limit
        check_and_record_usage(current_user.id, "path")

        # 5. Generate plan via AI service
        plan = generate_learning_path(profile_summary)

        # 6. Upsert LearningPath record
        if existing_path:
            existing_path.content_json = json.dumps(plan)
            existing_path.profile_hash = current_hash
            existing_path.generated_at = utc_now()
        else:
            new_path = LearningPath(
                user_id=current_user.id,
                content_json=json.dumps(plan),
                profile_hash=current_hash,
                generated_at=utc_now(),
            )
            db.session.add(new_path)

        db.session.commit()
        flash("Your personalized AI learning path has been generated!", "success")

    except AIServiceError as exc:
        flash(str(exc), "danger")
    except Exception as exc:
        flash(f"Failed to generate study plan: {exc}", "danger")

    return redirect(url_for("learning.dashboard"))

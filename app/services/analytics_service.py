"""
Analytics Service
=================
Computes local analytics, reporting metrics, and Chart.js datasets for the Admin Panel.
Fully deterministic calculations with zero external AI dependencies and safe handling
of completely empty databases.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import func, desc
from app import db
from app.models import (
    AIUsage,
    Answer,
    BuddyRequest,
    ChatRoom,
    Doubt,
    Message,
    MessageReport,
    QuizAttempt,
    Reputation,
    User,
)
from app.config import SUBJECTS, PROGRAMS


def get_admin_dashboard_metrics() -> dict[str, Any]:
    """Compile high-level KPIs and Chart.js datasets for the main admin dashboard."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # User counts
    total_students = User.query.filter_by(role="student").count()
    total_teachers = User.query.filter_by(role="teacher").count()
    total_admins = User.query.filter_by(role="admin").count()

    # New registrations
    reg_today = User.query.filter(User.created_at >= midnight).count()
    reg_7d = User.query.filter(User.created_at >= seven_days_ago).count()
    reg_30d = User.query.filter(User.created_at >= thirty_days_ago).count()

    # Doubts & Solutions
    total_doubts = Doubt.query.count()
    open_doubts = Doubt.query.filter_by(solved_answer_id=None).count()
    solved_doubts = Doubt.query.filter(Doubt.solved_answer_id.isnot(None)).count()
    total_answers = Answer.query.count()

    # Active chats & study groups
    active_chats = ChatRoom.query.filter_by(type="private", is_active=True).count()
    active_groups = ChatRoom.query.filter_by(type="group", is_active=True).count()

    # Moderation & safety
    pending_moderation = Message.query.filter_by(review_status="pending").count()
    total_reports = MessageReport.query.count()

    # AI daily usage breakdown
    ai_hint_today = AIUsage.query.filter(AIUsage.feature == "hint", AIUsage.created_at >= midnight).count()
    ai_quiz_today = AIUsage.query.filter(AIUsage.feature == "quiz", AIUsage.created_at >= midnight).count()
    ai_path_today = AIUsage.query.filter(AIUsage.feature == "learning_path", AIUsage.created_at >= midnight).count()
    ai_total_today = ai_hint_today + ai_quiz_today + ai_path_today

    # 30-Day Registrations Timeline for Chart.js
    reg_dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    reg_counts = []
    for d_str in reg_dates:
        start_d = datetime.strptime(d_str, "%Y-%m-%d")
        end_d = start_d + timedelta(days=1)
        c = User.query.filter(User.created_at >= start_d, User.created_at < end_d).count()
        reg_counts.append(c)

    # Roles Distribution for Chart.js
    role_labels = ["Students", "Faculty", "Administrators"]
    role_counts = [total_students, total_teachers, total_admins]

    return {
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_admins": total_admins,
        "reg_today": reg_today,
        "reg_7d": reg_7d,
        "reg_30d": reg_30d,
        "total_doubts": total_doubts,
        "open_doubts": open_doubts,
        "solved_doubts": solved_doubts,
        "total_answers": total_answers,
        "active_chats": active_chats,
        "active_groups": active_groups,
        "pending_moderation": pending_moderation,
        "total_reports": total_reports,
        "ai_hint_today": ai_hint_today,
        "ai_quiz_today": ai_quiz_today,
        "ai_path_today": ai_path_today,
        "ai_total_today": ai_total_today,
        "reg_dates": reg_dates,
        "reg_counts": reg_counts,
        "role_labels": role_labels,
        "role_counts": role_counts,
    }


def get_admin_analytics(date_range: str = "30") -> dict[str, Any]:
    """Calculate platform-wide academic and community analytics based on a time horizon."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    cutoff = None
    if date_range == "7":
        cutoff = now - timedelta(days=7)
    elif date_range == "30":
        cutoff = now - timedelta(days=30)
    elif date_range == "90":
        cutoff = now - timedelta(days=90)

    # 1. Users by Program
    prog_rows = (
        db.session.query(User.program, func.count(User.id))
        .filter(User.role == "student", User.program.isnot(None))
        .group_by(User.program)
        .all()
    )
    users_by_program = {p or "Unspecified": cnt for p, cnt in prog_rows}

    # 2. Users by Specialization
    spec_rows = (
        db.session.query(User.specialization, func.count(User.id))
        .filter(User.role == "student", User.specialization.isnot(None))
        .group_by(User.specialization)
        .order_by(desc(func.count(User.id)))
        .limit(10)
        .all()
    )
    users_by_specialization = {s or "Unspecified": cnt for s, cnt in spec_rows}

    # 3. Users by Academic Year
    year_rows = (
        db.session.query(User.year, func.count(User.id))
        .filter(User.role == "student", User.year.isnot(None))
        .group_by(User.year)
        .all()
    )
    users_by_year = {f"Year {y}": cnt for y, cnt in sorted(year_rows, key=lambda x: x[0] or 0)}

    # 4. Users by College
    college_rows = (
        db.session.query(User.college_name, func.count(User.id))
        .filter(User.college_name.isnot(None))
        .group_by(User.college_name)
        .order_by(desc(func.count(User.id)))
        .limit(8)
        .all()
    )
    users_by_college = {c or "Unknown": cnt for c, cnt in college_rows}

    # 5. Doubts per Subject (Open vs Solved)
    doubt_query = Doubt.query
    if cutoff:
        doubt_query = doubt_query.filter(Doubt.created_at >= cutoff)

    doubts_by_subject = []
    for s in SUBJECTS:
        open_c = doubt_query.filter(Doubt.subject == s, Doubt.solved_answer_id.is_(None)).count()
        solved_c = doubt_query.filter(Doubt.subject == s, Doubt.solved_answer_id.isnot(None)).count()
        doubts_by_subject.append({"subject": s, "open": open_c, "solved": solved_c, "total": open_c + solved_c})

    # 6. Average Time to First Answer
    answered_doubts = Doubt.query.filter(Doubt.answers.any()).all()
    time_diffs_minutes = []
    for d in answered_doubts:
        first_ans = Answer.query.filter_by(doubt_id=d.id).order_by(Answer.created_at.asc()).first()
        if first_ans and first_ans.created_at and d.created_at:
            delta = (first_ans.created_at - d.created_at).total_seconds() / 60.0
            if delta >= 0:
                time_diffs_minutes.append(delta)

    if time_diffs_minutes:
        avg_mins = sum(time_diffs_minutes) / len(time_diffs_minutes)
        if avg_mins >= 60:
            avg_time_str = f"{avg_mins / 60.0:.1f} hours"
        else:
            avg_time_str = f"{int(avg_mins)} mins"
    else:
        avg_time_str = "N/A (No answered doubts)"

    # 7. Top Helpers (Leaderboard)
    top_helpers_rows = (
        db.session.query(User, func.coalesce(func.sum(Reputation.score), 0).label("tot_score"))
        .join(Reputation, Reputation.user_id == User.id)
        .filter(User.role == "student")
        .group_by(User.id)
        .having(func.sum(Reputation.score) > 0)
        .order_by(desc("tot_score"))
        .limit(8)
        .all()
    )
    top_helpers = [{"name": u.name, "score": s, "college": u.college_name or "N/A"} for u, s in top_helpers_rows]

    # 8. Buddy Request Funnel
    req_query = BuddyRequest.query
    if cutoff:
        req_query = req_query.filter(BuddyRequest.created_at >= cutoff)
    total_reqs = req_query.count()
    pending_reqs = req_query.filter_by(status="pending").count()
    accepted_reqs = req_query.filter_by(status="accepted").count()
    rejected_reqs = req_query.filter_by(status="rejected").count()

    # 9. Groups per Subject
    group_rows = (
        db.session.query(ChatRoom.subject, func.count(ChatRoom.id))
        .filter(ChatRoom.type == "group", ChatRoom.subject.isnot(None))
        .group_by(ChatRoom.subject)
        .all()
    )
    groups_by_subject = {sub: count for sub, count in group_rows}

    # 10. Quiz Attempts & Average Score per Subject
    quiz_query = QuizAttempt.query
    if cutoff:
        quiz_query = quiz_query.filter(QuizAttempt.created_at >= cutoff)

    quiz_stats = []
    for s in SUBJECTS:
        attempts = quiz_query.filter_by(subject=s).all()
        if attempts:
            avg_sc = sum((a.score / max(1, a.num_questions)) * 100 for a in attempts) / len(attempts)
            quiz_stats.append({"subject": s, "attempts": len(attempts), "avg_score": round(avg_sc, 1)})
        else:
            quiz_stats.append({"subject": s, "attempts": 0, "avg_score": 0.0})

    # 11. AI Usage per Feature over the Selected Period
    ai_query = AIUsage.query
    if cutoff:
        ai_query = ai_query.filter(AIUsage.created_at >= cutoff)
    ai_hint_count = ai_query.filter_by(feature="hint").count()
    ai_quiz_count = ai_query.filter_by(feature="quiz").count()
    ai_path_count = ai_query.filter_by(feature="learning_path").count()

    # 12. Moderation Trends (Weekly buckets)
    mod_weeks = []
    mod_counts = []
    for w in range(3, -1, -1):
        w_start = now - timedelta(days=(w + 1) * 7)
        w_end = now - timedelta(days=w * 7)
        flagged_c = Message.query.filter(
            Message.review_status != "none",
            Message.created_at >= w_start,
            Message.created_at < w_end,
        ).count()
        mod_weeks.append(f"{w_start.strftime('%b %d')} - {w_end.strftime('%b %d')}")
        mod_counts.append(flagged_c)

    return {
        "date_range": date_range,
        "users_by_program": users_by_program,
        "users_by_specialization": users_by_specialization,
        "users_by_year": users_by_year,
        "users_by_college": users_by_college,
        "doubts_by_subject": doubts_by_subject,
        "avg_time_to_first_answer": avg_time_str,
        "top_helpers": top_helpers,
        "request_funnel": {
            "total": total_reqs,
            "accepted": accepted_reqs,
            "pending": pending_reqs,
            "rejected": rejected_reqs,
        },
        "groups_by_subject": groups_by_subject,
        "quiz_stats": quiz_stats,
        "ai_usage": {
            "hint": ai_hint_count,
            "quiz": ai_quiz_count,
            "learning_path": ai_path_count,
            "total": ai_hint_count + ai_quiz_count + ai_path_count,
        },
        "moderation_weeks": mod_weeks,
        "moderation_counts": mod_counts,
    }

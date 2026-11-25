"""
Main blueprint routes including home landing, student/teacher dashboard,
leaderboard, and system health status.
"""

from datetime import datetime, timedelta, timezone
import json
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.config import SUBJECTS
from app.models import (
    User,
    BuddyRequest,
    GroupInvite,
    ChatMember,
    ChatRoom,
    Doubt,
    Answer,
    Reputation,
    QuizAttempt,
    Message,
    Skill,
    TeacherSubject,
)
from app.services.exam_service import compute_most_asked_topics

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Platform home / landing page."""
    if current_user.is_authenticated:
        if getattr(current_user, "is_admin", False):
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("main.dashboard"))
    return render_template("main/index.html", title="AI-Powered Collaborative Learning Platform")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    """Dynamic user dashboard tailored for students and faculty."""
    if getattr(current_user, "is_admin", False):
        return redirect(url_for("admin.dashboard"))

    if current_user.is_student:
        pending_requests_count = BuddyRequest.query.filter_by(
            receiver_id=current_user.id, status="pending"
        ).count()
        pending_group_invites_count = GroupInvite.query.filter_by(
            invited_user_id=current_user.id, status="pending"
        ).count()
        my_open_doubts_count = Doubt.query.filter_by(
            user_id=current_user.id, solved_answer_id=None
        ).count()
        my_reputations = (
            Reputation.query.filter_by(user_id=current_user.id)
            .order_by(Reputation.score.desc())
            .all()
        )

        total_reputation = sum(r.score for r in my_reputations)
        if total_reputation >= 60:
            overall_badge = "Guru"
        elif total_reputation >= 30:
            overall_badge = "Expert"
        elif total_reputation >= 10:
            overall_badge = "Helper"
        else:
            overall_badge = "Learner"

        active_groups_count = (
            ChatMember.query.filter_by(user_id=current_user.id)
            .join(ChatRoom)
            .filter(ChatRoom.type == "group", ChatRoom.is_active.is_(True))
            .count()
        )
        active_chats_count = (
            ChatMember.query.filter_by(user_id=current_user.id)
            .join(ChatRoom)
            .filter(ChatRoom.type == "private", ChatRoom.is_active.is_(True))
            .count()
        )
        quizzes_taken_count = (
            QuizAttempt.query.filter_by(user_id=current_user.id)
            .filter(QuizAttempt.submitted_at.isnot(None))
            .count()
        )

        # Weak subjects with study buddy & quiz shortcuts
        weak_skills = Skill.query.filter_by(user_id=current_user.id, level="Weak").all()

        # Doubts I can answer: open doubts where student has Strong skill
        strong_skills = Skill.query.filter_by(user_id=current_user.id, level="Strong").all()
        strong_subjects = [s.subject for s in strong_skills]
        doubts_can_answer = []
        if strong_subjects:
            doubts_can_answer = (
                Doubt.query.filter(
                    Doubt.subject.in_(strong_subjects),
                    Doubt.solved_answer_id.is_(None),
                    Doubt.user_id != current_user.id,
                )
                .order_by(Doubt.created_at.desc())
                .limit(5)
                .all()
            )

        # My open doubts list
        my_open_doubts = (
            Doubt.query.filter_by(user_id=current_user.id, solved_answer_id=None)
            .order_by(Doubt.created_at.desc())
            .limit(5)
            .all()
        )

        stats = {
            "pending_requests_count": pending_requests_count,
            "pending_group_invites_count": pending_group_invites_count,
            "my_open_doubts_count": my_open_doubts_count,
            "my_open_doubts": my_open_doubts,
            "my_reputations": my_reputations,
            "total_reputation": total_reputation,
            "overall_badge": overall_badge,
            "active_groups_count": active_groups_count,
            "active_chats_count": active_chats_count,
            "quizzes_taken_count": quizzes_taken_count,
            "weak_skills": weak_skills,
            "doubts_can_answer": doubts_can_answer,
        }
    else:
        # Teacher dashboard metrics
        teacher_subjects = current_user.teaching_subject_list
        pending_moderation_count = Message.query.filter_by(review_status="pending").count()

        if teacher_subjects:
            unanswered_doubts = (
                Doubt.query.filter(
                    Doubt.subject.in_(teacher_subjects),
                    ~Doubt.answers.any(),
                )
                .order_by(Doubt.created_at.desc())
                .limit(6)
                .all()
            )
            unanswered_doubts_count = (
                Doubt.query.filter(
                    Doubt.subject.in_(teacher_subjects),
                    ~Doubt.answers.any(),
                ).count()
            )

            # "Needs human help" doubts
            needs_human_doubts = (
                Doubt.query.filter(
                    Doubt.subject.in_(teacher_subjects),
                    Doubt.needs_human.is_(True),
                    Doubt.solved_answer_id.is_(None),
                )
                .order_by(Doubt.created_at.desc())
                .limit(6)
                .all()
            )

            # Answers awaiting verification in teacher's subjects
            answers_awaiting_verification = (
                Answer.query.join(Doubt, Answer.doubt_id == Doubt.id)
                .filter(
                    Doubt.subject.in_(teacher_subjects),
                    Answer.is_verified.is_(False),
                )
                .order_by(Answer.created_at.desc())
                .limit(6)
                .all()
            )

            # Chart.js data: open vs solved per subject
            chart_labels = list(teacher_subjects)
            chart_open = []
            chart_solved = []
            for s in chart_labels:
                c_open = Doubt.query.filter_by(subject=s, solved_answer_id=None).count()
                c_solved = Doubt.query.filter(
                    Doubt.subject == s, Doubt.solved_answer_id.isnot(None)
                ).count()
                chart_open.append(c_open)
                chart_solved.append(c_solved)

            # Top student contributors in teacher's subjects
            top_contributors = (
                db.session.query(
                    User,
                    func.sum(Reputation.score).label("total_score"),
                )
                .join(Reputation, Reputation.user_id == User.id)
                .filter(User.role == "student", Reputation.subject.in_(teacher_subjects))
                .group_by(User.id)
                .having(func.sum(Reputation.score) > 0)
                .order_by(func.sum(Reputation.score).desc())
                .limit(5)
                .all()
            )

            # Class insight: most asked topics this month in teacher's subjects
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
            recent_doubts = (
                Doubt.query.filter(
                    Doubt.subject.in_(teacher_subjects),
                    Doubt.created_at >= cutoff,
                ).all()
            )
            class_topics = (
                compute_most_asked_topics(recent_doubts, top_k=6) if recent_doubts else []
            )
        else:
            unanswered_doubts = []
            unanswered_doubts_count = 0
            needs_human_doubts = []
            answers_awaiting_verification = []
            chart_labels = []
            chart_open = []
            chart_solved = []
            top_contributors = []
            class_topics = []

        verified_answers_count = Answer.query.filter_by(verified_by=current_user.id).count()
        total_doubts_count = Doubt.query.count()
        total_students_count = User.query.filter_by(role="student").count()

        stats = {
            "pending_moderation_count": pending_moderation_count,
            "unanswered_doubts_count": unanswered_doubts_count,
            "unanswered_doubts": unanswered_doubts,
            "needs_human_doubts": needs_human_doubts,
            "answers_awaiting_verification": answers_awaiting_verification,
            "verified_answers_count": verified_answers_count,
            "total_doubts_count": total_doubts_count,
            "total_students_count": total_students_count,
            "teacher_subjects": teacher_subjects,
            "chart_labels": json.dumps(chart_labels),
            "chart_open": json.dumps(chart_open),
            "chart_solved": json.dumps(chart_solved),
            "top_contributors": top_contributors,
            "class_topics": class_topics,
        }

    return render_template(
        "main/dashboard.html",
        title="Dashboard",
        user=current_user,
        stats=stats,
    )


@main_bp.route("/leaderboard")
def leaderboard():
    """
    Public / Authenticated Leaderboard showcasing top peer helpers.
    Calculates overall standings and subject-specific reputation leaders.
    Respects doubt anonymity (answers are always attributed to the peer helper).
    """
    selected_subject = request.args.get("subject", "").strip()

    # Overall top helpers across all subjects
    overall_rows = (
        db.session.query(
            User,
            func.coalesce(func.sum(Reputation.score), 0).label("total_score"),
            func.count(Reputation.id).label("subjects_count"),
        )
        .join(Reputation, Reputation.user_id == User.id)
        .filter(User.role == "student")
        .group_by(User.id)
        .having(func.sum(Reputation.score) > 0)
        .order_by(func.sum(Reputation.score).desc())
        .limit(20)
        .all()
    )

    overall_leaders = []
    for user, total_score, subjects_count in overall_rows:
        if total_score >= 60:
            badge = "Guru"
        elif total_score >= 30:
            badge = "Expert"
        elif total_score >= 10:
            badge = "Helper"
        else:
            badge = "Learner"

        overall_leaders.append({
            "user": user,
            "total_score": total_score,
            "subjects_count": subjects_count,
            "badge": badge,
        })

    # Subject-filtered leaders
    subject_leaders = []
    if selected_subject and selected_subject in SUBJECTS:
        reps = (
            Reputation.query.filter_by(subject=selected_subject)
            .join(User)
            .filter(User.role == "student", Reputation.score > 0)
            .order_by(Reputation.score.desc())
            .limit(15)
            .all()
        )
        for r in reps:
            subject_leaders.append({
                "user": r.user,
                "score": r.score,
                "badge": r.badge or "Helper",
                "subject": r.subject,
            })

    # Top champion per subject overview
    subject_champions = {}
    for subj in SUBJECTS:
        top_rep = (
            Reputation.query.filter_by(subject=subj)
            .join(User)
            .filter(User.role == "student", Reputation.score > 0)
            .order_by(Reputation.score.desc())
            .first()
        )
        if top_rep:
            subject_champions[subj] = {
                "user_name": top_rep.user.name,
                "score": top_rep.score,
                "badge": top_rep.badge or "Helper",
            }

    return render_template(
        "main/leaderboard.html",
        title="Reputation Leaderboard",
        overall_leaders=overall_leaders,
        subject_leaders=subject_leaders,
        selected_subject=selected_subject,
        subjects=SUBJECTS,
        subject_champions=subject_champions,
    )


@main_bp.route("/groups")
@login_required
def groups():
    """Redirect to the Stage 4 study groups hub."""
    return redirect(url_for("groups.index"))


@main_bp.route("/doubts")
@login_required
def doubts():
    """Redirect to the Stage 5 Doubt Resolution module."""
    return redirect(url_for("doubts.index"))


@main_bp.route("/quiz")
@login_required
def quiz():
    """Forward to Stage 6 AI-generated practice quizzes."""
    return redirect(url_for("quiz.index"))


@main_bp.route("/exam-mode-legacy")
@login_required
def exam_mode():
    """Forward to Stage 7 Exam Mode revision guide."""
    return redirect(url_for("exam.index"))


@main_bp.route("/learning-path")
@login_required
def learning_path():
    """Forward to Stage 6 Adaptive personalized roadmap."""
    return redirect(url_for("learning.dashboard"))


@main_bp.route("/answers/<int:answer_id>/image", methods=["GET"])
@login_required
def top_level_answer_image(answer_id: int):
    """Protected route to view answer images at /answers/<id>/image."""
    from app.doubts.routes import answer_image
    return answer_image(answer_id)

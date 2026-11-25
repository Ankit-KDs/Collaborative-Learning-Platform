"""
Routes for AI Quiz Generator & Assessment Module.
=================================================
Handles quiz generation via Gemini, private attempt delivery (with answers withheld),
server-side grading, score breakdown, and historical tracking.
"""

import json

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.config import SUBJECTS
from app.models import QuizAttempt, utc_now
from app.quiz import quiz_bp
from app.quiz.forms import QuizGeneratorForm
from app.services.ai_service import AIServiceError, check_and_record_usage, generate_quiz
from app.services.moderation import ModerationBlockedError, validate_content_profanity


@quiz_bp.route("", methods=["GET", "POST"])
@quiz_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    """
    Quiz generator configuration page.
    Students configure topic and difficulty to generate an AI assessment.
    Teachers receive a friendly faculty advisory notice.
    """
    if current_user.is_teacher:
        return render_template(
            "quiz/index.html",
            is_teacher=True,
            title="AI Practice Quiz Generator",
        )

    form = QuizGeneratorForm()

    # Pre-select subject if passed via query parameter (e.g. from Learning Path shortcut)
    preselected_sub = request.args.get("subject", "").strip()
    if request.method == "GET" and preselected_sub in SUBJECTS:
        form.subject.data = preselected_sub

    if form.validate_on_submit():
        subject = str(form.subject.data or "")
        topic = (form.topic.data or "").strip()
        difficulty = str(form.difficulty.data or "Medium")
        num_questions = int(form.num_questions.data) if form.num_questions.data is not None else 5

        # Profanity check for quiz topic
        try:
            validate_content_profanity(topic, source="doubt", user_id=current_user.id)
        except ModerationBlockedError as e:
            flash(e.message, "danger")
            return render_template(
                "quiz/index.html",
                form=form,
                subjects=SUBJECTS,
                title="AI Practice Quiz Generator",
            )

        try:
            # 1. Enforce per-user daily AI usage limit
            check_and_record_usage(current_user.id, "quiz")

            # 2. Call Gemini API via centralized AI service
            questions = generate_quiz(
                subject=subject,
                topic=topic,
                difficulty=difficulty,
                num_questions=num_questions,
            )

            # 3. Create persistent QuizAttempt record
            attempt = QuizAttempt(
                user_id=current_user.id,
                subject=subject,
                topic=topic,
                difficulty=difficulty,
                num_questions=len(questions),
                questions_json=json.dumps(questions),
                answers_json=None,
                score=None,
                created_at=utc_now(),
                submitted_at=None,
            )
            db.session.add(attempt)
            db.session.commit()

            flash("Your AI practice quiz has been generated! Answer each question and submit when ready.", "success")
            return redirect(url_for("quiz.take_quiz", quiz_id=attempt.id))

        except AIServiceError as exc:
            flash(str(exc), "danger")
        except Exception as exc:
            flash(f"An unexpected error occurred while preparing your quiz: {exc}", "danger")

    return render_template(
        "quiz/index.html",
        form=form,
        is_teacher=False,
        title="AI Practice Quiz Generator",
    )


@quiz_bp.route("/<int:quiz_id>", methods=["GET"])
@login_required
def take_quiz(quiz_id: int):
    """
    Display quiz questions for a student attempt.
    CRITICAL SECURITY INVARIANT:
    Withholds correct_index and explanation from template context before submission.
    """
    attempt = db.session.get(QuizAttempt, quiz_id)
    if not attempt:
        abort(404)

    # Ownership verification
    if attempt.user_id != current_user.id:
        abort(403)

    # If already submitted, redirect to result breakdown
    if attempt.is_submitted:
        return redirect(url_for("quiz.quiz_result", quiz_id=attempt.id))

    try:
        raw_questions = json.loads(attempt.questions_json)
    except (ValueError, TypeError):
        flash("Corrupted quiz payload. Please generate a new quiz.", "danger")
        return redirect(url_for("quiz.index"))

    # Strip correct answers and explanations for client presentation
    sanitized_questions = []
    for idx, q in enumerate(raw_questions):
        sanitized_questions.append({
            "index": idx,
            "question": q["question"],
            "options": q["options"],
        })

    return render_template(
        "quiz/take.html",
        attempt=attempt,
        questions=sanitized_questions,
        title=f"Quiz: {attempt.topic}",
    )


@quiz_bp.route("/<int:quiz_id>/submit", methods=["POST"])
@login_required
def submit_quiz(quiz_id: int):
    """
    Grade student quiz attempt on the server.
    Compares selected options with ground truth, calculates score, and saves timestamp.
    """
    attempt = db.session.get(QuizAttempt, quiz_id)
    if not attempt:
        abort(404)

    if attempt.user_id != current_user.id:
        abort(403)

    # Idempotency / single-submission guarantee
    if attempt.is_submitted:
        flash("This quiz has already been submitted and graded.", "info")
        return redirect(url_for("quiz.quiz_result", quiz_id=attempt.id))

    try:
        stored_questions = json.loads(attempt.questions_json)
    except (ValueError, TypeError):
        flash("Corrupted quiz questions.", "danger")
        return redirect(url_for("quiz.index"))

    # Collect student answers from form
    user_answers: dict[str, int | None] = {}
    correct_count = 0

    for idx, q in enumerate(stored_questions):
        field_name = f"q_{idx}"
        val = request.form.get(field_name)
        if val is not None and val.isdigit():
            chosen_opt = int(val)
            user_answers[str(idx)] = chosen_opt
            if chosen_opt == q["correct_index"]:
                correct_count += 1
        else:
            user_answers[str(idx)] = None  # Skipped / Unanswered

    attempt.answers_json = json.dumps(user_answers)
    attempt.score = correct_count
    attempt.submitted_at = utc_now()
    db.session.commit()

    flash(f"Quiz completed! You scored {correct_count} out of {attempt.num_questions}.", "success")
    return redirect(url_for("quiz.quiz_result", quiz_id=attempt.id))


@quiz_bp.route("/<int:quiz_id>/result", methods=["GET"])
@login_required
def quiz_result(quiz_id: int):
    """
    Display comprehensive grading result, highlighted correct answers, and explanations.
    """
    attempt = db.session.get(QuizAttempt, quiz_id)
    if not attempt:
        abort(404)

    if attempt.user_id != current_user.id:
        abort(403)

    if not attempt.is_submitted:
        return redirect(url_for("quiz.take_quiz", quiz_id=attempt.id))

    try:
        stored_questions = json.loads(attempt.questions_json)
        user_answers = json.loads(attempt.answers_json or "{}")
    except (ValueError, TypeError):
        flash("Error loading quiz results.", "danger")
        return redirect(url_for("quiz.index"))

    # Combine questions with user answers and feedback
    review_items = []
    for idx, q in enumerate(stored_questions):
        chosen = user_answers.get(str(idx))
        correct = q["correct_index"]
        is_correct = (chosen == correct)
        review_items.append({
            "index": idx + 1,
            "question": q["question"],
            "options": q["options"],
            "chosen_index": chosen,
            "correct_index": correct,
            "is_correct": is_correct,
            "explanation": q.get("explanation", ""),
        })

    pct = round((attempt.score / attempt.num_questions) * 100) if attempt.num_questions > 0 else 0

    return render_template(
        "quiz/result.html",
        attempt=attempt,
        review_items=review_items,
        percentage=pct,
        title=f"Results: {attempt.topic}",
    )


@quiz_bp.route("/history", methods=["GET"])
@login_required
def history():
    """
    Display complete list of student's past quiz attempts.
    """
    if current_user.is_teacher:
        return render_template(
            "quiz/history.html",
            is_teacher=True,
            attempts=[],
            title="Quiz History",
        )

    attempts = (
        QuizAttempt.query.filter_by(user_id=current_user.id)
        .order_by(QuizAttempt.created_at.desc())
        .all()
    )

    return render_template(
        "quiz/history.html",
        is_teacher=False,
        attempts=attempts,
        title="My Quiz Attempts & History",
    )


@quiz_bp.route("/<int:quiz_id>/delete", methods=["POST"])
@login_required
def delete_quiz(quiz_id: int):
    """
    Delete a quiz attempt (unsubmitted or submitted). Owner only.
    """
    attempt = db.session.get(QuizAttempt, quiz_id)
    if not attempt:
        abort(404)

    if attempt.user_id != current_user.id:
        abort(403)

    db.session.delete(attempt)
    db.session.commit()
    flash("Quiz attempt removed.", "info")
    return redirect(url_for("quiz.history"))

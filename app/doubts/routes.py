"""
Routes for Doubts Community Forum, Q&A, and Search.
"""

from pathlib import Path
from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from app import db
from app.config import SUBJECTS
from app.doubts import doubts_bp
from app.doubts.forms import AnswerForm, AskDoubtForm
from app.models import Answer, AnswerVote, Doubt, Skill
from app.utils import teacher_required
from app.services.ai_service import AIServiceError
from app.services.doubts_service import (
    DoubtServiceError,
    accept_answer,
    add_answer,
    create_doubt,
    delete_doubt,
    get_or_create_ai_hint,
    reopen_doubt,
    submit_hint_feedback,
    unverify_answer,
    upvote_answer,
    verify_answer,
)
from app.services.ranking import rank_answers
from app.services.search import filter_doubts_by_kmp
from app.services.similarity import find_similar_doubts


@doubts_bp.route("", methods=["GET"])
@doubts_bp.route("/", methods=["GET"])
@login_required
def index():
    """
    Main doubts catalog view with subject filtering, status filtering,
    KMP case-insensitive search, sorting, and 'Doubts for you' recommendations.
    """
    subject = request.args.get("subject", "").strip()
    status = request.args.get("status", "all").strip().lower()
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort", "newest").strip().lower()
    page = request.args.get("page", 1, type=int)
    per_page = 10

    # Base query
    query = Doubt.query
    if subject and subject in SUBJECTS:
        query = query.filter(Doubt.subject == subject)

    if status == "open":
        query = query.filter(Doubt.status == "open")
    elif status == "solved":
        query = query.filter(Doubt.status == "solved")

    # Fetch candidate doubts
    candidates = query.order_by(Doubt.created_at.desc()).all()

    # 1. Apply KMP substring search over title and body
    if q:
        filtered_doubts = filter_doubts_by_kmp(candidates, q)
    else:
        filtered_doubts = candidates

    # 2. Apply Sorting
    if sort_by == "most_answers":
        filtered_doubts.sort(key=lambda d: d.answers.count(), reverse=True)
    elif sort_by == "unanswered":
        filtered_doubts.sort(key=lambda d: (d.answers.count() > 0, d.created_at), reverse=False)
    else:  # newest default
        filtered_doubts.sort(key=lambda d: d.created_at, reverse=True)

    # 3. Pagination calculation
    total_count = len(filtered_doubts)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    paginated_doubts = filtered_doubts[start_idx : start_idx + per_page]

    # Pre-compute verified badge map for performance
    has_verified_map: dict[int, bool] = {}
    for d in paginated_doubts:
        has_verified_map[d.id] = d.answers.filter_by(is_verified=True).first() is not None

    # 4. 'Doubts for you' recommended questions (open, unanswered questions in subjects where user is Strong or Average)
    doubts_for_you: list[Doubt] = []
    if current_user.is_student:
        proficient_skills = (
            Skill.query.filter_by(user_id=current_user.id)
            .filter(Skill.level.in_(["Strong", "Average"]))
            .all()
        )
        pref_subjects = [s.subject for s in proficient_skills]
        if pref_subjects:
            recs = (
                Doubt.query.filter(
                    Doubt.subject.in_(pref_subjects),
                    Doubt.status == "open",
                    Doubt.user_id != current_user.id,
                )
                .order_by(Doubt.created_at.desc())
                .limit(20)
                .all()
            )
            # Filter strictly unanswered doubts, prioritizing doubts escalated to human peer help
            unanswered_recs = [d for d in recs if d.answers.count() == 0]
            unanswered_recs.sort(key=lambda d: (not d.needs_human, -d.created_at.timestamp()))
            doubts_for_you = unanswered_recs[:5]

    return render_template(
        "doubts/index.html",
        title="Doubt Resolution Community",
        doubts=paginated_doubts,
        has_verified_map=has_verified_map,
        doubts_for_you=doubts_for_you,
        all_subjects=SUBJECTS,
        current_subject=subject,
        current_status=status,
        current_query=q,
        current_sort=sort_by,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
    )


@doubts_bp.route("/ask", methods=["GET", "POST"])
@login_required
def ask():
    """
    Form to post a new student doubt with live similar question preview.
    Faculty members cannot post doubts.
    """
    if current_user.is_teacher:
        flash("Faculty accounts can answer and verify questions, but cannot post student doubts.", "info")
        return redirect(url_for("doubts.index"))

    form = AskDoubtForm()
    if form.validate_on_submit():
        try:
            doubt = create_doubt(
                user_id=current_user.id,
                subject=form.subject.data or "",
                title=form.title.data or "",
                body=form.body.data or "",
                image_file=form.image.data,
                is_anonymous=bool(form.is_anonymous.data),
            )
            flash("Your doubt has been posted to the community!", "success")
            return redirect(url_for("doubts.detail", doubt_id=doubt.id))
        except DoubtServiceError as e:
            flash(str(e), "danger")

    return render_template(
        "doubts/ask.html",
        title="Ask a Doubt",
        form=form,
        subjects=SUBJECTS,
    )


@doubts_bp.route("/<int:doubt_id>", methods=["GET"])
@login_required
def detail(doubt_id: int):
    """
    Doubt detail view showing full content, ranked answers (via Merge Sort),
    and answer submission form.
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        abort(404)

    # Hand-implemented Merge Sort ranking
    all_answers = doubt.answers.all()
    ranked_answers = rank_answers(all_answers, accepted_answer_id=doubt.solved_answer_id)

    # Compute which answers current_user has upvoted
    user_votes = set()
    if all_answers:
        voted_ids = (
            db.session.query(AnswerVote.answer_id)
            .filter(
                AnswerVote.user_id == current_user.id,
                AnswerVote.answer_id.in_([a.id for a in all_answers]),
            )
            .all()
        )
        user_votes = {row[0] for row in voted_ids}

    form = AnswerForm()

    return render_template(
        "doubts/detail.html",
        title=f"Doubt: {doubt.title}",
        doubt=doubt,
        answers=ranked_answers,
        user_votes=user_votes,
        form=form,
    )


@doubts_bp.route("/<int:doubt_id>/answers", methods=["POST"])
@login_required
def post_answer(doubt_id: int):
    """
    Submit an answer to an existing doubt.
    """
    form = AnswerForm()
    if form.validate_on_submit():
        try:
            add_answer(
                doubt_id=doubt_id,
                user_id=current_user.id,
                body=form.body.data or "",
                image_file=form.image.data,
            )
            flash("Your answer has been submitted successfully!", "success")
        except DoubtServiceError as e:
            flash(str(e), "danger")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field.capitalize()}: {error}", "danger")

    return redirect(url_for("doubts.detail", doubt_id=doubt_id))


@doubts_bp.route("/answers/<int:answer_id>/upvote", methods=["POST"])
@login_required
def upvote(answer_id: int):
    """
    AJAX endpoint for toggling answer upvotes.
    Returns JSON { "upvotes": int, "voted": bool }
    """
    try:
        result = upvote_answer(answer_id=answer_id, user_id=current_user.id)
        return jsonify(result), 200
    except DoubtServiceError as e:
        return jsonify({"error": str(e)}), 400


@doubts_bp.route("/answers/<int:answer_id>/verify", methods=["POST"])
@login_required
@teacher_required
def verify(answer_id: int):
    """
    Teacher verifies an answer as correct (+15 reputation points).
    """
    try:
        ans = verify_answer(answer_id=answer_id, teacher_id=current_user.id)
        flash("Answer marked as verified by faculty!", "success")
        return redirect(url_for("doubts.detail", doubt_id=ans.doubt_id))
    except DoubtServiceError as e:
        flash(str(e), "danger")
        return redirect(request.referrer or url_for("doubts.index"))


@doubts_bp.route("/answers/<int:answer_id>/unverify", methods=["POST"])
@login_required
@teacher_required
def unverify(answer_id: int):
    """
    Teacher removes verification status from an answer (-15 reputation points).
    """
    try:
        ans = unverify_answer(answer_id=answer_id, teacher_id=current_user.id)
        flash("Faculty verification removed.", "info")
        return redirect(url_for("doubts.detail", doubt_id=ans.doubt_id))
    except DoubtServiceError as e:
        flash(str(e), "danger")
        return redirect(request.referrer or url_for("doubts.index"))


@doubts_bp.route("/<int:doubt_id>/answers/<int:answer_id>/accept", methods=["POST"])
@login_required
def accept(doubt_id: int, answer_id: int):
    """
    Asker accepts an answer as the accepted solution (+10 reputation points).
    """
    try:
        accept_answer(doubt_id=doubt_id, asker_id=current_user.id, answer_id=answer_id)
        flash("Answer accepted as the solution to your doubt!", "success")
    except DoubtServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for("doubts.detail", doubt_id=doubt_id))


@doubts_bp.route("/<int:doubt_id>/reopen", methods=["POST"])
@login_required
def reopen(doubt_id: int):
    """
    Asker reopens a solved doubt.
    """
    try:
        reopen_doubt(doubt_id=doubt_id, asker_id=current_user.id)
        flash("Doubt reopened. Community members can continue answering.", "info")
    except DoubtServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for("doubts.detail", doubt_id=doubt_id))


@doubts_bp.route("/<int:doubt_id>/delete", methods=["POST"])
@login_required
def delete(doubt_id: int):
    """
    Delete a doubt. Permitted for asker (if 0 answers) or teachers (moderation override).
    """
    try:
        delete_doubt(doubt_id=doubt_id, user_id=current_user.id)
        flash("Doubt has been deleted successfully.", "success")
        return redirect(url_for("doubts.index"))
    except DoubtServiceError as e:
        flash(str(e), "danger")
        return redirect(url_for("doubts.detail", doubt_id=doubt_id))


@doubts_bp.route("/<int:doubt_id>/image", methods=["GET"])
@login_required
def doubt_image(doubt_id: int):
    """
    Serve attached doubt diagram/screenshot through authenticated route.
    Does not expose public static directories.
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt or not doubt.image_path:
        abort(404)

    upload_folder = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    image_file = upload_folder / doubt.image_path
    if not image_file.is_file():
        abort(404)

    # Use directory and filename for send_from_directory
    rel_path = Path(doubt.image_path)
    return send_from_directory(upload_folder / rel_path.parent, rel_path.name)


@doubts_bp.route("/answers/<int:answer_id>/image", methods=["GET"])
@login_required
def answer_image(answer_id: int):
    """
    Serve attached answer diagram/screenshot through authenticated route.
    """
    answer = db.session.get(Answer, answer_id)
    if not answer or not answer.image_path:
        abort(404)

    upload_folder = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    image_file = upload_folder / answer.image_path
    if not image_file.is_file():
        abort(404)

    rel_path = Path(answer.image_path)
    return send_from_directory(upload_folder / rel_path.parent, rel_path.name)


@doubts_bp.route("/similar", methods=["GET"])
@login_required
def similar():
    """
    Live duplicate check endpoint using TF-IDF + Cosine Similarity.
    Queried via debounced AJAX while student types title and body in /doubts/ask.
    """
    subject = request.args.get("subject", "").strip()
    title = request.args.get("title", "").strip()
    body = request.args.get("body", "").strip()

    if not subject or not title:
        return jsonify({"similar": []})

    results = find_similar_doubts(subject=subject, title=title, body=body, limit=5, threshold=0.35)

    data = [
        {
            "id": d.id,
            "title": d.title,
            "score": round(score, 3),
            "status": d.status,
            "answers_count": d.answers.count(),
        }
        for d, score in results
    ]
    return jsonify({"similar": data})


@doubts_bp.route("/<int:doubt_id>/ai-hint", methods=["POST"])
@login_required
def get_ai_hint(doubt_id: int):
    """
    Fetch or generate an instant AI pedagogical hint for a doubt.
    Cached hints are returned immediately without contacting Gemini.
    Regeneration is restricted to the doubt owner (max 2 regenerations).
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        return jsonify({"success": False, "error": "Doubt not found."}), 404

    data = request.get_json(silent=True) or {}
    regenerate = bool(data.get("regenerate") or request.form.get("regenerate"))

    try:
        hint, was_generated = get_or_create_ai_hint(
            doubt_id=doubt.id,
            user_id=current_user.id,
            regenerate=regenerate,
        )
        is_owner = (doubt.user_id == current_user.id)
        can_regenerate = is_owner and (hint.regenerated_count < 2)

        return jsonify({
            "success": True,
            "hint_text": hint.hint_text,
            "was_generated": was_generated,
            "regenerated_count": hint.regenerated_count,
            "can_regenerate": can_regenerate,
            "helpful": hint.helpful,
            "is_owner": is_owner,
            "needs_human": doubt.needs_human,
        })
    except (DoubtServiceError, AIServiceError) as err:
        return jsonify({"success": False, "error": str(err)}), 400


@doubts_bp.route("/<int:doubt_id>/ai-hint/feedback", methods=["POST"])
@login_required
def hint_feedback(doubt_id: int):
    """
    Record student feedback on an AI hint.
    Submitting helpful=False triggers escalation to classmates (needs_human=True).
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        return jsonify({"success": False, "error": "Doubt not found."}), 404

    data = request.get_json(silent=True) or {}
    helpful_raw = data.get("helpful")
    if helpful_raw is None:
        helpful = (request.form.get("helpful") == "true")
    else:
        helpful = bool(helpful_raw)

    try:
        hint = submit_hint_feedback(doubt_id=doubt.id, user_id=current_user.id, helpful=helpful)
        msg = (
            "Thank you! Glad the AI hint helped you make progress."
            if helpful
            else "Your question has been escalated to classmates and prioritized for peer help!"
        )
        return jsonify({
            "success": True,
            "helpful": hint.helpful,
            "needs_human": doubt.needs_human,
            "message": msg,
        })
    except (DoubtServiceError, AIServiceError) as err:
        return jsonify({"success": False, "error": str(err)}), 400

"""
Doubt Resolution & Peer Q&A Service
====================================
Contains core business logic for:
- Doubt creation with daily rate limiting, subject validation, and exact duplicate prevention
- Answer submission, answer limits per student, and notifications on solved doubts
- Answer upvoting with real-time score synchronization and toggle semantics
- Teacher answer verification and unverification
- Asker answer acceptance and doubt reopening
- Subject-specific reputation scoring and automatic badge awards
- Secure doubt deletion with cascading disk asset cleanup
- Anonymity protection guarantees
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import current_app

from app import db
from app.config import SUBJECTS
from app.models import AIHint, Answer, AnswerVote, Doubt, Reputation, User, utc_now
from app.services.ai_service import check_and_record_usage, generate_hint
from app.services.moderation import ModerationBlockedError, validate_content_profanity
from app.services.similarity import check_exact_duplicate
from app.services.uploads import InvalidImageError, save_image


class DoubtServiceError(Exception):
    """Raised when an operation violates doubt or answer business constraints."""


def apply_reputation_delta(user_id: int, subject: str, delta: int) -> Reputation:
    """
    Adjust a user's subject-specific reputation score and update their earned badge.

    Reputation Delta Rules:
    - +2 points per upvote received on an answer
    - +10 points when an answer is accepted as the solution by the asker
    - +15 points when an answer is verified by faculty

    Badge Award Tiers:
    - >= 60 points: 'Guru'
    - >= 30 points: 'Expert'
    - >= 10 points: 'Helper'
    - < 10 points: None
    """
    rep = Reputation.query.filter_by(user_id=user_id, subject=subject).first()
    if not rep:
        rep = Reputation(user_id=user_id, subject=subject, score=0, badge=None)
        db.session.add(rep)

    rep.score = max(0, rep.score + delta)

    if rep.score >= 60:
        rep.badge = "Guru"
    elif rep.score >= 30:
        rep.badge = "Expert"
    elif rep.score >= 10:
        rep.badge = "Helper"
    else:
        rep.badge = None

    return rep


def create_doubt(
    user_id: int,
    subject: str,
    title: str,
    body: str,
    image_file: Any = None,
    is_anonymous: bool = False,
) -> Doubt:
    """
    Create a new student doubt in the community forum.

    Constraints:
    - Only students can post doubts (teachers verify and answer).
    - Title must be 5-150 characters.
    - Body must be 10-3000 characters.
    - Subject must belong to SUBJECTS.
    - Rate limit: at most 10 doubts per user per 24 hours.
    - Exact duplicates from the same user are rejected using hash comparison.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise DoubtServiceError("User account not found.")

    if not user.is_student:
        raise DoubtServiceError("Faculty accounts cannot post doubts.")

    clean_subject = (subject or "").strip()
    if clean_subject not in SUBJECTS:
        raise DoubtServiceError(f"Subject '{clean_subject}' is not in the recognized subjects list.")

    clean_title = (title or "").strip()
    if len(clean_title) < 5 or len(clean_title) > 150:
        raise DoubtServiceError("Title must be between 5 and 150 characters.")

    clean_body = (body or "").strip()
    if len(clean_body) < 10 or len(clean_body) > 3000:
        raise DoubtServiceError("Doubt description must be between 10 and 3000 characters.")

    # Profanity moderation check: reject offensive language and record blocked log
    try:
        validate_content_profanity(f"{clean_title} {clean_body}", source="doubt", user_id=user_id)
    except ModerationBlockedError as e:
        raise DoubtServiceError(e.message) from e

    # 1. Exact Duplicate Hash Prevention
    if check_exact_duplicate(user_id, clean_title, clean_body):
        raise DoubtServiceError("You have already posted an identical doubt.")

    # 2. Daily Rate Limiting (max 10 doubts per 24 hours)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    recent_count = Doubt.query.filter(Doubt.user_id == user_id, Doubt.created_at >= cutoff).count()
    if recent_count >= 10:
        raise DoubtServiceError("Daily doubt limit reached (maximum 10 doubts per 24 hours).")

    # 3. Optional Image Attachment
    image_rel_path = None
    if image_file and getattr(image_file, "filename", None) and image_file.filename.strip():
        try:
            image_rel_path = save_image(image_file, subfolder="doubts")
        except InvalidImageError as e:
            raise DoubtServiceError(str(e)) from e

    doubt = Doubt(
        user_id=user_id,
        subject=clean_subject,
        title=clean_title,
        body=clean_body,
        image_path=image_rel_path,
        is_anonymous=bool(is_anonymous),
        status="open",
        solved_answer_id=None,
        created_at=utc_now(),
    )
    db.session.add(doubt)
    db.session.commit()
    return doubt


def add_answer(
    doubt_id: int,
    user_id: int,
    body: str,
    image_file: Any = None,
) -> Answer:
    """
    Post an answer to a doubt. Both students and teachers can answer.

    Constraints:
    - Body 5-3000 characters.
    - A student may post at most 3 answers per doubt (teachers have no limit).
    - Solved doubts still accept answers.
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        raise DoubtServiceError("Doubt not found.")

    user = db.session.get(User, user_id)
    if not user:
        raise DoubtServiceError("User account not found.")

    clean_body = (body or "").strip()
    if len(clean_body) < 5 or len(clean_body) > 3000:
        raise DoubtServiceError("Answer body must be between 5 and 3000 characters.")

    # Profanity moderation check: reject offensive language and record blocked log
    try:
        validate_content_profanity(clean_body, source="answer", user_id=user_id)
    except ModerationBlockedError as e:
        raise DoubtServiceError(e.message) from e

    # Student answer limit
    if user.is_student:
        existing_answers = Answer.query.filter_by(doubt_id=doubt_id, user_id=user_id).count()
        if existing_answers >= 3:
            raise DoubtServiceError("You have reached the maximum limit of 3 answers for this doubt.")

    # Optional image attachment
    image_rel_path = None
    if image_file and getattr(image_file, "filename", None) and image_file.filename.strip():
        try:
            image_rel_path = save_image(image_file, subfolder="answers")
        except InvalidImageError as e:
            raise DoubtServiceError(str(e)) from e

    answer = Answer(
        doubt_id=doubt_id,
        user_id=user_id,
        body=clean_body,
        image_path=image_rel_path,
        upvotes=0,
        is_verified=False,
        verified_by=None,
        verified_at=None,
        created_at=utc_now(),
    )
    db.session.add(answer)
    db.session.commit()
    return answer


def upvote_answer(answer_id: int, user_id: int) -> dict[str, Any]:
    """
    Toggle upvote for an answer. Synchronizes vote count and reputation.

    Constraints:
    - Cannot upvote your own answer.
    - One vote per user (toggles on/off).
    """
    answer = db.session.get(Answer, answer_id)
    if not answer:
        raise DoubtServiceError("Answer not found.")

    if answer.user_id == user_id:
        raise DoubtServiceError("You cannot upvote your own answer.")

    existing_vote = AnswerVote.query.filter_by(answer_id=answer_id, user_id=user_id).first()
    if existing_vote:
        # Toggle off
        db.session.delete(existing_vote)
        answer.upvotes = max(0, answer.upvotes - 1)
        apply_reputation_delta(answer.user_id, answer.doubt.subject, -2)
        voted = False
    else:
        # Toggle on
        vote = AnswerVote(answer_id=answer_id, user_id=user_id, created_at=utc_now())
        db.session.add(vote)
        answer.upvotes += 1
        apply_reputation_delta(answer.user_id, answer.doubt.subject, +2)
        voted = True

    db.session.commit()
    return {"upvotes": answer.upvotes, "voted": voted}


def verify_answer(answer_id: int, teacher_id: int) -> Answer:
    """
    Mark an answer as verified by faculty. Awards +15 reputation points.
    """
    teacher = db.session.get(User, teacher_id)
    if not teacher or not teacher.is_teacher:
        raise DoubtServiceError("Only faculty members can verify answers.")

    answer = db.session.get(Answer, answer_id)
    if not answer:
        raise DoubtServiceError("Answer not found.")

    if not answer.is_verified:
        answer.is_verified = True
        answer.verified_by = teacher_id
        answer.verified_at = utc_now()
        apply_reputation_delta(answer.user_id, answer.doubt.subject, +15)
        db.session.commit()

    return answer


def unverify_answer(answer_id: int, teacher_id: int) -> Answer:
    """
    Remove verification status from an answer. Reverses +15 reputation points.
    """
    teacher = db.session.get(User, teacher_id)
    if not teacher or not teacher.is_teacher:
        raise DoubtServiceError("Only faculty members can unverify answers.")

    answer = db.session.get(Answer, answer_id)
    if not answer:
        raise DoubtServiceError("Answer not found.")

    if answer.is_verified:
        answer.is_verified = False
        answer.verified_by = None
        answer.verified_at = None
        apply_reputation_delta(answer.user_id, answer.doubt.subject, -15)
        db.session.commit()

    return answer


def accept_answer(doubt_id: int, asker_id: int, answer_id: int) -> Doubt:
    """
    Mark an answer as accepted solution by the doubt's asker.
    Sets status to 'solved' and awards +10 reputation points to the answerer.
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        raise DoubtServiceError("Doubt not found.")

    if doubt.user_id != asker_id:
        raise DoubtServiceError("Only the author of this doubt can accept an answer.")

    answer = db.session.get(Answer, answer_id)
    if not answer or answer.doubt_id != doubt_id:
        raise DoubtServiceError("The selected answer does not belong to this doubt.")

    # If another answer was previously accepted, reverse its 10 points
    if doubt.solved_answer_id and doubt.solved_answer_id != answer_id:
        prev_ans = db.session.get(Answer, doubt.solved_answer_id)
        if prev_ans:
            apply_reputation_delta(prev_ans.user_id, doubt.subject, -10)

    # Award points to new accepted answer
    if doubt.solved_answer_id != answer_id:
        apply_reputation_delta(answer.user_id, doubt.subject, +10)

    doubt.solved_answer_id = answer_id
    doubt.status = "solved"
    db.session.commit()
    return doubt


def reopen_doubt(doubt_id: int, asker_id: int) -> Doubt:
    """
    Reopen a previously solved doubt, clearing accepted answer and reversing points.
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        raise DoubtServiceError("Doubt not found.")

    if doubt.user_id != asker_id:
        raise DoubtServiceError("Only the author of this doubt can reopen it.")

    if doubt.solved_answer_id:
        prev_ans = db.session.get(Answer, doubt.solved_answer_id)
        if prev_ans:
            apply_reputation_delta(prev_ans.user_id, doubt.subject, -10)
        doubt.solved_answer_id = None

    doubt.status = "open"
    db.session.commit()
    return doubt


def delete_doubt(doubt_id: int, user_id: int) -> bool:
    """
    Delete a doubt and cascade clean associated disk images.

    Permissions:
    - Doubt owner may delete ONLY if the doubt has 0 answers.
    - Teachers may delete any doubt (moderation override).
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        raise DoubtServiceError("Doubt not found.")

    user = db.session.get(User, user_id)
    if not user:
        raise DoubtServiceError("User account not found.")

    if not user.is_teacher and doubt.user_id != user_id:
        raise DoubtServiceError("You do not have permission to delete this doubt.")

    if not user.is_teacher and doubt.answers.count() > 0:
        raise DoubtServiceError("Cannot delete a doubt that has received answers.")

    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])

    # Remove doubt image
    if doubt.image_path:
        img_path = upload_folder / doubt.image_path
        if img_path.is_file():
            try:
                img_path.unlink()
            except OSError:
                pass

    # Remove answers images
    for ans in doubt.answers.all():
        if ans.image_path:
            ans_img_path = upload_folder / ans.image_path
            if ans_img_path.is_file():
                try:
                    ans_img_path.unlink()
                except OSError:
                    pass

    db.session.delete(doubt)
    db.session.commit()
    return True


def get_or_create_ai_hint(doubt_id: int, user_id: int, regenerate: bool = False) -> tuple[AIHint, bool]:
    """
    Retrieve cached AI hint for a doubt or generate a new hint via Gemini API.
    Enforces owner-only regeneration and 2-regeneration lifetime maximum per doubt.

    :param doubt_id: ID of the doubt.
    :param user_id: ID of the requesting user.
    :param regenerate: Whether to force a regeneration (owner only).
    :return: Tuple of (AIHint, was_generated_boolean).
    :raises DoubtServiceError: On permission or limit violations.
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        raise DoubtServiceError("Doubt not found.")

    is_owner = (doubt.user_id == user_id)
    if not is_owner:
        raise DoubtServiceError("Only the author of this doubt can request or regenerate an AI hint.")

    # 1. Existing cached hint check
    existing_hint = AIHint.query.filter_by(doubt_id=doubt_id).first()

    if existing_hint and not regenerate:
        return existing_hint, False

    if existing_hint and regenerate:
        if existing_hint.regenerated_count >= 2:
            raise DoubtServiceError("Maximum 2 hint regenerations reached for this doubt.")

    # 2. Check and record daily AI usage for the requesting user
    check_and_record_usage(user_id, "hint")

    # 3. Read image bytes safely if doubt has an attached image
    image_bytes = None
    mime_type = None
    if doubt.image_path:
        upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
        img_file = upload_folder / doubt.image_path
        if img_file.is_file():
            try:
                image_bytes = img_file.read_bytes()
                ext = img_file.suffix.lower()
                mime_type = "image/png" if ext == ".png" else "image/jpeg"
            except OSError:
                image_bytes = None
                mime_type = None

    # 4. Generate hint via AI service
    hint_text = generate_hint(
        subject=doubt.subject,
        title=doubt.title,
        body=doubt.body,
        image_bytes=image_bytes,
        mime=mime_type,
    )

    if existing_hint:
        existing_hint.hint_text = hint_text
        existing_hint.regenerated_count += 1
        db.session.commit()
        return existing_hint, True
    else:
        new_hint = AIHint(
            doubt_id=doubt_id,
            hint_text=hint_text,
            regenerated_count=0,
            created_at=utc_now(),
        )
        db.session.add(new_hint)
        db.session.commit()
        return new_hint, True


def submit_hint_feedback(doubt_id: int, user_id: int, helpful: bool) -> AIHint:
    """
    Record user feedback on an AI hint.
    If helpful=False ("Still stuck, ask classmates"), sets Doubt.needs_human=True.

    :param doubt_id: ID of the doubt.
    :param user_id: ID of the user submitting feedback.
    :param helpful: True (helped) or False (still stuck).
    :return: Updated AIHint.
    :raises DoubtServiceError: If doubt or hint does not exist.
    """
    doubt = db.session.get(Doubt, doubt_id)
    if not doubt:
        raise DoubtServiceError("Doubt not found.")

    hint = AIHint.query.filter_by(doubt_id=doubt_id).first()
    if not hint:
        raise DoubtServiceError("No AI hint found for this doubt.")

    hint.helpful = helpful
    if not helpful:
        doubt.needs_human = True

    db.session.commit()
    return hint

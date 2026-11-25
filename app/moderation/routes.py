"""
Faculty Moderation Review Queue Routes
======================================
Provides administrative endpoints for teachers to audit auto-flagged chat messages,
evaluate student harassment/abuse reports, dismiss false positives, or confirm
violations and issue moderation strikes.
"""

from collections import Counter
from typing import Any

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Message, utc_now
from app.moderation import moderation_bp
from app.services.moderation import contains_profanity


def teacher_required():
    """Ensure current authenticated user is faculty."""
    if not current_user.is_authenticated or not current_user.is_teacher:
        abort(403)


@moderation_bp.route("", methods=["GET"])
@moderation_bp.route("/", methods=["GET"])
@login_required
def index():
    """
    Teacher review queue displaying all pending flagged messages.
    Supports filtering by 'all', 'auto-flagged', and 'user-reported'.
    Paginated at 10 items per page with surrounding chat context.
    """
    teacher_required()

    filter_type = request.args.get("filter", "all").strip().lower()
    page = request.args.get("page", 1, type=int)
    per_page = 10

    # Base query: messages awaiting teacher resolution
    base_query = Message.query.filter_by(review_status="pending")

    if filter_type == "auto":
        base_query = base_query.filter(Message.flag_reason.like("auto%"))
    elif filter_type == "user":
        base_query = base_query.filter(Message.reports.any())

    base_query = base_query.order_by(Message.created_at.desc())

    total_count = base_query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    messages = base_query.offset((page - 1) * per_page).limit(per_page).all()

    # Build detailed metadata and context envelopes
    items: list[dict[str, Any]] = []
    for msg in messages:
        # Context: up to 3 messages before and 3 after in the same room
        context_before = (
            Message.query.filter(
                Message.room_id == msg.room_id,
                Message.id < msg.id,
            )
            .order_by(Message.id.desc())
            .limit(3)
            .all()
        )[::-1]

        context_after = (
            Message.query.filter(
                Message.room_id == msg.room_id,
                Message.id > msg.id,
            )
            .order_by(Message.id.asc())
            .limit(3)
            .all()
        )

        # Aggregate report reasons
        reports = msg.reports.all()
        reason_counts = Counter(r.reason for r in reports)
        notes = [r.note for r in reports if r.note]

        sender = msg.sender
        sender_strikes = sender.moderation_strikes if sender else 0
        is_repeat_offender = sender_strikes >= 3

        items.append({
            "message": msg,
            "sender": sender,
            "sender_strikes": sender_strikes,
            "is_repeat_offender": is_repeat_offender,
            "original_text": msg.original_text or msg.text,
            "masked_text": msg.text,
            "report_count": len(reports),
            "reason_counts": dict(reason_counts),
            "report_notes": notes,
            "context_before": context_before,
            "context_after": context_after,
        })

    return render_template(
        "moderation/index.html",
        title="Moderation Review Queue",
        items=items,
        filter_type=filter_type,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
    )


@moderation_bp.route("/<int:message_id>/dismiss", methods=["POST"])
@login_required
def dismiss(message_id: int):
    """
    Dismiss moderation flag on a message.
    If the message was reported by users and does NOT contain profanity,
    restores its original text to 'text'. If it contained auto-detected profanity,
    the text remains masked.
    """
    teacher_required()

    msg = Message.query.filter_by(id=message_id).first_or_404()

    is_auto = bool(msg.flag_reason and msg.flag_reason.startswith("auto"))
    raw = msg.original_text or msg.text
    has_profanity = contains_profanity(raw)

    if not is_auto and not has_profanity:
        # Innocent message falsely reported: restore original text
        if msg.original_text:
            msg.text = msg.original_text

    msg.review_status = "dismissed"
    msg.reviewed_by = current_user.id
    msg.reviewed_at = utc_now()
    db.session.commit()

    flash("Message report has been dismissed.", "info")
    return redirect(url_for("moderation.index"))


@moderation_bp.route("/<int:message_id>/confirm", methods=["POST"])
@login_required
def confirm(message_id: int):
    """
    Confirm violation on a message.
    Keeps the message masked, records review metadata, and increments
    the sender's moderation strikes count.
    """
    teacher_required()

    msg = Message.query.filter_by(id=message_id).first_or_404()

    msg.review_status = "confirmed"
    msg.reviewed_by = current_user.id
    msg.reviewed_at = utc_now()

    if msg.sender:
        msg.sender.moderation_strikes = (msg.sender.moderation_strikes or 0) + 1

    db.session.commit()

    sender_name = msg.sender.name if msg.sender else "Student"
    flash(
        f"Violation confirmed. Moderation strike recorded for {sender_name}.",
        "warning",
    )
    return redirect(url_for("moderation.index"))

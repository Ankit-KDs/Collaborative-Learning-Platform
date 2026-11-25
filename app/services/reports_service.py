"""
Message Reporting Service
=========================
Handles business logic for user-initiated chat message reporting:
- Permission checks (room membership, cannot report self, cannot report system messages)
- Uniqueness constraint (one report per user per message)
- Rate limiting (max 10 reports per user per day)
- Moderation escalation: sets review_status='pending'
- Auto-hiding threshold: auto-masks message if reported by >= 3 distinct users
- Complete anonymity: reporter identity is never disclosed to room members
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app import db
from app.models import ChatMember, Message, MessageReport, utc_now

VALID_REPORT_REASONS = {"abusive", "harassment", "spam", "inappropriate", "other"}
MAX_DAILY_REPORTS = 10
AUTO_HIDE_REPORT_THRESHOLD = 3


class ReportValidationError(Exception):
    """Raised when a message report violates platform rules or constraints."""


class ReportPermissionError(Exception):
    """Raised when an unauthenticated or non-member attempts to report a message."""


def report_message(
    room_id: int,
    message_id: int,
    reporter_id: int,
    reason: str,
    note: str = "",
) -> dict[str, Any]:
    """
    Submit a formal moderation report for a chat message.

    Constraints:
    1. Reporter must be an active member of the room (or raise ReportPermissionError -> 403).
    2. Message must exist and belong to the specified room.
    3. Users cannot report their own messages.
    4. System broadcast messages cannot be reported.
    5. Reason must be in VALID_REPORT_REASONS.
    6. Max 10 reports per user in the last 24 hours.
    7. One report per user per message (duplicate rejection).
    8. Threshold: If 3 distinct users report the message, it is auto-masked for all members.
    """
    # 1. Verify room membership
    membership = ChatMember.query.filter_by(room_id=room_id, user_id=reporter_id).first()
    if not membership:
        raise ReportPermissionError("You do not have permission to report messages in this room.")

    # 2. Verify message existence
    msg = db.session.get(Message, message_id)
    if not msg or msg.room_id != room_id:
        raise ReportValidationError("The requested message does not exist in this chat room.")

    # 3. Cannot report own messages
    if msg.sender_id == reporter_id:
        raise ReportValidationError("You cannot report your own message.")

    # 4. Cannot report system notifications
    if msg.is_system:
        raise ReportValidationError("System notifications cannot be reported.")

    # 5. Validate reason
    clean_reason = (reason or "").strip().lower()
    if clean_reason not in VALID_REPORT_REASONS:
        raise ReportValidationError(
            f"Invalid report reason. Choose from: {', '.join(sorted(VALID_REPORT_REASONS))}."
        )

    # 6. Daily report limit (10 per 24 hours)
    day_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    recent_reports_count = (
        MessageReport.query.filter(
            MessageReport.reporter_id == reporter_id,
            MessageReport.created_at >= day_cutoff,
        ).count()
    )
    if recent_reports_count >= MAX_DAILY_REPORTS:
        raise ReportValidationError("Daily report limit reached (maximum 10 reports per day).")

    # 7. Duplicate report prevention
    existing = MessageReport.query.filter_by(message_id=message_id, reporter_id=reporter_id).first()
    if existing:
        raise ReportValidationError("You have already reported this message.")

    # 8. Create and persist report
    clean_note = (note or "").strip()[:200]
    report = MessageReport(
        message_id=message_id,
        reporter_id=reporter_id,
        reason=clean_reason,
        note=clean_note if clean_note else None,
        created_at=utc_now(),
    )
    db.session.add(report)

    # 9. Escalate review status
    if msg.review_status == "none":
        msg.review_status = "pending"
    if not msg.flag_reason:
        msg.flag_reason = f"user: {clean_reason}"

    # 10. Check auto-hide threshold (3 distinct reporters)
    db.session.flush()
    distinct_reporters = (
        db.session.query(MessageReport.reporter_id)
        .filter_by(message_id=message_id)
        .distinct()
        .count()
    )

    is_auto_hidden = False
    if distinct_reporters >= AUTO_HIDE_REPORT_THRESHOLD:
        if not msg.original_text:
            msg.original_text = msg.text
        msg.text = "[message hidden pending review]"
        msg.is_flagged = True
        msg.review_status = "pending"
        is_auto_hidden = True

    db.session.commit()

    return {
        "success": True,
        "message": "Report submitted. Thank you for helping keep the community safe.",
        "is_hidden": is_auto_hidden,
    }

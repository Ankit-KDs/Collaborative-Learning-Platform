"""
Admin Service
=============
Core business logic for the administrative control center:
1. User Management (filtering, sorting, detail compilation, status toggling, strike resetting).
2. Data Browser (metadata introspection, redacted column filtering, privacy-masked chat content, anonymous doubt author tracking).
3. Reports Compilation (Message reports, auto-flagged messages, blocked moderation attempts, repeat offenders, doubt health).
4. Secure CSV Exporting with strict formula injection sanitization.
5. Append-only Admin Audit Logging.
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any, Generator
from sqlalchemy import func, or_, desc, asc
from app import db
from app.models import (
    AdminAuditLog,
    AIHint,
    AIUsage,
    Answer,
    AnswerVote,
    BuddyRequest,
    ChatMember,
    ChatRoom,
    Doubt,
    GroupInvite,
    LearningPath,
    Message,
    MessageReport,
    ModerationLog,
    QuizAttempt,
    Reputation,
    Skill,
    TeacherSubject,
    User,
    utc_now,
)
from app.config import SUBJECTS, PROGRAMS

# Hard-coded blocklist of sensitive substrings that must NEVER be displayed or exported
REDACTED_SUBSTRINGS = ("password", "secret", "token", "key", "hash")

# Canonical dictionary of models for the Data Browser
TABLE_MODEL_MAP: dict[str, Any] = {
    "users": User,
    "skills": Skill,
    "teacher_subjects": TeacherSubject,
    "buddy_requests": BuddyRequest,
    "chat_rooms": ChatRoom,
    "chat_members": ChatMember,
    "messages": Message,
    "message_reports": MessageReport,
    "doubts": Doubt,
    "answers": Answer,
    "answer_votes": AnswerVote,
    "reputations": Reputation,
    "group_invites": GroupInvite,
    "ai_hints": AIHint,
    "ai_usages": AIUsage,
    "quiz_attempts": QuizAttempt,
    "learning_paths": LearningPath,
    "moderation_logs": ModerationLog,
    "admin_audit_logs": AdminAuditLog,
}


def is_column_redacted(col_name: str) -> bool:
    """Check if a column name matches any sensitive credential or secret pattern."""
    col_lower = col_name.lower()
    return any(sub in col_lower for sub in REDACTED_SUBSTRINGS)


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitize CSV field values to prevent CSV formula injection (OWASP).
    Prefixes any value starting with '=', '+', '-', '@', '\t', '\r' with a single quote.
    """
    if value is None:
        return ""
    str_val = str(value)
    if str_val and str_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{str_val}"
    return str_val


def log_admin_action(
    admin_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> AdminAuditLog:
    """Write an append-only entry to the admin audit log."""
    audit = AdminAuditLog(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail[:255] if detail else None,
        ip=ip,
        created_at=utc_now(),
    )
    db.session.add(audit)
    db.session.commit()
    return audit


# ---------------------------------------------------------------------------
# 1. USER MANAGEMENT
# ---------------------------------------------------------------------------


def get_users_paginated(
    search: str | None = None,
    role: str | None = None,
    program: str | None = None,
    specialization: str | None = None,
    year: int | None = None,
    college: str | None = None,
    status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[User], int, int]:
    """
    Query, filter, sort, and paginate platform users.
    Returns (users_list, total_count, total_pages).
    """
    query = User.query

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.name.ilike(s),
                User.email.ilike(s),
                User.enrollment_no.ilike(s),
                User.employee_id.ilike(s),
                User.college_name.ilike(s),
            )
        )

    if role and role in ("student", "teacher", "admin"):
        query = query.filter(User.role == role)

    if program and program in PROGRAMS:
        query = query.filter(User.program == program)

    if specialization:
        query = query.filter(User.specialization.ilike(f"%{specialization.strip()}%"))

    if year and year in (1, 2, 3, 4):
        query = query.filter(User.year == year)

    if college:
        query = query.filter(User.college_name.ilike(f"%{college.strip()}%"))

    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "deactivated":
        query = query.filter_by(is_active=False)

    # Sorting
    allowed_sorts = {
        "created_at": User.created_at,
        "name": User.name,
        "email": User.email,
        "last_login_at": User.last_login_at,
    }
    sort_column = allowed_sorts.get(sort_by, User.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    total_count = query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    users = query.offset((page - 1) * per_page).limit(per_page).all()

    return users, total_count, total_pages


def get_user_detail(user_id: int) -> dict[str, Any] | None:
    """Compile comprehensive profile, metric counts, and recent activity for a user."""
    user = User.query.get(user_id)
    if not user:
        return None

    # Calculate upvotes received on all answers posted by user
    upvotes_received = (
        db.session.query(func.coalesce(func.sum(Answer.upvotes), 0))
        .filter(Answer.user_id == user.id)
        .scalar()
        or 0
    )

    # Calculate reports received on messages sent by user
    reports_received = (
        MessageReport.query.join(Message, MessageReport.message_id == Message.id)
        .filter(Message.sender_id == user.id)
        .count()
    )

    # Groups joined count
    groups_joined = (
        ChatMember.query.join(ChatRoom, ChatMember.room_id == ChatRoom.id)
        .filter(ChatMember.user_id == user.id, ChatRoom.type == "group")
        .count()
    )

    # Recent activity feeds
    recent_doubts = user.doubts.order_by(Doubt.created_at.desc()).limit(5).all()
    recent_answers = user.answers.order_by(Answer.created_at.desc()).limit(5).all()
    recent_reports = (
        MessageReport.query.join(Message, MessageReport.message_id == Message.id)
        .filter(Message.sender_id == user.id)
        .order_by(MessageReport.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "user": user,
        "counts": {
            "doubts": user.doubts.count(),
            "answers": user.answers.count(),
            "upvotes_received": int(upvotes_received),
            "requests_sent": user.sent_buddy_requests.count(),
            "requests_received": user.received_buddy_requests.count(),
            "groups_joined": groups_joined,
            "quiz_attempts": user.quiz_attempts.count(),
            "ai_usages": user.ai_usages.count(),
            "reports_received": reports_received,
        },
        "doubts_count": user.doubts.count(),
        "answers_count": user.answers.count(),
        "upvotes_received": int(upvotes_received),
        "reputations": user.reputations.all(),
        "reputation_by_subject": user.reputations.all(),
        "total_reputation": sum(r.score for r in user.reputations.all()),
        "requests_sent": user.sent_buddy_requests.count(),
        "requests_received": user.received_buddy_requests.count(),
        "groups_joined": groups_joined,
        "quiz_attempts_count": user.quiz_attempts.count(),
        "ai_usages_count": user.ai_usages.count(),
        "reports_received_count": reports_received,
        "moderation_strikes": user.moderation_strikes,
        "skills": user.skills.all() if user.is_student else [],
        "teaching_subjects": [ts.subject for ts in user.teaching_subjects.all()] if user.is_teacher else [],
        "recent_doubts": recent_doubts,
        "recent_answers": recent_answers,
        "recent_reports": recent_reports,
    }


def toggle_user_active(admin_user: Any, target_user_id: int, ip: str) -> tuple[bool, str]:
    """Deactivate or reactivate a user account with safety and audit checks."""
    target_user = User.query.get(target_user_id)
    if not target_user:
        return False, "User not found."

    if target_user.id == admin_user.id:
        return False, "You cannot deactivate your own administrator account."

    if target_user.is_admin and target_user.is_active:
        active_admins = User.query.filter_by(role="admin", is_active=True).count()
        if active_admins <= 1:
            return False, "Cannot deactivate the last remaining active administrator account."

    new_status = not target_user.is_active
    target_user.is_active = new_status
    action = "reactivate_user" if new_status else "deactivate_user"

    log_admin_action(
        admin_id=admin_user.id,
        action=action,
        target_type="user",
        target_id=str(target_user.id),
        detail=f"Admin {action} for {target_user.email}",
        ip=ip,
    )
    db.session.commit()

    verb = "reactivated" if new_status else "deactivated"
    return True, f"User {target_user.name} ({target_user.email}) has been {verb}."


def reset_user_strikes(admin_user: Any, target_user_id: int, ip: str) -> tuple[bool, str]:
    """Reset moderation strikes for a user account."""
    target_user = User.query.get(target_user_id)
    if not target_user:
        return False, "User not found."

    old_strikes = target_user.moderation_strikes
    target_user.moderation_strikes = 0

    log_admin_action(
        admin_id=admin_user.id,
        action="reset_strikes",
        target_type="user",
        target_id=str(target_user.id),
        detail=f"Moderation strikes reset from {old_strikes} to 0 for {target_user.email}",
        ip=ip,
    )
    db.session.commit()

    return True, f"Moderation strikes reset to 0 for {target_user.name}."


# ---------------------------------------------------------------------------
# 2. DATA BROWSER
# ---------------------------------------------------------------------------


def get_data_browser_tables() -> list[dict[str, Any]]:
    """List all database tables with model name and current live row counts."""
    tables = []
    for table_name, model_class in TABLE_MODEL_MAP.items():
        try:
            count = model_class.query.count()
        except Exception:
            count = 0

        doc = (model_class.__doc__ or "").strip().split("\n")[0]
        tables.append(
            {
                "table_name": table_name,
                "model_name": model_class.__name__,
                "row_count": count,
                "description": doc or f"{model_class.__name__} entity records",
            }
        )
    return sorted(tables, key=lambda t: t["table_name"])


def get_table_rows_paginated(
    table_name: str,
    search: str | None = None,
    sort_col: str | None = None,
    sort_dir: str = "asc",
    page: int = 1,
    per_page: int = 25,
    admin_can_view_chat: bool = False,
    admin_user: Any = None,
    ip: str | None = None,
) -> tuple[list[str], list[dict[str, Any]], int, int]:
    """
    Fetch paginated rows from a model table with hard-coded column redaction,
    privacy protection for private/group messages, and anonymous author auditing.
    Returns (columns_list, rows_list, total_count, total_pages).
    """
    model_class: Any = TABLE_MODEL_MAP.get(table_name)
    if not model_class:
        return [], [], 0, 1

    # Extract all model columns excluding redacted sensitive attributes
    columns = [
        col.name
        for col in model_class.__table__.columns
        if not is_column_redacted(col.name)
    ]

    query = model_class.query

    # Search filter across text columns
    if search:
        search_terms = []
        for col in model_class.__table__.columns:
            if not is_column_redacted(col.name) and hasattr(col.type, "python_type"):
                try:
                    if issubclass(col.type.python_type, str):
                        search_terms.append(getattr(model_class, col.name).ilike(f"%{search.strip()}%"))
                except (NotImplementedError, TypeError):
                    pass
        if search_terms:
            query = query.filter(or_(*search_terms))

    # Sorting
    if sort_col and sort_col in columns:
        sort_attr: Any = getattr(model_class, sort_col)
        query = query.order_by(sort_attr.asc() if sort_dir == "asc" else sort_attr.desc())
    elif hasattr(model_class, "id"):
        query = query.order_by(model_class.id.asc() if sort_dir == "asc" else model_class.id.desc())

    total_count = query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    records = query.offset((page - 1) * per_page).limit(per_page).all()

    # Format row records with privacy & anonymity rules
    formatted_rows = []
    viewed_chat_ids = []
    revealed_doubt_ids = []

    for item in records:
        row_dict = {}
        for col_name in columns:
            raw_val = getattr(item, col_name, None)

            # Rule 1: Chat Message Privacy
            if table_name == "messages" and col_name in ("text", "original_text", "image_path"):
                if not admin_can_view_chat:
                    row_dict[col_name] = "[hidden: privacy]"
                else:
                    row_dict[col_name] = str(raw_val) if raw_val is not None else ""
                    if getattr(item, "id", None) not in viewed_chat_ids:
                        viewed_chat_ids.append(item.id)

            # Rule 2: Anonymous Doubt Author Accountability
            elif table_name == "doubts" and col_name == "user_id":
                is_anon = getattr(item, "is_anonymous", False)
                author_name = item.user.name if getattr(item, "user", None) else f"User #{raw_val}"
                if is_anon:
                    row_dict[col_name] = {
                        "value": raw_val,
                        "label": f"{author_name} (Anonymous to students)",
                        "is_anonymous": True,
                    }
                    if item.id not in revealed_doubt_ids:
                        revealed_doubt_ids.append(item.id)
                else:
                    row_dict[col_name] = {
                        "value": raw_val,
                        "label": author_name,
                        "is_anonymous": False,
                    }

            # Rule 3: General User FK Resolution
            elif col_name.endswith("_id") and "user" in col_name:
                u = User.query.get(raw_val) if raw_val else None
                label = u.name if u else f"ID #{raw_val}"
                row_dict[col_name] = {"value": raw_val, "label": label}

            # Datetime formatting
            elif isinstance(raw_val, datetime):
                row_dict[col_name] = raw_val.strftime("%Y-%m-%d %H:%M:%S UTC")
            else:
                row_dict[col_name] = str(raw_val) if raw_val is not None else ""

        row_dict["__id__"] = getattr(item, "id", None)
        formatted_rows.append(row_dict)

    # Write audit logs for privileged views
    if admin_user and viewed_chat_ids:
        log_admin_action(
            admin_id=admin_user.id,
            action="view_chat_content",
            target_type="chat_message",
            target_id=",".join(map(str, viewed_chat_ids[:10])),
            detail=f"Viewed chat content for {len(viewed_chat_ids)} message(s) in Data Browser",
            ip=ip,
        )

    if admin_user and revealed_doubt_ids:
        log_admin_action(
            admin_id=admin_user.id,
            action="reveal_anonymous_author",
            target_type="doubt",
            target_id=",".join(map(str, revealed_doubt_ids[:10])),
            detail=f"Inspected real author for {len(revealed_doubt_ids)} anonymous doubt(s)",
            ip=ip,
        )

    return columns, formatted_rows, total_count, total_pages


def get_row_detail(
    table_name: str,
    row_id: int | str,
    admin_can_view_chat: bool = False,
    admin_user: Any = None,
    ip: str | None = None,
) -> dict[str, Any] | None:
    """Fetch a single record with redacted columns filtered and privileged fields audited."""
    model_class: Any = TABLE_MODEL_MAP.get(table_name)
    if not model_class:
        return None

    item = model_class.query.get(row_id)
    if not item:
        return None

    detail = {}
    for col in model_class.__table__.columns:
        if is_column_redacted(col.name):
            continue

        raw_val = getattr(item, col.name, None)

        if table_name == "messages" and col.name in ("text", "original_text", "image_path"):
            if not admin_can_view_chat:
                detail[col.name] = "[hidden: privacy]"
            else:
                detail[col.name] = str(raw_val) if raw_val is not None else ""
                if admin_user:
                    log_admin_action(
                        admin_id=admin_user.id,
                        action="view_chat_content",
                        target_type="message",
                        target_id=str(row_id),
                        detail=f"Viewed chat content for message #{row_id} in Row Detail",
                        ip=ip,
                    )

        elif table_name == "doubts" and col.name == "user_id":
            is_anon = getattr(item, "is_anonymous", False)
            author_name = item.user.name if getattr(item, "user", None) else f"User #{raw_val}"
            if is_anon:
                detail[col.name] = f"{author_name} (Anonymous to peers - Revealed to Admin)"
                if admin_user:
                    log_admin_action(
                        admin_id=admin_user.id,
                        action="view_anonymous_author",
                        target_type="doubt",
                        target_id=str(row_id),
                        detail=f"Inspected real author for anonymous doubt #{row_id}",
                        ip=ip,
                    )
            else:
                detail[col.name] = author_name
        elif isinstance(raw_val, datetime):
            detail[col.name] = raw_val.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            detail[col.name] = str(raw_val) if raw_val is not None else ""

    return detail


# ---------------------------------------------------------------------------
# 3. REPORTS
# ---------------------------------------------------------------------------


def get_message_reports_data(
    reason: str | None = None,
    status: str | None = None,
    user_id: int | None = None,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[MessageReport], int, int]:
    """Retrieve filtered, paginated student message reports."""
    query = MessageReport.query

    if reason:
        query = query.filter(MessageReport.reason == reason)
    if status:
        query = query.join(Message, MessageReport.message_id == Message.id).filter(
            Message.review_status == status
        )
    if user_id:
        query = query.filter(
            or_(
                MessageReport.reporter_id == user_id,
                MessageReport.message.has(Message.sender_id == user_id),
            )
        )

    query = query.order_by(MessageReport.created_at.desc())
    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    reports = query.offset((page - 1) * per_page).limit(per_page).all()
    return reports, total, pages


def get_auto_flagged_messages_data(
    status: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[Message], int, int]:
    """Retrieve automated Aho-Corasick flagged messages with moderation status."""
    query = Message.query.filter(
        or_(
            Message.review_status != "none",
            Message.flag_reason.isnot(None),
            Message.original_text.isnot(None),
        )
    )

    if status and status != "all":
        query = query.filter(Message.review_status == status)

    query = query.order_by(Message.created_at.desc())
    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    messages = query.offset((page - 1) * per_page).limit(per_page).all()
    return messages, total, pages


def get_blocked_submissions_data() -> list[dict[str, Any]]:
    """Aggregate moderation log submissions per user, source (doubt/answer/chat), and action."""
    rows = (
        db.session.query(
            ModerationLog.user_id,
            ModerationLog.source,
            ModerationLog.action,
            func.count(ModerationLog.id).label("blocked_count"),
            func.max(ModerationLog.created_at).label("last_blocked"),
        )
        .group_by(ModerationLog.user_id, ModerationLog.source, ModerationLog.action)
        .order_by(desc("blocked_count"))
        .all()
    )

    results = []
    for uid, src, act, cnt, last_dt in rows:
        u = db.session.get(User, uid) if uid else None
        results.append(
            {
                "user": u,
                "user_id": uid,
                "source": src,
                "action": act,
                "count": cnt,
                "blocked_count": cnt,
                "last_blocked": last_dt,
            }
        )
    return results


def get_repeat_offenders_data() -> list[dict[str, Any]]:
    """Identify students with active moderation strikes or high report counts."""
    users = (
        User.query.filter(or_(User.moderation_strikes > 0, User.role == "student"))
        .order_by(User.moderation_strikes.desc())
        .all()
    )

    offenders = []
    for u in users:
        rep_count = (
            MessageReport.query.join(Message, MessageReport.message_id == Message.id)
            .filter(Message.sender_id == u.id)
            .count()
        )
        if u.moderation_strikes > 0 or rep_count > 0:
            offenders.append(
                {
                    "user": u,
                    "strikes": u.moderation_strikes,
                    "reports_count": rep_count,
                    "status": "Active" if u.is_active else "Deactivated",
                }
            )
    return sorted(offenders, key=lambda o: (o["strikes"], o["reports_count"]), reverse=True)


def get_doubt_content_summary_data() -> dict[str, Any]:
    """Retrieve unanswered doubts older than 3 days, escalated doubts, and faculty verifications."""
    three_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)

    total_doubts = Doubt.query.count()
    unanswered_count = Doubt.query.filter(~Doubt.answers.any()).count()

    stale_unanswered = (
        Doubt.query.filter(~Doubt.answers.any(), Doubt.created_at <= three_days_ago)
        .order_by(Doubt.created_at.asc())
        .all()
    )

    needs_human_doubts = (
        Doubt.query.filter(Doubt.needs_human.is_(True), Doubt.solved_answer_id.is_(None))
        .order_by(Doubt.created_at.desc())
        .all()
    )

    faculty_verifications = (
        db.session.query(User, func.count(Answer.id).label("verified_count"))
        .join(Answer, Answer.verified_by == User.id)
        .filter(User.role == "teacher")
        .group_by(User.id)
        .order_by(desc("verified_count"))
        .all()
    )

    return {
        "total_doubts": total_doubts,
        "unanswered_count": unanswered_count,
        "stale_count": len(stale_unanswered),
        "stale_unanswered": stale_unanswered,
        "needs_human_doubts": needs_human_doubts,
        "faculty_verifications": faculty_verifications,
    }


# ---------------------------------------------------------------------------
# 4. EXPORT GENERATORS
# ---------------------------------------------------------------------------


def generate_users_csv() -> Generator[str, None, None]:
    """Generate CSV rows for all registered users without sensitive password hashes."""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "id",
        "name",
        "email",
        "role",
        "college_name",
        "program",
        "specialization",
        "year",
        "semester",
        "section",
        "is_active",
        "moderation_strikes",
        "created_at",
        "last_login_at",
    ]
    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for user in User.query.order_by(User.id.asc()).yield_per(100):
        row = [
            sanitize_csv_cell(user.id),
            sanitize_csv_cell(user.name),
            sanitize_csv_cell(user.email),
            sanitize_csv_cell(user.role),
            sanitize_csv_cell(user.college_name),
            sanitize_csv_cell(user.program),
            sanitize_csv_cell(user.specialization or user.branch),
            sanitize_csv_cell(user.year),
            sanitize_csv_cell(user.semester),
            sanitize_csv_cell(user.section),
            sanitize_csv_cell(user.is_active),
            sanitize_csv_cell(user.moderation_strikes),
            sanitize_csv_cell(user.created_at),
            sanitize_csv_cell(user.last_login_at),
        ]
        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


def generate_doubts_csv() -> Generator[str, None, None]:
    """Generate CSV rows for doubts."""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = ["id", "user_id", "subject", "title", "body", "is_anonymous", "status", "created_at"]
    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for d in Doubt.query.order_by(Doubt.id.asc()).yield_per(100):
        row = [
            sanitize_csv_cell(d.id),
            sanitize_csv_cell(d.user_id),
            sanitize_csv_cell(d.subject),
            sanitize_csv_cell(d.title),
            sanitize_csv_cell(d.body),
            sanitize_csv_cell(d.is_anonymous),
            sanitize_csv_cell(d.status),
            sanitize_csv_cell(d.created_at),
        ]
        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


def generate_answers_csv() -> Generator[str, None, None]:
    """Generate CSV rows for answers."""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "id",
        "doubt_id",
        "user_id",
        "body",
        "upvotes",
        "is_verified",
        "verified_by",
        "created_at",
    ]
    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for a in Answer.query.order_by(Answer.id.asc()).yield_per(100):
        row = [
            sanitize_csv_cell(a.id),
            sanitize_csv_cell(a.doubt_id),
            sanitize_csv_cell(a.user_id),
            sanitize_csv_cell(a.body),
            sanitize_csv_cell(a.upvotes),
            sanitize_csv_cell(a.is_verified),
            sanitize_csv_cell(a.verified_by),
            sanitize_csv_cell(a.created_at),
        ]
        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


def generate_reports_csv() -> Generator[str, None, None]:
    """Generate CSV rows for message reports."""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = ["id", "message_id", "reporter_id", "reason", "note", "status", "created_at"]
    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for r in MessageReport.query.order_by(MessageReport.id.asc()).yield_per(100):
        row = [
            sanitize_csv_cell(r.id),
            sanitize_csv_cell(r.message_id),
            sanitize_csv_cell(r.reporter_id),
            sanitize_csv_cell(r.reason),
            sanitize_csv_cell(r.note),
            sanitize_csv_cell(r.status),
            sanitize_csv_cell(r.created_at),
        ]
        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


def generate_quiz_attempts_csv() -> Generator[str, None, None]:
    """Generate CSV rows for practice quiz attempts."""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = ["id", "user_id", "subject", "topic", "num_questions", "score", "created_at"]
    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for q in QuizAttempt.query.order_by(QuizAttempt.id.asc()).yield_per(100):
        row = [
            sanitize_csv_cell(q.id),
            sanitize_csv_cell(q.user_id),
            sanitize_csv_cell(q.subject),
            sanitize_csv_cell(q.topic),
            sanitize_csv_cell(q.num_questions),
            sanitize_csv_cell(q.score),
            sanitize_csv_cell(q.created_at),
        ]
        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


def generate_table_csv(table_name: str) -> Generator[str, None, None]:
    """Generic CSV stream generator for any table in the data browser with column redactions."""
    model_class: Any = TABLE_MODEL_MAP.get(table_name)
    if not model_class:
        return

    output = io.StringIO()
    writer = csv.writer(output)

    columns = [col.name for col in model_class.__table__.columns if not is_column_redacted(col.name)]
    writer.writerow(columns)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for record in model_class.query.order_by(model_class.id.asc() if hasattr(model_class, "id") else None).yield_per(100):
        row = [sanitize_csv_cell(getattr(record, c, "")) for c in columns]
        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

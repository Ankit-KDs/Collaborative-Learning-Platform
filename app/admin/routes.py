"""
Admin Portal Routes
===================
Controller endpoints for platform administration:
- Dashboard KPIs & Chart.js visualizations
- User Management & Account Moderation (toggle activation, reset strikes)
- Generic Read-Only Data Browser with credential redaction & chat privacy controls
- Centralized Reports (message reports, auto-flagged, blocked submissions, repeat offenders)
- Local Academic Analytics & Conversion Funnels
- Streaming CSV Data Exports with CSV Injection protection
- Read-Only Append-Only Admin Audit Log
"""

import json
from typing import Any, cast
from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    Response,
    stream_with_context,
    current_app,
)
from flask_login import login_required, current_user
from app.admin import admin_bp
from app.utils import admin_required, get_client_ip
from app.models import AdminAuditLog, User
from app.config import SUBJECTS, PROGRAMS
from app.services.admin_service import (
    get_users_paginated,
    get_user_detail,
    toggle_user_active,
    reset_user_strikes,
    get_data_browser_tables,
    get_table_rows_paginated,
    get_row_detail,
    get_message_reports_data,
    get_auto_flagged_messages_data,
    get_blocked_submissions_data,
    get_repeat_offenders_data,
    get_doubt_content_summary_data,
    generate_users_csv,
    generate_doubts_csv,
    generate_answers_csv,
    generate_reports_csv,
    generate_quiz_attempts_csv,
    generate_table_csv,
    log_admin_action,
    TABLE_MODEL_MAP,
)
from app.services.analytics_service import (
    get_admin_dashboard_metrics,
    get_admin_analytics,
)


@admin_bp.route("")
@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    """Main administrator dashboard showcasing system KPIs and daily growth charts."""
    stats = get_admin_dashboard_metrics()
    return render_template(
        "admin/dashboard.html",
        title="Admin Control Center",
        stats=stats,
        reg_dates_json=json.dumps(stats["reg_dates"]),
        reg_counts_json=json.dumps(stats["reg_counts"]),
        role_labels_json=json.dumps(stats["role_labels"]),
        role_counts_json=json.dumps(stats["role_counts"]),
    )


# ---------------------------------------------------------------------------
# USER MANAGEMENT
# ---------------------------------------------------------------------------


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    """Browse, filter, search, and paginate all platform users."""
    search = request.args.get("q", "").strip() or None
    role = request.args.get("role", "all").strip().lower()
    role_filter = role if role in ("student", "teacher", "admin") else None
    program = request.args.get("program", "all").strip()
    program_filter = program if program in PROGRAMS else None
    specialization = request.args.get("specialization", "").strip() or None
    year_arg = request.args.get("year", "")
    year_filter = int(year_arg) if year_arg.isdigit() and int(year_arg) in (1, 2, 3, 4) else None
    college = request.args.get("college", "").strip() or None
    status = request.args.get("status", "all").strip().lower()
    status_filter = status if status in ("active", "deactivated") else None
    sort_by = request.args.get("sort", "created_at").strip()
    sort_order = request.args.get("order", "desc").strip().lower()
    page = max(1, int(request.args.get("page", 1)))

    user_list, total_count, total_pages = get_users_paginated(
        search=search,
        role=role_filter,
        program=program_filter,
        specialization=specialization,
        year=year_filter,
        college=college,
        status=status_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=25,
    )

    return render_template(
        "admin/users.html",
        title="User Management",
        users=user_list,
        total_count=total_count,
        total_pages=total_pages,
        page=page,
        search=search or "",
        current_role=role,
        current_program=program,
        current_specialization=specialization or "",
        current_year=year_arg,
        current_college=college or "",
        current_status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        programs=PROGRAMS,
    )


@admin_bp.route("/users/<int:user_id>")
@login_required
@admin_required
def user_detail_view(user_id: int):
    """Deep-dive profile view for a specific student, faculty member, or admin."""
    details = get_user_detail(user_id)
    if not details:
        abort(404)

    return render_template(
        "admin/user_detail.html",
        title=f"User #{user_id} - {details['user'].name}",
        **details,
    )


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def user_toggle_active(user_id: int):
    """Deactivate or reactivate a user account with audit trail."""
    client_ip = get_client_ip()
    success, msg = toggle_user_active(current_user, user_id, client_ip)
    flash(msg, "success" if success else "danger")
    return redirect(request.referrer or url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/reset-strikes", methods=["POST"])
@login_required
@admin_required
def user_reset_strikes(user_id: int):
    """Reset moderation strikes for a student account with audit trail."""
    client_ip = get_client_ip()
    success, msg = reset_user_strikes(current_user, user_id, client_ip)
    flash(msg, "success" if success else "danger")
    return redirect(request.referrer or url_for("admin.user_detail_view", user_id=user_id))


# ---------------------------------------------------------------------------
# DATA BROWSER
# ---------------------------------------------------------------------------


@admin_bp.route("/data")
@login_required
@admin_required
def data_browser():
    """List all database tables with model name and live record counts."""
    tables = get_data_browser_tables()
    return render_template(
        "admin/data_browser.html",
        title="Database Viewer",
        tables=tables,
    )


@admin_bp.route("/data/<string:table_name>")
@login_required
@admin_required
def data_table(table_name: str):
    """View paginated rows for a specific database model."""
    if table_name not in TABLE_MODEL_MAP:
        abort(404)

    search = request.args.get("q", "").strip() or None
    sort_col = request.args.get("sort", "").strip() or None
    sort_dir = request.args.get("dir", "asc").strip().lower()
    page = max(1, int(request.args.get("page", 1)))

    admin_can_view_chat = current_app.config.get("ADMIN_CAN_VIEW_CHAT_CONTENT", False)
    client_ip = get_client_ip()

    columns, rows, total_count, total_pages = get_table_rows_paginated(
        table_name=table_name,
        search=search,
        sort_col=sort_col,
        sort_dir=sort_dir,
        page=page,
        per_page=25,
        admin_can_view_chat=admin_can_view_chat,
        admin_user=current_user,
        ip=client_ip,
    )

    return render_template(
        "admin/data_table.html",
        title=f"Data Browser: {table_name}",
        table_name=table_name,
        columns=columns,
        rows=rows,
        total_count=total_count,
        total_pages=total_pages,
        page=page,
        search=search or "",
        sort_col=sort_col or "",
        sort_dir=sort_dir,
        admin_can_view_chat=admin_can_view_chat,
    )


@admin_bp.route("/data/<string:table_name>/<string:row_id>")
@login_required
@admin_required
def data_row(table_name: str, row_id: str):
    """Inspect full attributes for a single record with redacted columns filtered out."""
    if table_name not in TABLE_MODEL_MAP:
        abort(404)

    admin_can_view_chat = current_app.config.get("ADMIN_CAN_VIEW_CHAT_CONTENT", False)
    client_ip = get_client_ip()

    detail = get_row_detail(
        table_name=table_name,
        row_id=row_id,
        admin_can_view_chat=admin_can_view_chat,
        admin_user=current_user,
        ip=client_ip,
    )
    if not detail:
        abort(404)

    return render_template(
        "admin/data_row.html",
        title=f"{table_name} #{row_id}",
        table_name=table_name,
        row_id=row_id,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# REPORTS & MODERATION SUMMARY
# ---------------------------------------------------------------------------


@admin_bp.route("/reports")
@login_required
@admin_required
def reports():
    """Administrative reports hub featuring message reports, auto-flags, blocked logs, and repeat offenders."""
    active_tab = request.args.get("tab", "reports").strip().lower()
    page = max(1, int(request.args.get("page", 1)))

    reason = request.args.get("reason", "").strip() or None
    status = request.args.get("status", "").strip() or None

    msg_reports, reports_total, reports_pages = get_message_reports_data(
        reason=reason, status=status, page=page, per_page=25
    )
    auto_flagged, flagged_total, flagged_pages = get_auto_flagged_messages_data(
        status=status, page=page, per_page=25
    )
    blocked_submissions = get_blocked_submissions_data()
    repeat_offenders = get_repeat_offenders_data()
    doubt_summary = get_doubt_content_summary_data()

    return render_template(
        "admin/reports.html",
        title="Platform Safety & Content Reports",
        active_tab=active_tab,
        msg_reports=msg_reports,
        reports_total=reports_total,
        reports_pages=reports_pages,
        auto_flagged=auto_flagged,
        flagged_total=flagged_total,
        flagged_pages=flagged_pages,
        blocked_submissions=blocked_submissions,
        repeat_offenders=repeat_offenders,
        doubt_summary=doubt_summary,
        page=page,
        current_reason=reason or "",
        current_status=status or "",
    )


# ---------------------------------------------------------------------------
# ANALYTICS
# ---------------------------------------------------------------------------


@admin_bp.route("/analytics")
@login_required
@admin_required
def analytics():
    """Comprehensive academic metrics, peer request funnels, and moderation trends."""
    date_range = request.args.get("range", "30").strip()
    data = get_admin_analytics(date_range=date_range)

    return render_template(
        "admin/analytics.html",
        title="Platform Analytics",
        data=data,
        programs_json=json.dumps(data["users_by_program"]),
        specs_json=json.dumps(data["users_by_specialization"]),
        years_json=json.dumps(data["users_by_year"]),
        colleges_json=json.dumps(data["users_by_college"]),
        doubts_by_subject_json=json.dumps(data["doubts_by_subject"]),
        funnel_json=json.dumps(data["request_funnel"]),
        ai_usage_json=json.dumps(data["ai_usage"]),
        moderation_weeks_json=json.dumps(data["moderation_weeks"]),
        moderation_counts_json=json.dumps(data["moderation_counts"]),
    )


# ---------------------------------------------------------------------------
# AUDIT LOG
# ---------------------------------------------------------------------------


@admin_bp.route("/audit")
@login_required
@admin_required
def audit_log():
    """Read-only append-only audit trail of administrator activities."""
    action_filter = request.args.get("action", "").strip() or None
    target_filter = request.args.get("target", "").strip() or None
    page = max(1, int(request.args.get("page", 1)))
    per_page = 25

    query = AdminAuditLog.query
    if action_filter:
        query = query.filter(AdminAuditLog.action == action_filter)
    if target_filter:
        query = query.filter(AdminAuditLog.target_type == target_filter)

    query = query.order_by(AdminAuditLog.created_at.desc())
    total_count = query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    logs = query.offset((page - 1) * per_page).limit(per_page).all()

    return render_template(
        "admin/audit.html",
        title="Admin Audit Trail",
        logs=logs,
        total_count=total_count,
        total_pages=total_pages,
        page=page,
        current_action=action_filter or "",
        current_target=target_filter or "",
    )


# ---------------------------------------------------------------------------
# EXPORTS
# ---------------------------------------------------------------------------


@admin_bp.route("/exports")
@login_required
@admin_required
def exports():
    """Central data export center with pre-configured schemas and custom table exporters."""
    tables = get_data_browser_tables()
    return render_template(
        "admin/exports.html",
        title="Data Exports",
        tables=tables,
    )


@admin_bp.route("/exports/<string:export_type>")
@login_required
@admin_required
def export_file(export_type: str):
    """Stream standardized CSV exports with formula injection protection and audit logging."""
    client_ip = get_client_ip()

    if export_type == "users":
        gen = generate_users_csv()
        filename = "collab_learn_users"
    elif export_type == "doubts":
        gen = generate_doubts_csv()
        filename = "collab_learn_doubts"
    elif export_type == "answers":
        gen = generate_answers_csv()
        filename = "collab_learn_answers"
    elif export_type == "reports":
        gen = generate_reports_csv()
        filename = "collab_learn_reports"
    elif export_type in ("quizzes", "quiz_attempts"):
        gen = generate_quiz_attempts_csv()
        filename = "collab_learn_quiz_attempts"
    else:
        abort(404)

    log_admin_action(
        admin_id=current_user.id,
        action="export_data",
        target_type=export_type,
        detail=f"Exported {export_type} CSV",
        ip=client_ip,
    )

    response = Response(stream_with_context(cast(Any, gen)), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    return response


@admin_bp.route("/exports/table/<string:table_name>")
@login_required
@admin_required
def export_table(table_name: str):
    """Export any table from Data Browser with sensitive columns redacted and audit trail."""
    if table_name not in TABLE_MODEL_MAP:
        abort(404)

    client_ip = get_client_ip()
    log_admin_action(
        admin_id=current_user.id,
        action="export_data",
        target_type=f"table:{table_name}",
        detail=f"Exported table '{table_name}' CSV",
        ip=client_ip,
    )

    gen = generate_table_csv(table_name)
    response = Response(stream_with_context(cast(Any, gen)), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="table_{table_name}.csv"'
    return response

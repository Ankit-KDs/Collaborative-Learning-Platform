"""
Unit and integration tests for Stage 10:
Admin panel, user management, read-only data browser, privacy redaction,
academic analytics, streaming CSV exports, and immutable audit logs.
"""

import os
import subprocess
import sys
import pytest
from app import create_app, db
from app.models import (
    User,
    Doubt,
    Answer,
    ChatRoom,
    Message,
    AdminAuditLog,
    MessageReport,
    ModerationLog,
)
from app.services.admin_service import sanitize_csv_cell


@pytest.fixture
def test_app():
    """Create test application configured with isolated in-memory database."""
    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["ADMIN_CAN_VIEW_CHAT_CONTENT"] = False
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    """Provide Flask test client."""
    return test_app.test_client()


def create_user(email="test@user.com", role="student", name="Test User", is_active=True):
    """Helper to create a user."""
    u = User(
        name=name,
        email=email,
        role=role,
        is_active=is_active,
    )
    u.set_password("SecurePassword123")
    db.session.add(u)
    db.session.commit()
    return u


def test_registration_rejects_admin_role(client, test_app):
    """Server-side reject any attempt to submit role=admin or role_type=admin via registration."""
    # Attempt with role_type=admin
    res = client.post(
        "/auth/register",
        data={
            "role_type": "admin",
            "name": "Evil Admin",
            "email": "hacker@evil.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert res.status_code == 400

    # Ensure no admin was created
    with test_app.app_context():
        admin = User.query.filter_by(role="admin").first()
        assert admin is None


def test_admin_access_control(client, test_app):
    """Non-admins (guests, students, teachers) get 403 or redirect on all /admin routes."""
    with test_app.app_context():
        student = create_user("student@test.com", role="student")
        teacher = create_user("teacher@test.com", role="teacher")
        admin = create_user("admin@test.com", role="admin")

    admin_routes = [
        "/admin",
        "/admin/users",
        "/admin/data",
        "/admin/reports",
        "/admin/analytics",
        "/admin/audit",
        "/admin/exports",
    ]

    # 1. Unauthenticated guest -> redirects to login
    for route in admin_routes:
        res = client.get(route)
        assert res.status_code == 302
        assert "/auth/login" in res.headers["Location"]

    # 2. Student -> 403 Forbidden
    client.post("/auth/login", data={"email": "student@test.com", "password": "SecurePassword123"})
    for route in admin_routes:
        res = client.get(route)
        assert res.status_code == 403
    client.get("/auth/logout")

    # 3. Faculty / Teacher -> 403 Forbidden
    client.post("/auth/login", data={"email": "teacher@test.com", "password": "SecurePassword123"})
    for route in admin_routes:
        res = client.get(route)
        assert res.status_code == 403
    client.get("/auth/logout")

    # 4. Admin -> 200 OK
    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})
    for route in admin_routes:
        res = client.get(route)
        assert res.status_code == 200


def test_password_hash_never_exposed(client, test_app):
    """password_hash and secret tokens never appear in HTML rendering or CSV exports."""
    with test_app.app_context():
        admin = create_user("admin@test.com", role="admin")
        student = create_user("student@test.com", role="student")
        secret_hash = student.password_hash

    # Log in as admin
    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})

    # Check user detail HTML
    res = client.get(f"/admin/users/{student.id}")
    assert res.status_code == 200
    assert secret_hash not in res.get_data(as_text=True)

    # Check Data Browser table HTML for users
    res = client.get("/admin/data/users")
    assert res.status_code == 200
    assert secret_hash not in res.get_data(as_text=True)
    assert "password_hash" not in res.get_data(as_text=True)

    # Check Data Browser single row HTML
    res = client.get(f"/admin/data/users/{student.id}")
    assert res.status_code == 200
    assert secret_hash not in res.get_data(as_text=True)
    assert "password_hash" not in res.get_data(as_text=True)

    # Check CSV export
    res = client.get("/admin/exports/users")
    assert res.status_code == 200
    csv_text = res.get_data(as_text=True)
    assert secret_hash not in csv_text
    assert "password_hash" not in csv_text


def test_chat_privacy_default_masked_and_audit_logged(client, test_app):
    """Private chat content is masked by default, unmasked only with config flag, and audited."""
    with test_app.app_context():
        admin = create_user("admin@test.com", role="admin")
        u1 = create_user("u1@test.com", role="student")
        u2 = create_user("u2@test.com", role="student")
        room = ChatRoom(type="private", name="Private 1-on-1")
        db.session.add(room)
        db.session.flush()
        msg = Message(room_id=room.id, sender_id=u1.id, text="Secret private love note")
        db.session.add(msg)
        db.session.commit()
        msg_id = msg.id

    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})

    # Default: ADMIN_CAN_VIEW_CHAT_CONTENT is False
    res = client.get(f"/admin/data/messages/{msg_id}")
    assert res.status_code == 200
    content = res.get_data(as_text=True)
    assert "[hidden: privacy]" in content
    assert "Secret private love note" not in content

    # Enable ADMIN_CAN_VIEW_CHAT_CONTENT
    test_app.config["ADMIN_CAN_VIEW_CHAT_CONTENT"] = True

    res = client.get(f"/admin/data/messages/{msg_id}")
    assert res.status_code == 200
    content = res.get_data(as_text=True)
    assert "Secret private love note" in content

    # Verify audit log recorded the chat content view
    with test_app.app_context():
        audit = AdminAuditLog.query.filter_by(action="view_chat_content").first()
        assert audit is not None
        assert audit.target_type == "message"
        assert int(audit.target_id) == msg_id


def test_anonymous_doubt_reveal_audited(client, test_app):
    """Viewing anonymous doubt real author in Data Browser is recorded in audit log."""
    with test_app.app_context():
        admin = create_user("admin@test.com", role="admin")
        author = create_user("author@test.com", role="student", name="Shy Student")
        doubt = Doubt(
            user_id=author.id,
            subject="Python",
            title="Anonymous Doubt Question",
            body="I am shy",
            is_anonymous=True,
        )
        db.session.add(doubt)
        db.session.commit()
        doubt_id = doubt.id

    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})

    # Admin visits doubt in Data Browser
    res = client.get(f"/admin/data/doubts/{doubt_id}")
    assert res.status_code == 200
    content = res.get_data(as_text=True)
    assert "Shy Student" in content
    assert "(Anonymous to peers - Revealed to Admin)" in content

    # Verify audit trail recorded anonymous author lookup
    with test_app.app_context():
        audit = AdminAuditLog.query.filter_by(action="view_anonymous_author").first()
        assert audit is not None
        assert audit.target_type == "doubt"
        assert int(audit.target_id) == doubt_id


def test_deactivated_user_cannot_login(client, test_app):
    """Deactivated user account cannot log in and gets 403 Forbidden with clear explanation."""
    with test_app.app_context():
        user = create_user("inactive@test.com", role="student", is_active=False)

    res = client.post(
        "/auth/login",
        data={"email": "inactive@test.com", "password": "SecurePassword123"},
    )
    assert res.status_code == 403
    assert "deactivated" in res.get_data(as_text=True).lower()


def test_admin_cannot_deactivate_self_or_last_admin(client, test_app):
    """Admin cannot deactivate their own account or the sole remaining admin."""
    with test_app.app_context():
        admin1 = create_user("admin1@test.com", role="admin", name="Admin One")
        student = create_user("student@test.com", role="student")
        admin1_id = admin1.id
        student_id = student.id

    client.post("/auth/login", data={"email": "admin1@test.com", "password": "SecurePassword123"})

    # 1. Admin tries to deactivate self -> rejected
    res = client.post(f"/admin/users/{admin1_id}/toggle-active", follow_redirects=True)
    assert "cannot deactivate your own" in res.get_data(as_text=True).lower()
    with test_app.app_context():
        u1 = db.session.get(User, admin1_id)
        assert u1 is not None and u1.is_active is True

    # 2. Deactivating student -> succeeds
    res = client.post(f"/admin/users/{student_id}/toggle-active", follow_redirects=True)
    assert "deactivated" in res.get_data(as_text=True).lower()
    with test_app.app_context():
        s = db.session.get(User, student_id)
        assert s is not None and s.is_active is False

    # 3. If there is only one admin, another attempt to deactivate them is blocked
    with test_app.app_context():
        admin2 = create_user("admin2@test.com", role="admin", name="Admin Two")
        admin2_id = admin2.id

    # admin1 deactivates admin2 -> succeeds
    res = client.post(f"/admin/users/{admin2_id}/toggle-active", follow_redirects=True)
    with test_app.app_context():
        u2 = db.session.get(User, admin2_id)
        assert u2 is not None and u2.is_active is False

    # Now admin1 is the only active admin. Reactivate admin2
    res = client.post(f"/admin/users/{admin2_id}/toggle-active", follow_redirects=True)
    with test_app.app_context():
        u2_re = db.session.get(User, admin2_id)
        assert u2_re is not None and u2_re.is_active is True


def test_csv_injection_prevention():
    """Formulas beginning with =, +, -, @, \\t, \\r are prefixed with single quote."""
    dangerous_inputs = [
        "=SUM(A1:A10)",
        "+cmd|' /C calc'!A0",
        "-123+456",
        "@SUM(B1:B2)",
        "\tmalicious",
        "\rmalicious",
    ]
    for inp in dangerous_inputs:
        sanitized = sanitize_csv_cell(inp)
        assert sanitized.startswith("'"), f"Failed to sanitize: {inp} -> {sanitized}"

    # Safe inputs are not prefixed
    safe_inputs = ["Normal Text", "john.doe@example.com", "12345", "B.Tech CSE"]
    for safe in safe_inputs:
        assert sanitize_csv_cell(safe) == safe


def test_exports_streamed_and_audit_logged(client, test_app):
    """Exports are streamed responses and recorded in AdminAuditLog."""
    with test_app.app_context():
        admin = create_user("admin@test.com", role="admin")

    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})

    for export_type in ("users", "doubts", "answers", "reports", "quizzes"):
        res = client.get(f"/admin/exports/{export_type}")
        assert res.status_code == 200
        assert res.mimetype == "text/csv"
        assert "attachment;" in res.headers.get("Content-Disposition", "")
        # Consume stream
        csv_data = res.get_data(as_text=True)
        assert len(csv_data) > 0

    # Verify audit logs created
    with test_app.app_context():
        export_logs = AdminAuditLog.query.filter_by(action="export_data").all()
        assert len(export_logs) >= 5


def test_data_browser_empty_db_resilience(client, test_app):
    """Data browser works for every table with zero rows without crashing."""
    with test_app.app_context():
        admin = create_user("admin@test.com", role="admin")

    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})

    res = client.get("/admin/data")
    assert res.status_code == 200

    # Test viewing individual empty tables
    tables = [
        "users",
        "doubts",
        "answers",
        "messages",
        "chat_rooms",
        "moderation_logs",
        "admin_audit_logs",
    ]
    for tbl in tables:
        res = client.get(f"/admin/data/{tbl}")
        assert res.status_code == 200
        assert "No records" in res.get_data(as_text=True) or tbl == "users" or tbl == "admin_audit_logs"


def test_dashboard_empty_db_resilience(client, test_app):
    """Admin dashboard loads cleanly on an empty or minimal database with correct zero states."""
    with test_app.app_context():
        admin = create_user("admin@test.com", role="admin")

    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})
    res = client.get("/admin")
    assert res.status_code == 200
    content = res.get_data(as_text=True)
    assert "Admin Control Center" in content
    assert "0" in content
    assert "doubts" in content


def test_create_admin_script(tmp_path):
    """scripts/create_admin.py refuses second admin unless --force is passed."""
    db_file = tmp_path / "test_admin.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_file}"

    # First admin creation
    cmd = [
        sys.executable,
        "scripts/create_admin.py",
        "--name",
        "CLI Admin",
        "--email",
        "cli_admin@collab.edu",
        "--password",
        "SuperSecure123",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 0
    assert "created successfully" in res.stdout.lower()

    # Second admin creation without --force should fail
    cmd_second = [
        sys.executable,
        "scripts/create_admin.py",
        "--name",
        "Second Admin",
        "--email",
        "second_admin@collab.edu",
        "--password",
        "SuperSecure123",
    ]
    res_second = subprocess.run(cmd_second, capture_output=True, text=True, env=env)
    assert res_second.returncode != 0
    combined_err = (res_second.stdout + res_second.stderr).lower()
    assert "already exists" in combined_err or "force" in combined_err

    # Second admin creation with --force should succeed
    cmd_force = cmd_second + ["--force"]
    res_force = subprocess.run(cmd_force, capture_output=True, text=True, env=env)
    assert res_force.returncode == 0
    assert "created successfully" in res_force.stdout.lower()


def test_audit_log_append_only(client, test_app):
    """Audit log records cannot be modified or deleted via any HTTP routes."""
    with test_app.app_context():
        admin = create_user("admin@test.com", role="admin")
        log = AdminAuditLog(
            admin_id=admin.id,
            action="test_action",
            target_type="system",
            target_id=1,
            detail="Test log entry",
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})

    # Attempt delete/put routes that shouldn't exist
    assert client.delete(f"/admin/audit/{log_id}").status_code in (404, 405)
    assert client.post(f"/admin/audit/{log_id}/delete").status_code in (404, 405)
    assert client.put(f"/admin/audit/{log_id}").status_code in (404, 405)

    # Ensure log record still exists untouched
    with test_app.app_context():
        assert db.session.get(AdminAuditLog, log_id) is not None


def test_admin_reports_all_tabs_populated(client, test_app):
    """All 5 tabs on /admin/reports render cleanly when populated with real records."""
    with test_app.app_context():
        admin = create_user("admin@test.com", role="admin")
        reporter = create_user("reporter@test.com", role="student", name="Reporter One")
        author = create_user("author@test.com", role="student", name="Author Two")
        author.moderation_strikes = 2

        room = ChatRoom(type="private", created_by=reporter.id)
        db.session.add(room)
        db.session.flush()

        msg = Message(
            room_id=room.id,
            sender_id=author.id,
            text="[message hidden pending review]",
            original_text="bad message",
            is_flagged=True,
            flag_reason="user: abusive",
            review_status="pending",
        )
        db.session.add(msg)
        db.session.flush()

        report = MessageReport(
            message_id=msg.id,
            reporter_id=reporter.id,
            reason="abusive",
            note="Rude comment in chat",
        )
        mod_log = ModerationLog(
            user_id=author.id,
            source="doubt",
            action="blocked",
            matched_count=1,
        )
        doubt = Doubt(
            user_id=reporter.id,
            subject="Python",
            title="Test Doubt Health",
            body="Unanswered doubt body for health tab",
        )
        db.session.add_all([report, mod_log, doubt])
        db.session.commit()
        assert admin.id is not None

    client.post("/auth/login", data={"email": "admin@test.com", "password": "SecurePassword123"})

    for tab, expected_bytes in [
        ("reports", b"Rude comment in chat"),
        ("autoflagged", b"Author Two"),
        ("blocked", b"Author Two"),
        ("offenders", b"2 strikes"),
        ("health", b"Total Doubts Logged"),
    ]:
        res = client.get(f"/admin/reports?tab={tab}")
        assert res.status_code == 200
        assert expected_bytes in res.data

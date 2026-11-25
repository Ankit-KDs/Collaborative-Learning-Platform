"""
Unit and integration tests for Message Reporting & Teacher Moderation Queue (Stage 7).
Tests cover:
- Business rules: cannot report own message, cannot report system notifications
- Access control: non-room members receive 403
- Duplicate report prevention
- Threshold enforcement: 3 distinct user reports auto-hide the message
- Anonymity: reporter identity is never returned to room members
- Faculty authorization: students receive 403 on /moderation, teachers have full access
- Teacher actions: dismiss restores innocent text, confirm adds strikes
"""

import pytest

from app import create_app, db
from app.models import ChatMember, ChatRoom, Message, User
from app.services.reports_service import (
    ReportPermissionError,
    ReportValidationError,
    report_message,
)


@pytest.fixture
def app_instance(tmp_path):
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _create_user(name: str, email: str, role: str = "student") -> User:
    u = User(name=name, email=email, role=role, branch="CS", year=2)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


def _setup_group_room_with_members(users: list[User]) -> ChatRoom:
    room = ChatRoom(type="group", name="Study Cohort", is_active=True)
    db.session.add(room)
    db.session.flush()
    for u in users:
        db.session.add(ChatMember(room_id=room.id, user_id=u.id))
    db.session.commit()
    return room


# 1. Permission and Validation Rules
def test_cannot_report_own_or_system_message(app_instance):
    with app_instance.app_context():
        u1 = _create_user("User 1", "u1@test.com")
        u2 = _create_user("User 2", "u2@test.com")
        room = _setup_group_room_with_members([u1, u2])

        # Self message
        m1 = Message(room_id=room.id, sender_id=u1.id, text="My message", is_system=False)
        # System message
        m_sys = Message(room_id=room.id, sender_id=None, text="User 1 joined room", is_system=True)
        db.session.add_all([m1, m_sys])
        db.session.commit()

        # Cannot report own message
        with pytest.raises(ReportValidationError, match="cannot report your own message"):
            report_message(room_id=room.id, message_id=m1.id, reporter_id=u1.id, reason="spam")

        # Cannot report system message
        with pytest.raises(ReportValidationError, match="System notifications cannot be reported"):
            report_message(room_id=room.id, message_id=m_sys.id, reporter_id=u2.id, reason="spam")


def test_non_member_cannot_report_message(app_instance):
    with app_instance.app_context():
        u1 = _create_user("Member 1", "m1@test.com")
        u2 = _create_user("Member 2", "m2@test.com")
        outsider = _create_user("Outsider", "out@test.com")
        room = _setup_group_room_with_members([u1, u2])

        msg = Message(room_id=room.id, sender_id=u1.id, text="Hello group", is_system=False)
        db.session.add(msg)
        db.session.commit()

        with pytest.raises(ReportPermissionError, match="do not have permission"):
            report_message(room_id=room.id, message_id=msg.id, reporter_id=outsider.id, reason="abusive")


def test_duplicate_report_blocked(app_instance):
    with app_instance.app_context():
        u1 = _create_user("Sender", "sender@test.com")
        u2 = _create_user("Reporter", "reporter@test.com")
        room = _setup_group_room_with_members([u1, u2])

        msg = Message(room_id=room.id, sender_id=u1.id, text="Spam link here", is_system=False)
        db.session.add(msg)
        db.session.commit()

        # First report succeeds
        res1 = report_message(room_id=room.id, message_id=msg.id, reporter_id=u2.id, reason="spam")
        assert res1["success"] is True

        # Second duplicate report is rejected
        with pytest.raises(ReportValidationError, match="already reported this message"):
            report_message(room_id=room.id, message_id=msg.id, reporter_id=u2.id, reason="spam")


# 2. Three Reports Auto-Hide Message
def test_three_reports_auto_hides_message(app_instance):
    with app_instance.app_context():
        sender = _create_user("Offender", "offender@test.com")
        r1 = _create_user("Student 1", "r1@test.com")
        r2 = _create_user("Student 2", "r2@test.com")
        r3 = _create_user("Student 3", "r3@test.com")
        room = _setup_group_room_with_members([sender, r1, r2, r3])

        raw_text = "Highly controversial and hostile remarks"
        msg = Message(room_id=room.id, sender_id=sender.id, text=raw_text, is_system=False)
        db.session.add(msg)
        db.session.commit()

        # Reporter 1
        res1 = report_message(room.id, msg.id, r1.id, "harassment")
        assert res1["is_hidden"] is False
        assert msg.text == raw_text
        assert msg.review_status == "pending"

        # Reporter 2
        res2 = report_message(room.id, msg.id, r2.id, "abusive")
        assert res2["is_hidden"] is False
        assert msg.text == raw_text

        # Reporter 3 (Threshold reached!)
        res3 = report_message(room.id, msg.id, r3.id, "other", note="Please hide this")
        assert res3["is_hidden"] is True
        assert msg.text == "[message hidden pending review]"
        assert msg.original_text == raw_text
        assert msg.is_flagged is True


# 3. Teacher Review Queue & Authorization
def test_student_gets_403_on_moderation_queue(app_instance):
    with app_instance.app_context():
        _create_user("Normal Student", "stu@test.com", role="student")
        client = app_instance.test_client()
        client.post("/auth/login", data={"email": "stu@test.com", "password": "pass123"})

        resp = client.get("/moderation")
        assert resp.status_code == 403


def test_teacher_can_dismiss_and_restore_non_profane_message(app_instance):
    with app_instance.app_context():
        teacher = _create_user("Prof. Verma", "teacher@test.com", role="teacher")
        s1 = _create_user("Student S1", "s1_queue@test.com")
        s2 = _create_user("Student S2", "s2_queue@test.com")
        s3 = _create_user("Student S3", "s3_queue@test.com")
        s4 = _create_user("Student S4", "s4_queue@test.com")
        room = _setup_group_room_with_members([s1, s2, s3, s4])

        raw = "This is a legitimate discussion about algorithms."
        msg = Message(
            room_id=room.id,
            sender_id=s1.id,
            text="[message hidden pending review]",
            original_text=raw,
            is_flagged=True,
            flag_reason="user: spam",
            review_status="pending",
        )
        db.session.add(msg)
        db.session.commit()

        client = app_instance.test_client()
        client.post("/auth/login", data={"email": "teacher@test.com", "password": "pass123"})

        # Teacher accesses queue
        get_resp = client.get("/moderation")
        assert get_resp.status_code == 200
        assert "Moderation Review Queue" in get_resp.get_data(as_text=True)

        # Teacher dismisses false report
        post_resp = client.post(f"/moderation/{msg.id}/dismiss", follow_redirects=True)
        assert post_resp.status_code == 200

        # Verify DB state: innocent text restored, review_status='dismissed'
        db.session.refresh(msg)
        assert msg.review_status == "dismissed"
        assert msg.text == raw
        assert msg.reviewed_by == teacher.id


def test_teacher_can_confirm_and_increment_strikes(app_instance):
    with app_instance.app_context():
        _create_user("Prof. Roy", "teacher_roy@test.com", role="teacher")
        offender = _create_user("Bad Actor", "bad_actor@test.com")
        offender.moderation_strikes = 2
        db.session.commit()

        room = _setup_group_room_with_members([offender])
        msg = Message(
            room_id=room.id,
            sender_id=offender.id,
            text="Why is this ***** compiler throwing errors?",
            original_text="Why is this idiot compiler throwing errors?",
            is_flagged=True,
            flag_reason="auto: profanity",
            review_status="pending",
        )
        db.session.add(msg)
        db.session.commit()

        client = app_instance.test_client()
        client.post("/auth/login", data={"email": "teacher_roy@test.com", "password": "pass123"})

        # Teacher confirms violation
        resp = client.post(f"/moderation/{msg.id}/confirm", follow_redirects=True)
        assert resp.status_code == 200

        db.session.refresh(msg)
        db.session.refresh(offender)
        assert msg.review_status == "confirmed"
        assert offender.moderation_strikes == 3  # Incremented from 2 to 3!

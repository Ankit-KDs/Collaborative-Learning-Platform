"""
Tests for Collaborative Study Groups (Stage 4).
Uses pytest with an in-memory SQLite database.
Validates all 12 core group constraints, permissions, capacity, and chat reuse rules.
"""

import pytest
from app import create_app, db
from app.models import ChatMember, ChatRoom, Message, Skill, User
from app.services.groups_service import (
    GroupServiceError,
    accept_invite,
    close_group,
    create_group,
    invite_user,
    leave_group,
    remove_member,
    suggest_members,
)


@pytest.fixture
def app_instance(tmp_path):
    """Create test application instance with temporary uploads and testing config."""
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _create_student(name: str, email: str, branch: str = "CS", year: int = 2) -> User:
    """Helper to create and persist a student account."""
    u = User(name=name, email=email, role="student", branch=branch, year=year)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


def _create_teacher(name: str, email: str) -> User:
    """Helper to create and persist a teacher account."""
    u = User(name=name, email=email, role="teacher", branch="CS", year=1)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


# 1. Non-admin cannot invite
def test_non_admin_cannot_invite(app_instance):
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        member = _create_student("Member Student", "member@test.com")
        candidate = _create_student("Candidate Student", "candidate@test.com")

        room = create_group(admin.id, "Algorithms Group", "DAA")

        # Add member to group
        db.session.add(ChatMember(room_id=room.id, user_id=member.id, role="member"))
        db.session.commit()

        with pytest.raises(GroupServiceError, match="Only group administrators have permission to invite"):
            invite_user(room_id=room.id, inviter_id=member.id, invited_user_id=candidate.id)


# 2. Group cannot exceed 5 members (including pending invites)
def test_group_cannot_exceed_max_size_with_pending_invites(app_instance):
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        room = create_group(admin.id, "Algorithms Group", "DAA")

        # Admin is 1 member. Invite 4 students -> total 5 (capacity full)
        candidates = [_create_student(f"Candidate {i}", f"c{i}@test.com") for i in range(1, 5)]
        for c in candidates:
            invite_user(room_id=room.id, inviter_id=admin.id, invited_user_id=c.id)

        # Attempt to invite a 6th student (5th candidate)
        extra = _create_student("Extra Student", "extra@test.com")
        with pytest.raises(GroupServiceError, match="capacity"):
            invite_user(room_id=room.id, inviter_id=admin.id, invited_user_id=extra.id)


# 3. Only the invited user can accept an invite
def test_only_invited_user_can_accept_invite(app_instance):
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        target = _create_student("Target Student", "target@test.com")
        intruder = _create_student("Intruder Student", "intruder@test.com")

        room = create_group(admin.id, "DAA Group", "DAA")
        invite = invite_user(room.id, admin.id, target.id)

        with pytest.raises(GroupServiceError, match="permission to accept this invitation"):
            accept_invite(invite.id, intruder.id)


# 4. Accepting a full group fails
def test_accepting_full_group_fails(app_instance):
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        target = _create_student("Target Student", "target@test.com")

        room = create_group(admin.id, "DAA Group", "DAA")
        invite = invite_user(room.id, admin.id, target.id)

        # Fill the group up to 5 members with other users
        for i in range(1, 5):
            u = _create_student(f"Filler {i}", f"filler{i}@test.com")
            db.session.add(ChatMember(room_id=room.id, user_id=u.id, role="member"))
        db.session.commit()

        # Target tries to accept when members count is already 5
        with pytest.raises(GroupServiceError, match="maximum capacity"):
            accept_invite(invite.id, target.id)


# 5. Teacher cannot create or join groups
def test_teacher_cannot_create_or_join_groups(app_instance):
    with app_instance.app_context():
        teacher = _create_teacher("Prof. Smith", "prof@test.com")
        admin = _create_student("Admin Student", "admin@test.com")

        # Teacher cannot create group
        with pytest.raises(GroupServiceError, match="Faculty accounts cannot create study groups"):
            create_group(teacher.id, "Faculty Group", "DAA")

        # Teacher cannot be invited to group
        room = create_group(admin.id, "Student Group", "DAA")
        with pytest.raises(GroupServiceError, match="Only students can be invited to study groups"):
            invite_user(room.id, admin.id, teacher.id)


# 6. Non-member gets 403 on group page and polling
def test_non_member_gets_403_on_group_page_and_polling(app_instance):
    client = app_instance.test_client()
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        outsider = _create_student("Outsider Student", "outsider@test.com")
        room = create_group(admin.id, "DAA Group", "DAA")
        room_id = room.id
        outsider_id = outsider.id

    # Log in as outsider
    with client.session_transaction() as sess:
        sess["_user_id"] = str(outsider_id)
        sess["_fresh"] = True

    # 1. Group room page
    res_page = client.get(f"/groups/{room_id}")
    assert res_page.status_code == 403

    # 2. Polling messages
    res_poll = client.get(f"/chats/{room_id}/messages")
    assert res_poll.status_code == 403

    # 3. Sending message
    res_send = client.post(f"/chats/{room_id}/send", data={"text": "Hello"})
    assert res_send.status_code == 403


# 7. Closed group rejects sends with 403
def test_closed_group_rejects_sends_with_403(app_instance):
    client = app_instance.test_client()
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        room = create_group(admin.id, "DAA Group", "DAA")
        close_group(room.id, admin.id)
        room_id = room.id
        admin_id = admin.id

    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin_id)
        sess["_fresh"] = True

    res = client.post(f"/chats/{room_id}/send", data={"text": "Trying to talk in closed group"})
    assert res.status_code == 403


# 8. Admin cannot leave while others remain
def test_admin_cannot_leave_while_others_remain(app_instance):
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        member = _create_student("Member Student", "member@test.com")

        room = create_group(admin.id, "DAA Group", "DAA")
        db.session.add(ChatMember(room_id=room.id, user_id=member.id, role="member"))
        db.session.commit()

        with pytest.raises(GroupServiceError, match="cannot leave while other students remain"):
            leave_group(room.id, admin.id)

        # But a regular member can leave
        leave_group(room.id, member.id)
        assert ChatMember.query.filter_by(room_id=room.id, user_id=member.id).first() is None


# 9. Remove member works only for admin
def test_remove_member_works_only_for_admin(app_instance):
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        member1 = _create_student("Member 1", "m1@test.com")
        member2 = _create_student("Member 2", "m2@test.com")

        room = create_group(admin.id, "DAA Group", "DAA")
        db.session.add(ChatMember(room_id=room.id, user_id=member1.id, role="member"))
        db.session.add(ChatMember(room_id=room.id, user_id=member2.id, role="member"))
        db.session.commit()

        # Non-admin cannot remove anyone
        with pytest.raises(GroupServiceError, match="Only group administrators can remove members"):
            remove_member(room.id, admin_id=member1.id, member_id=member2.id)

        # Admin cannot remove themselves
        with pytest.raises(GroupServiceError, match="cannot remove yourself as administrator"):
            remove_member(room.id, admin_id=admin.id, member_id=admin.id)

        # Admin removes member1
        remove_member(room.id, admin_id=admin.id, member_id=member1.id)
        assert ChatMember.query.filter_by(room_id=room.id, user_id=member1.id).first() is None

        # System message was generated
        sys_msg = Message.query.filter_by(room_id=room.id, is_system=True).order_by(Message.id.desc()).first()
        assert sys_msg is not None
        assert "was removed from the group" in sys_msg.text


# 10. suggest_members excludes existing members and pending invites
def test_suggest_members_excludes_existing_members_and_pending_invites(app_instance):
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com", branch="CS", year=2)
        existing_member = _create_student("Existing Member", "existing@test.com", branch="CS", year=2)
        pending_invitee = _create_student("Pending Invitee", "pending@test.com", branch="CS", year=2)
        valid_candidate = _create_student("Valid Candidate", "valid@test.com", branch="CS", year=2)

        # Assign skills in DAA
        db.session.add(Skill(user_id=valid_candidate.id, subject="DAA", level="Strong"))
        db.session.add(Skill(user_id=pending_invitee.id, subject="DAA", level="Strong"))
        db.session.add(Skill(user_id=existing_member.id, subject="DAA", level="Strong"))
        db.session.commit()

        room = create_group(admin.id, "DAA Group", "DAA")
        db.session.add(ChatMember(room_id=room.id, user_id=existing_member.id, role="member"))
        db.session.commit()

        # Invite pending_invitee
        invite_user(room.id, admin.id, pending_invitee.id)

        suggestions = suggest_members(room.id)
        all_suggested_ids = [s["user"].id for tier in suggestions.values() for s in tier]

        assert valid_candidate.id in all_suggested_ids
        assert existing_member.id not in all_suggested_ids
        assert pending_invitee.id not in all_suggested_ids
        assert admin.id not in all_suggested_ids


# 11. /chats does not list group rooms
def test_chats_list_does_not_show_group_rooms(app_instance):
    client = app_instance.test_client()
    with app_instance.app_context():
        u1 = _create_student("Student One", "s1@test.com")
        u2 = _create_student("Student Two", "s2@test.com")

        # 1. Private chat room between u1 and u2
        private_room = ChatRoom(type="private", is_active=True)
        db.session.add(private_room)
        db.session.flush()
        db.session.add(ChatMember(room_id=private_room.id, user_id=u1.id, role="member"))
        db.session.add(ChatMember(room_id=private_room.id, user_id=u2.id, role="member"))

        # 2. Group room where u1 is member
        _ = create_group(u1.id, "Special Secret Group", "DAA")
        u1_id = u1.id

    with client.session_transaction() as sess:
        sess["_user_id"] = str(u1_id)
        sess["_fresh"] = True

    res = client.get("/chats")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    # Private partner is visible
    assert "Student Two" in html
    # Group room name should NOT be listed under /chats
    assert "Special Secret Group" not in html


# 12. System messages cannot be created via send endpoint
def test_system_messages_cannot_be_created_via_send_endpoint(app_instance):
    client = app_instance.test_client()
    with app_instance.app_context():
        admin = _create_student("Admin Student", "admin@test.com")
        room = create_group(admin.id, "DAA Group", "DAA")
        room_id = room.id
        admin_id = admin.id

    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin_id)
        sess["_fresh"] = True

    # User attempts to spoof is_system=True
    res = client.post(
        f"/chats/{room_id}/send",
        data={"text": "I am pretending to be the system!", "is_system": "true"},
    )
    assert res.status_code == 201

    with app_instance.app_context():
        user_msg = Message.query.filter_by(room_id=room_id, text="I am pretending to be the system!").first()
        assert user_msg is not None
        assert user_msg.is_system is False

"""
Tests for Buddy Requests, Private 1-to-1 Chat, Polling, and Protected Image Attachments.
Uses pytest with an in-memory SQLite database.
"""

import io
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import create_app, db
from app.models import ChatRoom, Message, Skill, User
from app.services.requests_service import (
    RequestValidationError,
    accept_buddy_request,
    get_or_create_private_room,
    reject_buddy_request,
    send_buddy_request,
)
from app.services.uploads import InvalidImageError, save_image


@pytest.fixture
def app_instance(tmp_path):
    """Create test application instance with temporary uploads folder and testing config."""
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def create_mock_image(format="PNG") -> io.BytesIO:
    """Generate a valid in-memory image for upload testing."""
    buf = io.BytesIO()
    img = Image.new("RGB", (80, 80), color="blue")
    img.save(buf, format=format)
    buf.seek(0)
    return buf


def test_cannot_request_yourself(app_instance):
    """Requirement: Sender cannot send a buddy request to themselves."""
    with app_instance.app_context():
        u = User(name="Solo", email="solo@test.com", role="student", branch="CS", year=2)
        u.set_password("pass123")
        db.session.add(u)
        db.session.commit()
        db.session.add(Skill(user_id=u.id, subject="Python", level="Weak"))
        db.session.commit()

        with pytest.raises(RequestValidationError, match="cannot send a study buddy request to yourself"):
            send_buddy_request(sender_id=u.id, receiver_id=u.id, subject="Python")


def test_cannot_request_without_weak_strong_match(app_instance):
    """Requirement: Seeker must be Weak and helper must be Strong in the requested subject."""
    with app_instance.app_context():
        s = User(name="Seeker", email="s@test.com", role="student", branch="CS", year=2)
        s.set_password("pass123")
        h = User(name="Helper", email="h@test.com", role="student", branch="CS", year=2)
        h.set_password("pass123")
        db.session.add_all([s, h])
        db.session.commit()

        # Both are Average -> Invalid
        db.session.add(Skill(user_id=s.id, subject="DBMS", level="Average"))
        db.session.add(Skill(user_id=h.id, subject="DBMS", level="Strong"))
        db.session.commit()

        with pytest.raises(RequestValidationError, match="marked as 'Weak'"):
            send_buddy_request(sender_id=s.id, receiver_id=h.id, subject="DBMS")

        # Now fix seeker to Weak, but helper is Average -> Invalid
        s_skill = Skill.query.filter_by(user_id=s.id, subject="DBMS").first()
        h_skill = Skill.query.filter_by(user_id=h.id, subject="DBMS").first()
        assert s_skill is not None and h_skill is not None
        s_skill.level = "Weak"
        h_skill.level = "Average"
        db.session.commit()

        with pytest.raises(RequestValidationError, match="registered as 'Strong'"):
            send_buddy_request(sender_id=s.id, receiver_id=h.id, subject="DBMS")


def test_duplicate_pending_request_blocked(app_instance):
    """Requirement: Cannot send duplicate pending requests between the same pair for the same subject."""
    with app_instance.app_context():
        s = User(name="Seeker", email="s@test.com", role="student", branch="CS", year=2)
        s.set_password("pass123")
        h = User(name="Helper", email="h@test.com", role="student", branch="CS", year=2)
        h.set_password("pass123")
        db.session.add_all([s, h])
        db.session.commit()

        db.session.add(Skill(user_id=s.id, subject="DAA", level="Weak"))
        db.session.add(Skill(user_id=h.id, subject="DAA", level="Strong"))
        db.session.commit()

        # First request succeeds
        req1 = send_buddy_request(sender_id=s.id, receiver_id=h.id, subject="DAA")
        assert req1.status == "pending"

        # Duplicate attempt fails
        with pytest.raises(RequestValidationError, match="pending connection request already exists"):
            send_buddy_request(sender_id=s.id, receiver_id=h.id, subject="DAA")


def test_only_receiver_can_accept_and_creates_single_private_room(app_instance):
    """
    Requirement:
    - Only the receiver can accept a pending request.
    - Accepting creates exactly one private room with two members.
    - Subsequent calls or existing rooms are reused without duplication.
    """
    with app_instance.app_context():
        s = User(name="Seeker", email="s@test.com", role="student", branch="CS", year=2)
        s.set_password("pass123")
        h = User(name="Helper", email="h@test.com", role="student", branch="CS", year=2)
        h.set_password("pass123")
        third = User(name="Third Party", email="third@test.com", role="student", branch="CS", year=2)
        third.set_password("pass123")
        db.session.add_all([s, h, third])
        db.session.commit()

        db.session.add(Skill(user_id=s.id, subject="Java", level="Weak"))
        db.session.add(Skill(user_id=h.id, subject="Java", level="Strong"))
        db.session.commit()

        req = send_buddy_request(sender_id=s.id, receiver_id=h.id, subject="Java")

        # Sender cannot accept their own request
        with pytest.raises(RequestValidationError, match="do not have permission to accept"):
            accept_buddy_request(request_id=req.id, user_id=s.id)

        # Third party cannot accept
        with pytest.raises(RequestValidationError, match="do not have permission to accept"):
            accept_buddy_request(request_id=req.id, user_id=third.id)

        # Receiver accepts successfully
        room = accept_buddy_request(request_id=req.id, user_id=h.id)
        assert room is not None
        assert room.type == "private"
        assert room.members.count() == 2
        member_ids = {m.user_id for m in room.members.all()}
        assert member_ids == {s.id, h.id}

        # Verify no duplicate room created if get_or_create_private_room is called again
        room2 = get_or_create_private_room(s.id, h.id, subject="Java")
        assert room2.id == room.id
        assert ChatRoom.query.filter_by(type="private").count() == 1


def test_non_member_gets_403_on_chat_and_polling(app_instance):
    """Requirement: Users not in a room get HTTP 403 Forbidden when trying to access or poll messages."""
    client = app_instance.test_client()

    with app_instance.app_context():
        u1 = User(name="User 1", email="u1@test.com", role="student", branch="CS", year=2)
        u1.set_password("pass123")
        u2 = User(name="User 2", email="u2@test.com", role="student", branch="CS", year=2)
        u2.set_password("pass123")
        intruder = User(name="Intruder", email="intruder@test.com", role="student", branch="CS", year=2)
        intruder.set_password("pass123")
        db.session.add_all([u1, u2, intruder])
        db.session.commit()

        room = get_or_create_private_room(u1.id, u2.id, subject="Physics")
        room_id = room.id

    # Login as Intruder
    client.post("/auth/login", data={"email": "intruder@test.com", "password": "pass123"})

    # Try opening chat room -> 403
    res_page = client.get(f"/chats/{room_id}")
    assert res_page.status_code == 403

    # Try polling messages -> 403
    res_poll = client.get(f"/chats/{room_id}/messages")
    assert res_poll.status_code == 403

    # Try sending message -> 403
    res_send = client.post(f"/chats/{room_id}/send", data={"text": "Hello"})
    assert res_send.status_code == 403


def test_polling_with_after_id_returns_only_newer_messages(app_instance):
    """Requirement: Polling /chats/<room_id>/messages?after_id=<n> returns only messages with id > n."""
    client = app_instance.test_client()

    with app_instance.app_context():
        u1 = User(name="U1", email="u1@test.com", role="student", branch="CS", year=2)
        u1.set_password("pass123")
        u2 = User(name="U2", email="u2@test.com", role="student", branch="CS", year=2)
        u2.set_password("pass123")
        db.session.add_all([u1, u2])
        db.session.commit()

        room = get_or_create_private_room(u1.id, u2.id, subject="Python")
        room_id = room.id

        m1 = Message(room_id=room_id, sender_id=u1.id, text="Msg 1")
        m2 = Message(room_id=room_id, sender_id=u2.id, text="Msg 2")
        m3 = Message(room_id=room_id, sender_id=u1.id, text="Msg 3")
        db.session.add_all([m1, m2, m3])
        db.session.commit()

        m1_id, m2_id, m3_id = m1.id, m2.id, m3.id

    client.post("/auth/login", data={"email": "u1@test.com", "password": "pass123"})

    # Poll with after_id = m1_id -> should return m2 and m3
    res = client.get(f"/chats/{room_id}/messages?after_id={m1_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["messages"]) == 2
    returned_ids = [m["id"] for m in data["messages"]]
    assert returned_ids == [m2_id, m3_id]

    # Poll with after_id = m3_id -> should return 0 new messages
    res_latest = client.get(f"/chats/{room_id}/messages?after_id={m3_id}")
    assert res_latest.status_code == 200
    assert len(res_latest.get_json()["messages"]) == 0


def test_invalid_file_type_is_rejected(app_instance):
    """Requirement: Uploading invalid extensions or non-image files raises InvalidImageError."""
    with app_instance.app_context():
        # Text file disguised with .png extension
        fake_stream = io.BytesIO(b"this is plain text not an image binary")
        fs_fake = FileStorage(stream=fake_stream, filename="test.png", content_type="image/png")

        with pytest.raises(InvalidImageError, match="not a valid image or is corrupted"):
            save_image(fs_fake, subfolder="chats")

        # Prohibited extension
        real_img_stream = create_mock_image("PNG")
        fs_bad_ext = FileStorage(stream=real_img_stream, filename="script.exe", content_type="application/octet-stream")

        with pytest.raises(InvalidImageError, match="not permitted"):
            save_image(fs_bad_ext, subfolder="chats")

        # Valid PNG saves successfully
        valid_stream = create_mock_image("PNG")
        fs_valid = FileStorage(stream=valid_stream, filename="diagram.png", content_type="image/png")
        path = save_image(fs_valid, subfolder="chats")
        assert path.startswith("chats/")
        assert path.endswith(".png")


def test_rejected_cooldown_blocks_resending(app_instance):
    """Requirement: If a request was rejected, re-sending for the same pair and subject is blocked for 24 hours."""
    with app_instance.app_context():
        s = User(name="Seeker", email="s@test.com", role="student", branch="CS", year=2)
        s.set_password("pass123")
        h = User(name="Helper", email="h@test.com", role="student", branch="CS", year=2)
        h.set_password("pass123")
        db.session.add_all([s, h])
        db.session.commit()

        db.session.add(Skill(user_id=s.id, subject="Mathematics", level="Weak"))
        db.session.add(Skill(user_id=h.id, subject="Mathematics", level="Strong"))
        db.session.commit()

        req = send_buddy_request(sender_id=s.id, receiver_id=h.id, subject="Mathematics")
        reject_buddy_request(request_id=req.id, user_id=h.id)

        # Attempt to re-request immediately -> blocked by 24h cooldown
        with pytest.raises(RequestValidationError, match="declined. Please wait"):
            send_buddy_request(sender_id=s.id, receiver_id=h.id, subject="Mathematics")

        # Simulate 25 hours elapsed
        req.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=25)
        db.session.commit()

        # Re-requesting after 24h cooldown should succeed
        req2 = send_buddy_request(sender_id=s.id, receiver_id=h.id, subject="Mathematics")
        assert req2.status == "pending"

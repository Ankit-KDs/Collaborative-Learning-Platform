"""
Buddy Request and Private Chat Room Management Service.
Handles business logic for sending, accepting, rejecting, and cancelling buddy requests,
enforcing capacity caps, 24-hour cooldowns, role restrictions, and private room creation.
"""

from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import and_, or_

from app import db
from app.config import MAX_HELPER_LOAD
from app.models import BuddyRequest, ChatMember, ChatRoom, Skill, User
from app.services.matching import compute_helper_load


def utc_now() -> datetime:
    """Return timezone-naive UTC datetime for seamless SQLite compatibility."""
    return datetime.now(UTC).replace(tzinfo=None)


class RequestValidationError(Exception):
    """Raised when a buddy request violates domain constraints."""


def send_buddy_request(sender_id: int, receiver_id: int, subject: str) -> BuddyRequest:
    """
    Validate and dispatch a 1-to-1 study buddy connection request from a seeker to a helper.

    Validation Rules:
    a. Sender and receiver must both be students, and not the same user.
    b. Sender must be Weak and receiver must be Strong in that subject.
    c. No existing pending or accepted request between the same pair for the same subject (either direction).
    d. Receiver's load must be below MAX_HELPER_LOAD.
    e. If the same pair + subject was rejected earlier, block re-sending for 24 hours (cooldown).
    """
    if sender_id == receiver_id:
        raise RequestValidationError("You cannot send a study buddy request to yourself.")

    sender = db.session.get(User, sender_id)
    receiver = db.session.get(User, receiver_id)

    if not sender or not receiver:
        raise RequestValidationError("User account could not be found.")

    if not sender.is_student or not receiver.is_student:
        raise RequestValidationError("Study buddy requests can only be sent between student accounts.")

    # Rule b: Proficiency check (Seeker must be Weak, Helper must be Strong)
    sender_skill = Skill.query.filter_by(user_id=sender_id, subject=subject, level="Weak").first()
    if not sender_skill:
        raise RequestValidationError(f"You must be marked as 'Weak' in {subject} to request a study buddy.")

    receiver_skill = Skill.query.filter_by(user_id=receiver_id, subject=subject, level="Strong").first()
    if not receiver_skill:
        raise RequestValidationError(f"The selected peer is not registered as 'Strong' in {subject}.")

    # Rule c: Active request mutual exclusion (pending or accepted in either direction)
    existing_active = BuddyRequest.query.filter(
        BuddyRequest.subject == subject,
        BuddyRequest.status.in_(["pending", "accepted"]),
        or_(
            and_(BuddyRequest.sender_id == sender_id, BuddyRequest.receiver_id == receiver_id),
            and_(BuddyRequest.sender_id == receiver_id, BuddyRequest.receiver_id == sender_id),
        ),
    ).first()

    if existing_active:
        if existing_active.status == "accepted":
            raise RequestValidationError("You are already connected with this student for this subject.")
        raise RequestValidationError("A pending connection request already exists between you and this student.")

    # Rule d: Receiver active capacity check
    max_load = current_app.config.get("MAX_HELPER_LOAD", MAX_HELPER_LOAD)
    current_load = compute_helper_load(receiver_id)
    if current_load >= max_load:
        raise RequestValidationError("This helper is currently at maximum capacity. Please choose another match.")

    # Rule e: 24-hour cooldown after rejection
    recent_rejection = (
        BuddyRequest.query.filter(
            BuddyRequest.subject == subject,
            BuddyRequest.status == "rejected",
            or_(
                and_(BuddyRequest.sender_id == sender_id, BuddyRequest.receiver_id == receiver_id),
                and_(BuddyRequest.sender_id == receiver_id, BuddyRequest.receiver_id == sender_id),
            ),
        )
        .order_by(BuddyRequest.created_at.desc())
        .first()
    )

    if recent_rejection:
        elapsed = utc_now() - recent_rejection.created_at
        if elapsed < timedelta(hours=24):
            hours_left = max(1, 24 - int(elapsed.total_seconds() // 3600))
            raise RequestValidationError(
                f"A previous request for {subject} was declined. "
                f"Please wait {hours_left} more hour(s) before re-requesting."
            )

    # All validations passed -> create and persist request
    buddy_req = BuddyRequest(
        sender_id=sender_id,
        receiver_id=receiver_id,
        subject=subject,
        status="pending",
        created_at=utc_now(),
    )
    db.session.add(buddy_req)
    db.session.commit()
    return buddy_req


def accept_buddy_request(request_id: int, user_id: int) -> ChatRoom:
    """
    Accept a pending buddy request and unlock/create the private chat room.
    Only the intended recipient can accept.
    """
    req = db.session.get(BuddyRequest, request_id)
    if not req:
        raise RequestValidationError("The requested connection invitation does not exist.")

    if req.receiver_id != user_id:
        raise RequestValidationError("You do not have permission to accept this request.")

    if req.status != "pending":
        raise RequestValidationError(f"This request cannot be accepted because it is already {req.status}.")

    req.status = "accepted"

    # Create or retrieve the private chat room for this pair
    room = get_or_create_private_room(
        user1_id=req.sender_id,
        user2_id=req.receiver_id,
        subject=req.subject,
    )

    db.session.commit()
    return room


def reject_buddy_request(request_id: int, user_id: int) -> BuddyRequest:
    """
    Decline an incoming buddy request.
    Resets the timestamp to initiate the 24-hour cooldown period.
    Only the intended recipient can decline.
    """
    req = db.session.get(BuddyRequest, request_id)
    if not req:
        raise RequestValidationError("The requested connection invitation does not exist.")

    if req.receiver_id != user_id:
        raise RequestValidationError("You do not have permission to decline this request.")

    if req.status != "pending":
        raise RequestValidationError(f"This request cannot be declined because it is already {req.status}.")

    req.status = "rejected"
    req.created_at = utc_now()  # Cooldown starts from rejection moment
    db.session.commit()
    return req


def cancel_buddy_request(request_id: int, user_id: int) -> None:
    """
    Cancel an outgoing pending buddy request.
    Only the sender can cancel their own pending request.
    """
    req = db.session.get(BuddyRequest, request_id)
    if not req:
        raise RequestValidationError("The requested connection invitation does not exist.")

    if req.sender_id != user_id:
        raise RequestValidationError("You do not have permission to cancel this request.")

    if req.status != "pending":
        raise RequestValidationError(f"This request cannot be cancelled because it is already {req.status}.")

    db.session.delete(req)
    db.session.commit()


def get_or_create_private_room(user1_id: int, user2_id: int, subject: str | None = None) -> ChatRoom:
    """
    Retrieve existing private ChatRoom between two students, or instantiate a new one.
    Guarantees no duplicate rooms exist between the pair.
    """
    # Find room IDs where user1 is a member
    rooms_user1 = (
        db.session.query(ChatMember.room_id)
        .join(ChatRoom, ChatRoom.id == ChatMember.room_id)
        .filter(ChatRoom.type == "private", ChatMember.user_id == user1_id)
        .scalar_subquery()
    )

    # Find the room from that set where user2 is also a member
    common_room = (
        ChatRoom.query.filter(ChatRoom.id.in_(rooms_user1))
        .join(ChatMember, ChatMember.room_id == ChatRoom.id)
        .filter(ChatMember.user_id == user2_id)
        .first()
    )

    if common_room:
        if not common_room.is_active:
            common_room.is_active = True
        if subject and not common_room.subject:
            common_room.subject = subject
        db.session.commit()
        return common_room

    # Instantiate new private ChatRoom
    room = ChatRoom(
        type="private",
        name=None,
        subject=subject,
        created_by=user1_id,
        created_at=utc_now(),
        is_active=True,
    )
    db.session.add(room)
    db.session.flush()

    m1 = ChatMember(room_id=room.id, user_id=user1_id)
    m2 = ChatMember(room_id=room.id, user_id=user2_id)
    db.session.add_all([m1, m2])
    db.session.commit()

    return room

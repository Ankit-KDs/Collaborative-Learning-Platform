"""
Routes for 1-to-1 private chat rooms, real-time message polling, and protected image retrieval.
"""

from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models import ChatMember, ChatRoom, Message
from app.services.moderation import log_moderation_event, scan_text
from app.services.reports_service import (
    ReportPermissionError,
    ReportValidationError,
    report_message,
)
from app.services.uploads import InvalidImageError, save_image

chat_bp = Blueprint("chat", __name__, url_prefix="/chats")


def verify_room_membership(room_id: int, user_id: int) -> ChatRoom:
    """
    Ensure the user is an active member of the specified chat room.
    Raises 403 Forbidden if unauthorized, or 404 if the room does not exist.
    """
    room = db.session.get(ChatRoom, room_id)
    if not room:
        abort(404)

    is_member = ChatMember.query.filter_by(room_id=room_id, user_id=user_id).first()
    if not is_member:
        abort(403)

    return room


@chat_bp.route("", methods=["GET"])
@login_required
def list_chats():
    """
    List all active private chat rooms for the authenticated user.
    Shows the study partner's profile, focus subject, and last message preview.
    """
    # Query private chat rooms where current_user is a member
    rooms = (
        ChatRoom.query.join(ChatMember, ChatMember.room_id == ChatRoom.id)
        .filter(
            ChatMember.user_id == current_user.id,
            ChatRoom.type == "private",
            ChatRoom.is_active.is_(True),
        )
        .order_by(ChatRoom.created_at.desc())
        .all()
    )

    room_items = []
    for r in rooms:
        # Identify the other student in the private room
        other_member = [m.user for m in r.members if m.user_id != current_user.id]
        other_user = other_member[0] if other_member else None

        last_message = (
            r.messages.order_by(Message.created_at.desc()).first()
        )

        room_items.append({
            "room": r,
            "other_user": other_user,
            "last_message": last_message,
        })

    return render_template(
        "chat/list.html",
        title="Your Chats",
        room_items=room_items,
    )


@chat_bp.route("/<int:room_id>", methods=["GET"])
@login_required
def chat_room(room_id: int):
    """
    Render 1-to-1 private chat interface.
    Fetches the initial 50 recent messages in chronological order.
    """
    room = verify_room_membership(room_id, current_user.id)

    other_member = room.members.filter(ChatMember.user_id != current_user.id).first()
    other_user = other_member.user if other_member else None

    # Fetch last 50 messages, ordered oldest to newest for initial render
    recent_messages = (
        Message.query.filter_by(room_id=room.id).order_by(Message.created_at.desc())
        .limit(50)
        .all()
    )
    recent_messages.reverse()

    return render_template(
        "chat/room.html",
        title=f"Chat with {other_user.name if other_user else 'Peer'}",
        room=room,
        other_user=other_user,
        initial_messages=recent_messages,
    )


@chat_bp.route("/<int:room_id>/send", methods=["POST"])
@login_required
def send_message(room_id: int):
    """
    Post a new text message and/or image attachment to a chat room.
    Returns JSON of the created message for dynamic DOM insertion.
    """
    room = verify_room_membership(room_id, current_user.id)
    if not room.is_active:
        abort(403)

    text = request.form.get("text", "").strip()
    image_file = request.files.get("image")

    # Constraint: Reject if both text and image are empty
    has_image = bool(image_file and image_file.filename and image_file.filename.strip())
    if not text and not has_image:
        return jsonify({"error": "Message cannot be empty. Please enter text or attach an image."}), 400

    # Constraint: Text max 1000 characters
    if len(text) > 1000:
        return jsonify({"error": "Message exceeds the maximum limit of 1000 characters."}), 400

    image_rel_path = None
    if has_image and image_file is not None:
        try:
            image_rel_path = save_image(image_file, subfolder="chats")
        except InvalidImageError as e:
            return jsonify({"error": str(e)}), 400

    # Moderation: Auto-detect profanity using Aho-Corasick
    scan_res = scan_text(text) if text else {"is_flagged": False, "matched_count": 0, "masked_text": text}
    is_flagged = bool(scan_res["is_flagged"])
    stored_text = scan_res["masked_text"] if is_flagged else text
    original_text = text if is_flagged else None
    flag_reason = "auto: profanity" if is_flagged else None
    review_status = "pending" if is_flagged else "none"

    if is_flagged:
        log_moderation_event(
            user_id=current_user.id,
            source="chat",
            action="flagged",
            matched_count=int(scan_res["matched_count"]),
        )

    msg = Message(
        room_id=room.id,
        sender_id=current_user.id,
        text=stored_text,
        original_text=original_text,
        image_path=image_rel_path,
        is_system=False,
        is_flagged=is_flagged,
        flag_reason=flag_reason,
        review_status=review_status,
    )
    db.session.add(msg)
    db.session.commit()

    image_url = None
    if msg.image_path:
        image_url = url_for("chat.get_message_image", room_id=room.id, message_id=msg.id)

    payload: dict[str, Any] = {
        "id": msg.id,
        "sender_id": msg.sender_id,
        "sender_name": current_user.name,
        "text": msg.text,
        "image_url": image_url,
        "is_system": False,
        "created_at": msg.created_at.strftime("%I:%M %p"),
        "created_at_iso": msg.created_at.isoformat(),
        "is_self": True,
    }
    if is_flagged:
        payload["warning"] = "Your message contained inappropriate language and was masked."

    return jsonify(payload), 201


@chat_bp.route("/<int:room_id>/messages", methods=["GET"])
@login_required
def poll_messages(room_id: int):
    """
    Polling endpoint returning all messages with ID > after_id,
    plus hidden message IDs so already-rendered client DOM elements can be updated.
    """
    room = verify_room_membership(room_id, current_user.id)
    after_id = request.args.get("after_id", 0, type=int)

    new_messages = (
        room.messages.filter(Message.id > after_id)
        .order_by(Message.id.asc())
        .all()
    )

    items = []
    for m in new_messages:
        img_url = None
        if m.image_path:
            img_url = url_for("chat.get_message_image", room_id=room.id, message_id=m.id)

        items.append({
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_name": m.sender.name if m.sender else "System",
            "text": m.text,
            "image_url": img_url,
            "is_system": m.is_system,
            "created_at": m.created_at.strftime("%I:%M %p"),
            "created_at_iso": m.created_at.isoformat(),
            "is_self": (m.sender_id == current_user.id and not m.is_system),
        })

    # Find any messages currently in hidden status
    hidden_ids: list[int] = [
        row[0]
        for row in room.messages.filter(
            Message.text == "[message hidden pending review]",
        )
        .with_entities(Message.id)
        .all()
    ]

    return jsonify({"messages": items, "hidden_ids": hidden_ids})


@chat_bp.route("/<int:room_id>/messages/<int:message_id>/report", methods=["POST"])
@login_required
def report_chat_message(room_id: int, message_id: int):
    """
    AJAX endpoint for reporting an abusive or inappropriate chat message.
    """
    data = request.get_json(silent=True) or request.form
    reason = str(data.get("reason", "")).strip()
    note = str(data.get("note", "")).strip()

    try:
        res = report_message(
            room_id=room_id,
            message_id=message_id,
            reporter_id=current_user.id,
            reason=reason,
            note=note,
        )
        return jsonify(res), 200
    except ReportPermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ReportValidationError as e:
        return jsonify({"error": str(e)}), 400


@chat_bp.route("/<int:room_id>/image/<int:message_id>", methods=["GET"])
@login_required
def get_message_image(room_id: int, message_id: int):
    """
    Serve message image attachment securely.
    Verifies that the requester is a member of the chat room to prevent URL guessing.
    """
    room = verify_room_membership(room_id, current_user.id)

    msg = Message.query.filter_by(id=message_id, room_id=room.id).first_or_404()
    if not msg.image_path:
        abort(404)

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    full_path = (upload_root / msg.image_path).resolve()

    # Prevent directory traversal attacks
    if not full_path.is_relative_to(upload_root) or not full_path.is_file():
        abort(404)

    return send_from_directory(str(full_path.parent), full_path.name)

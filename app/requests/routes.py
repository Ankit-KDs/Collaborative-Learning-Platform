"""
Routes for student study buddy requests (sending, listing, accepting, declining, and cancelling).
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import BuddyRequest, ChatMember, ChatRoom
from app.services.requests_service import (
    RequestValidationError,
    accept_buddy_request,
    cancel_buddy_request,
    reject_buddy_request,
    send_buddy_request,
)

requests_bp = Blueprint("requests", __name__, url_prefix="/requests")


def get_private_room_map(user_id: int) -> dict[int, int]:
    """
    Map peer_user_id -> room_id for all private rooms involving user_id.
    Used to generate 'Open Chat' links for accepted requests.
    """
    memberships = (
        db.session.query(ChatRoom.id, ChatMember.user_id)
        .join(ChatMember, ChatMember.room_id == ChatRoom.id)
        .filter(ChatRoom.type == "private")
        .all()
    )
    # Group by room_id
    room_members: dict[int, set[int]] = {}
    for r_id, u_id in memberships:
        room_members.setdefault(r_id, set()).add(u_id)

    peer_to_room: dict[int, int] = {}
    for r_id, members in room_members.items():
        if user_id in members and len(members) == 2:
            peer_id = next(m for m in members if m != user_id)
            peer_to_room[peer_id] = r_id

    return peer_to_room


@requests_bp.route("", methods=["GET"])
@login_required
def list_requests():
    """
    Display incoming and sent study buddy requests in dedicated tabs.
    """
    if current_user.is_teacher:
        return render_template(
            "requests/requests.html",
            title="Buddy Requests",
            is_teacher=True,
            incoming_requests=[],
            sent_requests=[],
            peer_to_room={},
        )

    incoming_requests = (
        BuddyRequest.query.filter_by(receiver_id=current_user.id, status="pending")
        .order_by(BuddyRequest.created_at.desc())
        .all()
    )

    sent_requests = (
        BuddyRequest.query.filter_by(sender_id=current_user.id)
        .order_by(BuddyRequest.created_at.desc())
        .all()
    )

    peer_to_room = get_private_room_map(current_user.id)

    return render_template(
        "requests/requests.html",
        title="Study Buddy Requests",
        is_teacher=False,
        incoming_requests=incoming_requests,
        sent_requests=sent_requests,
        peer_to_room=peer_to_room,
    )


@requests_bp.route("/send", methods=["POST"])
@login_required
def send_request():
    """
    Dispatch a buddy request from the Matches page.
    """
    if current_user.is_teacher:
        flash("Faculty accounts cannot send peer study buddy requests.", "warning")
        return redirect(url_for("main.dashboard"))

    receiver_id = request.form.get("receiver_id", type=int)
    subject = request.form.get("subject", "").strip()

    if not receiver_id or not subject:
        flash("Invalid request parameters.", "danger")
        return redirect(url_for("matches.matches"))

    try:
        req = send_buddy_request(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            subject=subject,
        )
        flash(f"Study buddy request sent to {req.receiver.name} for {subject}!", "success")
    except RequestValidationError as e:
        flash(str(e), "danger")

    return redirect(url_for("matches.matches"))


@requests_bp.route("/<int:request_id>/accept", methods=["POST"])
@login_required
def accept_request(request_id: int):
    """
    Accept an incoming study buddy request and redirect directly into the unlocked private chat.
    """
    try:
        room = accept_buddy_request(request_id=request_id, user_id=current_user.id)
        flash("Buddy request accepted! Your private chat room is now open.", "success")
        return redirect(url_for("chat.chat_room", room_id=room.id))
    except RequestValidationError as e:
        flash(str(e), "danger")
        return redirect(url_for("requests.list_requests"))


@requests_bp.route("/<int:request_id>/reject", methods=["POST"])
@login_required
def reject_request(request_id: int):
    """
    Decline an incoming study buddy request.
    """
    try:
        reject_buddy_request(request_id=request_id, user_id=current_user.id)
        flash("Connection request declined.", "info")
    except RequestValidationError as e:
        flash(str(e), "danger")

    return redirect(url_for("requests.list_requests"))


@requests_bp.route("/<int:request_id>/cancel", methods=["POST"])
@login_required
def cancel_request(request_id: int):
    """
    Cancel an outgoing pending study buddy request.
    """
    try:
        cancel_buddy_request(request_id=request_id, user_id=current_user.id)
        flash("Buddy request cancelled successfully.", "info")
    except RequestValidationError as e:
        flash(str(e), "danger")

    return redirect(url_for("requests.list_requests"))

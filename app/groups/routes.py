"""
Routes for study group creation, membership management, invitations, and group chats.
"""

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.groups import groups_bp
from app.groups.forms import CreateGroupForm
from app.models import ChatMember, ChatRoom, GroupInvite, Message
from app.services.groups_service import (
    GroupServiceError,
    accept_invite,
    cancel_invite,
    close_group,
    create_group,
    decline_invite,
    get_group_view_data,
    get_user_pending_invites,
    get_user_study_groups,
    invite_user,
    leave_group,
    remove_member,
)


@groups_bp.route("", methods=["GET"])
@groups_bp.route("/", methods=["GET"])
@login_required
def index():
    """
    Overview page for study groups.
    Shows the user's groups, pending invitations, and button to create a new group.
    Displays an informative faculty view for teachers.
    """
    if current_user.is_teacher:
        return render_template(
            "groups/index.html",
            title="Study Groups",
            is_teacher=True,
            user_groups=[],
            pending_invites=[],
        )

    user_groups = get_user_study_groups(current_user.id)
    pending_invites = get_user_pending_invites(current_user.id)

    return render_template(
        "groups/index.html",
        title="Study Groups",
        is_teacher=False,
        user_groups=user_groups,
        pending_invites=pending_invites,
    )


@groups_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    """
    Form to create a new collaborative study group.
    Restricted to student accounts.
    """
    if current_user.is_teacher:
        flash("Faculty accounts cannot create student study groups.", "warning")
        return redirect(url_for("groups.index"))

    form = CreateGroupForm()
    if form.validate_on_submit():
        try:
            room = create_group(
                creator_id=current_user.id,
                name=form.name.data or "",
                subject=form.subject.data or "",
            )
            flash(f"Study group '{room.name}' created successfully!", "success")
            return redirect(url_for("groups.group_room", room_id=room.id))
        except GroupServiceError as e:
            flash(str(e), "danger")

    return render_template(
        "groups/create.html",
        title="Create Study Group",
        form=form,
    )


@groups_bp.route("/<int:room_id>", methods=["GET"])
@login_required
def group_room(room_id: int):
    """
    Group chat view and roster administration.
    Only active members can access (returns 403 otherwise).
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        abort(404)

    member = ChatMember.query.filter_by(room_id=room_id, user_id=current_user.id).first()
    if not member:
        abort(403)

    try:
        data = get_group_view_data(room_id, current_user.id)
    except GroupServiceError:
        abort(403)

    # Initial 50 recent messages in chronological order
    recent_messages = (
        Message.query.filter_by(room_id=room.id)
        .order_by(Message.created_at.desc())
        .limit(50)
        .all()
    )
    recent_messages.reverse()

    return render_template(
        "groups/room.html",
        title=f"Group: {room.name}",
        data=data,
        room=room,
        is_admin=data["is_admin"],
        initial_messages=recent_messages,
    )


@groups_bp.route("/<int:room_id>/invite", methods=["POST"])
@login_required
def send_invite(room_id: int):
    """
    Admin sends an invitation to a prospective student member.
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        abort(404)

    admin_member = ChatMember.query.filter_by(room_id=room_id, user_id=current_user.id, role="admin").first()
    if not admin_member:
        abort(403)

    invited_user_id = request.form.get("invited_user_id", type=int)
    if not invited_user_id:
        flash("Invalid student selected.", "danger")
        return redirect(url_for("groups.group_room", room_id=room_id))

    try:
        invite = invite_user(
            room_id=room_id,
            inviter_id=current_user.id,
            invited_user_id=invited_user_id,
        )
        flash(f"Invitation successfully dispatched to {invite.invited_user.name}!", "success")
    except GroupServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for("groups.group_room", room_id=room_id))


@groups_bp.route("/invites/<int:invite_id>/accept", methods=["POST"])
@login_required
def accept_group_invite(invite_id: int):
    """
    Invited student accepts a pending group invitation.
    """
    invite = db.session.get(GroupInvite, invite_id)
    if not invite:
        abort(404)

    if invite.invited_user_id != current_user.id:
        abort(403)

    try:
        room = accept_invite(invite_id, current_user.id)
        flash(f"You have successfully joined '{room.name}'!", "success")
        return redirect(url_for("groups.group_room", room_id=room.id))
    except GroupServiceError as e:
        flash(str(e), "danger")
        return redirect(url_for("groups.index"))


@groups_bp.route("/invites/<int:invite_id>/decline", methods=["POST"])
@login_required
def decline_group_invite(invite_id: int):
    """
    Invited student declines a pending group invitation.
    """
    invite = db.session.get(GroupInvite, invite_id)
    if not invite:
        abort(404)

    if invite.invited_user_id != current_user.id:
        abort(403)

    try:
        decline_invite(invite_id, current_user.id)
        flash("Group invitation declined.", "info")
    except GroupServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for("groups.index"))


@groups_bp.route("/invites/<int:invite_id>/cancel", methods=["POST"])
@login_required
def cancel_group_invite(invite_id: int):
    """
    Admin cancels an outgoing pending group invitation.
    """
    invite = db.session.get(GroupInvite, invite_id)
    if not invite:
        abort(404)

    admin_member = ChatMember.query.filter_by(room_id=invite.room_id, user_id=current_user.id, role="admin").first()
    if not admin_member:
        abort(403)

    room_id = invite.room_id
    try:
        cancel_invite(invite_id, current_user.id)
        flash("Group invitation cancelled.", "info")
    except GroupServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for("groups.group_room", room_id=room_id))


@groups_bp.route("/<int:room_id>/leave", methods=["POST"])
@login_required
def leave(room_id: int):
    """
    Student leaves an active study group.
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        abort(404)

    member = ChatMember.query.filter_by(room_id=room_id, user_id=current_user.id).first()
    if not member:
        abort(403)

    try:
        leave_group(room_id, current_user.id)
        flash(f"You have left '{room.name}'.", "info")
        return redirect(url_for("groups.index"))
    except GroupServiceError as e:
        flash(str(e), "danger")
        return redirect(url_for("groups.group_room", room_id=room_id))


@groups_bp.route("/<int:room_id>/remove/<int:member_id>", methods=["POST"])
@login_required
def remove(room_id: int, member_id: int):
    """
    Admin removes a member from the study group.
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        abort(404)

    admin_member = ChatMember.query.filter_by(room_id=room_id, user_id=current_user.id, role="admin").first()
    if not admin_member:
        abort(403)

    try:
        remove_member(room_id, current_user.id, member_id)
        flash("Member has been removed from the study group.", "info")
    except GroupServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for("groups.group_room", room_id=room_id))


@groups_bp.route("/<int:room_id>/close", methods=["POST"])
@login_required
def close(room_id: int):
    """
    Admin archives and closes the study group, transitioning it to read-only.
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        abort(404)

    admin_member = ChatMember.query.filter_by(room_id=room_id, user_id=current_user.id, role="admin").first()
    if not admin_member:
        abort(403)

    try:
        close_group(room_id, current_user.id)
        flash("The study group has been closed and archived (read-only).", "warning")
    except GroupServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for("groups.group_room", room_id=room_id))

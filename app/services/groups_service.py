"""
Study Group Management & Collaborative Group Service
=====================================================
Handles business logic for:
- Study group creation (3-5 members max, 1 student max 5 active groups)
- Group member invitations and capacity enforcement
- Invitation lifecycle (accept, decline, cancel)
- Group moderation (remove member, leave group, close group)
- Pedagogically-balanced group recommendation engine (suggest_members)
"""

from typing import Any
from flask import current_app

from app import db
from app.config import GROUP_MAX_SIZE, MAX_USER_GROUPS, SUBJECTS
from app.models import ChatMember, ChatRoom, GroupInvite, Message, Skill, User, utc_now
from app.services.moderation import ModerationBlockedError, validate_content_profanity


class GroupServiceError(Exception):
    """Raised when an operation violates study group business logic or constraints."""


def get_user_active_groups_count(user_id: int) -> int:
    """
    Count how many active study groups a student is currently a member of.
    """
    return (
        db.session.query(ChatMember.id)
        .join(ChatRoom, ChatRoom.id == ChatMember.room_id)
        .filter(
            ChatMember.user_id == user_id,
            ChatRoom.type == "group",
            ChatRoom.is_active.is_(True),
        )
        .count()
    )


def create_group(creator_id: int, name: str, subject: str) -> ChatRoom:
    """
    Create a new study group room.

    Constraints:
    - Creator must be an authenticated student.
    - Group name must be 3-50 characters.
    - Subject must be a canonical subject from SUBJECTS.
    - Creator cannot be an active member of more than MAX_USER_GROUPS (5).
    - Creator is assigned the 'admin' role in ChatMember.
    - A system broadcast message is created to mark group instantiation.
    """
    creator = db.session.get(User, creator_id)
    if not creator:
        raise GroupServiceError("User account not found.")

    if not creator.is_student:
        raise GroupServiceError("Faculty accounts cannot create study groups.")

    clean_name = (name or "").strip()
    if len(clean_name) < 3 or len(clean_name) > 50:
        raise GroupServiceError("Group name must be between 3 and 50 characters.")

    # Profanity moderation check: reject offensive group names
    try:
        validate_content_profanity(clean_name, source="chat", user_id=creator_id)
    except ModerationBlockedError as e:
        raise GroupServiceError(e.message) from e

    if subject not in SUBJECTS:
        raise GroupServiceError(f"Subject '{subject}' is not in the recognized subjects list.")

    active_groups = get_user_active_groups_count(creator_id)
    max_groups = current_app.config.get("MAX_USER_GROUPS", MAX_USER_GROUPS)
    if active_groups >= max_groups:
        raise GroupServiceError(f"You cannot join or create more than {max_groups} active study groups.")

    room = ChatRoom(
        type="group",
        name=clean_name,
        subject=subject,
        created_by=creator_id,
        is_active=True,
        created_at=utc_now(),
    )
    db.session.add(room)
    db.session.flush()

    # Creator is granted the 'admin' role
    admin_member = ChatMember(
        room_id=room.id,
        user_id=creator_id,
        role="admin",
        joined_at=utc_now(),
    )
    db.session.add(admin_member)

    # Initial system message
    sys_msg = Message(
        room_id=room.id,
        sender_id=creator_id,
        text=f"{creator.name} created the study group.",
        is_system=True,
        created_at=utc_now(),
    )
    db.session.add(sys_msg)

    db.session.commit()
    return room


def invite_user(room_id: int, inviter_id: int, invited_user_id: int) -> GroupInvite:
    """
    Invite a prospective student member to a study group.

    Constraints:
    - Room must exist, be of type 'group', and be active.
    - Inviter must be an active 'admin' of the group.
    - Invited user must be a student and cannot be the inviter themselves.
    - Invited user cannot already be a member of the group.
    - Invited user cannot have an existing 'pending' invitation for this room.
    - Capacity check: (active members + pending invites) < GROUP_MAX_SIZE (5).
    - Invited user must not exceed MAX_USER_GROUPS (5).
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        raise GroupServiceError("Study group does not exist.")

    if not room.is_active:
        raise GroupServiceError("Cannot invite members to an archived or closed group.")

    # Admin verification
    inviter_member = ChatMember.query.filter_by(room_id=room_id, user_id=inviter_id).first()
    if not inviter_member or inviter_member.role != "admin":
        raise GroupServiceError("Only group administrators have permission to invite new members.")

    if inviter_id == invited_user_id:
        raise GroupServiceError("You cannot invite yourself to the group.")

    invited_user = db.session.get(User, invited_user_id)
    if not invited_user:
        raise GroupServiceError("Selected student could not be found.")

    if not invited_user.is_student:
        raise GroupServiceError("Only students can be invited to study groups.")

    # Membership check
    existing_member = ChatMember.query.filter_by(room_id=room_id, user_id=invited_user_id).first()
    if existing_member:
        raise GroupServiceError(f"{invited_user.name} is already a member of this study group.")

    # Pending invitation check
    existing_invite = GroupInvite.query.filter_by(
        room_id=room_id,
        invited_user_id=invited_user_id,
        status="pending",
    ).first()
    if existing_invite:
        raise GroupServiceError(f"A pending invitation already exists for {invited_user.name}.")

    # Capacity check (Active members + Pending invites vs GROUP_MAX_SIZE)
    max_size = current_app.config.get("GROUP_MAX_SIZE", GROUP_MAX_SIZE)
    current_members = ChatMember.query.filter_by(room_id=room_id).count()
    current_pending = GroupInvite.query.filter_by(room_id=room_id, status="pending").count()
    total_committed = current_members + current_pending

    if total_committed >= max_size:
        raise GroupServiceError(
            f"This study group is at full capacity ({max_size} members including pending invitations)."
        )

    # User active group limit
    max_groups = current_app.config.get("MAX_USER_GROUPS", MAX_USER_GROUPS)
    user_active_groups = get_user_active_groups_count(invited_user_id)
    if user_active_groups >= max_groups:
        raise GroupServiceError(
            f"{invited_user.name} has already reached the maximum limit of {max_groups} active study groups."
        )

    invite = GroupInvite(
        room_id=room_id,
        invited_user_id=invited_user_id,
        invited_by_id=inviter_id,
        status="pending",
        created_at=utc_now(),
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def accept_invite(invite_id: int, user_id: int) -> ChatRoom:
    """
    Accept an invitation and add the student as a group member.

    Constraints:
    - Only the designated recipient can accept.
    - Invitation must be in 'pending' status.
    - Room must still be active and current member count < GROUP_MAX_SIZE.
    - Student cannot exceed MAX_USER_GROUPS.
    - Inserts a system notification into chat.
    """
    invite = db.session.get(GroupInvite, invite_id)
    if not invite:
        raise GroupServiceError("Group invitation does not exist.")

    if invite.invited_user_id != user_id:
        raise GroupServiceError("You do not have permission to accept this invitation.")

    if invite.status != "pending":
        raise GroupServiceError(f"This invitation cannot be accepted because it is already {invite.status}.")

    room = db.session.get(ChatRoom, invite.room_id)
    if not room or not room.is_active:
        raise GroupServiceError("This study group is no longer active.")

    max_size = current_app.config.get("GROUP_MAX_SIZE", GROUP_MAX_SIZE)
    current_members = ChatMember.query.filter_by(room_id=room.id).count()
    if current_members >= max_size:
        raise GroupServiceError(f"This study group has reached its maximum capacity of {max_size} members.")

    max_groups = current_app.config.get("MAX_USER_GROUPS", MAX_USER_GROUPS)
    if get_user_active_groups_count(user_id) >= max_groups:
        raise GroupServiceError(f"You cannot join more than {max_groups} active study groups.")

    # Check if somehow already a member
    already_member = ChatMember.query.filter_by(room_id=room.id, user_id=user_id).first()
    if not already_member:
        member = ChatMember(
            room_id=room.id,
            user_id=user_id,
            role="member",
            joined_at=utc_now(),
        )
        db.session.add(member)

    invite.status = "accepted"

    # Insert broadcast system message
    joining_user = db.session.get(User, user_id)
    sys_msg = Message(
        room_id=room.id,
        sender_id=user_id,
        text=f"{joining_user.name if joining_user else 'A new student'} joined the study group.",
        is_system=True,
        created_at=utc_now(),
    )
    db.session.add(sys_msg)

    db.session.commit()
    return room


def decline_invite(invite_id: int, user_id: int) -> GroupInvite:
    """
    Decline an incoming study group invitation.
    """
    invite = db.session.get(GroupInvite, invite_id)
    if not invite:
        raise GroupServiceError("Group invitation does not exist.")

    if invite.invited_user_id != user_id:
        raise GroupServiceError("You do not have permission to decline this invitation.")

    if invite.status != "pending":
        raise GroupServiceError(f"This invitation cannot be declined because it is already {invite.status}.")

    invite.status = "declined"
    db.session.commit()
    return invite


def cancel_invite(invite_id: int, admin_id: int) -> GroupInvite:
    """
    Cancel an outgoing pending invitation.
    Only an administrator of the group can cancel.
    """
    invite = db.session.get(GroupInvite, invite_id)
    if not invite:
        raise GroupServiceError("Group invitation does not exist.")

    if invite.status != "pending":
        raise GroupServiceError(f"This invitation cannot be cancelled because it is already {invite.status}.")

    admin_member = ChatMember.query.filter_by(room_id=invite.room_id, user_id=admin_id, role="admin").first()
    if not admin_member:
        raise GroupServiceError("Only group administrators can cancel invitations.")

    invite.status = "cancelled"
    db.session.commit()
    return invite


def leave_group(room_id: int, user_id: int) -> None:
    """
    Leave a study group.

    Constraints:
    - User must be an active member of the group.
    - The admin cannot leave while other members remain in the group.
      (They must remove other members, transfer role, or close the group).
    - If the last remaining member leaves, the group is automatically archived (is_active=False).
    - Inserts a system broadcast message into chat.
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        raise GroupServiceError("Study group does not exist.")

    member = ChatMember.query.filter_by(room_id=room_id, user_id=user_id).first()
    if not member:
        raise GroupServiceError("You are not a member of this study group.")

    total_members = ChatMember.query.filter_by(room_id=room_id).count()

    if member.role == "admin" and total_members > 1:
        raise GroupServiceError(
            "As group administrator, you cannot leave while other students remain. "
            "Please remove members or close the study group instead."
        )

    user = db.session.get(User, user_id)
    user_name = user.name if user else "A student"

    db.session.delete(member)

    if total_members == 1:
        room.is_active = False

    sys_msg = Message(
        room_id=room.id,
        sender_id=user_id,
        text=f"{user_name} left the study group.",
        is_system=True,
        created_at=utc_now(),
    )
    db.session.add(sys_msg)

    db.session.commit()


def remove_member(room_id: int, admin_id: int, member_id: int) -> None:
    """
    Remove a member from the group.
    Admin only; admin cannot remove themselves (must use leave_group or close_group).
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        raise GroupServiceError("Study group does not exist.")

    admin_member = ChatMember.query.filter_by(room_id=room_id, user_id=admin_id, role="admin").first()
    if not admin_member:
        raise GroupServiceError("Only group administrators can remove members.")

    if admin_id == member_id:
        raise GroupServiceError("You cannot remove yourself as administrator. Use Close Group instead.")

    target_member = ChatMember.query.filter_by(room_id=room_id, user_id=member_id).first()
    if not target_member:
        raise GroupServiceError("The specified user is not a member of this study group.")

    target_user = db.session.get(User, member_id)
    target_name = target_user.name if target_user else "Student"
    admin_user = db.session.get(User, admin_id)
    admin_name = admin_user.name if admin_user else "Administrator"

    db.session.delete(target_member)

    sys_msg = Message(
        room_id=room.id,
        sender_id=admin_id,
        text=f"{target_name} was removed from the group by {admin_name}.",
        is_system=True,
        created_at=utc_now(),
    )
    db.session.add(sys_msg)

    db.session.commit()


def close_group(room_id: int, admin_id: int) -> None:
    """
    Close and archive a study group.
    Admin only; sets room.is_active = False.
    Closed groups become read-only: historical messages remain visible, but sends are blocked.
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        raise GroupServiceError("Study group does not exist.")

    admin_member = ChatMember.query.filter_by(room_id=room_id, user_id=admin_id, role="admin").first()
    if not admin_member:
        raise GroupServiceError("Only group administrators can close the study group.")

    if not room.is_active:
        raise GroupServiceError("This study group is already closed.")

    room.is_active = False

    admin_user = db.session.get(User, admin_id)
    admin_name = admin_user.name if admin_user else "Administrator"

    sys_msg = Message(
        room_id=room.id,
        sender_id=admin_id,
        text=f"This study group was closed by {admin_name}.",
        is_system=True,
        created_at=utc_now(),
    )
    db.session.add(sys_msg)

    db.session.commit()


def suggest_members(room_id: int) -> dict[str, list[dict[str, Any]]]:
    """
    Pedagogically Balanced Study Group Member Recommendation Heuristic
    ===================================================================

    Theoretical Foundation & Algorithm Explanation (for DAA Viva):
    --------------------------------------------------------------
    Educational psychology and collaborative learning research (e.g., Vygotsky's
    Zone of Proximal Development and peer scaffolding frameworks) demonstrate
    that heterogeneous/mixed-ability study groups achieve superior learning
    outcomes compared to homogeneous groups:
    - Strong students act as mentors, reinforcing conceptual mastery through teaching.
    - Average students bridge cognitive gaps and maintain active discourse.
    - Weak students receive targeted peer explanations in a low-anxiety setting.

    Algorithm Steps:
    1. Retrieve the group's subject focus S.
    2. Build an exclusion set E containing:
       - Current active members of room_id
       - Prospective members who already hold a 'pending' invitation for room_id
       - Faculty/teacher accounts
    3. Query candidate student accounts who have registered a skill proficiency in S.
    4. Categorize candidates into three pedagogical skill tiers:
       - "Strong": helpers/mentors
       - "Average": moderators/peers
       - "Weak": seekers/learners
    5. Within each tier, rank candidates using a multi-criteria heuristic:
       a. Homophily score (same branch and same academic year as existing group members)
       b. Load balance (students participating in fewer active study groups are ranked higher)
       c. Alphabetical order by name (deterministic tiebreaking)
    6. Return a structured dictionary:
       {"Strong": [...], "Average": [...], "Weak": [...]}

    Time Complexity: O(|Candidates| log |Candidates|)
    Space Complexity: O(|Candidates|)
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group" or not room.subject:
        return {"Strong": [], "Average": [], "Weak": []}

    # Step 1: Exclusion Set E
    existing_members = ChatMember.query.filter_by(room_id=room_id).all()
    excluded_ids = {m.user_id for m in existing_members}

    pending_invites = GroupInvite.query.filter_by(room_id=room_id, status="pending").all()
    excluded_ids.update({inv.invited_user_id for inv in pending_invites})

    # Find dominant branch and year among current group members for homophily tiebreaker
    member_users = [db.session.get(User, m.user_id) for m in existing_members]
    member_branches = [u.branch for u in member_users if u]
    member_years = [u.year for u in member_users if u]

    dominant_branch = max(set(member_branches), key=member_branches.count) if member_branches else None
    dominant_year = max(set(member_years), key=member_years.count) if member_years else None

    # Step 2: Query candidate students who have a recorded skill in the room's subject
    subject = room.subject
    candidate_skills = (
        Skill.query.join(User, User.id == Skill.user_id)
        .filter(
            Skill.subject == subject,
            User.role == "student",
            ~User.id.in_(excluded_ids),
        )
        .all()
    )

    grouped_candidates: dict[str, list[dict[str, Any]]] = {
        "Strong": [],
        "Average": [],
        "Weak": [],
    }

    # Pre-fetch user active group counts for batch load calculation
    candidate_user_ids = [s.user_id for s in candidate_skills]
    active_group_counts: dict[int, int] = {}
    if candidate_user_ids:
        counts = (
            db.session.query(ChatMember.user_id, db.func.count(ChatMember.id))
            .join(ChatRoom, ChatRoom.id == ChatMember.room_id)
            .filter(
                ChatMember.user_id.in_(candidate_user_ids),
                ChatRoom.type == "group",
                ChatRoom.is_active.is_(True),
            )
            .group_by(ChatMember.user_id)
            .all()
        )
        for uid, cnt in counts:
            active_group_counts[uid] = cnt

    max_groups = current_app.config.get("MAX_USER_GROUPS", MAX_USER_GROUPS)

    for skill in candidate_skills:
        user = skill.user
        if not user:
            continue

        active_cnt = active_group_counts.get(user.id, 0)
        # Exclude students who are already at the maximum 5 active groups limit
        if active_cnt >= max_groups:
            continue

        same_branch = (user.branch == dominant_branch)
        same_year = (user.year == dominant_year)

        candidate_item = {
            "user": user,
            "skill_level": skill.level,
            "active_groups": active_cnt,
            "same_branch": same_branch,
            "same_year": same_year,
        }

        if skill.level in grouped_candidates:
            grouped_candidates[skill.level].append(candidate_item)

    # Step 3: Heuristic Multi-criteria Sorting within each tier
    for level, candidates in grouped_candidates.items():
        candidates.sort(
            key=lambda c: (
                -1 if c["same_branch"] else 0,   # Same branch preferred
                -1 if c["same_year"] else 0,     # Same year preferred
                c["active_groups"],              # Fewer groups -> more bandwidth
                c["user"].name.lower(),          # Alphabetical tiebreaker
            )
        )

    return grouped_candidates


def get_user_study_groups(user_id: int) -> list[dict[str, Any]]:
    """
    Retrieve all study groups (active and closed) where the user is a member.
    Includes member counts, user role, and last message summary.
    """
    memberships = (
        ChatMember.query.filter_by(user_id=user_id)
        .join(ChatRoom, ChatRoom.id == ChatMember.room_id)
        .filter(ChatRoom.type == "group")
        .order_by(ChatRoom.is_active.desc(), ChatRoom.created_at.desc())
        .all()
    )

    group_list = []
    for m in memberships:
        room = m.room
        total_members = room.members.count()
        last_msg = (
            Message.query.filter_by(room_id=room.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        group_list.append({
            "room": room,
            "role": m.role,
            "is_admin": m.role == "admin",
            "member_count": total_members,
            "max_size": current_app.config.get("GROUP_MAX_SIZE", GROUP_MAX_SIZE),
            "last_message": last_msg,
        })

    return group_list


def get_user_pending_invites(user_id: int) -> list[GroupInvite]:
    """
    Retrieve incoming pending group invitations for a student.
    """
    return (
        GroupInvite.query.filter_by(invited_user_id=user_id, status="pending")
        .join(ChatRoom, ChatRoom.id == GroupInvite.room_id)
        .filter(ChatRoom.is_active.is_(True))
        .order_by(GroupInvite.created_at.desc())
        .all()
    )


def get_group_view_data(room_id: int, user_id: int) -> dict[str, Any]:
    """
    Package room details, members with their proficiency levels, and admin options.
    """
    room = db.session.get(ChatRoom, room_id)
    if not room or room.type != "group":
        raise GroupServiceError("Study group does not exist.")

    current_member = ChatMember.query.filter_by(room_id=room_id, user_id=user_id).first()
    if not current_member:
        raise GroupServiceError("You are not a member of this study group.")

    is_admin = (current_member.role == "admin")

    # Member list with subject skill proficiency
    members = room.members.all()
    member_details = []
    for m in members:
        user = m.user
        skill = Skill.query.filter_by(user_id=user.id, subject=room.subject).first()
        member_details.append({
            "member": m,
            "user": user,
            "role": m.role,
            "is_admin": (m.role == "admin"),
            "skill_level": skill.level if skill else "Not Set",
        })

    # Sort members: admins first, then by name
    member_details.sort(key=lambda item: (0 if item["is_admin"] else 1, item["user"].name.lower()))

    # Admin view additions: pending invites and suggestions
    pending_invites = []
    suggestions: dict[str, list[dict[str, Any]]] = {"Strong": [], "Average": [], "Weak": []}
    if is_admin and room.is_active:
        pending_invites = GroupInvite.query.filter_by(room_id=room.id, status="pending").all()
        suggestions = suggest_members(room.id)

    max_size = current_app.config.get("GROUP_MAX_SIZE", GROUP_MAX_SIZE)

    return {
        "room": room,
        "is_admin": is_admin,
        "current_member": current_member,
        "members": member_details,
        "member_count": len(members),
        "max_size": max_size,
        "pending_invites": pending_invites,
        "suggestions": suggestions,
        "can_invite": (is_admin and room.is_active and (len(members) + len(pending_invites) < max_size)),
    }

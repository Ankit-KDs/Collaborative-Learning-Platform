"""
Study Buddy Bipartite Matching Service
======================================

Theoretical Foundation & Algorithm Explanation (for DAA Viva):
--------------------------------------------------------------
This module models the peer study-buddy recommendation problem as an attributed
Bipartite Matching problem with capacity constraints and a multi-criteria Greedy
Load-Balancing heuristic.

1. Formal Graph Modeling:
   For each academic subject s in S, we construct a directed bipartite compatibility
   graph G_s = (Seekers_s U Helpers_s, E_s):
   - Seekers_s = { u in Students | Level(u, s) = 'Weak' }
   - Helpers_s = { v in Students | Level(v, s) = 'Strong', v != u, Role(v) != 'teacher' }
   - An edge (u, v) in E_s exists if helper v has proficiency to assist seeker u
     and no active connection exists between u and v for subject s.

2. Constraints & Edge Pruning:
   a. Active Request Mutual Exclusion:
      An edge (u, v) is pruned if there exists any BuddyRequest r where:
      Subject(r) = s, {Sender(r), Receiver(r)} = {u, v}, and Status(r) in {'pending', 'accepted'}.
   b. Helper Capacity Cap (Starvation & Burnout Prevention):
      Each helper v has an in-degree load L(v) defined as:
      L(v) = |{ r in BuddyRequests | Receiver(r) = v and Status(r) in {'pending', 'accepted'} }|
      If L(v) >= MAX_HELPER_LOAD (default: 3), helper v is deemed saturated/exhausted
      and is removed from the candidate set Helpers_s.

3. Greedy Multi-Criteria Objective Function:
   To prevent load concentration on popular helpers and ensure fair distribution
   across the helper pool (load balancing), candidate helpers v are ordered greedily
   using a lexicographical sorting tuple:

   RankKey(v) = (
       L(v),                              # Primary: Minimize helper current active load
       -1 if Branch(v) == Branch(u) else 0, # Secondary (Tiebreaker): Homophily (same department)
       -1 if Year(v) == Year(u) else 0,     # Tertiary (Tiebreaker): Cohort proximity (same year)
       Name(v).lower()                    # Quaternary: Deterministic alphabetical order
   )

4. Complexity Analysis:
   - Let k be the number of weak subjects for seeker u (k <= |S|).
   - Let n be the total number of students in the institution.
   - Finding candidate helpers for a subject: O(|Helpers_s|) using indexed queries.
   - Computing active loads: O(|Helpers_s|) via indexed BuddyRequest receiver counts.
   - Pruning and sorting candidates: O(|Helpers_s| * log |Helpers_s|).
   - Total Time Complexity: O(k * |Helpers_s| * log |Helpers_s|), which runs in milliseconds
     even for thousands of students.
   - Space Complexity: O(|Helpers_s|) for the candidate ranking list.
"""

from typing import Any

from flask import current_app
from sqlalchemy import or_

from app import db
from app.config import MAX_HELPER_LOAD
from app.models import BuddyRequest, Skill, User


def get_active_buddy_pairs(user_id: int, subject: str) -> set[int]:
    """
    Retrieve user IDs of peers who already share an active (pending or accepted)
    BuddyRequest with user_id for a specific subject in either direction.

    Time Complexity: O(|Requests_u,s|)
    """
    active_requests = BuddyRequest.query.filter(
        BuddyRequest.subject == subject,
        BuddyRequest.status.in_(["pending", "accepted"]),
        or_(
            BuddyRequest.sender_id == user_id,
            BuddyRequest.receiver_id == user_id,
        ),
    ).all()

    excluded_peer_ids = set()
    for req in active_requests:
        if req.sender_id == user_id:
            excluded_peer_ids.add(req.receiver_id)
        else:
            excluded_peer_ids.add(req.sender_id)

    return excluded_peer_ids


def compute_helper_load(helper_id: int) -> int:
    """
    Calculate a helper's current active incoming load:
    Total number of pending + accepted BuddyRequests where helper_id is the receiver.

    Time Complexity: O(1) indexed SQL count query.
    """
    return (
        BuddyRequest.query.filter(
            BuddyRequest.receiver_id == helper_id,
            BuddyRequest.status.in_(["pending", "accepted"]),
        ).count()
    )


def compute_bulk_helper_loads(helper_ids: list[int]) -> dict[int, int]:
    """
    Efficiently compute active loads for a batch of helpers in a single grouped query.
    """
    if not helper_ids:
        return {}

    loads = {hid: 0 for hid in helper_ids}
    results = (
        db.session.query(BuddyRequest.receiver_id, db.func.count(BuddyRequest.id))
        .filter(
            BuddyRequest.receiver_id.in_(helper_ids),
            BuddyRequest.status.in_(["pending", "accepted"]),
        )
        .group_by(BuddyRequest.receiver_id)
        .all()
    )

    for hid, count in results:
        loads[hid] = count

    return loads


def find_matches_for_user(user_id: int, include_pending: bool = False) -> list[dict[str, Any]]:
    """
    Find and rank compatible strong peer helpers for all subjects where user_id is Weak.

    Algorithm:
    1. Fetch seeker user and their 'Weak' skills.
    2. For each weak subject:
       a. Query all student helpers who marked this subject as 'Strong'.
       b. Exclude self and teacher accounts.
       c. Exclude helpers with existing active buddy requests (or mark pending requests if include_pending=True).
       d. Batch-calculate current load for candidate helpers.
       e. Exclude helpers whose load >= MAX_HELPER_LOAD.
       f. Rank remaining helpers using Greedy Load-Balancing and tiebreakers.
    3. Return a structured list per subject with candidate profiles and load status.
    """
    user = db.session.get(User, user_id)
    if not user or user.role != "student":
        return []

    # Get user's weak skills
    weak_skills = Skill.query.filter_by(user_id=user_id, level="Weak").all()
    if not weak_skills:
        return []

    max_load = current_app.config.get("MAX_HELPER_LOAD", MAX_HELPER_LOAD)
    matches_by_subject = []

    for skill in weak_skills:
        subject = skill.subject

        pending_sent_to_ids = set()
        if include_pending:
            # Exclude accepted connections and incoming pending requests
            accepted_requests = BuddyRequest.query.filter(
                BuddyRequest.subject == subject,
                BuddyRequest.status == "accepted",
                or_(
                    BuddyRequest.sender_id == user_id,
                    BuddyRequest.receiver_id == user_id,
                ),
            ).all()
            excluded_peer_ids = {
                r.receiver_id if r.sender_id == user_id else r.sender_id
                for r in accepted_requests
            }

            incoming_pending = BuddyRequest.query.filter_by(
                receiver_id=user_id, subject=subject, status="pending"
            ).all()
            excluded_peer_ids.update({r.sender_id for r in incoming_pending})

            # Track helpers to whom this user has already dispatched a pending request
            outgoing_pending = BuddyRequest.query.filter_by(
                sender_id=user_id, subject=subject, status="pending"
            ).all()
            pending_sent_to_ids = {r.receiver_id for r in outgoing_pending}
        else:
            # Exclude peers who already have pending or accepted requests with this user for this subject
            excluded_peer_ids = get_active_buddy_pairs(user_id, subject)

        excluded_peer_ids.add(user_id)  # Exclude self

        # Fetch potential helpers: Must be 'Strong' in this subject and a 'student'
        candidate_helpers = (
            User.query.join(Skill, Skill.user_id == User.id)
            .filter(
                Skill.subject == subject,
                Skill.level == "Strong",
                User.role == "student",
                ~User.id.in_(excluded_peer_ids),
            )
            .all()
        )

        if not candidate_helpers:
            matches_by_subject.append({
                "subject": subject,
                "helpers": [],
                "total_available": 0,
            })
            continue

        # Bulk compute loads for all candidate helpers in this subject
        helper_ids = [h.id for h in candidate_helpers]
        load_map = compute_bulk_helper_loads(helper_ids)

        # Filter out helpers who have reached or exceeded MAX_HELPER_LOAD capacity
        eligible_helpers = []
        for helper in candidate_helpers:
            load = load_map.get(helper.id, 0)
            if load < max_load:
                same_branch = (helper.branch == user.branch)
                same_year = (helper.year == user.year)

                # Load status indicator: "Available" if load is low, "Busy" if close to capacity
                load_status = "Busy" if load >= (max_load - 1) else "Available"

                eligible_helpers.append({
                    "user": helper,
                    "load": load,
                    "load_status": load_status,
                    "same_branch": same_branch,
                    "same_year": same_year,
                    "request_sent": (helper.id in pending_sent_to_ids),
                })

        # Multi-criteria Greedy Sorting:
        # 1. Lowest load first (asc)
        # 2. Same branch (True before False -> -1 before 0)
        # 3. Same year (True before False -> -1 before 0)
        # 4. Name alphabetically (asc)
        eligible_helpers.sort(
            key=lambda h: (
                h["load"],
                -1 if h["same_branch"] else 0,
                -1 if h["same_year"] else 0,
                h["user"].name.lower(),
            )
        )

        matches_by_subject.append({
            "subject": subject,
            "helpers": eligible_helpers,
            "total_available": len(eligible_helpers),
        })

    return matches_by_subject


def find_help_opportunities(user_id: int) -> list[dict[str, Any]]:
    """
    Reverse view for strong students to see peers who need help in their strong subjects.
    Informational view showing students with 'Weak' skill level in the subjects
    where user_id has 'Strong' skill level.

    Algorithm:
    1. Fetch seeker user and their 'Strong' skills.
    2. For each strong subject:
       a. Query all students who marked this subject as 'Weak'.
       b. Exclude self, teachers, and peers with existing active requests.
       c. Rank by same branch, same year, and name.
    """
    user = db.session.get(User, user_id)
    if not user or user.role != "student":
        return []

    strong_skills = Skill.query.filter_by(user_id=user_id, level="Strong").all()
    if not strong_skills:
        return []

    opportunities = []

    for skill in strong_skills:
        subject = skill.subject

        # Exclude peers who already share an active request with this user
        excluded_peer_ids = get_active_buddy_pairs(user_id, subject)
        excluded_peer_ids.add(user_id)  # Exclude self

        # Seekers: Students who marked this subject as 'Weak'
        seekers = (
            User.query.join(Skill, Skill.user_id == User.id)
            .filter(
                Skill.subject == subject,
                Skill.level == "Weak",
                User.role == "student",
                ~User.id.in_(excluded_peer_ids),
            )
            .all()
        )

        ranked_seekers = []
        for seeker in seekers:
            same_branch = (seeker.branch == user.branch)
            same_year = (seeker.year == user.year)
            ranked_seekers.append({
                "user": seeker,
                "same_branch": same_branch,
                "same_year": same_year,
            })

        # Rank seekers by same branch, same year, then name
        ranked_seekers.sort(
            key=lambda s: (
                -1 if s["same_branch"] else 0,
                -1 if s["same_year"] else 0,
                s["user"].name.lower(),
            )
        )

        opportunities.append({
            "subject": subject,
            "seekers": ranked_seekers,
            "total_seekers": len(ranked_seekers),
        })

    return opportunities

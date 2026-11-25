"""
Routes for peer study buddy recommendations and matching discovery.
"""

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.models import Skill
from app.services.matching import find_help_opportunities, find_matches_for_user

matches_bp = Blueprint("matches", __name__)


@matches_bp.route("/matches", methods=["GET"])
@login_required
def matches():
    """
    Peer study buddy matching overview.
    - Shows weak subjects and recommended strong peer helpers (load-balanced).
    - Shows subjects where user is strong and peers who need help (informational).
    - Friendly state for faculty/teacher accounts.
    """
    if current_user.is_teacher:
        return render_template(
            "matches/matches.html",
            title="Peer Matches",
            is_teacher=True,
            matches=[],
            help_opportunities=[],
            has_skills=False,
        )

    # Check if student has defined any skills
    user_skills_count = Skill.query.filter_by(user_id=current_user.id).count()
    has_skills = user_skills_count > 0

    # Call matching service (Strictly in service, not in route)
    buddy_matches = find_matches_for_user(current_user.id, include_pending=True)
    help_opportunities = find_help_opportunities(current_user.id)

    return render_template(
        "matches/matches.html",
        title="Study Buddy Matches",
        is_teacher=False,
        matches=buddy_matches,
        help_opportunities=help_opportunities,
        has_skills=has_skills,
    )

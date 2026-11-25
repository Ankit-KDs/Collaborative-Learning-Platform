"""
Learning Analytics & Weak-Topic Prioritization Service.
======================================================

Computes weak-topic metrics and student skill diagnostics purely locally without AI.
Ranks subjects by pedagogical priority score to guide personalized study interventions.
Generates deterministic profile hashes to detect when student skills change.
"""

import hashlib
import json
from typing import Any

from app import db
from app.config import SUBJECTS
from app.models import Doubt, QuizAttempt, Skill, User


def compute_student_learning_stats(user_id: int) -> dict[str, Any]:
    """
    Compute comprehensive subject-by-subject diagnostics for a student.

    Priority Scoring Formula:
    -------------------------
    Priority = Base_Level_Score + Open_Doubts_Bonus + Quiz_Performance_Adjustment

    1. Base Skill Score:
       - Weak:     50 pts
       - Not Set:  30 pts
       - Average:  25 pts
       - Strong:   10 pts

    2. Open Doubts Adjustment:
       - +10 pts per unresolved (open) doubt asked in this subject.

    3. Quiz Performance Adjustment:
       - Average < 50%:     +20 pts (Critical reinforcement needed)
       - 50% <= Avg < 70%:  +10 pts (Moderate reinforcement needed)
       - No quizzes taken:  +5 pts (Needs diagnostic practice)
       - Average >= 80%:    -10 pts (Demonstrated mastery)

    :param user_id: ID of the student.
    :return: Dict containing ranked subject metrics, chart data, and current profile hash.
    """
    user = db.session.get(User, user_id)
    if not user:
        return {"ranked_subjects": [], "chart_data": {}, "profile_hash": ""}

    # 1. Fetch skills map
    skills = Skill.query.filter_by(user_id=user_id).all()
    skill_map = {s.subject: s.level for s in skills}

    # 2. Fetch all submitted quizzes for user
    quizzes = QuizAttempt.query.filter(
        QuizAttempt.user_id == user_id,
        QuizAttempt.submitted_at.isnot(None),
    ).all()

    # Aggregate quiz performance per subject
    quiz_stats_by_subject: dict[str, list[float]] = {}
    for q in quizzes:
        if q.num_questions > 0 and q.score is not None:
            pct = (q.score / q.num_questions) * 100.0
            quiz_stats_by_subject.setdefault(q.subject, []).append(pct)

    # 3. Fetch doubts asked by user
    user_doubts = Doubt.query.filter_by(user_id=user_id).all()
    doubts_by_subject: dict[str, list[Doubt]] = {}
    for d in user_doubts:
        doubts_by_subject.setdefault(d.subject, []).append(d)

    # 4. Compute per-subject diagnostics across all canonical subjects
    subject_diagnostics: list[dict[str, Any]] = []

    for sub in SUBJECTS:
        level = skill_map.get(sub, "Not Set")

        # Doubts counts
        sub_doubts = doubts_by_subject.get(sub, [])
        total_doubts = len(sub_doubts)
        open_doubts = sum(1 for d in sub_doubts if d.status == "open")

        # Quiz averages
        q_scores = quiz_stats_by_subject.get(sub, [])
        quiz_avg: float | None = None
        if q_scores:
            quiz_avg = round(sum(q_scores) / len(q_scores), 1)

        # Base score by level
        level_bases = {
            "Weak": 50,
            "Not Set": 30,
            "Average": 25,
            "Strong": 10,
        }
        base_score = level_bases.get(level, 25)

        # Doubts bonus
        doubt_bonus = open_doubts * 10

        # Quiz adjustment
        if quiz_avg is None:
            quiz_adj = 5
        elif quiz_avg < 50.0:
            quiz_adj = 20
        elif quiz_avg < 70.0:
            quiz_adj = 10
        elif quiz_avg >= 80.0:
            quiz_adj = -10
        else:
            quiz_adj = 0

        total_priority = base_score + doubt_bonus + quiz_adj

        subject_diagnostics.append({
            "subject": sub,
            "level": level,
            "has_skill": sub in skill_map,
            "total_doubts": total_doubts,
            "open_doubts": open_doubts,
            "quiz_attempts_count": len(q_scores),
            "quiz_avg": quiz_avg,
            "priority_score": total_priority,
        })

    # Sort descending by priority score; tie-breaker: open doubts desc, total doubts desc
    ranked_subjects = sorted(
        subject_diagnostics,
        key=lambda x: (x["priority_score"], x["open_doubts"], x["total_doubts"]),
        reverse=True,
    )

    # 5. Build Chart.js payload for quiz performance
    chart_labels = []
    chart_scores = []
    for item in ranked_subjects:
        chart_labels.append(item["subject"])
        chart_scores.append(item["quiz_avg"] if item["quiz_avg"] is not None else 0.0)

    chart_data = {
        "labels": chart_labels,
        "datasets": [
            {
                "label": "Average Quiz Score (%)",
                "data": chart_scores,
                "backgroundColor": "rgba(99, 102, 241, 0.6)",
                "borderColor": "rgba(99, 102, 241, 1.0)",
                "borderWidth": 1,
            }
        ],
    }

    # 6. Compute Profile Hash (Deterministic SHA-256 string)
    hash_items = [
        {
            "sub": s["subject"],
            "lvl": s["level"],
            "open": s["open_doubts"],
            "q_avg": s["quiz_avg"],
        }
        for s in ranked_subjects
    ]
    hash_payload = json.dumps(hash_items, sort_keys=True)
    profile_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()

    return {
        "ranked_subjects": ranked_subjects,
        "chart_data": chart_data,
        "profile_hash": profile_hash,
    }

"""
Integration and algorithmic tests for Weak-Topic Analytics & Learning Path (Stage 6).
=====================================================================================
Validates:
- Algorithmic priority score computation (Weak + open doubts > Strong).
- Faculty advisory notice on /learning-path.
- SHA-256 profile hash mismatch detection when student skills are modified.
- 1-hour regeneration cooldown enforcement.
"""

from datetime import timedelta
import json
from unittest.mock import MagicMock
import pytest

from app import create_app, db
from app.models import LearningPath, QuizAttempt, Skill, User, utc_now
from app.services.doubts_service import create_doubt
from app.services.learning_stats import compute_student_learning_stats


@pytest.fixture
def app_instance(tmp_path):
    """Create test application instance with in-memory SQLite database."""
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _create_student(name: str, email: str) -> User:
    u = User(name=name, email=email, role="student", branch="CS", year=2)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


def _create_teacher(name: str, email: str) -> User:
    u = User(name=name, email=email, role="teacher", branch="CS", year=1)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, user_id: int):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_priority_score_ranking_heuristics(app_instance):
    """
    Weak subjects with open doubts must rank higher than Strong subjects with high quiz scores.
    Priority Score = Base (Weak=50, Strong=10) + Open Doubts (+10 each) + Quiz Adj.
    """
    with app_instance.app_context():
        student = _create_student("Alice", "alice_analytics@test.com")

        # Subject 1: DAA (Weak + 2 open doubts)
        db.session.add(Skill(user_id=student.id, subject="DAA", level="Weak"))
        create_doubt(student.id, "DAA", "Doubt 1 Title", "Detailed question body description 1.")
        create_doubt(student.id, "DAA", "Doubt 2 Title", "Detailed question body description 2.")

        # Subject 2: Python (Strong + 0 doubts + 100% quiz)
        db.session.add(Skill(user_id=student.id, subject="Python", level="Strong"))
        db.session.add(
            QuizAttempt(
                user_id=student.id,
                subject="Python",
                topic="Basics",
                difficulty="Easy",
                num_questions=5,
                questions_json="[]",
                answers_json="{}",
                score=5,
                created_at=utc_now(),
                submitted_at=utc_now(),
            )
        )
        db.session.commit()

        stats = compute_student_learning_stats(student.id)
        ranked = stats["ranked_subjects"]

        # DAA must be ranked first (highest priority score)
        assert ranked[0]["subject"] == "DAA"
        assert ranked[0]["level"] == "Weak"
        assert ranked[0]["open_doubts"] == 2
        # Score: 50 (Weak) + 20 (2 doubts) + 5 (No quiz in DAA) = 75
        assert ranked[0]["priority_score"] == 75

        # Python must have lower priority
        # Score: 10 (Strong) + 0 (doubts) - 10 (100% quiz) = 0
        python_stat = next(s for s in ranked if s["subject"] == "Python")
        assert python_stat["priority_score"] == 0


def test_teacher_visiting_learning_path_receives_advisory(app_instance):
    """Teachers visiting /learning-path receive a faculty notice rather than student analytics."""
    client = app_instance.test_client()
    with app_instance.app_context():
        teacher = _create_teacher("Prof. Verma", "verma@test.com")
        t_id = teacher.id

    _login(client, t_id)
    resp = client.get("/learning-path", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Faculty Advisory" in resp.data
    assert b"designed for student self-directed learning" in resp.data


def test_profile_hash_mismatch_detected_on_skill_update(app_instance):
    """Updating a student's skill must change profile_hash and trigger has_hash_mismatch flag."""
    client = app_instance.test_client()
    with app_instance.app_context():
        student = _create_student("Bob", "bob_hash@test.com")
        s_id = student.id

        # Initial skill: Weak in DAA
        skill = Skill(user_id=s_id, subject="DAA", level="Weak")
        db.session.add(skill)
        db.session.commit()

        stats_initial = compute_student_learning_stats(s_id)
        initial_hash = stats_initial["profile_hash"]

        # Save learning path with initial hash generated 2 hours ago
        lp = LearningPath(
            user_id=s_id,
            content_json=json.dumps({"motivation": "Keep going!", "subjects": []}),
            profile_hash=initial_hash,
            generated_at=utc_now() - timedelta(hours=2),
        )
        db.session.add(lp)
        db.session.commit()

    _login(client, s_id)

    # 1. Before skill change -> No mismatch
    resp1 = client.get("/learning-path", follow_redirects=True)
    assert resp1.status_code == 200
    assert b"Your skills or activity changed since this plan was generated." not in resp1.data

    # 2. Update student skill to Strong in DAA
    with app_instance.app_context():
        s = Skill.query.filter_by(user_id=s_id, subject="DAA").first()
        assert s is not None
        s.level = "Strong"
        db.session.commit()

    # 3. After skill change -> Mismatch banner is displayed
    resp2 = client.get("/learning-path", follow_redirects=True)
    assert resp2.status_code == 200
    assert b"Your skills or activity changed since this plan was generated." in resp2.data


def test_regeneration_cooldown_enforced(app_instance, monkeypatch):
    """Generating a plan within 1 hour of the previous generation is rejected by the server."""
    client = app_instance.test_client()
    with app_instance.app_context():
        student = _create_student("Charlie", "charlie_cooldown@test.com")
        s_id = student.id

        # Pre-seed a learning path generated 15 minutes ago
        recent_time = utc_now() - timedelta(minutes=15)
        lp = LearningPath(
            user_id=s_id,
            content_json=json.dumps({"motivation": "Recent plan", "subjects": []}),
            profile_hash="sample_hash",
            generated_at=recent_time,
        )
        db.session.add(lp)
        db.session.commit()

        # Mock AI generation to ensure it is never called
        mock_gen = MagicMock()
        monkeypatch.setattr("app.learning.routes.generate_learning_path", mock_gen)

    _login(client, s_id)
    resp = client.post("/learning-path/generate", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Study plan can only be regenerated once per hour" in resp.data
    mock_gen.assert_not_called()

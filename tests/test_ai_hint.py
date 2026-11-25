"""
Integration and unit tests for AI Doubt Hints & Human Escalation (Stage 6).
===========================================================================
Validates:
- Cached hints return without triggering redundant LLM calls.
- Owner-only permission for generating/regenerating hints.
- Cap of max 2 regenerations per doubt.
- Anonymity preservation (author identity never exposed).
- AI hints are NOT treated as Answers in ranking or reputation.
- Feedback flow: "helpful=False" flags doubt as needs_human=True.
- Escalated doubts (needs_human=True) are prioritized at top of peer recommendations.
"""

from unittest.mock import MagicMock
import pytest

from app import create_app, db
from app.models import AIHint, Doubt, Skill, User
from app.services.doubts_service import (
    DoubtServiceError,
    create_doubt,
    get_or_create_ai_hint,
    submit_hint_feedback,
)


@pytest.fixture
def app_instance(tmp_path):
    """Create test application instance with temporary upload folder."""
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["GEMINI_API_KEY"] = "fake-test-key-12345"
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


def test_cached_hint_avoids_llm_call(app_instance, monkeypatch):
    """If an AI hint is already generated and cached, it must return immediately without calling Gemini."""
    with app_instance.app_context():
        student = _create_student("Alice", "alice@test.com")
        doubt = create_doubt(student.id, "DAA", "Binary Search Bug", "Off by one error.")

        # Pre-seed a cached hint
        hint = AIHint(
            doubt_id=doubt.id,
            hint_text="Check your loop boundary condition (low <= high).",
            regenerated_count=0,
        )
        db.session.add(hint)
        db.session.commit()

        # Mock generate_hint to ensure it is NEVER called
        mock_generate = MagicMock()
        monkeypatch.setattr("app.services.doubts_service.generate_hint", mock_generate)

        fetched_hint, _ = get_or_create_ai_hint(doubt.id, student.id, regenerate=False)
        assert fetched_hint.id == hint.id
        assert fetched_hint.hint_text == "Check your loop boundary condition (low <= high)."
        mock_generate.assert_not_called()


def test_only_owner_can_request_or_regenerate_hint(app_instance, monkeypatch):
    """A classmate who does not own the doubt cannot trigger hint generation or regeneration."""
    with app_instance.app_context():
        owner = _create_student("Owner", "owner@test.com")
        classmate = _create_student("Classmate", "classmate@test.com")
        doubt = create_doubt(owner.id, "DAA", "Master Theorem", "T(n) = 2T(n/2) + n")

        monkeypatch.setattr(
            "app.services.doubts_service.generate_hint",
            lambda *args, **kwargs: "Look at case 2 of Master Theorem.",
        )

        with pytest.raises(DoubtServiceError, match="Only the author of this doubt"):
            get_or_create_ai_hint(doubt.id, classmate.id, regenerate=False)


def test_regeneration_limit_enforced(app_instance, monkeypatch):
    """Regeneration is capped at 2 times per doubt."""
    with app_instance.app_context():
        owner = _create_student("Owner", "owner_regen@test.com")
        doubt = create_doubt(owner.id, "DAA", "DP Memoization", "How to cache overlapping subproblems?")

        monkeypatch.setattr(
            "app.services.doubts_service.generate_hint",
            lambda *args, **kwargs: "Store previously computed results in a table.",
        )

        # Initial generation (count=0)
        h0, _ = get_or_create_ai_hint(doubt.id, owner.id, regenerate=False)
        assert h0.regenerated_count == 0

        # Regeneration 1
        h1, _ = get_or_create_ai_hint(doubt.id, owner.id, regenerate=True)
        assert h1.regenerated_count == 1

        # Regeneration 2
        h2, _ = get_or_create_ai_hint(doubt.id, owner.id, regenerate=True)
        assert h2.regenerated_count == 2

        # Regeneration 3 -> Exceeds limit
        with pytest.raises(DoubtServiceError, match="Maximum 2 hint regenerations reached"):
            get_or_create_ai_hint(doubt.id, owner.id, regenerate=True)


def test_ai_hint_not_counted_as_answer_or_reputation(app_instance, monkeypatch):
    """Generating an AI hint must not alter the doubt's answer count or user reputation."""
    with app_instance.app_context():
        owner = _create_student("Owner", "owner_rep@test.com")
        doubt = create_doubt(owner.id, "Data Structures", "AVL Trees", "Height balancing?")

        monkeypatch.setattr(
            "app.services.doubts_service.generate_hint",
            lambda *args, **kwargs: "Balance factor must be -1, 0, or 1.",
        )

        get_or_create_ai_hint(doubt.id, owner.id, regenerate=False)

        refreshed_doubt = db.session.get(Doubt, doubt.id)
        assert refreshed_doubt is not None
        assert refreshed_doubt.answers.count() == 0
        assert refreshed_doubt.ai_hint is not None


def test_anonymous_doubt_never_sends_author_identity(app_instance, monkeypatch):
    """For anonymous doubts, author identity is stripped and not provided to AI prompt."""
    with app_instance.app_context():
        owner = _create_student("Alice Confidential", "alice_anon@test.com")
        doubt = create_doubt(owner.id, "Python", "GIL Question", "Does GIL affect I/O?", is_anonymous=True)

        captured_args = {}

        def mock_gen_hint(subject, title, body, **kwargs):
            captured_args["subject"] = subject
            captured_args["title"] = title
            captured_args["body"] = body
            return "GIL is released during blocking I/O calls."

        monkeypatch.setattr("app.services.doubts_service.generate_hint", mock_gen_hint)

        get_or_create_ai_hint(doubt.id, owner.id, regenerate=False)

        assert "Alice" not in captured_args["title"]
        assert "Alice" not in captured_args["body"]
        assert "alice_anon@test.com" not in captured_args["body"]


def test_feedback_negative_sets_needs_human_escalation(app_instance):
    """Submitting helpful=False flags doubt.needs_human = True for peer escalation."""
    with app_instance.app_context():
        owner = _create_student("Owner", "owner_fb@test.com")
        doubt = create_doubt(owner.id, "DBMS", "Deadlock Graph", "Cycle detection in wait-for graph.")

        hint = AIHint(doubt_id=doubt.id, hint_text="Use DFS to find cycles.", regenerated_count=0)
        db.session.add(hint)
        db.session.commit()

        assert not doubt.needs_human

        # Owner submits negative feedback ("Still stuck")
        res_hint = submit_hint_feedback(doubt.id, owner.id, helpful=False)
        assert res_hint.helpful is False

        refreshed_doubt = db.session.get(Doubt, doubt.id)
        assert refreshed_doubt is not None
        assert refreshed_doubt.needs_human is True


def test_needs_human_prioritized_in_doubts_for_you(app_instance):
    """Escalated doubts with 0 answers appear at the very top of peer recommendations."""
    client = app_instance.test_client()
    with app_instance.app_context():
        helper = _create_student("Helper", "helper@test.com")
        h_id = helper.id
        db.session.add(Skill(user_id=h_id, subject="DAA", level="Strong"))

        asker1 = _create_student("Asker1", "asker1@test.com")
        asker2 = _create_student("Asker2", "asker2@test.com")

        # Doubt A: Normal doubt (needs_human=False)
        d_normal = create_doubt(asker1.id, "DAA", "Normal Doubt", "Standard DAA question.")
        # Doubt B: Escalated doubt (needs_human=True)
        d_escalated = create_doubt(asker2.id, "DAA", "Escalated Doubt", "Needs peer help desperately.")
        d_escalated.needs_human = True
        db.session.commit()
        d_norm_title = d_normal.title
        d_esc_title = d_escalated.title

    with client.session_transaction() as sess:
        sess["_user_id"] = str(h_id)
        sess["_fresh"] = True

    resp = client.get("/doubts", follow_redirects=True)
    assert resp.status_code == 200
    page_text = resp.data.decode("utf-8")
    assert "Doubts for you" in page_text
    assert "Asked for human help" in page_text
    # Escalated doubt appears before normal doubt in the page text
    assert page_text.index(d_esc_title) < page_text.index(d_norm_title)

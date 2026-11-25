"""
Unit tests for TF-IDF Semantic Duplicate Detection & Cryptographic Hashing (Stage 5).
Validates cosine similarity scoring, subject isolation, and hash-based exact duplicate blocking.
"""

import pytest
from app import create_app, db
from app.models import Doubt, User
from app.services.similarity import (
    check_exact_duplicate,
    compute_doubt_hash,
    find_similar_doubts,
    normalize_text_for_hash,
)


@pytest.fixture
def app_instance():
    """Create test application instance with in-memory SQLite database."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _create_user(name: str, email: str) -> User:
    u = User(name=name, email=email, role="student", branch="CS", year=2)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


def test_text_normalization_and_hashing():
    """Verify normalization strips punctuation, lowercases, and collapses whitespaces."""
    t1 = "  How   does Dijkstra's   algorithm work?!  "
    t2 = "how does dijkstras algorithm work"
    assert normalize_text_for_hash(t1) == normalize_text_for_hash(t2)

    # Hash should be identical for normalized variations
    h1 = compute_doubt_hash("Dijkstra Algorithm?", "How does it work, step by step???")
    h2 = compute_doubt_hash("dijkstra algorithm", "how does it work step by step")
    assert h1 == h2


def test_exact_duplicate_hash_check(app_instance):
    """Verify check_exact_duplicate flags identical questions from the same user."""
    with app_instance.app_context():
        u1 = _create_user("Alice", "alice@test.com")
        u2 = _create_user("Bob", "bob@test.com")

        # 1. Initially no duplicates
        assert check_exact_duplicate(u1.id, "Red-Black Trees", "Explain left rotations") is False

        # 2. Add doubt for Alice
        d = Doubt(
            user_id=u1.id,
            subject="Data Structures",
            title="Red-Black Trees",
            body="Explain left rotations",
            status="open",
        )
        db.session.add(d)
        db.session.commit()

        # 3. Alice re-submitting with slightly different casing/whitespace is detected as duplicate
        assert check_exact_duplicate(u1.id, "  red-black trees! ", "Explain left rotations... ") is True

        # 4. Bob submitting the same question is NOT blocked (different user)
        assert check_exact_duplicate(u2.id, "Red-Black Trees", "Explain left rotations") is False

        # 5. Alice submitting a completely different question is NOT blocked
        assert check_exact_duplicate(u1.id, "B+ Tree Indexing", "Explain leaf nodes") is False


def test_find_similar_doubts_same_subject_and_cross_subject_isolation(app_instance):
    """
    Verify TF-IDF + Cosine Similarity detects semantically related doubts in the same subject,
    and strictly ignores doubts in different subjects.
    """
    with app_instance.app_context():
        u = _create_user("Alice", "alice@test.com")

        # Doubt 1 in DAA
        d1 = Doubt(
            user_id=u.id,
            subject="DAA",
            title="Why does Dijkstra algorithm fail on negative edge weights?",
            body="Dijkstra assumes shortest path is finalized once visited. Why does negative weight fail?",
            status="open",
        )
        # Doubt 2 in Data Structures with identical text (different subject!)
        d2 = Doubt(
            user_id=u.id,
            subject="Data Structures",
            title="Why does Dijkstra algorithm fail on negative edge weights?",
            body="Dijkstra assumes shortest path is finalized once visited. Why does negative weight fail?",
            status="open",
        )
        # Doubt 3 in DAA on unrelated topic
        d3 = Doubt(
            user_id=u.id,
            subject="DAA",
            title="Dynamic programming matrix chain multiplication",
            body="How to compute optimal parenthesis order?",
            status="open",
        )
        db.session.add_all([d1, d2, d3])
        db.session.commit()

        # Query in DAA for near-duplicate phrasing
        results = find_similar_doubts(
            subject="DAA",
            title="Dijkstra shortest path with negative weight edges",
            body="Does Dijkstra give incorrect distances when weights are negative?",
            threshold=0.30,
        )

        assert len(results) >= 1
        matched_doubt, score = results[0]
        # Should match d1 (DAA), NOT d2 (Data Structures)
        assert matched_doubt.id == d1.id
        assert matched_doubt.subject == "DAA"
        assert score >= 0.30

        # Query in Mathematics (empty subject)
        math_results = find_similar_doubts(
            subject="Mathematics",
            title="Dijkstra shortest path with negative weight edges",
            body="Does Dijkstra give incorrect distances when weights are negative?",
        )
        assert math_results == []


def test_find_similar_doubts_edge_cases(app_instance):
    """Test edge cases: empty strings, short text, threshold filtering."""
    with app_instance.app_context():
        assert find_similar_doubts("DAA", "", "") == []
        assert find_similar_doubts("DAA", "Hi", "") == []

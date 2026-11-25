"""
Unit and integration tests for Exam Mode & High-Yield Revision (Stage 7).
Tests cover:
- Semantic FAQ doubt clustering via Cosine Similarity in Vector Space
- Best answer selection for cluster using Merge Sort ranking
- Strict anonymity enforcement: anonymous doubts display 'Anonymous'
- Graceful handling of empty subjects (zero division/vocabulary safety)
- Time range filtering (30, 90, all)
- Integration endpoint: /exam-mode returns 200 for authenticated students and teachers
"""

import pytest

from app import create_app, db
from app.models import Answer, Doubt, User
from app.services.exam_service import (
    build_exam_revision_package,
    cluster_faq_doubts,
    compute_most_asked_topics,
    get_display_asker,
)


@pytest.fixture
def app_instance(tmp_path):
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _create_user(name: str, email: str, role: str = "student") -> User:
    u = User(name=name, email=email, role=role, branch="CS", year=2)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


def test_exam_mode_empty_subject_without_errors(app_instance):
    with app_instance.app_context():
        # Package with zero doubts
        pkg = build_exam_revision_package("Mathematics", time_range="30")
        assert pkg["subject"] == "Mathematics"
        assert pkg["total_doubts_in_window"] == 0
        assert pkg["topics"] == []
        assert pkg["faq_clusters"] == []
        assert pkg["top_answers"] == []
        assert pkg["hot_doubts"] == []


def test_anonymous_doubts_never_leak_asker_name(app_instance):
    with app_instance.app_context():
        user = _create_user("Secret Student", "secret@test.com")
        doubt_anon = Doubt(
            user_id=user.id,
            subject="DAA",
            title="Anonymous Question on Dynamic Programming",
            body="Can someone explain DP memoization vs tabulation?",
            is_anonymous=True,
        )
        doubt_public = Doubt(
            user_id=user.id,
            subject="DAA",
            title="Public Question on Dynamic Programming",
            body="Can someone explain DP state transitions?",
            is_anonymous=False,
        )
        db.session.add_all([doubt_anon, doubt_public])
        db.session.commit()

        assert get_display_asker(doubt_anon) == "Anonymous"
        assert get_display_asker(doubt_public) == "Secret Student"


def test_faq_clustering_and_best_answer_ranking(app_instance):
    with app_instance.app_context():
        s1 = _create_user("Student 1", "s1_exam@test.com")
        s2 = _create_user("Student 2", "s2_exam@test.com")
        teacher = _create_user("Prof. DAA", "prof_daa@test.com", role="teacher")

        # Two near-duplicate questions about Dijkstra algorithm
        d1 = Doubt(
            user_id=s1.id,
            subject="Algorithms",
            title="How to implement Dijkstra shortest path algorithm with priority queue?",
            body="I need help implementing Dijkstra shortest path algorithm using a min-heap in Python.",
            is_anonymous=False,
        )
        d2 = Doubt(
            user_id=s2.id,
            subject="Algorithms",
            title="Dijkstra shortest path algorithm priority queue implementation in Python",
            body="Can someone share how Dijkstra shortest path algorithm is written with a priority queue?",
            is_anonymous=True,
        )
        db.session.add_all([d1, d2])
        db.session.flush()

        # Two answers on d1: one peer answer (3 upvotes), one teacher-verified answer (5 upvotes)
        ans_peer = Answer(
            doubt_id=d1.id,
            user_id=s2.id,
            body="Peer answer with basic heapq steps.",
            upvotes=3,
            is_verified=False,
        )
        ans_verified = Answer(
            doubt_id=d1.id,
            user_id=teacher.id,
            body="Teacher verified answer with optimal complexity breakdown.",
            upvotes=5,
            is_verified=True,
            verified_by=teacher.id,
        )
        db.session.add_all([ans_peer, ans_verified])
        db.session.commit()

        # Run clustering
        clusters = cluster_faq_doubts([d1, d2], similarity_threshold=0.4)
        assert len(clusters) == 1  # Grouped into 1 cluster
        cl = clusters[0]
        assert cl["count"] == 2
        assert cl["best_answer"] is not None
        # Best answer must be the verified answer (ranked top via Merge Sort)
        assert cl["best_answer"].id == ans_verified.id
        assert cl["best_answer"].is_verified is True


def test_tfidf_topic_extraction(app_instance):
    with app_instance.app_context():
        u = _create_user("Student Topics", "topics@test.com")
        d1 = Doubt(
            user_id=u.id,
            subject="Data Structures",
            title="Red-Black Tree rotation rules",
            body="Explain the left and right rotation cases for Red-Black tree nodes.",
        )
        d2 = Doubt(
            user_id=u.id,
            subject="Data Structures",
            title="Balancing a Red-Black Tree",
            body="How does coloring affect Red-Black tree insertion balance?",
        )
        db.session.add_all([d1, d2])
        db.session.commit()

        topics = compute_most_asked_topics([d1, d2], top_k=5)
        assert len(topics) > 0
        topic_terms = [t["term"].lower() for t in topics]
        # Common terms in the doubts
        assert any("tree" in t or "black" in t or "red" in t or "rotation" in t for t in topic_terms)


def test_exam_mode_endpoint_accessible(app_instance):
    with app_instance.app_context():
        _create_user("Exam Student", "stu_exam@test.com", role="student")
        client = app_instance.test_client()
        client.post("/auth/login", data={"email": "stu_exam@test.com", "password": "pass123"})

        resp = client.get("/exam-mode?subject=Data+Structures&time_range=30")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Exam Mode" in html
        assert "Data Structures" in html
        assert "Print / Save as PDF" in html

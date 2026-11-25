"""
Integration and security tests for AI Quiz Generator (Stage 6).
================================================================
Validates:
- Faculty redirection/notice on student quiz generator.
- Information leakage prevention (correct_index and explanations NOT sent before submission).
- Strict ownership verification (403 on other users' attempts).
- Single-submission guarantee / idempotency lock.
- Server-side grading accuracy and history tracking.
"""

import json
import pytest

from app import create_app, db
from app.models import QuizAttempt, User, utc_now


@pytest.fixture
def app_instance():
    """Create test application instance with in-memory SQLite database."""
    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = False  # Simplify POST form submissions in tests
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


def test_teacher_visiting_quiz_receives_advisory(app_instance):
    """Faculty members visiting /quiz receive an informative notice rather than a generation form."""
    client = app_instance.test_client()
    with app_instance.app_context():
        teacher = _create_teacher("Prof. Sharma", "sharma@test.com")
        t_id = teacher.id

    _login(client, t_id)
    resp = client.get("/quiz", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Faculty Advisory" in resp.data
    assert b"tailored for student self-testing" in resp.data


def test_take_quiz_does_not_leak_answers_or_explanations(app_instance):
    """Before submission, the quiz HTML must NEVER contain the correct_index or explanation string."""
    client = app_instance.test_client()
    with app_instance.app_context():
        student = _create_student("Alice", "alice_quiz@test.com")
        s_id = student.id

        questions_payload = [
            {
                "question": "What is the worst-case time complexity of QuickSort?",
                "options": ["O(n)", "O(n log n)", "O(n^2)", "O(2^n)"],
                "correct_index": 2,
                "explanation": "SECRET_EXPLANATION: When unbalanced partitions occur with worst pivot choice.",
            }
        ]

        attempt = QuizAttempt(
            user_id=s_id,
            subject="DAA",
            topic="QuickSort Worst Case",
            difficulty="Medium",
            num_questions=1,
            questions_json=json.dumps(questions_payload),
            answers_json=None,
            score=None,
            created_at=utc_now(),
        )
        db.session.add(attempt)
        db.session.commit()
        attempt_id = attempt.id

    _login(client, s_id)
    resp = client.get(f"/quiz/{attempt_id}")
    assert resp.status_code == 200
    page_text = resp.data.decode("utf-8")

    # Question and options must be rendered
    assert "What is the worst-case time complexity of QuickSort?" in page_text
    assert "O(n log n)" in page_text
    assert "O(n^2)" in page_text

    # Ground truth answer and explanation must NOT be present anywhere in the DOM or script tags
    assert "SECRET_EXPLANATION" not in page_text
    assert "correct_index" not in page_text


def test_other_student_cannot_access_quiz_attempt(app_instance):
    """Attempting to access another student's quiz must abort with 403 Forbidden."""
    client = app_instance.test_client()
    with app_instance.app_context():
        alice = _create_student("Alice", "alice_owner@test.com")
        bob = _create_student("Bob", "bob_snooper@test.com")

        attempt = QuizAttempt(
            user_id=alice.id,
            subject="DAA",
            topic="Binary Search",
            difficulty="Easy",
            num_questions=1,
            questions_json=json.dumps([{
                "question": "Q?",
                "options": ["1", "2", "3", "4"],
                "correct_index": 0,
                "explanation": "E",
            }]),
            answers_json=None,
            score=None,
            created_at=utc_now(),
        )
        db.session.add(attempt)
        db.session.commit()
        attempt_id = attempt.id
        bob_id = bob.id

    _login(client, bob_id)
    resp_take = client.get(f"/quiz/{attempt_id}")
    assert resp_take.status_code == 403

    resp_submit = client.post(f"/quiz/{attempt_id}/submit", data={"q_0": "0"})
    assert resp_submit.status_code == 403


def test_single_submission_lock_and_server_grading(app_instance):
    """Quizzes are graded server-side, locked against re-submission, and score is computed accurately."""
    client = app_instance.test_client()
    with app_instance.app_context():
        student = _create_student("Charlie", "charlie@test.com")
        s_id = student.id

        questions_payload = [
            {"question": "Q1?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "A is correct."},
            {"question": "Q2?", "options": ["A", "B", "C", "D"], "correct_index": 1, "explanation": "B is correct."},
            {"question": "Q3?", "options": ["A", "B", "C", "D"], "correct_index": 2, "explanation": "C is correct."},
        ]

        attempt = QuizAttempt(
            user_id=s_id,
            subject="DAA",
            topic="Sorting Algorithms",
            difficulty="Medium",
            num_questions=3,
            questions_json=json.dumps(questions_payload),
            answers_json=None,
            score=None,
            created_at=utc_now(),
        )
        db.session.add(attempt)
        db.session.commit()
        attempt_id = attempt.id

    _login(client, s_id)

    # Submit: Q0=0 (Correct), Q1=3 (Wrong), Q2 not submitted (Skipped) -> Score = 1
    resp_submit = client.post(
        f"/quiz/{attempt_id}/submit",
        data={"q_0": "0", "q_1": "3"},
        follow_redirects=True,
    )
    assert resp_submit.status_code == 200

    with app_instance.app_context():
        graded_attempt = db.session.get(QuizAttempt, attempt_id)
        assert graded_attempt is not None
        assert graded_attempt.score == 1
        assert graded_attempt.is_submitted
        answers = json.loads(graded_attempt.answers_json)
        assert answers["0"] == 0
        assert answers["1"] == 3
        assert answers["2"] is None

    # Subsequent submission attempt should be blocked and redirected to result
    resp_resubmit = client.post(
        f"/quiz/{attempt_id}/submit",
        data={"q_0": "0", "q_1": "1", "q_2": "2"},
        follow_redirects=False,
    )
    assert resp_resubmit.status_code == 302
    assert f"/quiz/{attempt_id}/result" in resp_resubmit.headers["Location"]


def test_quiz_history_lists_attempts(app_instance):
    """The /quiz/history route displays student attempts with subject, score, and percentage."""
    client = app_instance.test_client()
    with app_instance.app_context():
        student = _create_student("David", "david@test.com")
        s_id = student.id

        q = QuizAttempt(
            user_id=s_id,
            subject="DBMS",
            topic="ACID Properties",
            difficulty="Easy",
            num_questions=4,
            questions_json=json.dumps([{
                "question": "Q?",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explanation": "E",
            }] * 4),
            answers_json=json.dumps({"0": 0, "1": 0, "2": 0, "3": 0}),
            score=4,
            created_at=utc_now(),
            submitted_at=utc_now(),
        )
        db.session.add(q)
        db.session.commit()

    _login(client, s_id)
    resp = client.get("/quiz/history")
    assert resp.status_code == 200
    page_text = resp.data.decode("utf-8")
    assert "ACID Properties" in page_text
    assert "4 / 4" in page_text
    assert "100%" in page_text

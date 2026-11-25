"""
Comprehensive unit and integration tests for Doubt Resolution & Q&A (Stage 5).
Uses pytest with an in-memory SQLite database.
Validates permissions, reputation scoring, anonymity guarantees, rate limits, and verification flows.
"""

import pytest
from app import create_app, db
from app.models import Answer, Doubt, Reputation, User
from app.services.doubts_service import (
    DoubtServiceError,
    accept_answer,
    add_answer,
    apply_reputation_delta,
    create_doubt,
    delete_doubt,
    reopen_doubt,
    upvote_answer,
    verify_answer,
)


@pytest.fixture
def app_instance(tmp_path):
    """Create test application instance with temporary uploads folder."""
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
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


# 1. Teacher cannot post a doubt
def test_teacher_cannot_post_doubt(app_instance):
    with app_instance.app_context():
        teacher = _create_teacher("Prof. Kumar", "prof@test.com")
        with pytest.raises(DoubtServiceError, match="Faculty accounts cannot post doubts"):
            create_doubt(
                user_id=teacher.id,
                subject="DAA",
                title="Teacher posting question",
                body="Faculty members should not post questions.",
            )


# 2. Student cannot verify
def test_student_cannot_verify_answer(app_instance):
    with app_instance.app_context():
        s1 = _create_student("Student One", "s1@test.com")
        s2 = _create_student("Student Two", "s2@test.com")

        doubt = create_doubt(s1.id, "DAA", "Title of the question", "Body of the question here.")
        ans = add_answer(doubt.id, s2.id, "Here is an answer to your doubt.")

        with pytest.raises(DoubtServiceError, match="Only faculty members can verify answers"):
            verify_answer(ans.id, teacher_id=s1.id)


# 3. Cannot upvote own answer
def test_cannot_upvote_own_answer(app_instance):
    with app_instance.app_context():
        s1 = _create_student("Student One", "s1@test.com")
        s2 = _create_student("Student Two", "s2@test.com")

        doubt = create_doubt(s1.id, "DBMS", "Title of DBMS Question", "Body explanation of DBMS issue.")
        ans = add_answer(doubt.id, s2.id, "Valid answer given by s2.")

        with pytest.raises(DoubtServiceError, match="cannot upvote your own answer"):
            upvote_answer(ans.id, user_id=s2.id)


# 4. Double upvote toggles off and keeps count in sync
def test_upvote_toggle_and_sync(app_instance):
    with app_instance.app_context():
        s1 = _create_student("Student One", "s1@test.com")
        s2 = _create_student("Student Two", "s2@test.com")

        doubt = create_doubt(s1.id, "DBMS", "Title of DBMS Question", "Body explanation of DBMS issue.")
        ans = add_answer(doubt.id, s2.id, "Valid answer given by s2.")

        # 1. Upvote ON -> returns upvotes=1, voted=True
        res1 = upvote_answer(ans.id, user_id=s1.id)
        assert res1["upvotes"] == 1
        assert res1["voted"] is True
        assert ans.upvotes == 1

        rep = Reputation.query.filter_by(user_id=s2.id, subject="DBMS").first()
        assert rep is not None
        assert rep.score == 2  # +2 pts

        # 2. Upvote OFF (toggle) -> returns upvotes=0, voted=False
        res2 = upvote_answer(ans.id, user_id=s1.id)
        assert res2["upvotes"] == 0
        assert res2["voted"] is False
        assert ans.upvotes == 0
        assert rep.score == 0  # -2 pts


# 5. Only owner can accept answer
def test_only_owner_can_accept_answer(app_instance):
    with app_instance.app_context():
        s1 = _create_student("Asker Student", "asker@test.com")
        s2 = _create_student("Answerer Student", "answerer@test.com")
        intruder = _create_student("Intruder Student", "intruder@test.com")

        doubt = create_doubt(s1.id, "Python", "Python GIL question title", "Python GIL detailed body text.")
        ans = add_answer(doubt.id, s2.id, "Detailed answer explaining GIL.")

        # Intruder attempts to accept answer -> raises
        with pytest.raises(DoubtServiceError, match="Only the author of this doubt can accept"):
            accept_answer(doubt.id, asker_id=intruder.id, answer_id=ans.id)

        # Owner accepts answer -> succeeds
        accept_answer(doubt.id, asker_id=s1.id, answer_id=ans.id)
        assert doubt.status == "solved"
        assert doubt.solved_answer_id == ans.id

        # Reputation awarded: +10 pts
        rep = Reputation.query.filter_by(user_id=s2.id, subject="Python").first()
        assert rep is not None
        assert rep.score == 10
        assert rep.badge == "Helper"

        # Reopen doubt -> clears status and reverses 10 pts
        reopen_doubt(doubt.id, asker_id=s1.id)
        assert doubt.status == "open"
        assert doubt.solved_answer_id is None
        assert rep.score == 0
        assert rep.badge is None


# 6. Anonymous doubt never exposes asker name to another user
def test_anonymous_doubt_never_leaks_author_name(app_instance):
    client = app_instance.test_client()
    with app_instance.app_context():
        secret_author = _create_student("Secret Infiltrator", "secret@test.com")
        _create_student("Curious Viewer", "viewer@test.com")

        doubt = create_doubt(
            user_id=secret_author.id,
            subject="Physics",
            title="Quantum Entanglement question",
            body="Explain Einstein Podolsky Rosen paradox.",
            is_anonymous=True,
        )
        doubt_id = doubt.id

    # 1. Other user logs in and views detail page
    client.post("/auth/login", data={"email": "viewer@test.com", "password": "pass123"})
    res = client.get(f"/doubts/{doubt_id}")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Secret Infiltrator" not in html
    assert "Anonymous Student" in html

    # 2. Other user views doubts index
    res_index = client.get("/doubts", follow_redirects=True)
    html_index = res_index.data.decode("utf-8")
    assert "Secret Infiltrator" not in html_index
    assert "Anonymous" in html_index

    # 3. Author logs in and views their own doubt -> sees 'You (Posted anonymously)'
    client.get("/auth/logout")
    client.post("/auth/login", data={"email": "secret@test.com", "password": "pass123"})
    res_author = client.get(f"/doubts/{doubt_id}")
    html_author = res_author.data.decode("utf-8")
    assert "You (Posted anonymously)" in html_author


# 7. Reputation and badge tier updates
def test_reputation_and_badge_updates(app_instance):
    with app_instance.app_context():
        u = _create_student("Learner", "learner@test.com")

        # Initial: 0 pts, no badge
        rep = apply_reputation_delta(u.id, "Java", 5)
        assert rep.score == 5
        assert rep.badge is None

        # Reach Helper tier (>= 10)
        rep = apply_reputation_delta(u.id, "Java", 5)
        assert rep.score == 10
        assert rep.badge == "Helper"

        # Reach Expert tier (>= 30)
        rep = apply_reputation_delta(u.id, "Java", 20)
        assert rep.score == 30
        assert rep.badge == "Expert"

        # Reach Guru tier (>= 60)
        rep = apply_reputation_delta(u.id, "Java", 35)
        assert rep.score == 65
        assert rep.badge == "Guru"

        # Demote back
        rep = apply_reputation_delta(u.id, "Java", -40)
        assert rep.score == 25
        assert rep.badge == "Helper"


# 8. Student answer limit of 3 per doubt
def test_student_answer_limit(app_instance):
    with app_instance.app_context():
        asker = _create_student("Asker", "asker2@test.com")
        answerer = _create_student("Answerer", "answerer2@test.com")
        teacher = _create_teacher("Prof. Teacher", "teacher_limit@test.com")

        doubt = create_doubt(asker.id, "DAA", "Title of DAA question", "Detailed body of DAA question.")

        # Post 3 answers as student -> succeeds
        add_answer(doubt.id, answerer.id, "Answer #1 for the doubt.")
        add_answer(doubt.id, answerer.id, "Answer #2 for the doubt.")
        add_answer(doubt.id, answerer.id, "Answer #3 for the doubt.")

        # 4th answer by student -> blocked
        with pytest.raises(DoubtServiceError, match="maximum limit of 3 answers"):
            add_answer(doubt.id, answerer.id, "Answer #4 attempted by student.")

        # Teachers have no 3-answer limit
        add_answer(doubt.id, teacher.id, "Teacher feedback answer #1.")
        add_answer(doubt.id, teacher.id, "Teacher feedback answer #2.")
        add_answer(doubt.id, teacher.id, "Teacher feedback answer #3.")
        add_answer(doubt.id, teacher.id, "Teacher feedback answer #4.")
        assert Answer.query.filter_by(doubt_id=doubt.id, user_id=teacher.id).count() == 4


# 9. Owner cannot delete a doubt that has answers
def test_owner_cannot_delete_doubt_with_answers(app_instance):
    with app_instance.app_context():
        asker = _create_student("Asker", "asker3@test.com")
        helper = _create_student("Helper", "helper3@test.com")
        teacher = _create_teacher("Prof. Mod", "mod@test.com")

        doubt = create_doubt(asker.id, "DBMS", "Title of DBMS question", "Detailed body of question.")

        # Asker can delete when 0 answers
        # Let's add an answer
        add_answer(doubt.id, helper.id, "Helpful answer to question.")

        # Asker attempts to delete -> blocked
        with pytest.raises(DoubtServiceError, match="Cannot delete a doubt that has received answers"):
            delete_doubt(doubt.id, user_id=asker.id)

        # Faculty can delete any doubt (moderation override)
        assert delete_doubt(doubt.id, user_id=teacher.id) is True
        assert db.session.get(Doubt, doubt.id) is None


# 10. Image routes require login
def test_image_routes_require_login(app_instance):
    client = app_instance.test_client()
    # Unauthenticated GET
    res_doubt = client.get("/doubts/1/image")
    assert res_doubt.status_code == 302  # redirects to login

    res_ans = client.get("/answers/1/image")
    assert res_ans.status_code == 302

    res_ans_doubts = client.get("/doubts/answers/1/image")
    assert res_ans_doubts.status_code == 302

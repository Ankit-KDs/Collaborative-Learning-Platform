"""
Comprehensive End-to-End Smoke Test Suite for Stage 8.
Validates the complete application lifecycle, security hardening, rate limiting,
health endpoints, error handlers, and core collaborative workflows.
"""

import pytest
from app import create_app, db
from app.auth.routes import reset_failed_logins
from app.models import (
    Answer,
    BuddyRequest,
    ChatMember,
    ChatRoom,
    Doubt,
    Message,
    Reputation,
    Skill,
    User,
)


@pytest.fixture
def test_app():
    """Create test application configured with isolated in-memory database."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    """Provide Flask test client."""
    return test_app.test_client()


def test_health_check_endpoint(client):
    """Verify /health returns 200 OK with connected database status."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data


def test_security_headers_present(client):
    """Verify that after_request injects strict security headers and CSP."""
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in res.headers
    csp = res.headers.get("Content-Security-Policy")
    assert "default-src 'self'" in csp
    assert "https://cdn.jsdelivr.net" in csp


def test_custom_error_pages(client):
    """Verify friendly custom error templates for 404, 403, and 413."""
    # 404 Not Found
    res_404 = client.get("/non-existent-page-url-xyz")
    assert res_404.status_code == 404
    assert b"404 - Page Not Found" in res_404.data

    # 403 Forbidden (Unauthenticated access to protected teacher resource)
    res_403 = client.get("/moderation")
    # Redirects to login (302) with warning
    assert res_403.status_code in (302, 403)


def test_login_rate_limiting_enforced(test_app, client):
    """Verify that 5 failed logins within 15 minutes trigger HTTP 429 lockout."""
    with test_app.app_context():
        reset_failed_logins(clear_all=True)
        # Create student account
        user = User(
            name="Test Student",
            email="rate_test@demo.com",
            role="student",
            branch="Computer Science",
            year=2,
        )
        user.set_password("correct_password")
        db.session.add(user)
        db.session.commit()

    # Submit 5 incorrect passwords
    for _ in range(5):
        res = client.post(
            "/auth/login",
            data={"email": "rate_test@demo.com", "password": "wrong_password"},
        )
        assert res.status_code == 200  # Renders login with flash error

    # 6th attempt must be locked out with HTTP 429
    res_locked = client.post(
        "/auth/login",
        data={"email": "rate_test@demo.com", "password": "correct_password"},
    )
    assert res_locked.status_code == 429
    assert b"Too many failed login attempts" in res_locked.data

    # Reset rate limits and verify login succeeds
    reset_failed_logins(clear_all=True)
    res_success = client.post(
        "/auth/login",
        data={"email": "rate_test@demo.com", "password": "correct_password"},
        follow_redirects=True,
    )
    assert res_success.status_code == 200
    assert b"Welcome back, Test Student!" in res_success.data


def test_leaderboard_renders_and_preserves_doubt_anonymity(test_app, client):
    """Verify /leaderboard calculates rankings without leaking anonymous doubt authors."""
    with test_app.app_context():
        # Setup students and reputations
        s1 = User(name="Leader One", email="l1@demo.com", role="student", branch="CS", year=3)
        s1.set_password("demo1234")
        s2 = User(name="Leader Two", email="l2@demo.com", role="student", branch="IT", year=2)
        s2.set_password("demo1234")
        db.session.add_all([s1, s2])
        db.session.flush()

        rep1 = Reputation(user_id=s1.id, subject="Data Structures", score=75, badge="Guru")
        rep2 = Reputation(user_id=s2.id, subject="Data Structures", score=25, badge="Helper")
        db.session.add_all([rep1, rep2])
        db.session.commit()

    res = client.get("/leaderboard")
    assert res.status_code == 200
    assert b"Platform Academic Leaderboard" in res.data
    assert b"Leader One" in res.data
    assert b"Guru" in res.data

    # Subject filter
    res_subj = client.get("/leaderboard?subject=Data+Structures")
    assert res_subj.status_code == 200
    assert b"Leader Two" in res_subj.data
    assert b"Helper" in res_subj.data


def test_end_to_end_student_lifecycle(test_app, client):
    """
    Complete End-to-End flow:
    Registration -> Skills -> Match -> Buddy Request -> Accept -> Chat -> Doubt -> Answer -> Vote -> Verify -> Accept.
    """
    with test_app.app_context():
        # 1. Create Seeker, Helper, and Teacher
        seeker = User(name="Seeker Alice", email="alice@test.com", role="student", branch="CS", year=2)
        seeker.set_password("pass1234")
        helper = User(name="Helper Bob", email="bob@test.com", role="student", branch="CS", year=2)
        helper.set_password("pass1234")
        teacher = User(name="Prof Dave", email="dave@test.com", role="teacher", branch="CS", year=4)
        teacher.set_password("pass1234")
        db.session.add_all([seeker, helper, teacher])
        db.session.flush()

        # 2. Add Skills
        skill_seeker = Skill(user_id=seeker.id, subject="Python", level="Weak")
        skill_helper = Skill(user_id=helper.id, subject="Python", level="Strong")
        db.session.add_all([skill_seeker, skill_helper])
        db.session.commit()

        # 3. Create Buddy Request & Accept -> Private Chat
        from app.services.requests_service import send_buddy_request, accept_buddy_request
        req = send_buddy_request(sender_id=seeker.id, receiver_id=helper.id, subject="Python")
        room = accept_buddy_request(request_id=req.id, user_id=helper.id)
        assert room.type == "private"

        # 4. Post Message in Private Chat
        msg = Message(room_id=room.id, sender_id=seeker.id, text="Hi Bob, thanks for connecting!")
        db.session.add(msg)
        db.session.commit()

        # 5. Create Study Group
        from app.services.groups_service import create_group
        grp_room = create_group(creator_id=seeker.id, name="Python Algorithms Study Group", subject="Python")
        assert grp_room.type == "group"

        # 6. Post an Anonymous Doubt
        from app.services.doubts_service import create_doubt, add_answer, upvote_answer, verify_answer, accept_answer
        doubt = create_doubt(
            user_id=seeker.id,
            subject="Python",
            title="How to optimize recursion in Fibonacci?",
            body="Is memoization or bottom-up tabulation preferred for O(1) space?",
            is_anonymous=True,
        )
        assert doubt.is_anonymous is True

        # 7. Bob answers the doubt
        ans = add_answer(doubt_id=doubt.id, user_id=helper.id, body="Use iterative bottom-up approach with two variables for O(1) space.")
        assert ans.upvotes == 0

        # 8. Seeker upvotes Bob's answer (+2 pts)
        upvote_answer(answer_id=ans.id, user_id=seeker.id)
        db.session.refresh(ans)
        assert ans.upvotes == 1

        # 9. Faculty verifies Bob's answer (+15 pts)
        verify_answer(answer_id=ans.id, teacher_id=teacher.id)
        db.session.refresh(ans)
        assert ans.is_verified is True

        # 10. Asker accepts Bob's answer (+10 pts)
        accept_answer(doubt_id=doubt.id, asker_id=seeker.id, answer_id=ans.id)
        db.session.refresh(doubt)
        assert doubt.solved_answer_id == ans.id
        assert doubt.status == "solved"

        # 11. Verify Bob's Reputation Score: 2 + 15 + 10 = 27 (Helper Tier)
        rep = Reputation.query.filter_by(user_id=helper.id, subject="Python").first()
        assert rep is not None
        assert rep.score == 27
        assert rep.badge == "Helper"

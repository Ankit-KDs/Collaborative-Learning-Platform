"""
Unit and algorithmic tests for Study Buddy Bipartite Matching Service.
Uses pytest with an in-memory SQLite database.
"""

import pytest

from app import create_app, db
from app.models import BuddyRequest, Skill, User
from app.services.matching import (
    compute_helper_load,
    find_help_opportunities,
    find_matches_for_user,
)


@pytest.fixture
def app_instance():
    """Create and configure a clean testing app instance with an in-memory SQLite database."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db_session(app_instance):
    """Provide clean database session for tests."""
    with app_instance.app_context():
        yield db.session


def test_weak_user_gets_strong_helpers_only(app_instance, db_session):
    """
    Test Rule 1: A user with 'Weak' proficiency in a subject must only be matched
    with helpers who have 'Strong' proficiency in that exact subject.
    Peers with 'Average' or 'Weak' in that subject must be excluded.
    """
    with app_instance.app_context():
        # Seeker
        seeker = User(name="Seeker Alice", email="alice@test.com", role="student", branch="Computer Science", year=2)
        seeker.set_password("pass123")
        db.session.add(seeker)
        db.session.commit()
        db.session.add(Skill(user_id=seeker.id, subject="Data Structures", level="Weak"))

        # Helper 1: Strong (Should be matched)
        helper_strong = User(name="Strong Bob", email="bob@test.com", role="student", branch="Computer Science", year=2)
        helper_strong.set_password("pass123")
        db.session.add(helper_strong)
        db.session.commit()
        db.session.add(Skill(user_id=helper_strong.id, subject="Data Structures", level="Strong"))

        # Helper 2: Average (Should be excluded)
        helper_avg = User(
            name="Average Charlie", email="charlie@test.com", role="student", branch="Computer Science", year=2
        )
        helper_avg.set_password("pass123")
        db.session.add(helper_avg)
        db.session.commit()
        db.session.add(Skill(user_id=helper_avg.id, subject="Data Structures", level="Average"))

        # Helper 3: Weak (Should be excluded)
        helper_weak = User(name="Weak Dan", email="dan@test.com", role="student", branch="Computer Science", year=2)
        helper_weak.set_password("pass123")
        db.session.add(helper_weak)
        db.session.commit()
        db.session.add(Skill(user_id=helper_weak.id, subject="Data Structures", level="Weak"))

        db.session.commit()

        # Execute matching
        matches = find_matches_for_user(seeker.id)
        assert len(matches) == 1
        assert matches[0]["subject"] == "Data Structures"
        matched_helpers = matches[0]["helpers"]
        assert len(matched_helpers) == 1
        assert matched_helpers[0]["user"].id == helper_strong.id
        assert matched_helpers[0]["user"].name == "Strong Bob"


def test_self_is_excluded_from_matches(app_instance, db_session):
    """
    Test Rule 2: A student cannot be matched with themselves, even if they have
    skills in that or other subjects.
    """
    with app_instance.app_context():
        user = User(name="Self User", email="self@test.com", role="student", branch="Computer Science", year=2)
        user.set_password("pass123")
        db.session.add(user)
        db.session.commit()

        # Give user Weak in OS
        db.session.add(Skill(user_id=user.id, subject="Operating Systems", level="Weak"))
        db.session.commit()

        matches = find_matches_for_user(user.id)
        assert len(matches) == 1
        assert len(matches[0]["helpers"]) == 0


def test_teachers_are_excluded_from_matches(app_instance, db_session):
    """
    Test Rule 3: Faculty / Teacher accounts must never be returned as peer helpers.
    """
    with app_instance.app_context():
        student = User(name="Student Sam", email="sam@test.com", role="student", branch="Computer Science", year=2)
        student.set_password("pass123")
        teacher = User(
            name="Prof. Alan Turing", email="turing@test.com", role="teacher", branch="Computer Science", year=1
        )
        teacher.set_password("pass123")
        db.session.add_all([student, teacher])
        db.session.commit()

        db.session.add(Skill(user_id=student.id, subject="DAA", level="Weak"))
        db.session.add(Skill(user_id=teacher.id, subject="DAA", level="Strong"))
        db.session.commit()

        matches = find_matches_for_user(student.id)
        assert len(matches) == 1
        # Teacher must be excluded
        assert len(matches[0]["helpers"]) == 0

        # Teacher requesting matches returns empty
        teacher_matches = find_matches_for_user(teacher.id)
        assert teacher_matches == []


def test_overloaded_helper_is_excluded(app_instance, db_session):
    """
    Test Rule 4: Saturated / Overloaded helpers (load >= MAX_HELPER_LOAD, default 3)
    must be capped and excluded to prevent helper burnout and starvation.
    """
    with app_instance.app_context():
        seeker = User(name="Seeker", email="seeker@test.com", role="student", branch="IT", year=2)
        seeker.set_password("pass123")
        helper = User(name="Popular Helper", email="popular@test.com", role="student", branch="IT", year=2)
        helper.set_password("pass123")
        db.session.add_all([seeker, helper])
        db.session.commit()

        db.session.add(Skill(user_id=seeker.id, subject="DBMS", level="Weak"))
        db.session.add(Skill(user_id=helper.id, subject="DBMS", level="Strong"))
        db.session.commit()

        # Initially helper has load 0 -> should appear
        m1 = find_matches_for_user(seeker.id)
        assert len(m1[0]["helpers"]) == 1

        # Simulate 3 other students sending requests to helper (reaching cap = 3)
        other_students = []
        for i in range(3):
            u = User(name=f"Peer {i}", email=f"peer{i}@test.com", role="student", branch="IT", year=2)
            u.set_password("pass123")
            db.session.add(u)
            other_students.append(u)
        db.session.commit()

        for peer in other_students:
            req = BuddyRequest(sender_id=peer.id, receiver_id=helper.id, subject="DBMS", status="pending")
            db.session.add(req)
        db.session.commit()

        assert compute_helper_load(helper.id) == 3

        # Now helper must be excluded due to load >= 3
        m2 = find_matches_for_user(seeker.id)
        assert len(m2[0]["helpers"]) == 0


def test_lower_load_helper_is_ranked_first(app_instance, db_session):
    """
    Test Rule 5: Load Balancing - helpers with lower active loads are ranked
    ahead of helpers with higher active loads.
    """
    with app_instance.app_context():
        seeker = User(name="Seeker", email="seeker@test.com", role="student", branch="IT", year=2)
        seeker.set_password("pass123")

        # Helper A: Load = 2
        helper_a = User(name="Helper Busy", email="busy@test.com", role="student", branch="IT", year=2)
        helper_a.set_password("pass123")

        # Helper B: Load = 0
        helper_b = User(name="Helper Free", email="free@test.com", role="student", branch="IT", year=2)
        helper_b.set_password("pass123")

        # Helper C: Load = 1
        helper_c = User(name="Helper Moderate", email="mod@test.com", role="student", branch="IT", year=2)
        helper_c.set_password("pass123")

        db.session.add_all([seeker, helper_a, helper_b, helper_c])
        db.session.commit()

        db.session.add(Skill(user_id=seeker.id, subject="Python", level="Weak"))
        db.session.add(Skill(user_id=helper_a.id, subject="Python", level="Strong"))
        db.session.add(Skill(user_id=helper_b.id, subject="Python", level="Strong"))
        db.session.add(Skill(user_id=helper_c.id, subject="Python", level="Strong"))
        db.session.commit()

        # Add dummy users to assign loads
        dummy1 = User(name="D1", email="d1@test.com", role="student", branch="IT", year=2)
        dummy1.set_password("pass123")
        dummy2 = User(name="D2", email="d2@test.com", role="student", branch="IT", year=2)
        dummy2.set_password("pass123")
        dummy3 = User(name="D3", email="d3@test.com", role="student", branch="IT", year=2)
        dummy3.set_password("pass123")
        db.session.add_all([dummy1, dummy2, dummy3])
        db.session.commit()

        # Helper A gets 2 requests
        db.session.add(BuddyRequest(sender_id=dummy1.id, receiver_id=helper_a.id, subject="Python", status="pending"))
        db.session.add(BuddyRequest(sender_id=dummy2.id, receiver_id=helper_a.id, subject="Python", status="accepted"))

        # Helper C gets 1 request
        db.session.add(BuddyRequest(sender_id=dummy3.id, receiver_id=helper_c.id, subject="Python", status="pending"))

        db.session.commit()

        matches = find_matches_for_user(seeker.id)
        helpers = matches[0]["helpers"]
        assert len(helpers) == 3

        # Expected Ranking: Helper B (load 0) -> Helper C (load 1) -> Helper A (load 2)
        assert helpers[0]["user"].id == helper_b.id
        assert helpers[0]["load"] == 0
        assert helpers[0]["load_status"] == "Available"

        assert helpers[1]["user"].id == helper_c.id
        assert helpers[1]["load"] == 1

        assert helpers[2]["user"].id == helper_a.id
        assert helpers[2]["load"] == 2
        assert helpers[2]["load_status"] == "Busy"


def test_existing_buddy_request_excludes_helper(app_instance, db_session):
    """
    Test Rule 6: An existing pending or accepted BuddyRequest between seeker and helper
    for that subject prunes the matching edge.
    """
    with app_instance.app_context():
        seeker = User(name="Seeker", email="seeker@test.com", role="student", branch="CS", year=2)
        seeker.set_password("pass123")
        helper = User(name="Helper", email="helper@test.com", role="student", branch="CS", year=2)
        helper.set_password("pass123")
        db.session.add_all([seeker, helper])
        db.session.commit()

        db.session.add(Skill(user_id=seeker.id, subject="Java", level="Weak"))
        db.session.add(Skill(user_id=helper.id, subject="Java", level="Strong"))
        db.session.commit()

        # Before request -> appears
        m1 = find_matches_for_user(seeker.id)
        assert len(m1[0]["helpers"]) == 1

        # Add pending request from seeker to helper
        req = BuddyRequest(sender_id=seeker.id, receiver_id=helper.id, subject="Java", status="pending")
        db.session.add(req)
        db.session.commit()

        # After request -> excluded
        m2 = find_matches_for_user(seeker.id)
        assert len(m2[0]["helpers"]) == 0


def test_tiebreaker_same_branch_and_year(app_instance, db_session):
    """
    Test Rule 7: Tiebreakers - when helper loads are equal, preference is given
    first to same branch, then same year, then name.
    """
    with app_instance.app_context():
        seeker = User(name="Seeker", email="s@test.com", role="student", branch="Computer Science", year=3)
        seeker.set_password("pass123")

        # Helper 1: Different branch (Mechanical), Different year (1)
        h1 = User(name="Alpha", email="h1@test.com", role="student", branch="Mechanical Engineering", year=1)
        h1.set_password("pass123")

        # Helper 2: Same branch (Computer Science), Same year (3) -> Best match!
        h2 = User(name="Beta", email="h2@test.com", role="student", branch="Computer Science", year=3)
        h2.set_password("pass123")

        # Helper 3: Same branch (Computer Science), Different year (2)
        h3 = User(name="Gamma", email="h3@test.com", role="student", branch="Computer Science", year=2)
        h3.set_password("pass123")

        db.session.add_all([seeker, h1, h2, h3])
        db.session.commit()

        db.session.add(Skill(user_id=seeker.id, subject="Machine Learning", level="Weak"))
        db.session.add(Skill(user_id=h1.id, subject="Machine Learning", level="Strong"))
        db.session.add(Skill(user_id=h2.id, subject="Machine Learning", level="Strong"))
        db.session.add(Skill(user_id=h3.id, subject="Machine Learning", level="Strong"))
        db.session.commit()

        matches = find_matches_for_user(seeker.id)
        helpers = matches[0]["helpers"]
        assert len(helpers) == 3

        # h2 (same branch & year) must be 1st
        assert helpers[0]["user"].id == h2.id
        # h3 (same branch, diff year) must be 2nd
        assert helpers[1]["user"].id == h3.id
        # h1 (diff branch & year) must be 3rd
        assert helpers[2]["user"].id == h1.id


def test_find_help_opportunities_reverse_view(app_instance, db_session):
    """
    Test Rule 8: find_help_opportunities returns students who are Weak in the user's
    Strong subjects, excluding self and teachers.
    """
    with app_instance.app_context():
        strong_student = User(name="Expert Student", email="expert@test.com", role="student", branch="CS", year=3)
        strong_student.set_password("pass123")

        weak_student = User(name="Learner Student", email="learner@test.com", role="student", branch="CS", year=2)
        weak_student.set_password("pass123")

        teacher = User(name="Prof. Teacher", email="prof@test.com", role="teacher", branch="CS", year=1)
        teacher.set_password("pass123")

        db.session.add_all([strong_student, weak_student, teacher])
        db.session.commit()

        db.session.add(Skill(user_id=strong_student.id, subject="Physics", level="Strong"))
        db.session.add(Skill(user_id=weak_student.id, subject="Physics", level="Weak"))
        db.session.add(Skill(user_id=teacher.id, subject="Physics", level="Weak"))  # Teachers shouldn't appear
        db.session.commit()

        opps = find_help_opportunities(strong_student.id)
        assert len(opps) == 1
        assert opps[0]["subject"] == "Physics"
        assert len(opps[0]["seekers"]) == 1
        assert opps[0]["seekers"][0]["user"].id == weak_student.id

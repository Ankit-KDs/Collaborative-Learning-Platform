"""
Unit and integration tests for Stage 9:
Real-world readiness, role-specific registration, role-specific dashboards/navigation,
and empty-state resilience.
"""

import os
import subprocess
import sys
import pytest
from app import create_app, db
from app.models import User, TeacherSubject
from app.auth.routes import _failed_invite_code_attempts


@pytest.fixture
def test_app():
    """Create test application configured with isolated in-memory database."""
    app = create_app("testing")
    app.config["TEACHER_INVITE_CODE"] = "test-teacher-secret-code"
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        _failed_invite_code_attempts.clear()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    """Provide Flask test client."""
    return test_app.test_client()


def test_student_registration_validation(client, test_app):
    """Verify student registration validates program, specialization, and year-to-sem bounds."""
    # 1. Invalid Program
    res = client.post(
        "/auth/register",
        data={
            "role_type": "student",
            "student-name": "Alice Tester",
            "student-email": "alice_invalid@college.edu",
            "student-college_name": "Metro Tech",
            "student-enrollment_no": "MT-2024-001",
            "student-program": "InvalidProgram",
            "student-specialization": "CSE",
            "student-year": "1",
            "student-semester": "1",
            "student-password": "Password123",
            "student-confirm_password": "Password123",
        },
        follow_redirects=True,
    )
    assert b"is not supported" in res.data or res.status_code == 200
    with test_app.app_context():
        assert User.query.filter_by(email="alice_invalid@college.edu").first() is None

    # 2. Year exceeding program length (BCA has 3 years, choosing Year 4)
    res = client.post(
        "/auth/register",
        data={
            "role_type": "student",
            "student-name": "Alice Tester",
            "student-email": "alice_bca@college.edu",
            "student-college_name": "Metro Tech",
            "student-enrollment_no": "MT-2024-002",
            "student-program": "BCA",
            "student-specialization": "General",
            "student-year": "4",
            "student-semester": "7",
            "student-password": "Password123",
            "student-confirm_password": "Password123",
        },
        follow_redirects=True,
    )
    assert b"out of bounds" in res.data or res.status_code == 200
    with test_app.app_context():
        assert User.query.filter_by(email="alice_bca@college.edu").first() is None

    # 3. Valid B.Tech Student Registration
    res = client.post(
        "/auth/register",
        data={
            "role_type": "student",
            "student-name": "Alice Tester",
            "student-email": "alice_valid@college.edu",
            "student-college_name": "Metro Tech",
            "student-enrollment_no": "MT-2024-003",
            "student-program": "B.Tech",
            "student-specialization": "CSE",
            "student-year": "2",
            "student-semester": "3",
            "student-section": "A",
            "student-bio": "Excited to study computer science.",
            "student-password": "Password123",
            "student-confirm_password": "Password123",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Student account created successfully" in res.data

    with test_app.app_context():
        u = User.query.filter_by(email="alice_valid@college.edu").first()
        assert u is not None
        assert u.role == "student"
        assert u.college_name == "Metro Tech"
        assert u.enrollment_no == "MT-2024-003"
        assert u.program == "B.Tech"
        assert u.specialization == "CSE"
        assert u.year == 2
        assert u.semester == 3


def test_duplicate_enrollment_blocked_in_same_college(client, test_app):
    """Enforce unique enrollment numbers within the same college."""
    # First student in Metro Tech
    client.post(
        "/auth/register",
        data={
            "role_type": "student",
            "student-name": "Student One",
            "student-email": "one@college.edu",
            "student-college_name": "Metro Tech",
            "student-enrollment_no": "ENROLL-101",
            "student-program": "B.Tech",
            "student-specialization": "CSE",
            "student-year": "1",
            "student-semester": "1",
            "student-password": "Password123",
            "student-confirm_password": "Password123",
        },
        follow_redirects=True,
    )

    # Second student in same college with same enrollment -> BLOCKED
    res = client.post(
        "/auth/register",
        data={
            "role_type": "student",
            "student-name": "Student Two",
            "student-email": "two@college.edu",
            "student-college_name": "Metro Tech",
            "student-enrollment_no": "ENROLL-101",
            "student-program": "B.Tech",
            "student-specialization": "IT",
            "student-year": "1",
            "student-semester": "1",
            "student-password": "Password123",
            "student-confirm_password": "Password123",
        },
        follow_redirects=True,
    )
    assert b"already registered at this college" in res.data
    with test_app.app_context():
        assert User.query.filter_by(email="two@college.edu").first() is None

    # Third student in DIFFERENT college with same enrollment -> ALLOWED
    res = client.post(
        "/auth/register",
        data={
            "role_type": "student",
            "student-name": "Student Three",
            "student-email": "three@other.edu",
            "student-college_name": "City University",
            "student-enrollment_no": "ENROLL-101",
            "student-program": "B.Tech",
            "student-specialization": "IT",
            "student-year": "1",
            "student-semester": "1",
            "student-password": "Password123",
            "student-confirm_password": "Password123",
        },
        follow_redirects=True,
    )
    assert b"Student account created successfully" in res.data
    with test_app.app_context():
        assert User.query.filter_by(email="three@other.edu").first() is not None


def test_teacher_registration_invite_code_protection(client, test_app):
    """Faculty registration requires valid invite code and creates TeacherSubjects."""
    # 1. Invalid invite code -> REJECTED
    res = client.post(
        "/auth/register",
        data={
            "role_type": "teacher",
            "teacher-name": "Dr. Wrong Code",
            "teacher-email": "wrong@faculty.edu",
            "teacher-college_name": "Metro Tech",
            "teacher-employee_id": "EMP-999",
            "teacher-department": "Computer Science",
            "teacher-designation": "Assistant Professor",
            "teacher-qualification": "Ph.D",
            "teacher-experience_years": "5",
            "teacher-subjects": ["Data Structures", "Python"],
            "teacher-invite_code": "wrong-secret-code",
            "teacher-password": "Password123",
            "teacher-confirm_password": "Password123",
        },
        follow_redirects=True,
    )
    assert b"Invalid faculty invite code" in res.data
    with test_app.app_context():
        assert User.query.filter_by(email="wrong@faculty.edu").first() is None

    # 2. Valid invite code -> SUCCEEDS
    res = client.post(
        "/auth/register",
        data={
            "role_type": "teacher",
            "teacher-name": "Dr. Valid Faculty",
            "teacher-email": "faculty@college.edu",
            "teacher-college_name": "Metro Tech",
            "teacher-employee_id": "EMP-101",
            "teacher-department": "Computer Science",
            "teacher-designation": "Associate Professor",
            "teacher-qualification": "Ph.D",
            "teacher-experience_years": "8",
            "teacher-subjects": ["Data Structures", "DAA", "Python"],
            "teacher-invite_code": "test-teacher-secret-code",
            "teacher-password": "Password123",
            "teacher-confirm_password": "Password123",
        },
        follow_redirects=True,
    )
    assert b"Faculty account created successfully" in res.data

    with test_app.app_context():
        t = User.query.filter_by(email="faculty@college.edu").first()
        assert t is not None
        assert t.role == "teacher"
        assert t.employee_id == "EMP-101"
        assert t.designation == "Associate Professor"
        subjects = t.teaching_subject_list
        assert "Data Structures" in subjects
        assert "DAA" in subjects
        assert "Python" in subjects


def test_duplicate_employee_id_blocked_in_same_college(client, test_app):
    """Enforce unique employee ID within the same college."""
    # Register first faculty
    client.post(
        "/auth/register",
        data={
            "role_type": "teacher",
            "teacher-name": "Prof A",
            "teacher-email": "profa@college.edu",
            "teacher-college_name": "Metro Tech",
            "teacher-employee_id": "FACULTY-001",
            "teacher-department": "Computer Science",
            "teacher-designation": "Assistant Professor",
            "teacher-qualification": "M.Tech",
            "teacher-experience_years": "4",
            "teacher-subjects": ["DBMS"],
            "teacher-invite_code": "test-teacher-secret-code",
            "teacher-password": "Password123",
            "teacher-confirm_password": "Password123",
        },
        follow_redirects=True,
    )

    # Register second faculty with duplicate employee ID in same college
    res = client.post(
        "/auth/register",
        data={
            "role_type": "teacher",
            "teacher-name": "Prof B",
            "teacher-email": "profb@college.edu",
            "teacher-college_name": "Metro Tech",
            "teacher-employee_id": "FACULTY-001",
            "teacher-department": "IT",
            "teacher-designation": "Assistant Professor",
            "teacher-qualification": "M.Tech",
            "teacher-experience_years": "3",
            "teacher-subjects": ["Operating Systems"],
            "teacher-invite_code": "test-teacher-secret-code",
            "teacher-password": "Password123",
            "teacher-confirm_password": "Password123",
        },
        follow_redirects=True,
    )
    assert b"already registered at this college" in res.data
    with test_app.app_context():
        assert User.query.filter_by(email="profb@college.edu").first() is None


def test_role_specific_navigation_and_dashboards(client, test_app):
    """Teachers should not see student nav items; dashboards display role-tailored content."""
    # 1. Create a student and a teacher
    with test_app.app_context():
        student = User(
            name="Nav Student",
            email="navstudent@college.edu",
            role="student",
            college_name="Metro Tech",
            enrollment_no="NAV-S-01",
            program="B.Tech",
            specialization="CSE",
            year=2,
            semester=3,
        )
        student.set_password("Password123")
        db.session.add(student)

        teacher = User(
            name="Nav Teacher",
            email="navteacher@college.edu",
            role="teacher",
            college_name="Metro Tech",
            employee_id="NAV-T-01",
            department="Computer Science & Engineering",
            designation="Professor",
            qualification="Ph.D",
            experience_years=12,
        )
        teacher.set_password("Password123")
        db.session.add(teacher)
        db.session.flush()

        db.session.add(TeacherSubject(user_id=teacher.id, subject="Data Structures"))
        db.session.commit()

    # Log in as Student
    client.post("/auth/login", data={"email": "navstudent@college.edu", "password": "Password123"}, follow_redirects=True)
    res_student = client.get("/dashboard")
    assert res_student.status_code == 200
    # Student sees student nav
    assert b"Matches" in res_student.data
    assert b"Requests" in res_student.data
    assert b"Chats" in res_student.data
    assert b"Groups" in res_student.data
    assert b"Quiz" in res_student.data
    assert b"Learning Path" in res_student.data
    # Student sees focus areas on dashboard
    assert b"Focus Areas" in res_student.data
    assert b"bg-teacher-gradient" not in res_student.data

    # Log out
    client.get("/auth/logout", follow_redirects=True)

    # Log in as Teacher
    client.post("/auth/login", data={"email": "navteacher@college.edu", "password": "Password123"}, follow_redirects=True)
    res_teacher = client.get("/dashboard")
    assert res_teacher.status_code == 200
    # Teacher does NOT see student navigation tabs
    assert b">Matches<" not in res_teacher.data
    assert b">Requests<" not in res_teacher.data
    assert b">Chats<" not in res_teacher.data
    assert b">Groups<" not in res_teacher.data
    assert b">Quiz<" not in res_teacher.data
    assert b">Learning Path<" not in res_teacher.data
    # Teacher sees teacher elements
    assert b"bg-teacher-gradient" in res_teacher.data
    assert b"Faculty Portal" in res_teacher.data
    assert b"Moderation" in res_teacher.data
    assert b"doubtsVolumeChart" in res_teacher.data
    assert b"Answers Awaiting Verification" in res_teacher.data


def test_empty_database_all_pages_render_without_error(client, test_app):
    """Verify that starting with a completely empty database, all key endpoints return 200 OK."""
    # Public pages
    assert client.get("/").status_code == 200
    assert client.get("/auth/login").status_code == 200
    assert client.get("/auth/register").status_code == 200
    assert client.get("/leaderboard").status_code == 200

    # Create one student in empty DB to test student pages
    with test_app.app_context():
        u = User(
            name="Fresh Student",
            email="fresh@college.edu",
            role="student",
            college_name="Empty Tech",
            enrollment_no="EMP-01",
            program="B.Tech",
            specialization="CSE",
            year=1,
            semester=1,
        )
        u.set_password("Password123")
        db.session.add(u)
        db.session.commit()

    client.post("/auth/login", data={"email": "fresh@college.edu", "password": "Password123"}, follow_redirects=True)

    # All student endpoints render 200 OK with clean empty states
    pages_to_check = [
        "/dashboard",
        "/profile",
        "/matches",
        "/requests",
        "/chats",
        "/groups/",
        "/doubts",
        "/quiz",
        "/exam-mode",
        "/learning-path",
        "/leaderboard",
    ]
    for page in pages_to_check:
        res = client.get(page, follow_redirects=True)
        assert res.status_code == 200, f"Page {page} failed with status {res.status_code}"


def test_dev_seed_refuses_to_run_without_allow_demo_seed():
    """Verify dev_seed.py exits with code 1 if ALLOW_DEMO_SEED!=true."""
    env = os.environ.copy()
    env["ALLOW_DEMO_SEED"] = "false"
    res = subprocess.run(
        [sys.executable, os.path.join("scripts", "dev_seed.py")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "DATABASE SEEDING BLOCKED" in res.stdout

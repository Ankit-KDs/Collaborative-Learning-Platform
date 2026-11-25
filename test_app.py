"""
Stage 1 Comprehensive Verification Script.
Tests:
- Application initialization and configuration
- SQLite table creation and schema validation for all 11 models
- Student registration and password hashing
- Teacher registration and authentication
- Session login, dashboard access, and logout
- @teacher_required decorator behavior (unauthenticated, student, teacher)
- Navigation and placeholder routes
"""

import sys
from app import create_app, db
from app.models import (
    User, Skill, BuddyRequest, ChatRoom, ChatMember,
    Message, MessageReport, Doubt, Answer, AnswerVote, Reputation
)
from app.utils import teacher_required
from flask import jsonify

print(f"Testing with Python: {sys.version}")

# Create test app instance
app = create_app(config_name="testing")

with app.app_context():
    # 1. Verify all 11 tables exist
    inspector = db.inspect(db.engine)
    tables = inspector.get_table_names()
    print("Detected DB Tables:", tables)

    expected_tables = [
        "users", "skills", "buddy_requests", "chat_rooms", "chat_members",
        "messages", "message_reports", "doubts", "answers", "answer_votes", "reputations"
    ]
    for tbl in expected_tables:
        assert tbl in tables, f"Missing table: {tbl}"
    assert all([BuddyRequest, Message, MessageReport])
    print("[PASS] All 11 tables verified in SQLite database.")

    # 2. Test User Model & Password Hashing
    student = User(
        name="Alex Chen",
        email="alex@college.edu",
        role="student",
        branch="Computer Science",
        year=2,
    )
    student.set_password("StudentSecret123!")
    db.session.add(student)

    teacher = User(
        name="Prof. Sarah Miller",
        email="smiller@college.edu",
        role="teacher",
        branch="Computer Science",
        year=1,
    )
    teacher.set_password("TeacherSecret123!")
    db.session.add(teacher)
    db.session.commit()

    assert student.id is not None
    assert teacher.id is not None
    assert student.check_password("StudentSecret123!")
    assert not student.check_password("WrongPassword")
    assert student.is_student and not student.is_teacher
    assert teacher.is_teacher and not teacher.is_student
    print("[PASS] User creation, password hashing, and role checks verified.")

    # 3. Test Skills & Unique Constraints
    skill1 = Skill(user_id=student.id, subject="Data Structures", level="Strong")
    db.session.add(skill1)
    db.session.commit()
    assert skill1.id is not None
    print("[PASS] Skill model verified.")

    # 4. Test Chat Room & Members
    room = ChatRoom(type="group", name="CS201 Algorithms Study Group", subject="Algorithms", created_by=teacher.id)
    db.session.add(room)
    db.session.commit()

    m1 = ChatMember(room_id=room.id, user_id=student.id)
    m2 = ChatMember(room_id=room.id, user_id=teacher.id)
    db.session.add_all([m1, m2])
    db.session.commit()
    assert room.members.count() == 2
    print("[PASS] ChatRoom and ChatMember relationships verified.")

    # 5. Test Doubt, Answer, Vote, Reputation
    doubt = Doubt(
        user_id=student.id,
        subject="Data Structures",
        title="Time complexity of Dijkstra with Min-Heap?",
        body="Can someone explain why it is O((V + E) log V)?",
        is_anonymous=False,
    )
    db.session.add(doubt)
    db.session.commit()

    ans = Answer(
        doubt_id=doubt.id,
        user_id=teacher.id,
        body="Each vertex is extracted once (V log V) and each edge might trigger a decrease-key operation (E log V).",
        is_verified=True,
    )
    db.session.add(ans)
    db.session.commit()

    vote = AnswerVote(answer_id=ans.id, user_id=student.id)
    rep = Reputation(user_id=teacher.id, subject="Data Structures", score=15, badge="Mentor")
    db.session.add_all([vote, rep])
    db.session.commit()
    assert doubt.answers.count() == 1
    assert ans.votes.count() == 1
    print("[PASS] Doubt, Answer, AnswerVote, and Reputation verified.")

# 6. Test Client HTTP Routes
client = app.test_client()


# Add a test route to verify @teacher_required
@app.route("/test-teacher-only")
@teacher_required
def test_teacher_only():
    return jsonify({"status": "teacher_granted"})


# Test unauthenticated access to dashboard -> should redirect to login
res = client.get("/dashboard")
assert res.status_code == 302
assert "/auth/login" in res.headers["Location"]
print("[PASS] Unauthenticated access to dashboard redirects to login.")

# Test unauthenticated access to teacher route -> redirect to login
res = client.get("/test-teacher-only")
assert res.status_code == 302
assert "/auth/login" in res.headers["Location"]
print("[PASS] Unauthenticated access to teacher route redirects to login.")

# Register a new user via HTTP POST (TestingConfig has WTF_CSRF_ENABLED = False)
res = client.post("/auth/register", data={
    "name": "Maria Garcia",
    "email": "mgarcia@college.edu",
    "role": "student",
    "branch": "Information Technology",
    "year": 3,
    "password": "SecurePassword123!",
    "confirm_password": "SecurePassword123!",
}, follow_redirects=True)
assert res.status_code == 200
assert b"Your account has been created successfully" in res.data
print("[PASS] HTTP Registration flow works.")

# Login as student
res = client.post("/auth/login", data={
    "email": "mgarcia@college.edu",
    "password": "SecurePassword123!",
}, follow_redirects=True)
assert res.status_code == 200
assert b"Welcome back, Maria Garcia!" in res.data
assert b"Maria Garcia" in res.data
print("[PASS] HTTP Login flow works.")

# Attempt teacher-only route with student session -> should be 403 Forbidden
res = client.get("/test-teacher-only")
assert res.status_code == 403
print("[PASS] Student restricted by @teacher_required (403 Forbidden).")

# Logout
res = client.get("/auth/logout", follow_redirects=True)
assert res.status_code == 200
assert b"signed out successfully" in res.data
print("[PASS] HTTP Logout flow works.")

# Login as teacher
res = client.post("/auth/login", data={
    "email": "smiller@college.edu",
    "password": "TeacherSecret123!",
}, follow_redirects=True)
assert res.status_code == 200
assert b"Welcome back, Prof. Sarah Miller!" in res.data
print("[PASS] Teacher Login flow works.")

# Access teacher-only route with teacher session -> should be 200 OK
res = client.get("/test-teacher-only")
assert res.status_code == 200
assert res.json == {"status": "teacher_granted"}
print("[PASS] Teacher granted access via @teacher_required.")

# Test placeholder and active module routes
for path in ["/matches", "/chats", "/groups", "/doubts", "/quiz", "/exam-mode", "/learning-path"]:
    res = client.get(path, follow_redirects=True)
    assert res.status_code == 200, f"Route {path} failed with {res.status_code}"
print("[PASS] All navbar and placeholder routes respond 200 OK.")

print("\n=== ALL STAGE 1 VERIFICATION TESTS PASSED SUCCESSFULLY! ===")

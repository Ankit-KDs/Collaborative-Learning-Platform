"""
Database Seeding Script for Stage 2.
Creates 15 demo students, 2 demo teachers, and distributes skills
such that all subjects have at least 2 Weak and 2 Strong students.
Safe to execute multiple times (idempotent).
Safe for Windows consoles (ASCII and UTF-8 stream handling).
"""

import io
import json
import os
import subprocess
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.abspath(os.path.join(_script_dir, ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

# Gate: strictly require ALLOW_DEMO_SEED=true
if os.environ.get("ALLOW_DEMO_SEED", "").strip().lower() != "true":
    print("=" * 70)
    print("CRITICAL: DATABASE SEEDING BLOCKED.")
    print("This script is for LOCAL DEVELOPMENT ONLY.")
    print("To run, set the environment variable ALLOW_DEMO_SEED=true:")
    print("  PowerShell: $env:ALLOW_DEMO_SEED='true'; python scripts/dev_seed.py")
    print("  Bash/Linux: ALLOW_DEMO_SEED=true python scripts/dev_seed.py")
    print("=" * 70)
    sys.exit(1)

# If invoked with global Python outside virtual environment, re-exec with venv Python
if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
    _venv_py = os.path.join(_proj_root, "venv", "Scripts", "python.exe")
    if os.path.isfile(_venv_py) and os.path.abspath(sys.executable) != os.path.abspath(_venv_py):
        _res = subprocess.run([_venv_py, os.path.abspath(__file__)] + sys.argv[1:])
        sys.exit(_res.returncode)

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError
_reconfig_stdout = getattr(sys.stdout, "reconfigure", None)
if callable(_reconfig_stdout):
    try:
        _reconfig_stdout(encoding="utf-8", errors="replace")
    except (AttributeError, io.UnsupportedOperation, ValueError):
        pass

_reconfig_stderr = getattr(sys.stderr, "reconfigure", None)
if callable(_reconfig_stderr):
    try:
        _reconfig_stderr(encoding="utf-8", errors="replace")
    except (AttributeError, io.UnsupportedOperation, ValueError):
        pass

from app import create_app, db  # noqa: E402
from app.config import SUBJECTS  # noqa: E402
from app.models import (  # noqa: E402
    AIHint,
    Answer,
    AnswerVote,
    BuddyRequest,
    ChatMember,
    ChatRoom,
    Doubt,
    GroupInvite,
    LearningPath,
    Message,
    MessageReport,
    QuizAttempt,
    Skill,
    TeacherSubject,
    User,
    utc_now,
)
from app.services.doubts_service import apply_reputation_delta  # noqa: E402
from app.services.requests_service import get_or_create_private_room  # noqa: E402
from typing import TypedDict  # noqa: E402

app = create_app("development")


class DemoUserDict(TypedDict):
    name: str
    email: str
    branch: str
    year: int


class SampleRequestDict(TypedDict):
    sender_id: int
    receiver_id: int
    subject: str
    status: str


class SeedAnswerDict(TypedDict):
    user_email: str
    body: str
    upvotes: int
    is_verified: bool
    is_accepted: bool


class SeedDoubtDict(TypedDict):
    asker_email: str
    subject: str
    title: str
    body: str
    is_anonymous: bool
    status: str
    answers: list[SeedAnswerDict]


DEMO_STUDENTS: list[DemoUserDict] = [
    {"name": "Aarav Sharma", "email": "student1@demo.com", "branch": "Computer Science", "year": 2},
    {"name": "Priya Patel", "email": "student2@demo.com", "branch": "Information Technology", "year": 3},
    {"name": "Rohan Iyer", "email": "student3@demo.com", "branch": "Computer Science", "year": 4},
    {"name": "Ananya Gupta", "email": "student4@demo.com", "branch": "Electronics & Communication", "year": 2},
    {"name": "Vikram Malhotra", "email": "student5@demo.com", "branch": "Mechanical Engineering", "year": 3},
    {"name": "Ishaan Verma", "email": "student6@demo.com", "branch": "Computer Science", "year": 1},
    {"name": "Neha Joshi", "email": "student7@demo.com", "branch": "Information Technology", "year": 2},
    {"name": "Siddharth Nair", "email": "student8@demo.com", "branch": "Electrical Engineering", "year": 3},
    {"name": "Kavya Reddy", "email": "student9@demo.com", "branch": "Computer Science", "year": 3},
    {"name": "Rahul Deshmukh", "email": "student10@demo.com", "branch": "Civil Engineering", "year": 2},
    {"name": "Pooja Mehta", "email": "student11@demo.com", "branch": "Information Technology", "year": 4},
    {"name": "Aditya Kulkarni", "email": "student12@demo.com", "branch": "Computer Science", "year": 2},
    {"name": "Sneha Choudhury", "email": "student13@demo.com", "branch": "Electronics & Communication", "year": 1},
    {"name": "Arjun Rao", "email": "student14@demo.com", "branch": "Computer Science", "year": 3},
    {"name": "Riya Sen", "email": "student15@demo.com", "branch": "Information Technology", "year": 2},
]

DEMO_TEACHERS: list[DemoUserDict] = [
    {"name": "Prof. Rajesh Sharma", "email": "teacher1@demo.com", "branch": "Computer Science", "year": 1},
    {"name": "Dr. Sunita Rao", "email": "teacher2@demo.com", "branch": "Information Technology", "year": 1},
]

# Subject proficiency mapping: ensures >= 2 Weak and >= 2 Strong per subject
SKILLS_DISTRIBUTION = {
    "Data Structures": {
        "Weak": ["student1@demo.com", "student4@demo.com", "student10@demo.com"],
        "Strong": ["student2@demo.com", "student3@demo.com", "student9@demo.com"],
        "Average": ["student5@demo.com"],
    },
    "DAA": {
        "Weak": ["student1@demo.com", "student5@demo.com", "student13@demo.com"],
        "Strong": ["student3@demo.com", "student7@demo.com", "student12@demo.com"],
        "Average": ["student2@demo.com"],
    },
    "DBMS": {
        "Weak": ["student2@demo.com", "student6@demo.com", "student8@demo.com"],
        "Strong": ["student1@demo.com", "student9@demo.com", "student11@demo.com"],
        "Average": ["student4@demo.com"],
    },
    "Operating Systems": {
        "Weak": ["student3@demo.com", "student7@demo.com", "student15@demo.com"],
        "Strong": ["student2@demo.com", "student4@demo.com", "student14@demo.com"],
        "Average": ["student1@demo.com"],
    },
    "Computer Networks": {
        "Weak": ["student4@demo.com", "student8@demo.com", "student12@demo.com"],
        "Strong": ["student1@demo.com", "student5@demo.com", "student11@demo.com"],
        "Average": ["student6@demo.com"],
    },
    "Mathematics": {
        "Weak": ["student5@demo.com", "student9@demo.com", "student14@demo.com"],
        "Strong": ["student6@demo.com", "student8@demo.com", "student10@demo.com"],
        "Average": ["student3@demo.com"],
    },
    "Physics": {
        "Weak": ["student6@demo.com", "student10@demo.com", "student11@demo.com"],
        "Strong": ["student4@demo.com", "student5@demo.com", "student13@demo.com"],
        "Average": ["student7@demo.com"],
    },
    "Python": {
        "Weak": ["student7@demo.com", "student11@demo.com", "student13@demo.com"],
        "Strong": ["student1@demo.com", "student6@demo.com", "student15@demo.com"],
        "Average": ["student8@demo.com"],
    },
    "Java": {
        "Weak": ["student8@demo.com", "student12@demo.com", "student14@demo.com"],
        "Strong": ["student2@demo.com", "student7@demo.com", "student9@demo.com"],
        "Average": ["student10@demo.com"],
    },
    "Machine Learning": {
        "Weak": ["student2@demo.com", "student9@demo.com", "student15@demo.com"],
        "Strong": ["student3@demo.com", "student12@demo.com", "student14@demo.com"],
        "Average": ["student1@demo.com"],
    },
}


def seed():
    """Seed users, skills, and sample load requests idempotently."""
    with app.app_context():
        # Ensure database tables exist
        db.create_all()

        print("=" * 60)
        print("[SEED] Starting Stage 2 Demo Data Seeding...")
        print("=" * 60)

        # 1. Seed Students
        users_by_email = {}
        students_added = 0
        students_skipped = 0

        for idx, s_data in enumerate(DEMO_STUDENTS):
            existing = User.query.filter_by(email=s_data["email"]).first()
            if existing:
                users_by_email[s_data["email"]] = existing
                students_skipped += 1
            else:
                user = User(
                    name=s_data["name"],
                    email=s_data["email"],
                    role="student",
                    college_name="Apex Institute of Technology",
                    enrollment_no=f"2024CS{idx+1:02d}",
                    program="B.Tech",
                    specialization="CSE",
                    branch=s_data["branch"],
                    year=s_data["year"],
                    semester=min(s_data["year"] * 2, 8),
                    section="A",
                    bio=f"Year {s_data['year']} engineering student active in peer study groups.",
                )
                user.set_password("demo1234")
                db.session.add(user)
                users_by_email[s_data["email"]] = user
                students_added += 1

        # 2. Seed Teachers
        teachers_added = 0
        teachers_skipped = 0

        for idx, t_data in enumerate(DEMO_TEACHERS):
            existing = User.query.filter_by(email=t_data["email"]).first()
            if existing:
                teachers_skipped += 1
            else:
                teacher = User(
                    name=t_data["name"],
                    email=t_data["email"],
                    role="teacher",
                    college_name="Apex Institute of Technology",
                    employee_id=f"FAC-CS-10{idx+1}",
                    department=t_data["branch"],
                    designation="Associate Professor" if idx == 0 else "Assistant Professor",
                    qualification="Ph.D" if idx == 0 else "M.Tech",
                    experience_years=8 if idx == 0 else 5,
                    branch=t_data["branch"],
                    year=1,
                    bio="Faculty member guiding students in foundational & advanced computing.",
                )
                teacher.set_password("demo1234")
                db.session.add(teacher)
                teachers_added += 1

        db.session.commit()

        # Refresh map with fresh user instances from database
        users_by_email = {u.email: u for u in User.query.all()}

        # Seed Faculty Teaching Subjects
        t1 = users_by_email.get("teacher1@demo.com")
        t2 = users_by_email.get("teacher2@demo.com")
        if t1:
            for s in ["Data Structures", "DAA", "Python", "Machine Learning"]:
                if not TeacherSubject.query.filter_by(user_id=t1.id, subject=s).first():
                    db.session.add(TeacherSubject(user_id=t1.id, subject=s))
        if t2:
            for s in ["DBMS", "Operating Systems", "Computer Networks", "Java"]:
                if not TeacherSubject.query.filter_by(user_id=t2.id, subject=s).first():
                    db.session.add(TeacherSubject(user_id=t2.id, subject=s))
        db.session.commit()

        # 3. Seed Skills
        skills_added = 0
        skills_skipped = 0

        for subject, levels in SKILLS_DISTRIBUTION.items():
            for level, email_list in levels.items():
                for email in email_list:
                    user = users_by_email.get(email)
                    if not user:
                        user = User.query.filter_by(email=email).first()
                        if user:
                            users_by_email[email] = user
                    if not user:
                        continue

                    existing_skill = Skill.query.filter_by(user_id=user.id, subject=subject).first()
                    if existing_skill:
                        existing_skill.level = level
                        skills_skipped += 1
                    else:
                        skill = Skill(user_id=user.id, subject=subject, level=level)
                        db.session.add(skill)
                        skills_added += 1

        db.session.commit()

        # 4. Seed Sample BuddyRequests, Private Chat Rooms, and Messages
        s1 = User.query.filter_by(email="student1@demo.com").first()
        s2 = User.query.filter_by(email="student2@demo.com").first()
        s3 = User.query.filter_by(email="student3@demo.com").first()
        s4 = User.query.filter_by(email="student4@demo.com").first()
        s5 = User.query.filter_by(email="student5@demo.com").first()
        s6 = User.query.filter_by(email="student6@demo.com").first()
        s9 = User.query.filter_by(email="student9@demo.com").first()

        requests_added = 0
        chats_created = 0
        messages_added = 0

        if s1 and s2 and s3 and s4 and s5 and s6 and s9:
            sample_requests: list[SampleRequestDict] = [
                # 1. Accepted: s1 (Aarav, weak) -> s2 (Priya, strong) in Data Structures
                {"sender_id": s1.id, "receiver_id": s2.id, "subject": "Data Structures", "status": "accepted"},
                # 2. Pending outgoing: s1 (Aarav, weak) -> s3 (Rohan, strong) in DAA
                {"sender_id": s1.id, "receiver_id": s3.id, "subject": "DAA", "status": "pending"},
                # 3. Incoming pending: s6 (Ishaan, weak) -> s1 (Aarav, strong) in DBMS
                {"sender_id": s6.id, "receiver_id": s1.id, "subject": "DBMS", "status": "pending"},
                # 4. Rejected: s1 (Aarav, weak) -> s9 (Kavya, strong) in Data Structures
                {"sender_id": s1.id, "receiver_id": s9.id, "subject": "Data Structures", "status": "rejected"},
                # 5. Additional requests to demonstrate helper load capping on s3 (Rohan)
                {"sender_id": s4.id, "receiver_id": s3.id, "subject": "Machine Learning", "status": "pending"},
                {"sender_id": s5.id, "receiver_id": s3.id, "subject": "DAA", "status": "pending"},
            ]

            for req in sample_requests:
                existing_req = BuddyRequest.query.filter_by(
                    sender_id=req["sender_id"],
                    receiver_id=req["receiver_id"],
                    subject=req["subject"],
                ).first()
                if not existing_req:
                    br = BuddyRequest(
                        sender_id=req["sender_id"],
                        receiver_id=req["receiver_id"],
                        subject=req["subject"],
                        status=req["status"],
                    )
                    db.session.add(br)
                    requests_added += 1
                elif existing_req.status != req["status"]:
                    existing_req.status = req["status"]

            db.session.commit()

            # Create private chat room for the accepted request between s1 and s2
            accepted_room = get_or_create_private_room(
                user1_id=s1.id,
                user2_id=s2.id,
                subject="Data Structures",
            )
            chats_created += 1

            # Seed 4 sample messages in the s1-s2 chat room if room has no messages
            if accepted_room.messages.count() == 0:
                demo_messages = [
                    (s1.id, "Hi Priya! Thanks for accepting my buddy request for Data Structures."),
                    (s2.id, "Hey Aarav! Happy to collaborate. What specific topic are you working on right now?"),
                    (s1.id, "I am struggling with Red-Black Tree balancing and left/right rotation rules."),
                    (
                        s2.id,
                        (
                            "Rotations can be tricky at first! Let me explain with the standard tree pivot rule. "
                            "I can also send a sketch."
                        ),
                    ),
                ]
                for sender_id, msg_text in demo_messages:
                    m = Message(
                        room_id=accepted_room.id,
                        sender_id=sender_id,
                        text=msg_text,
                        image_path=None,
                        is_flagged=False,
                    )
                    db.session.add(m)
                    messages_added += 1

                db.session.commit()

        # 5. Stage 4: Seed Collaborative Study Groups
        groups_added = 0
        group_messages_added = 0
        group_invites_added = 0

        s12 = User.query.filter_by(email="student12@demo.com").first()
        s13 = User.query.filter_by(email="student13@demo.com").first()

        # Group 1: "Algorithms Masterclass" (DAA)
        # Admin: s3 (Rohan), Members: s5 (Vikram), s12 (Aditya), s13 (Sneha)
        # Pending invite: s1 (Aarav)
        if s3 and s5 and s12 and s13 and s1:
            g1 = ChatRoom.query.filter_by(type="group", name="Algorithms Masterclass").first()
            if not g1:
                g1 = ChatRoom(
                    type="group",
                    name="Algorithms Masterclass",
                    subject="DAA",
                    created_by=s3.id,
                    is_active=True,
                    created_at=utc_now(),
                )
                db.session.add(g1)
                db.session.flush()
                groups_added += 1

                # Add members
                members_g1 = [
                    (s3, "admin"),
                    (s5, "member"),
                    (s12, "member"),
                    (s13, "member"),
                ]
                for member_user, role in members_g1:
                    db.session.add(
                        ChatMember(
                            room_id=g1.id,
                            user_id=member_user.id,
                            role=role,
                            joined_at=utc_now(),
                        )
                    )
                    welcome_text = (
                        f"{member_user.name} created the study group."
                        if role == "admin"
                        else f"{member_user.name} joined the group."
                    )
                    db.session.add(
                        Message(
                            room_id=g1.id,
                            sender_id=member_user.id,
                            text=welcome_text,
                            is_system=True,
                            created_at=utc_now(),
                        )
                    )
                    group_messages_added += 1

                # Add sample peer messages
                chat_g1 = [
                    (
                        s3.id,
                        (
                            "Welcome everyone to the DAA masterclass! "
                            "We will focus on Dynamic Programming and Greedy proofs."
                        ),
                    ),
                    (s5.id, "Excited to be here! Can we start with Dijkstra vs Bellman-Ford shortest paths?"),
                    (s12.id, "Sounds great. I have notes on optimal substructure for matrix chain multiplication too."),
                ]
                for sender_id, text in chat_g1:
                    db.session.add(
                        Message(
                            room_id=g1.id,
                            sender_id=sender_id,
                            text=text,
                            is_system=False,
                            created_at=utc_now(),
                        )
                    )
                    group_messages_added += 1

                # Add pending invite for s1 (Aarav Sharma)
                invite_s1 = GroupInvite(
                    room_id=g1.id,
                    invited_user_id=s1.id,
                    invited_by_id=s3.id,
                    status="pending",
                    created_at=utc_now(),
                )
                db.session.add(invite_s1)
                group_invites_added += 1

                db.session.commit()

        # Group 2: "Database System Internals" (DBMS)
        # Admin: s1 (Aarav), Members: s2 (Priya), s9 (Kavya)
        if s1 and s2 and s9:
            g2 = ChatRoom.query.filter_by(type="group", name="Database System Internals").first()
            if not g2:
                g2 = ChatRoom(
                    type="group",
                    name="Database System Internals",
                    subject="DBMS",
                    created_by=s1.id,
                    is_active=True,
                    created_at=utc_now(),
                )
                db.session.add(g2)
                db.session.flush()
                groups_added += 1

                # Add members
                members_g2 = [
                    (s1, "admin"),
                    (s2, "member"),
                    (s9, "member"),
                ]
                for member_user, role in members_g2:
                    db.session.add(
                        ChatMember(
                            room_id=g2.id,
                            user_id=member_user.id,
                            role=role,
                            joined_at=utc_now(),
                        )
                    )
                    welcome_text = (
                        f"{member_user.name} created the study group."
                        if role == "admin"
                        else f"{member_user.name} joined the group."
                    )
                    db.session.add(
                        Message(
                            room_id=g2.id,
                            sender_id=member_user.id,
                            text=welcome_text,
                            is_system=True,
                            created_at=utc_now(),
                        )
                    )
                    group_messages_added += 1

                # Add sample peer messages
                chat_g2 = [
                    (
                        s1.id,
                        (
                            "Hey folks, let's use this space to prepare for "
                            "DBMS concurrency control and ACID transactions."
                        ),
                    ),
                    (s2.id, "Great idea Aarav! We should also cover B+ tree indexing vs Hash indexing."),
                    (s9.id, "I have prepared some SQL query optimization examples with EXPLAIN ANALYZE."),
                ]
                for sender_id, text in chat_g2:
                    db.session.add(
                        Message(
                            room_id=g2.id,
                            sender_id=sender_id,
                            text=text,
                            is_system=False,
                            created_at=utc_now(),
                        )
                    )
                    group_messages_added += 1

                db.session.commit()

        # 6. Stage 5: Seed Doubts, Answers, Votes, and Reputations
        doubts_added = 0
        answers_added = 0
        users_map = {u.email: u for u in User.query.all()}
        teacher1 = users_map.get("teacher1@demo.com")
        teacher2 = users_map.get("teacher2@demo.com")

        demo_doubts_data: list[SeedDoubtDict] = [
            # 1. Solved + Teacher-verified answer (Data Structures)
            {
                "asker_email": "student1@demo.com",
                "subject": "Data Structures",
                "title": "How to balance a Red-Black Tree after node insertion?",
                "body": (
                    "I am having trouble understanding the recoloring and rotation cases "
                    "when inserting a node into a Red-Black tree. How do we know whether a "
                    "left or right rotation is required?"
                ),
                "is_anonymous": False,
                "status": "solved",
                "answers": [
                    {
                        "user_email": "student2@demo.com",
                        "body": (
                            "When inserting a node, there are 3 uncle cases. Case 1: uncle is Red -> "
                            "recolor parent, uncle, and grandparent. Case 2/3: uncle is Black -> "
                            "perform single or double rotations depending on whether the child is inside "
                            "or outside relative to grandparent."
                        ),
                        "upvotes": 4,
                        "is_verified": False,
                        "is_accepted": True,
                    },
                    {
                        "user_email": "teacher1@demo.com",
                        "body": (
                            "Priya's breakdown is spot on. Remember the fundamental invariant: "
                            "no two consecutive red nodes on any simple path from root to leaf, "
                            "and equal black-height across all paths."
                        ),
                        "upvotes": 6,
                        "is_verified": True,
                        "is_accepted": False,
                    },
                ],
            },
            # 2. Near-duplicate of #1 in same subject (Data Structures)
            {
                "asker_email": "student4@demo.com",
                "subject": "Data Structures",
                "title": "Balancing rules and rotations in Red-Black Tree insertion",
                "body": (
                    "Can someone explain the insertion fixup procedure in Red-Black trees? "
                    "Especially when the uncle node is red versus black."
                ),
                "is_anonymous": False,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student3@demo.com",
                        "body": (
                            "The key rule is that if the uncle is red, you recolor; if the uncle is black, "
                            "you rotate. There are four rotation cases: Left-Left, Left-Right, "
                            "Right-Right, and Right-Left."
                        ),
                        "upvotes": 2,
                        "is_verified": False,
                        "is_accepted": False,
                    }
                ],
            },
            # 3. Anonymous + Teacher-verified answer (DAA)
            {
                "asker_email": "student5@demo.com",
                "subject": "DAA",
                "title": "Why does Dijkstra algorithm fail on negative edge weights?",
                "body": (
                    "I understand that Dijkstra assumes once a node is visited its shortest path is finalized. "
                    "But what is the exact counter-example where it gives an incorrect shortest distance "
                    "with negative weights?"
                ),
                "is_anonymous": True,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student3@demo.com",
                        "body": (
                            "Consider 3 vertices: A->B (weight 3), A->C (weight 5), C->B (weight -4). "
                            "Dijkstra visits B with distance 3 and marks it finalized. Later it relaxes C "
                            "with distance 5, and through C reaches B with distance 1 (5 - 4 = 1). "
                            "Because B was already finalized, Dijkstra fails to update it. "
                            "Use Bellman-Ford for negative weights!"
                        ),
                        "upvotes": 5,
                        "is_verified": True,
                        "is_accepted": False,
                    }
                ],
            },
            # 4. Near-duplicate of #3 in same subject (DAA) - Unanswered
            {
                "asker_email": "student13@demo.com",
                "subject": "DAA",
                "title": "Dijkstra shortest path with negative weight cycles and edges",
                "body": (
                    "Why does Dijkstra give wrong results when there are negative weights? "
                    "Is Bellman-Ford always required instead?"
                ),
                "is_anonymous": False,
                "status": "open",
                "answers": [],
            },
            # 5. Solved with accepted answer (DBMS)
            {
                "asker_email": "student6@demo.com",
                "subject": "DBMS",
                "title": "Difference between B+ Tree index and Hash index in MySQL InnoDB",
                "body": (
                    "When should we choose a B+ tree index over a Hash index? Does B+ tree support "
                    "range queries like BETWEEN or greater than?"
                ),
                "is_anonymous": False,
                "status": "solved",
                "answers": [
                    {
                        "user_email": "student1@demo.com",
                        "body": (
                            "Hash indexing gives O(1) equality lookups (id = 5), but completely fails "
                            "for range scans because hashes do not preserve ordering. B+ Trees maintain "
                            "sorted order across doubly-linked leaf nodes, allowing O(log N) search and "
                            "fast sequential range scans."
                        ),
                        "upvotes": 3,
                        "is_verified": False,
                        "is_accepted": True,
                    }
                ],
            },
            # 6. Multiple answers (Operating Systems)
            {
                "asker_email": "student7@demo.com",
                "subject": "Operating Systems",
                "title": "Deadlock prevention versus deadlock avoidance Banker's algorithm",
                "body": (
                    "What is the key difference between deadlock prevention and avoidance? "
                    "How does the Banker's algorithm determine a safe state?"
                ),
                "is_anonymous": True,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student2@demo.com",
                        "body": (
                            "Prevention eliminates one of Coffman's 4 conditions (Mutual exclusion, "
                            "Hold & Wait, No preemption, Circular wait). Avoidance dynamically checks "
                            "safe states using Banker's algorithm before granting resource requests."
                        ),
                        "upvotes": 3,
                        "is_verified": False,
                        "is_accepted": False,
                    },
                    {
                        "user_email": "student4@demo.com",
                        "body": (
                            "In Banker's algorithm, a state is safe if there exists an execution sequence "
                            "P1, P2... such that each process can satisfy its Max Need with Current Available "
                            "+ already allocated resources."
                        ),
                        "upvotes": 2,
                        "is_verified": False,
                        "is_accepted": False,
                    },
                ],
            },
            # 7. Computer Networks
            {
                "asker_email": "student8@demo.com",
                "subject": "Computer Networks",
                "title": "TCP 3-way handshake sequence numbers and SYN flood attacks",
                "body": (
                    "How do initial sequence numbers (ISN) work during the SYN, SYN-ACK, ACK handshake, "
                    "and why does half-open state enable SYN flood DoS?"
                ),
                "is_anonymous": False,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student1@demo.com",
                        "body": (
                            "During SYN, client sends ISN_C. Server responds with SYN-ACK containing ISN_S "
                            "and Ack = ISN_C + 1. In a SYN flood, attacker sends thousands of SYNs with spoofed "
                            "IPs and never sends the final ACK, exhausting server connection backlogs."
                        ),
                        "upvotes": 4,
                        "is_verified": False,
                        "is_accepted": False,
                    }
                ],
            },
            # 8. Python + Teacher-verified (t2)
            {
                "asker_email": "student11@demo.com",
                "subject": "Python",
                "title": "GIL impact on multithreading versus multiprocessing in CPU-bound tasks",
                "body": (
                    "Why does Python multithreading not speed up CPU-bound operations? "
                    "Should I use multiprocessing or asyncio?"
                ),
                "is_anonymous": False,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student6@demo.com",
                        "body": (
                            "The Global Interpreter Lock (GIL) allows only one native thread to execute Python "
                            "bytecode at a time. For CPU-bound tasks, threads fight over the GIL. "
                            "Use multiprocessing to spawn separate OS processes with independent GILs."
                        ),
                        "upvotes": 5,
                        "is_verified": True,
                        "is_accepted": False,
                    }
                ],
            },
            # 9. Java
            {
                "asker_email": "student12@demo.com",
                "subject": "Java",
                "title": "HashMap internal collision handling: Linked List vs Red-Black Tree in Java 8",
                "body": (
                    "At what threshold does a Java HashMap bucket convert from a LinkedList to a TreeNode? "
                    "What happens during resize?"
                ),
                "is_anonymous": True,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student2@demo.com",
                        "body": (
                            "TREEIFY_THRESHOLD is 8: when bucket collisions reach 8 and table capacity >= 64, "
                            "the linked list transforms into a balanced Red-Black tree (O(log n) worst case). "
                            "UNTREEIFY_THRESHOLD is 6 when shrinking."
                        ),
                        "upvotes": 3,
                        "is_verified": False,
                        "is_accepted": False,
                    }
                ],
            },
            # 10. Machine Learning
            {
                "asker_email": "student9@demo.com",
                "subject": "Machine Learning",
                "title": "Overfitting mitigation: L1 Lasso vs L2 Ridge regularization",
                "body": (
                    "Why does L1 regularization lead to sparse weights (feature selection), "
                    "while L2 shrinks weights toward zero without setting them exactly to zero?"
                ),
                "is_anonymous": False,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student3@demo.com",
                        "body": (
                            "L1 penalty has diamond-shaped contour constraint (|w1| + |w2| <= C). "
                            "The elliptical loss contours touch the diamond at corners on the axes, "
                            "driving coefficients to exactly zero. L2 has spherical contour (w1^2 + w2^2 <= C)."
                        ),
                        "upvotes": 4,
                        "is_verified": False,
                        "is_accepted": False,
                    }
                ],
            },
            # 11. Mathematics - Unanswered
            {
                "asker_email": "student14@demo.com",
                "subject": "Mathematics",
                "title": "Eigenvalues and Eigenvectors intuition in Principal Component Analysis",
                "body": (
                    "How does calculating eigenvectors of the covariance matrix find the directions "
                    "of maximum variance in PCA?"
                ),
                "is_anonymous": False,
                "status": "open",
                "answers": [],
            },
            # 12. Physics
            {
                "asker_email": "student10@demo.com",
                "subject": "Physics",
                "title": "Wave-particle duality and de Broglie wavelength for macroscopic objects",
                "body": (
                    "Why is the de Broglie wavelength lambda = h / p completely unobservable "
                    "for everyday macroscopic objects like a baseball?"
                ),
                "is_anonymous": True,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student4@demo.com",
                        "body": (
                            "Because Planck's constant h = 6.626 x 10^-34 J*s is infinitesimally small. "
                            "For a 0.15kg baseball at 40m/s, p = 6 kg*m/s, giving lambda ~ 10^-34 meters, "
                            "which is orders of magnitude smaller than subatomic nuclei."
                        ),
                        "upvotes": 2,
                        "is_verified": False,
                        "is_accepted": False,
                    }
                ],
            },
        ]

        # Candidate voter student accounts for realistic upvotes
        voters = [
            u for u in [users_map.get(f"student{i}@demo.com") for i in range(1, 8)]
            if u is not None
        ]

        for dd in demo_doubts_data:
            asker = users_map.get(dd["asker_email"])
            if not asker:
                continue

            existing_doubt = Doubt.query.filter_by(title=dd["title"]).first()
            if not existing_doubt:
                doubt = Doubt(
                    user_id=asker.id,
                    subject=dd["subject"],
                    title=dd["title"],
                    body=dd["body"],
                    image_path=None,
                    is_anonymous=dd["is_anonymous"],
                    status=dd["status"],
                    created_at=utc_now(),
                )
                db.session.add(doubt)
                db.session.flush()
                doubts_added += 1

                accepted_ans_id = None

                for ad in dd["answers"]:
                    author = users_map.get(ad["user_email"])
                    if not author:
                        continue

                    verifier_id = None
                    if ad["is_verified"]:
                        is_not_py = dd["subject"] != "Python"
                        verifier_id = teacher1.id if (teacher1 and is_not_py) else (teacher2.id if teacher2 else None)

                    ans = Answer(
                        doubt_id=doubt.id,
                        user_id=author.id,
                        body=ad["body"],
                        image_path=None,
                        upvotes=ad["upvotes"],
                        is_verified=ad["is_verified"],
                        verified_by=verifier_id,
                        verified_at=utc_now() if ad["is_verified"] else None,
                        created_at=utc_now(),
                    )
                    db.session.add(ans)
                    db.session.flush()
                    answers_added += 1

                    if ad["is_accepted"]:
                        accepted_ans_id = ans.id
                        apply_reputation_delta(author.id, doubt.subject, 10)

                    if ad["is_verified"]:
                        apply_reputation_delta(author.id, doubt.subject, 15)

                    if ad["upvotes"] > 0:
                        apply_reputation_delta(author.id, doubt.subject, ad["upvotes"] * 2)

                    # Add actual AnswerVote records
                    vote_count = 0
                    for v in voters:
                        if v.id != author.id and vote_count < ad["upvotes"]:
                            db.session.add(AnswerVote(answer_id=ans.id, user_id=v.id, created_at=utc_now()))
                            vote_count += 1

                if accepted_ans_id:
                    doubt.solved_answer_id = accepted_ans_id

                db.session.commit()

        # 7. Stage 6: Seed AI Hints, Quiz Attempts, and Learning Paths
        ai_hints_added = 0
        quiz_attempts_added = 0
        learning_paths_added = 0

        # Seed cached AI hint on Doubt 1 (Red-Black tree doubt)
        doubt1 = Doubt.query.filter_by(title="How to balance a Red-Black Tree after node insertion?").first()
        if doubt1:
            existing_hint = AIHint.query.filter_by(doubt_id=doubt1.id).first()
            if not existing_hint:
                db.session.add(
                    AIHint(
                        doubt_id=doubt1.id,
                        hint_text=(
                            "Focus on the uncle node's color! When the uncle is Red, you recolor the parent, "
                            "uncle, and grandparent. When the uncle is Black, check whether the inserted node "
                            "forms a line or an elbow with parent and grandparent to perform single or double "
                            "rotations. Remember to verify your logic with classmates or course instructors."
                        ),
                        regenerated_count=0,
                        helpful=True,
                        created_at=utc_now(),
                    )
                )
                ai_hints_added += 1

        # Seed sample submitted Quiz Attempts for student1, student2, student3
        s1 = users_map.get("student1@demo.com")
        s2 = users_map.get("student2@demo.com")
        s3 = users_map.get("student3@demo.com")

        demo_quizzes = [
            (
                s1,
                "Data Structures",
                "Red-Black Trees & Balancing",
                "Medium",
                5,
                4,
                [
                    {
                        "question": "What is the maximum height of a Red-Black tree with n internal nodes?",
                        "options": ["log2(n)", "2 * log2(n+1)", "n/2", "n - 1"],
                        "correct_index": 1,
                        "explanation": "A Red-Black tree has maximum height 2*log2(n+1).",
                    },
                    {
                        "question": "What is the color of the root in a valid Red-Black tree?",
                        "options": ["Red", "Black", "Either Red or Black", "Depends on tree depth"],
                        "correct_index": 1,
                        "explanation": "The root of a Red-Black tree must always be Black.",
                    },
                    {
                        "question": "Can two red nodes be adjacent (parent-child) in a Red-Black tree?",
                        "options": [
                            "Yes, if root is black",
                            "No, never",
                            "Yes, at leaf nodes only",
                            "Only during deletions",
                        ],
                        "correct_index": 1,
                        "explanation": "No two red nodes can appear consecutively on any path.",
                    },
                    {
                        "question": "What is the time complexity of search in a Red-Black tree?",
                        "options": ["O(1)", "O(log n)", "O(n)", "O(n log n)"],
                        "correct_index": 1,
                        "explanation": "Height is logarithmic, guaranteeing O(log n) search.",
                    },
                    {
                        "question": "What operation restores balance after an 'elbow' violation?",
                        "options": [
                            "Single rotation only",
                            "Recoloring only",
                            "Double rotation (left-right or right-left)",
                            "Tree rebuild",
                        ],
                        "correct_index": 2,
                        "explanation": "Elbow violations require a double rotation.",
                    },
                ],
                {"0": 1, "1": 1, "2": 1, "3": 1, "4": 0},
            ),
            (
                s1,
                "DAA",
                "Dynamic Programming & Substructure",
                "Hard",
                5,
                2,
                [
                    {
                        "question": "Which property is strictly required for Dynamic Programming to apply?",
                        "options": [
                            "Greedy choice property",
                            "Optimal substructure and overlapping subproblems",
                            "Divide and conquer independence",
                            "Strict monotonicity",
                        ],
                        "correct_index": 1,
                        "explanation": "Optimal substructure and overlapping subproblems are the hallmarks of DP.",
                    },
                    {
                        "question": "What is the time complexity of Matrix Chain Multiplication with DP?",
                        "options": ["O(n)", "O(n log n)", "O(n^2)", "O(n^3)"],
                        "correct_index": 3,
                        "explanation": "Standard DP has n^2 subproblems each taking O(n) work, giving O(n^3).",
                    },
                    {
                        "question": "What is the difference between memoization and tabulation?",
                        "options": [
                            "Memoization is bottom-up, tabulation is top-down",
                            "Memoization is top-down (recursive), tabulation is bottom-up (iterative)",
                            "They are identical in implementation",
                            "Tabulation requires hash maps",
                        ],
                        "correct_index": 1,
                        "explanation": "Memoization caches top-down recursion; tabulation fills tables bottom-up.",
                    },
                    {
                        "question": "What is the space complexity of Longest Common Subsequence (LCS)?",
                        "options": ["O(1)", "O(min(m, n)) for length only", "O(m + n)", "O(2^n)"],
                        "correct_index": 1,
                        "explanation": "When finding only the length, space can be optimized to O(min(m, n)).",
                    },
                    {
                        "question": "Does 0/1 Knapsack exhibit greedy choice property?",
                        "options": ["Yes", "No", "Only when sorted by weight", "Only if weights are powers of 2"],
                        "correct_index": 1,
                        "explanation": "0/1 Knapsack lacks the greedy choice property and requires DP.",
                    },
                ],
                {"0": 1, "1": 0, "2": 1, "3": 0, "4": 0},
            ),
            (
                s1,
                "DBMS",
                "Transactions & Concurrency Control",
                "Medium",
                5,
                5,
                [
                    {
                        "question": "What does the 'I' stand for in ACID properties?",
                        "options": ["Integrity", "Isolation", "Inheritance", "Indexing"],
                        "correct_index": 1,
                        "explanation": "Isolation ensures concurrent transactions execute without interference.",
                    },
                    {
                        "question": "Which concurrency protocol prevents cascading aborts?",
                        "options": ["Basic 2PL", "Strict 2PL", "Timestamp ordering", "Validation protocol"],
                        "correct_index": 1,
                        "explanation": "Strict 2PL holds exclusive locks until commit, preventing dirty reads.",
                    },
                    {
                        "question": "What is a phantom read?",
                        "options": [
                            "Reading uncommitted data",
                            "Reading modified values within transaction",
                            "A query retrieves a set of rows satisfying a condition that changes concurrently",
                            "Deadlock detection failure",
                        ],
                        "correct_index": 2,
                        "explanation": "Phantom reads occur when concurrent transactions insert matching rows.",
                    },
                    {
                        "question": "What is the purpose of WAL (Write-Ahead Logging)?",
                        "options": [
                            "Speed up SELECT queries",
                            "Ensure Atomicity and Durability before writing dirty pages to disk",
                            "Enforce foreign keys",
                            "Compress tables",
                        ],
                        "correct_index": 1,
                        "explanation": "WAL guarantees log records are on non-volatile storage before page updates.",
                    },
                    {
                        "question": "Which isolation level prevents non-repeatable reads but allows phantom reads?",
                        "options": ["Read Uncommitted", "Read Committed", "Repeatable Read", "Serializable"],
                        "correct_index": 2,
                        "explanation": "Repeatable Read locks rows read, preventing non-repeatable reads.",
                    },
                ],
                {"0": 1, "1": 1, "2": 2, "3": 1, "4": 2},
            ),
            (
                s2,
                "Data Structures",
                "Graph Traversals (BFS & DFS)",
                "Hard",
                5,
                5,
                [
                    {
                        "question": "What data structure does BFS use?",
                        "options": ["Stack", "Queue", "Priority Queue", "Binary Search Tree"],
                        "correct_index": 1,
                        "explanation": "BFS uses a FIFO queue.",
                    },
                    {
                        "question": "What is the time complexity of BFS on an adjacency list graph G=(V, E)?",
                        "options": ["O(V)", "O(E)", "O(V + E)", "O(V * E)"],
                        "correct_index": 2,
                        "explanation": "BFS visits every vertex and edge once: O(V + E).",
                    },
                    {
                        "question": "Can DFS be used to detect cycles in a directed graph?",
                        "options": [
                            "No",
                            "Yes, by tracking back edges in recursion stack",
                            "Only in trees",
                            "Only if weights are positive",
                        ],
                        "correct_index": 1,
                        "explanation": "A back edge in DFS indicates a cycle in directed graphs.",
                    },
                    {
                        "question": "Which algorithm computes topological sort of a DAG?",
                        "options": [
                            "BFS / Kahn's algorithm or DFS finish times",
                            "Dijkstra",
                            "Kruskal",
                            "Floyd-Warshall",
                        ],
                        "correct_index": 0,
                        "explanation": "Kahn's in-degree BFS or reverse DFS post-order produce topological sort.",
                    },
                    {
                        "question": "Does BFS find shortest path in unweighted graphs?",
                        "options": ["No", "Yes, guaranteed minimal edge count", "Only if bipartite", "Only in DAGs"],
                        "correct_index": 1,
                        "explanation": "BFS explores level by level, ensuring shortest edge paths.",
                    },
                ],
                {"0": 1, "1": 2, "2": 1, "3": 0, "4": 1},
            ),
            (
                s3,
                "Machine Learning",
                "Supervised Learning Fundamentals",
                "Medium",
                5,
                3,
                [
                    {
                        "question": "What is the primary difference between classification and regression?",
                        "options": [
                            "Classification predicts continuous values, regression predicts discrete",
                            "Classification predicts categorical labels, regression predicts continuous values",
                            "Regression cannot handle multiple features",
                            "Classification does not require training data",
                        ],
                        "correct_index": 1,
                        "explanation": "Classification outputs discrete labels; regression outputs continuous numbers.",
                    },
                    {
                        "question": "What does high variance indicate in a model?",
                        "options": [
                            "Underfitting",
                            "Overfitting to training noise",
                            "Perfect generalization",
                            "Insufficient model parameters",
                        ],
                        "correct_index": 1,
                        "explanation": "High variance means the model is overly sensitive to training fluctuations.",
                    },
                    {
                        "question": "What is the goal of L2 regularization (Ridge)?",
                        "options": [
                            "Set weights strictly to zero",
                            "Shrink weights toward zero to reduce complexity",
                            "Eliminate bias completely",
                            "Speed up training",
                        ],
                        "correct_index": 1,
                        "explanation": "Ridge penalizes sum of squared weights, shrinking coefficients smoothly.",
                    },
                    {
                        "question": "What is cross-validation used for?",
                        "options": [
                            "Data cleaning",
                            "Feature scaling",
                            "Evaluating generalization performance and preventing overfitting",
                            "Model deployment",
                        ],
                        "correct_index": 2,
                        "explanation": "Cross-validation provides an unbiased estimate of generalization performance.",
                    },
                    {
                        "question": "What loss function is standard for binary classification?",
                        "options": [
                            "Mean Squared Error",
                            "Binary Cross-Entropy (Log Loss)",
                            "Hinge Loss",
                            "Huber Loss",
                        ],
                        "correct_index": 1,
                        "explanation": "Binary cross-entropy optimizes log-likelihood for Bernoulli labels.",
                    },
                ],
                {"0": 1, "1": 1, "2": 1, "3": 0, "4": 0},
            ),
        ]

        for user_obj, sub, topic, diff, num_q, score, q_list, a_dict in demo_quizzes:
            if not user_obj:
                continue
            existing_quiz = QuizAttempt.query.filter_by(
                user_id=user_obj.id,
                subject=sub,
                topic=topic,
            ).first()
            if not existing_quiz:
                q_attempt = QuizAttempt(
                    user_id=user_obj.id,
                    subject=sub,
                    topic=topic,
                    difficulty=diff,
                    num_questions=num_q,
                    questions_json=json.dumps(q_list),
                    answers_json=json.dumps(a_dict),
                    score=score,
                    created_at=utc_now(),
                    submitted_at=utc_now(),
                )
                db.session.add(q_attempt)
                quiz_attempts_added += 1

        # Seed cached LearningPath for student1
        if s1:
            existing_lp = LearningPath.query.filter_by(user_id=s1.id).first()
            if not existing_lp:
                from app.services.learning_stats import compute_student_learning_stats
                stats_s1 = compute_student_learning_stats(s1.id)
                demo_plan = {
                    "motivation": (
                        "Focusing on Dynamic Programming proofs and Red-Black tree rotations will "
                        "strengthen your algorithmic foundations rapidly!"
                    ),
                    "subjects": [
                        {
                            "subject": "DAA",
                            "steps": [
                                "Step 1: Master optimal substructure proof technique using cut-and-paste arguments.",
                                "Step 2: Practice matrix chain multiplication and 0/1 knapsack state transitions.",
                                "Step 3: Solve 3 classic DP problems on peer platforms and verify with your group.",
                            ],
                        },
                        {
                            "subject": "Data Structures",
                            "steps": [
                                "Step 1: Review Red-Black tree properties and the 3 uncle-color cases.",
                                "Step 2: Sketch left and right rotations manually on paper for 5 test sequences.",
                                "Step 3: Take another AI practice quiz to test edge cases in deletion recoloring.",
                            ],
                        },
                        {
                            "subject": "Physics",
                            "steps": [
                                "Step 1: Review de Broglie wavelength calculations and Planck constant scaling.",
                                "Step 2: Solve uncertainty principle momentum vs position spread equations.",
                                "Step 3: Ask a doubt in the community forum if wave-packet dispersion is unclear.",
                            ],
                        },
                    ],
                }
                db.session.add(
                    LearningPath(
                        user_id=s1.id,
                        content_json=json.dumps(demo_plan),
                        profile_hash=stats_s1["profile_hash"],
                        generated_at=utc_now(),
                    )
                )
                learning_paths_added += 1

        db.session.commit()

        # 8. Stage 7: Seed Moderation (Auto-flagged, User-reported, Hidden, and Reviewed Messages) and Exam Doubts
        moderation_messages_added = 0
        extra_exam_doubts_added = 0

        mod_group = ChatRoom.query.filter_by(type="group").first()
        if mod_group and s1 and s2:
            s3 = users_map.get("student3@demo.com")
            s4 = users_map.get("student4@demo.com")
            s5 = users_map.get("student5@demo.com")
            s6 = users_map.get("student6@demo.com")
            s7 = users_map.get("student7@demo.com")

            # A. Auto-flagged message (mild profanity masked)
            existing_m1 = Message.query.filter_by(
                room_id=mod_group.id,
                original_text="Why is this idiot compiler throwing a segmentation fault?",
            ).first()
            if not existing_m1:
                db.session.add(
                    Message(
                        room_id=mod_group.id,
                        sender_id=s3.id if s3 else s1.id,
                        text="Why is this ***** compiler throwing a segmentation fault?",
                        original_text="Why is this idiot compiler throwing a segmentation fault?",
                        is_system=False,
                        is_flagged=True,
                        flag_reason="auto: profanity",
                        review_status="pending",
                        created_at=utc_now(),
                    )
                )
                moderation_messages_added += 1

            # B. User-reported message 1 (reason: spam)
            existing_m2 = Message.query.filter_by(
                room_id=mod_group.id,
                text="Check out this external coaching service for exam notes!",
            ).first()
            if not existing_m2:
                m2 = Message(
                    room_id=mod_group.id,
                    sender_id=s4.id if s4 else s2.id,
                    text="Check out this external coaching service for exam notes!",
                    is_system=False,
                    is_flagged=False,
                    flag_reason="user: spam",
                    review_status="pending",
                    created_at=utc_now(),
                )
                db.session.add(m2)
                db.session.flush()
                db.session.add(
                    MessageReport(
                        message_id=m2.id,
                        reporter_id=s1.id,
                        reason="spam",
                        note="Posting irrelevant promotional advertisements in study room",
                        created_at=utc_now(),
                    )
                )
                moderation_messages_added += 1

            # C. User-reported message 2 (reason: harassment)
            existing_m3 = Message.query.filter_by(
                room_id=mod_group.id,
                text="You do not understand simple pointers, stop asking dumb questions.",
            ).first()
            if not existing_m3:
                m3 = Message(
                    room_id=mod_group.id,
                    sender_id=s5.id if s5 else s2.id,
                    text="You do not understand simple pointers, stop asking dumb questions.",
                    is_system=False,
                    is_flagged=False,
                    flag_reason="user: harassment",
                    review_status="pending",
                    created_at=utc_now(),
                )
                db.session.add(m3)
                db.session.flush()
                db.session.add(
                    MessageReport(
                        message_id=m3.id,
                        reporter_id=s2.id,
                        reason="harassment",
                        note="Rude and disrespectful comments targeting peers",
                        created_at=utc_now(),
                    )
                )
                moderation_messages_added += 1

            # D. Auto-hidden message (3 distinct user reports)
            existing_m4 = Message.query.filter_by(
                room_id=mod_group.id,
                original_text="Unacceptable offensive remark towards cohort",
            ).first()
            if not existing_m4 and s1 and s2 and s3:
                m4 = Message(
                    room_id=mod_group.id,
                    sender_id=s6.id if s6 else s3.id,
                    text="[message hidden pending review]",
                    original_text="Unacceptable offensive remark towards cohort",
                    is_system=False,
                    is_flagged=True,
                    flag_reason="user: abusive",
                    review_status="pending",
                    created_at=utc_now(),
                )
                db.session.add(m4)
                db.session.flush()
                for reporter, note in [
                    (s1, "Extremely hostile tone"),
                    (s2, "Inappropriate conduct"),
                    (s3, "Violates community guidelines"),
                ]:
                    db.session.add(
                        MessageReport(
                            message_id=m4.id,
                            reporter_id=reporter.id,
                            reason="abusive",
                            note=note,
                            created_at=utc_now(),
                        )
                    )
                moderation_messages_added += 1

            # E. Already-reviewed message with strikes
            existing_m5 = Message.query.filter_by(
                room_id=mod_group.id,
                original_text="Previous offensive violation resolved by faculty",
            ).first()
            if not existing_m5 and teacher1 and s7:
                m5 = Message(
                    room_id=mod_group.id,
                    sender_id=s7.id,
                    text="[message hidden pending review]",
                    original_text="Previous offensive violation resolved by faculty",
                    is_system=False,
                    is_flagged=True,
                    flag_reason="auto: profanity",
                    review_status="confirmed",
                    reviewed_by=teacher1.id,
                    reviewed_at=utc_now(),
                    created_at=utc_now(),
                )
                db.session.add(m5)
                # Give student7 3 strikes to demonstrate the 'Repeat offender' badge
                s7.moderation_strikes = 3
                moderation_messages_added += 1

        # F. Extra doubts in 2 subjects (Algorithms & Data Structures) with near-duplicates for Exam Mode clusters
        exam_doubts_data: list[SeedDoubtDict] = [
            # Algorithms: Dijkstra cluster
            {
                "asker_email": "student2@demo.com",
                "subject": "Algorithms",
                "title": "Implementing Dijkstra algorithm using a priority queue in Python",
                "body": (
                    "How do we efficiently implement Dijkstra's single source shortest path algorithm "
                    "using heapq? How to handle duplicate vertices in the min-heap when edge relaxation occurs?"
                ),
                "is_anonymous": False,
                "status": "solved",
                "answers": [
                    {
                        "user_email": "teacher1@demo.com",
                        "body": (
                            "Use a standard min-heap with (distance, vertex) tuples. Whenever a shorter distance "
                            "is found, push the new tuple to the heap. When popping, if the popped distance is greater "
                            "than dist[u], simply skip it (lazy deletion)."
                        ),
                        "upvotes": 7,
                        "is_verified": True,
                        "is_accepted": True,
                    }
                ],
            },
            {
                "asker_email": "student3@demo.com",
                "subject": "Algorithms",
                "title": "Dijkstra algorithm shortest path implementation with min-heap",
                "body": (
                    "What is the best way to write Dijkstra's shortest path algorithm with priority queues? "
                    "Is lazy deletion in min-heap sufficient for O((V + E) log V) time complexity?"
                ),
                "is_anonymous": True,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student1@demo.com",
                        "body": (
                            "Yes! With lazy deletion, the heap contains at most O(E) elements, so each heap operation "
                            "takes O(log E) = O(log V^2) = O(log V) time, preserving optimal asymptotic complexity."
                        ),
                        "upvotes": 5,
                        "is_verified": False,
                        "is_accepted": False,
                    }
                ],
            },
            # Algorithms: Unanswered hot doubt
            {
                "asker_email": "student4@demo.com",
                "subject": "Algorithms",
                "title": "Difference between Bellman-Ford and Floyd-Warshall for negative cycle detection",
                "body": (
                    "Can someone help explain when to prefer Bellman-Ford versus Floyd-Warshall "
                    "when graphs have negative weight edges and cycles? Need help preparing for endsems."
                ),
                "is_anonymous": False,
                "status": "open",
                "answers": [],
            },
            # Data Structures: B-Tree vs B+ Tree cluster
            {
                "asker_email": "student5@demo.com",
                "subject": "Data Structures",
                "title": "Difference between B-Tree and B+ Tree in database index structures",
                "body": (
                    "Why do relational database management systems prefer B+ Trees over B-Trees "
                    "for disk-based indexing? How do leaf node linked list pointers speed up range queries?"
                ),
                "is_anonymous": False,
                "status": "solved",
                "answers": [
                    {
                        "user_email": "teacher2@demo.com",
                        "body": (
                            "In a B+ Tree, non-leaf nodes store only keys (routing search), so a disk block holds "
                            "much higher fanout. Leaf nodes contain all data records and are linked sequentially, "
                            "allowing range scans in linear sequential I/O."
                        ),
                        "upvotes": 8,
                        "is_verified": True,
                        "is_accepted": True,
                    }
                ],
            },
            {
                "asker_email": "student6@demo.com",
                "subject": "Data Structures",
                "title": "Why do relational databases use B+ Tree instead of B-Tree for indexing?",
                "body": (
                    "What are the concrete advantages of B+ Tree index structures over standard B-Trees "
                    "for range queries and disk block I/O operations?"
                ),
                "is_anonymous": True,
                "status": "open",
                "answers": [
                    {
                        "user_email": "student2@demo.com",
                        "body": (
                            "Higher fanout means lower tree height, which minimizes disk seeks. Also, range scans "
                            "don't need in-order tree traversal; you just follow the leaf linked list."
                        ),
                        "upvotes": 3,
                        "is_verified": False,
                        "is_accepted": False,
                    }
                ],
            },
        ]

        for edd in exam_doubts_data:
            asker = users_map.get(edd["asker_email"])
            if not asker:
                continue
            existing_ed = Doubt.query.filter_by(title=edd["title"]).first()
            if not existing_ed:
                d_obj = Doubt(
                    user_id=asker.id,
                    subject=edd["subject"],
                    title=edd["title"],
                    body=edd["body"],
                    image_path=None,
                    is_anonymous=edd["is_anonymous"],
                    status=edd["status"],
                    needs_human=(len(edd["answers"]) == 0),
                    created_at=utc_now(),
                )
                db.session.add(d_obj)
                db.session.flush()
                extra_exam_doubts_added += 1

                for ans_data in edd["answers"]:
                    author = users_map.get(ans_data["user_email"])
                    if not author:
                        continue
                    ans_obj = Answer(
                        doubt_id=d_obj.id,
                        user_id=author.id,
                        body=ans_data["body"],
                        upvotes=ans_data["upvotes"],
                        is_verified=ans_data["is_verified"],
                        verified_by=teacher1.id if ans_data["is_verified"] and teacher1 else None,
                        verified_at=utc_now() if ans_data["is_verified"] else None,
                        created_at=utc_now(),
                    )
                    db.session.add(ans_obj)
                    db.session.flush()
                    if ans_data["is_accepted"]:
                        d_obj.solved_answer_id = ans_obj.id

        db.session.commit()

        # 9. Verify Invariant: Each subject has >= 2 Weak and >= 2 Strong
        print("\nSubject Proficiency Distribution Verification:")
        all_passed = True
        for sub in SUBJECTS:
            weak_cnt = Skill.query.filter_by(subject=sub, level="Weak").count()
            strong_cnt = Skill.query.filter_by(subject=sub, level="Strong").count()
            avg_cnt = Skill.query.filter_by(subject=sub, level="Average").count()
            status = "[PASS]" if (weak_cnt >= 2 and strong_cnt >= 2) else "[FAIL]"
            if "[FAIL]" in status:
                all_passed = False
            print(f"  - {sub:<20} | Weak: {weak_cnt} | Average: {avg_cnt} | Strong: {strong_cnt} | {status}")

        print("\n" + "=" * 60)
        print("=== SEEDING SUMMARY ===")
        print("=" * 60)
        print(f"Students Created : {students_added} (Skipped existing: {students_skipped})")
        print(f"Teachers Created : {teachers_added} (Skipped existing: {teachers_skipped})")
        print(f"Skills Seeded    : {skills_added} (Updated existing: {skills_skipped})")
        print("Buddy Requests   : Sample requests (pending, accepted, rejected) configured")
        print(f"Private Chats    : Sample chat room with {messages_added} initial messages configured")
        print(
            f"Study Groups     : {groups_added} groups created with {group_messages_added} messages "
            f"and {group_invites_added} pending invite(s)"
        )
        print(f"Community Doubts : {doubts_added} doubts seeded with {answers_added} answers and reputation points")
        print(
            f"AI Stage 6 Demo  : {ai_hints_added} AI hint(s), {quiz_attempts_added} quiz attempt(s), "
            f"{learning_paths_added} learning path(s)"
        )
        print(
            f"Stage 7 Moderation: {moderation_messages_added} flagged/reported messages, "
            f"{extra_exam_doubts_added} extra Exam Mode doubts"
        )
        print("\n" + "=" * 60)
        print("=== LOCAL DEVELOPMENT ONLY: DEMO CREDENTIALS ===")
        print("=== DO NOT USE IN PRODUCTION OR TESTING ===")
        print("=" * 60)
        print(f"{'Email':<25} | {'Role':<18} | {'Password':<10}")
        print("-" * 60)
        print(f"{'student1@demo.com':<25} | {'Student (Year 2)':<18} | {'demo1234':<10}")
        print(f"{'student2@demo.com':<25} | {'Student (Year 3)':<18} | {'demo1234':<10}")
        print(f"{'student3@demo.com':<25} | {'Student (Year 4)':<18} | {'demo1234':<10}")
        print(f"{'student4@demo.com':<25} | {'Student (Year 2)':<18} | {'demo1234':<10}")
        print(f"{'student5@demo.com':<25} | {'Student (Year 3)':<18} | {'demo1234':<10}")
        print(f"{'teacher1@demo.com':<25} | {'Faculty (CS/DSA)':<18} | {'demo1234':<10}")
        print(f"{'teacher2@demo.com':<25} | {'Faculty (DBMS/OS)':<18} | {'demo1234':<10}")
        print("=" * 60)


if __name__ == "__main__":
    seed()

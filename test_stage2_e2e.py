"""
Comprehensive verification test for Stage 2 features:
- Profile viewing and updating
- Student subject skill addition, updating (upsert), and deletion
- Skill badge rendering (Weak, Average, Strong)
- Matches page rendering (Weak subjects, helpers, load badges, disabled request button)
- Reverse view (Students you can help)
- Teacher viewing /profile and /matches (friendly messages, no crashes)
"""

import re

from app import create_app, db
from app.models import Skill, User

app = create_app("testing")


def get_csrf(html_text: str) -> str:
    """Extract CSRF token from HTML."""
    match = re.search(r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', html_text)
    if not match:
        match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']', html_text)
    return match.group(1) if match else ""


def test_stage2_complete_flow():
    client = app.test_client()

    with app.app_context():
        # Setup: Create 1 student, 2 helpers, 1 teacher
        s1 = User(name="Student One", email="s1@test.com", role="student", branch="Computer Science", year=2)
        s1.set_password("pass123")

        h1 = User(name="Helper Alice", email="h1@test.com", role="student", branch="Computer Science", year=2)
        h1.set_password("pass123")

        h2 = User(name="Helper Bob", email="h2@test.com", role="student", branch="Information Technology", year=3)
        h2.set_password("pass123")

        teacher = User(name="Prof. Sharma", email="prof@test.com", role="teacher", branch="Computer Science", year=1)
        teacher.set_password("pass123")

        db.session.add_all([s1, h1, h2, teacher])
        db.session.commit()

        # s1 is Weak in Data Structures
        db.session.add(Skill(user_id=s1.id, subject="Data Structures", level="Weak"))
        # s1 is Strong in Python
        db.session.add(Skill(user_id=s1.id, subject="Python", level="Strong"))

        # h1 and h2 are Strong in Data Structures
        db.session.add(Skill(user_id=h1.id, subject="Data Structures", level="Strong"))
        db.session.add(Skill(user_id=h2.id, subject="Data Structures", level="Strong"))

        # h2 is Weak in Python (help opportunity for s1)
        db.session.add(Skill(user_id=h2.id, subject="Python", level="Weak"))

        db.session.commit()

    # 1. Login as Student
    res = client.post("/auth/login", data={"email": "s1@test.com", "password": "pass123"}, follow_redirects=True)
    assert res.status_code == 200
    print("[PASS] 1. Student logged in.")

    # 2. View Profile & Skills
    res = client.get("/profile")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Student One" in html
    assert "Data Structures" in html
    assert "bg-danger" in html  # Weak badge
    assert "Python" in html
    assert "bg-success" in html  # Strong badge
    print("[PASS] 2. Profile and current skills loaded with colored badges.")

    # 3. Update Profile Information (name, branch, year)
    res = client.post("/profile", data={
        "profile-name": "Student One Updated",
        "profile-branch": "Information Technology",
        "profile-year": 3,
        "profile-submit": "Save Profile",
    }, follow_redirects=True)
    assert res.status_code == 200
    assert "Student One Updated" in res.data.decode("utf-8")
    assert "Information Technology" in res.data.decode("utf-8")
    print("[PASS] 3. Profile update successful.")

    # 4. Add a new skill (DAA: Weak)
    res = client.post("/profile", data={
        "skill-subject": "DAA",
        "skill-level": "Weak",
        "skill-submit": "Add / Update Skill",
    }, follow_redirects=True)
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "DAA" in html
    assert "Added" in html or "Updated" in html
    print("[PASS] 4. New skill added.")

    # 5. Update existing skill (DAA from Weak to Average)
    res = client.post("/profile", data={
        "skill-subject": "DAA",
        "skill-level": "Average",
        "skill-submit": "Add / Update Skill",
    }, follow_redirects=True)
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "bg-warning" in html  # Average badge
    print("[PASS] 5. Skill upsert (update) verified.")

    # 6. Delete a skill
    with app.app_context():
        student_user = User.query.filter_by(email="s1@test.com").first()
        assert student_user is not None
        daa_skill = Skill.query.filter_by(user_id=student_user.id, subject="DAA").first()
        assert daa_skill is not None
        skill_id = daa_skill.id

    res = client.post(f"/profile/skill/delete/{skill_id}", follow_redirects=True)
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "removed from your profile" in html
    print("[PASS] 6. Skill deletion verified.")

    # 7. Visit /matches
    res = client.get("/matches")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Data Structures" in html
    assert "Helper Alice" in html
    assert "Helper Bob" in html
    assert "Available" in html
    assert "Send Request" in html
    assert "Students You Can Help" in html
    assert "Python" in html
    print("[PASS] 7. Matches page displays weak subjects, helpers, load status, and help opportunities.")

    # 8. Logout Student
    client.get("/auth/logout")

    # 9. Login as Teacher
    res = client.post("/auth/login", data={"email": "prof@test.com", "password": "pass123"}, follow_redirects=True)
    assert res.status_code == 200
    print("[PASS] 8. Teacher logged in.")

    # 10. Teacher visits /profile
    res = client.get("/profile")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Faculty Account Overview" in html
    assert "Teacher" in html
    print("[PASS] 9. Teacher /profile shows friendly faculty banner.")

    # 11. Teacher visits /matches
    res = client.get("/matches")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Faculty Account Information" in html
    assert "Peer study buddy matching is tailored specifically for students" in html
    print("[PASS] 10. Teacher /matches shows friendly informational message.")

    print("\n🌟 ALL STAGE 2 END-TO-END VERIFICATION CHECKS PASSED! 🌟")


if __name__ == "__main__":
    test_stage2_complete_flow()

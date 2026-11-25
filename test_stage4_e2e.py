"""
Stage 4 End-to-End Verification Script
Tests web interface, group views, invitations, and chat features with actual session cookies.
"""

import re
from app import create_app, db
from app.models import ChatMember, ChatRoom, GroupInvite, User

app = create_app("development")
client = app.test_client()


def get_csrf(html_text: str) -> str:
    match = re.search(r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', html_text)
    if not match:
        match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']', html_text)
    return match.group(1) if match else ""


print("\n--- Running Stage 4 End-to-End Verification ---")

# 1. Login as Student 1 (Aarav Sharma)
with app.app_context():
    s1 = User.query.filter_by(email="student1@demo.com").first()
    assert s1 is not None, "Demo student1 not found"
    s1_id = s1.id

    # Reset invite & membership for Group 1 so test is repeatable
    g1 = ChatRoom.query.filter_by(name="Algorithms Masterclass").first()
    if g1:
        ChatMember.query.filter_by(room_id=g1.id, user_id=s1_id).delete()
        inv = GroupInvite.query.filter_by(room_id=g1.id, invited_user_id=s1_id).first()
        if inv:
            inv.status = "pending"
        else:
            s3 = User.query.filter_by(email="student3@demo.com").first()
            if s3:
                db.session.add(GroupInvite(room_id=g1.id, invited_user_id=s1_id, invited_by_id=s3.id, status="pending"))
        db.session.commit()

with client.session_transaction() as sess:
    sess["_user_id"] = str(s1_id)
    sess["_fresh"] = True

res = client.get("/groups", follow_redirects=True)
assert res.status_code == 200
html = res.data.decode("utf-8")
csrf = get_csrf(html)
assert "Study Groups" in html
assert "Database System Internals" in html
assert "Algorithms Masterclass" in html  # Pending invite card
print("[PASS] 1. Student 1 groups hub loaded with active groups and pending invite.")

# 2. Inspect Group 2 (Database System Internals)
with app.app_context():
    g2 = ChatRoom.query.filter_by(name="Database System Internals").first()
    assert g2 is not None
    g2_id = g2.id

res = client.get(f"/groups/{g2_id}")
assert res.status_code == 200
html = res.data.decode("utf-8")
assert "Database System Internals" in html
assert "Roster" in html
assert "Pedagogically Balanced Recommendations" in html
assert "DBMS concurrency control" in html
print("[PASS] 2. Student 1 viewed group room with roster, recommendations, and chat history.")

# 3. Accept Pending Invite to Algorithms Masterclass
with app.app_context():
    invite = GroupInvite.query.filter_by(invited_user_id=s1_id, status="pending").first()
    assert invite is not None
    invite_id = invite.id

res = client.post(
    f"/groups/invites/{invite_id}/accept",
    data={"csrf_token": csrf},
    follow_redirects=True,
)
assert res.status_code == 200
html = res.data.decode("utf-8")
assert "Algorithms Masterclass" in html

with app.app_context():
    g1 = ChatRoom.query.filter_by(name="Algorithms Masterclass").first()
    assert g1 is not None
    is_member = ChatMember.query.filter_by(room_id=g1.id, user_id=s1_id).first() is not None
    assert is_member, "Student 1 should now be an active member of Group 1"
print("[PASS] 3. Student 1 successfully accepted invite and entered Algorithms Masterclass.")

# 4. Teacher View
with app.app_context():
    t1 = User.query.filter_by(email="teacher1@demo.com").first()
    assert t1 is not None
    t1_id = t1.id

with client.session_transaction() as sess:
    sess["_user_id"] = str(t1_id)
    sess["_fresh"] = True

res = client.get("/groups", follow_redirects=True)
assert res.status_code == 200
html = res.data.decode("utf-8")
assert "Faculty Advisory" in html or "teacher" in html.lower()
print("[PASS] 4. Teacher /groups displays friendly faculty informational notice.")

print("\n🌟 ALL STAGE 4 END-TO-END VERIFICATION CHECKS PASSED! 🌟\n")

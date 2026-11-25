"""
Live End-to-End HTTP Test Script.
"""

import re
import requests

session = requests.Session()
BASE = "http://127.0.0.1:5000"


def get_csrf(html_text: str) -> str:
    """Extract CSRF token from rendered HTML form."""
    match = re.search(r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', html_text)
    if not match:
        match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']', html_text)
    return match.group(1) if match else ""


# 1. Fetch Register page and CSRF
res = session.get(f"{BASE}/auth/register")
assert res.status_code == 200, f"Register page failed: {res.status_code}"
csrf = get_csrf(res.text)
assert csrf, "Failed to extract CSRF token"
print("[PASS] 1. Fetched register form with valid CSRF token.")

# 2. Register Student
student_data = {
    "csrf_token": csrf,
    "name": "John Doe",
    "email": "john.doe@college.edu",
    "role": "student",
    "branch": "Computer Science",
    "year": 2,
    "password": "StudentPassword123!",
    "confirm_password": "StudentPassword123!",
}
res = session.post(f"{BASE}/auth/register", data=student_data, allow_redirects=True)
assert res.status_code == 200
assert "Your account has been created successfully" in res.text
assert "Sign In" in res.text
print("[PASS] 2. Student registered successfully over HTTP.")

# 3. Login as Student
csrf = get_csrf(res.text)
login_data = {
    "csrf_token": csrf,
    "email": "john.doe@college.edu",
    "password": "StudentPassword123!",
}
res = session.post(f"{BASE}/auth/login", data=login_data, allow_redirects=True)
assert res.status_code == 200
assert "Welcome back, John Doe!" in res.text
assert "Student Account" in res.text
assert "Computer Science" in res.text
assert "Year 2" in res.text
print("[PASS] 3. Student logged in and viewed dashboard.")

# 4. Logout Student
res = session.get(f"{BASE}/auth/logout", allow_redirects=True)
assert res.status_code == 200
assert "signed out successfully" in res.text
print("[PASS] 4. Student logged out.")

# 5. Register Teacher
res = session.get(f"{BASE}/auth/register")
csrf = get_csrf(res.text)
teacher_data = {
    "csrf_token": csrf,
    "name": "Dr. Watson",
    "email": "watson@college.edu",
    "role": "teacher",
    "branch": "Information Technology",
    "year": 1,
    "password": "TeacherPassword123!",
    "confirm_password": "TeacherPassword123!",
}
res = session.post(f"{BASE}/auth/register", data=teacher_data, allow_redirects=True)
assert res.status_code == 200
assert "Your account has been created successfully" in res.text
print("[PASS] 5. Teacher registered successfully over HTTP.")

# 6. Login as Teacher
csrf = get_csrf(res.text)
login_data = {
    "csrf_token": csrf,
    "email": "watson@college.edu",
    "password": "TeacherPassword123!",
}
res = session.post(f"{BASE}/auth/login", data=login_data, allow_redirects=True)
assert res.status_code == 200
assert "Welcome back, Dr. Watson!" in res.text
assert "Teacher Account" in res.text
print("[PASS] 6. Teacher logged in and viewed dashboard.")

# 7. Logout Teacher
res = session.get(f"{BASE}/auth/logout", allow_redirects=True)
assert res.status_code == 200
assert "signed out successfully" in res.text
print("[PASS] 7. Teacher logged out.")

print("\n*** ALL LIVE HTTP END-TO-END TESTS COMPLETED SUCCESSFULLY! ***")

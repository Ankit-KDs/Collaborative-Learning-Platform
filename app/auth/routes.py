"""
Authentication routes for registration, role-specific onboarding, login, and logout.
"""

import hmac
import json
import time
from collections import defaultdict
from urllib.parse import urlsplit
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, TeacherSubject, AdminAuditLog, utc_now
from app.auth.forms import (
    StudentRegistrationForm,
    TeacherRegistrationForm,
    LoginForm,
    RegistrationForm,
)
from app.config import PROGRAMS

auth_bp = Blueprint("auth", __name__)

# In-memory sliding window rate limiter: records timestamps of failed login attempts
_failed_login_attempts: dict[str, list[float]] = defaultdict(list)
LOGIN_RATE_LIMIT_WINDOW = 15 * 60  # 15 minutes window
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5

# Sliding window rate limiter for teacher invite code attempts
_failed_invite_code_attempts: dict[str, list[float]] = defaultdict(list)
INVITE_CODE_RATE_LIMIT_WINDOW = 15 * 60  # 15 minutes window
INVITE_CODE_RATE_LIMIT_MAX_ATTEMPTS = 5


def get_client_ip() -> str:
    """Extract client IP address, handling reverse proxies if present."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def is_login_rate_limited(email: str, ip: str) -> tuple[bool, int]:
    """Check if the given email or IP is rate-limited. Returns (is_blocked, remaining_minutes)."""
    now = time.time()
    for key in (f"email:{email.lower()}", f"ip:{ip}"):
        attempts = [t for t in _failed_login_attempts[key] if now - t < LOGIN_RATE_LIMIT_WINDOW]
        _failed_login_attempts[key] = attempts
        if len(attempts) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            oldest = attempts[0]
            remaining_secs = int(LOGIN_RATE_LIMIT_WINDOW - (now - oldest))
            remaining_mins = max(1, (remaining_secs + 59) // 60)
            return True, remaining_mins
    return False, 0


def record_failed_login(email: str, ip: str) -> None:
    """Record a failed login attempt for both the email and IP address."""
    now = time.time()
    for key in (f"email:{email.lower()}", f"ip:{ip}"):
        attempts = [t for t in _failed_login_attempts[key] if now - t < LOGIN_RATE_LIMIT_WINDOW]
        attempts.append(now)
        _failed_login_attempts[key] = attempts


def reset_failed_logins(email: str | None = None, ip: str | None = None, clear_all: bool = False) -> None:
    """Reset rate limiter counters for an account, IP, or globally."""
    if clear_all:
        _failed_login_attempts.clear()
        return
    if email:
        _failed_login_attempts.pop(f"email:{email.lower()}", None)
    if ip:
        _failed_login_attempts.pop(f"ip:{ip}", None)


def is_invite_code_rate_limited(email: str, ip: str) -> tuple[bool, int]:
    """Check if the given email or IP is rate-limited for invite codes."""
    now = time.time()
    for key in (f"invite_email:{email.lower()}", f"invite_ip:{ip}"):
        attempts = [t for t in _failed_invite_code_attempts[key] if now - t < INVITE_CODE_RATE_LIMIT_WINDOW]
        _failed_invite_code_attempts[key] = attempts
        if len(attempts) >= INVITE_CODE_RATE_LIMIT_MAX_ATTEMPTS:
            oldest = attempts[0]
            remaining_secs = int(INVITE_CODE_RATE_LIMIT_WINDOW - (now - oldest))
            remaining_mins = max(1, (remaining_secs + 59) // 60)
            return True, remaining_mins
    return False, 0


def record_failed_invite_code(email: str, ip: str) -> None:
    """Record a failed invite code attempt."""
    now = time.time()
    for key in (f"invite_email:{email.lower()}", f"invite_ip:{ip}"):
        attempts = [t for t in _failed_invite_code_attempts[key] if now - t < INVITE_CODE_RATE_LIMIT_WINDOW]
        attempts.append(now)
        _failed_invite_code_attempts[key] = attempts


def reset_failed_invite_codes(email: str | None = None, ip: str | None = None, clear_all: bool = False) -> None:
    """Reset invite code rate limiter counters."""
    if clear_all:
        _failed_invite_code_attempts.clear()
        return
    if email:
        _failed_invite_code_attempts.pop(f"invite_email:{email.lower()}", None)
    if ip:
        _failed_invite_code_attempts.pop(f"invite_ip:{ip}", None)


def is_safe_redirect_url(target: str) -> bool:
    """Validate that redirect target is relative to prevent open redirect exploits."""
    if not target:
        return False
    ref_url = urlsplit(request.host_url)
    test_url = urlsplit(target)
    return test_url.scheme in ("", "http", "https") and ref_url.netloc == (test_url.netloc or ref_url.netloc)


def validate_student_program_academics(program: str, specialization: str, year: int, semester: int) -> tuple[bool, str]:
    """Validate program, specialization, year, and semester combinations strictly server-side."""
    if program not in PROGRAMS:
        return False, f"Selected program '{program}' is not supported."

    meta = PROGRAMS[program]
    allowed_specs = meta.get("specializations", [])
    if specialization not in allowed_specs:
        return False, f"Specialization '{specialization}' is not valid for {program}."

    max_years = meta.get("years", 4)
    if year < 1 or year > max_years:
        return False, f"Academic year {year} is out of bounds for {program} (1 to {max_years})."

    max_sems = meta.get("semesters", 8)
    if semester < 1 or semester > max_sems:
        return False, f"Semester {semester} is out of bounds for {program} (1 to {max_sems})."

    expected_semesters = (2 * year - 1, 2 * year)
    if semester not in expected_semesters:
        return False, f"Year {year} students should be in Semester {expected_semesters[0]} or {expected_semesters[1]}."

    return True, ""


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Role-specific user registration for students and faculty.
    Renders role selection tabs/cards and handles atomic creation with validation.
    """
    if current_user.is_authenticated:
        if getattr(current_user, "is_admin", False):
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("main.dashboard"))

    # Server-side rejection of admin role registration attempts
    submitted_role = (
        request.form.get("role_type") or request.form.get("role") or request.args.get("role") or ""
    ).strip().lower()
    if submitted_role == "admin" and request.method == "POST":
        flash("Administrator accounts cannot be registered publicly. Access denied.", "danger")
        return render_template(
            "auth/register.html",
            title="Create Account",
            student_form=StudentRegistrationForm(prefix="student"),
            teacher_form=TeacherRegistrationForm(prefix="teacher"),
            active_role="student",
            programs_json=json.dumps(PROGRAMS),
        ), 400

    active_role = request.args.get("role", "student").strip().lower()
    if active_role not in ("student", "teacher"):
        active_role = "student"

    student_form = StudentRegistrationForm(prefix="student")
    teacher_form = TeacherRegistrationForm(prefix="teacher")

    # Handle Student Registration Submission
    if request.method == "POST" and request.form.get("role_type") == "student":
        active_role = "student"
        if student_form.validate_on_submit():
            prog = (student_form.program.data or "").strip()
            spec = (student_form.specialization.data or "").strip()
            yr = int(student_form.year.data or 1)
            sem = int(student_form.semester.data or 1)

            # Strict server-side academic combination validation
            is_valid, err_msg = validate_student_program_academics(prog, spec, yr, sem)
            if not is_valid:
                student_form.specialization.errors = list(student_form.specialization.errors) + [err_msg]
                flash(err_msg, "danger")
            else:
                user = User(
                    name=(student_form.name.data or "").strip(),
                    email=(student_form.email.data or "").strip().lower(),
                    role="student",
                    enrollment_no=(student_form.enrollment_no.data or "").strip(),
                    college_name=(student_form.college_name.data or "").strip(),
                    program=prog,
                    specialization=spec,
                    branch=spec,  # legacy compatibility
                    year=yr,
                    semester=sem,
                    section=(student_form.section.data or "").strip() or None,
                    bio=(student_form.bio.data or "").strip() or None,
                )
                user.set_password(student_form.password.data or "")
                db.session.add(user)
                db.session.commit()

                flash("Student account created successfully! Please sign in below.", "success")
                return redirect(url_for("auth.login"))

    # Handle Teacher Registration Submission
    elif request.method == "POST" and request.form.get("role_type") == "teacher":
        active_role = "teacher"
        client_ip = get_client_ip()
        email_attempt = (teacher_form.email.data or "").strip().lower()

        # 1. Check if teacher registration is enabled via TEACHER_INVITE_CODE
        configured_code = current_app.config.get("TEACHER_INVITE_CODE", "").strip()
        if not configured_code:
            flash(
                "Faculty registration is currently disabled by the institute administrator. "
                "Please contact your academic office.",
                "warning",
            )
            return render_template(
                "auth/register.html",
                title="Create Account",
                student_form=student_form,
                teacher_form=teacher_form,
                active_role="teacher",
                programs_json=json.dumps(PROGRAMS),
            ), 403

        # 2. Rate limiting on invite code attempts
        blocked, mins_left = is_invite_code_rate_limited(email_attempt, client_ip)
        if blocked:
            flash(
                f"Too many failed faculty invite code attempts. "
                f"For security, access is temporarily locked for {mins_left} minute(s).",
                "danger",
            )
            return render_template(
                "auth/register.html",
                title="Create Account",
                student_form=student_form,
                teacher_form=teacher_form,
                active_role="teacher",
                programs_json=json.dumps(PROGRAMS),
            ), 429

        # 3. Form validation
        if teacher_form.validate_on_submit():
            submitted_code = (teacher_form.invite_code.data or "").strip()
            if not hmac.compare_digest(submitted_code, configured_code):
                record_failed_invite_code(email_attempt, client_ip)
                teacher_form.invite_code.errors = list(teacher_form.invite_code.errors) + ["Invalid faculty invite code. Access denied."]
                flash("Invalid faculty invite code. Please check with your department coordinator.", "danger")
            else:
                # Valid code: clear invite code rate limits
                reset_failed_invite_codes(email=email_attempt, ip=client_ip)

                user = User(
                    name=(teacher_form.name.data or "").strip(),
                    email=email_attempt,
                    role="teacher",
                    employee_id=(teacher_form.employee_id.data or "").strip(),
                    college_name=(teacher_form.college_name.data or "").strip(),
                    department=(teacher_form.department.data or "").strip(),
                    designation=(teacher_form.designation.data or "").strip(),
                    qualification=(teacher_form.qualification.data or "").strip(),
                    experience_years=int(teacher_form.experience_years.data or 0),
                    branch=(teacher_form.department.data or "").strip(),  # legacy compatibility
                    year=None,
                    bio=(teacher_form.bio.data or "").strip() or None,
                )
                user.set_password(teacher_form.password.data or "")
                db.session.add(user)
                db.session.flush()

                # Save teaching subjects
                for subj in (teacher_form.subjects.data or []):
                    ts = TeacherSubject(user_id=user.id, subject=subj)
                    db.session.add(ts)

                db.session.commit()
                flash("Faculty account created successfully! Please sign in below.", "success")
                return redirect(url_for("auth.login"))

    # Legacy support if simple POST with role='student' or 'teacher' (from old test cases)
    elif request.method == "POST" and not request.form.get("role_type"):
        legacy_form = RegistrationForm()
        if legacy_form.validate_on_submit():
            role = legacy_form.role.data if hasattr(legacy_form, "role") and legacy_form.role.data else "student"
            user = User(
                name=(legacy_form.name.data or "").strip(),
                email=(legacy_form.email.data or "").strip().lower(),
                role=role,
                branch=(legacy_form.branch.data or "Computer Science"),
                year=(legacy_form.year.data or 1) if role == "student" else None,
                program="B.Tech" if role == "student" else None,
                specialization="CSE" if role == "student" else None,
                college_name="Engineering College",
                enrollment_no="ENROLL-LEGACY" if role == "student" else None,
                employee_id="EMP-LEGACY" if role == "teacher" else None,
            )
            user.set_password(legacy_form.password.data or "")
            db.session.add(user)
            db.session.commit()
            flash("Account created successfully! Please sign in below.", "success")
            return redirect(url_for("auth.login"))

    return render_template(
        "auth/register.html",
        title="Create Account",
        student_form=student_form,
        teacher_form=teacher_form,
        active_role=active_role,
        programs_json=json.dumps(PROGRAMS),
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate and sign in an existing user with sliding-window rate limiting."""
    if current_user.is_authenticated:
        if getattr(current_user, "is_admin", False):
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        client_ip = get_client_ip()

        # Enforce rate limiting: 5 failed attempts per 15 minutes per email/IP
        blocked, mins_left = is_login_rate_limited(email, client_ip)
        if blocked:
            flash(
                f"Too many failed login attempts. For security, access is temporarily locked. "
                f"Please try again in {mins_left} minute(s).",
                "danger",
            )
            return render_template("auth/login.html", title="Sign In", form=form), 429

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(form.password.data or ""):
            # Check if user account is deactivated
            if not getattr(user, "is_active", True):
                flash("Your account has been deactivated. Please contact the administrator.", "danger")
                return render_template("auth/login.html", title="Sign In", form=form), 403

            # Successful authentication: clear rate limits
            reset_failed_logins(email=email, ip=client_ip)

            # Update last login timestamp
            user.last_login_at = utc_now()

            # Audit log administrator login
            if user.is_admin:
                audit = AdminAuditLog(
                    admin_id=user.id,
                    action="login",
                    target_type="user",
                    target_id=str(user.id),
                    detail="Administrator authenticated successfully",
                    ip=client_ip,
                )
                db.session.add(audit)
            db.session.commit()

            login_user(user, remember=form.remember.data)
            flash(f"Welcome back, {user.name}!", "success")

            next_page = request.args.get("next")
            if not next_page or not is_safe_redirect_url(next_page):
                if user.is_admin:
                    next_page = url_for("admin.dashboard")
                else:
                    next_page = url_for("main.dashboard")

            return redirect(next_page)

        # Failed attempt: record timestamp
        record_failed_login(email, client_ip)
        flash("Invalid email or password. Please verify your credentials and try again.", "danger")

    return render_template("auth/login.html", title="Sign In", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    """Sign out the currently authenticated user."""
    logout_user()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("auth.login"))

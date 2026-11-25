"""
Utility helpers and custom route decorators for the application.
"""

from functools import wraps
from flask import abort, current_app, flash, redirect, request, url_for
from flask_login import current_user, logout_user


def get_client_ip() -> str:
    """Extract client IP address, handling reverse proxies if present."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def teacher_required(f):
    """
    Decorator to restrict view access to authenticated users with the 'teacher' role.
    If the user is not authenticated, redirects to the login page.
    If the user is authenticated but not a teacher, aborts with HTTP 403 Forbidden.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        if current_user.role != "teacher":
            flash("Access denied. Teacher privileges required.", "danger")
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    Decorator to restrict view access strictly to authenticated administrators.
    Enforces role check, account active status, and optional IP allowlist.
    Non-admins (including teachers and students) receive HTTP 403 Forbidden.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please sign in with administrator credentials.", "warning")
            return redirect(url_for("auth.login", next=request.url))

        # Check account activation
        if not getattr(current_user, "is_active", True):
            logout_user()
            flash("Your administrator account has been deactivated. Please contact support.", "danger")
            return redirect(url_for("auth.login"))

        # Role verification
        if getattr(current_user, "role", "") != "admin":
            abort(403)

        # Optional IP allowlist enforcement
        allowlist_str = current_app.config.get("ADMIN_IP_ALLOWLIST", "").strip()
        if allowlist_str:
            allowed_ips = {ip.strip() for ip in allowlist_str.split(",") if ip.strip()}
            client_ip = get_client_ip()
            if client_ip not in allowed_ips:
                abort(403)

        return f(*args, **kwargs)

    return decorated_function

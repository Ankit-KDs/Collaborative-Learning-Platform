"""
Application factory and extension initialization for AI-Powered Collaborative Learning Platform.
"""

import os
import re
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, g, has_request_context
from flask.sessions import SecureCookieSessionInterface
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from app.config import config_by_name, BASE_DIR

_TAB_ID_RE = re.compile(r"^t_[a-zA-Z0-9_-]{6,32}$")


def extract_valid_tab_id(req) -> str | None:
    """Extract and validate a per-tab isolation token from request headers or query params."""
    if not req:
        return None
    raw = req.headers.get("X-Tab-Id") or req.args.get("_tab")
    if raw and _TAB_ID_RE.match(raw):
        return raw
    return None


class TabAwareSessionInterface(SecureCookieSessionInterface):
    """
    Isolates Flask sessions per browser tab when a valid tab ID is present
    (_tab query param or X-Tab-Id header), while preserving standard cookie
    behavior for non-tab requests (e.g., tests, CLI, API clients).
    """

    def get_cookie_name(self, app: Flask) -> str:
        tab_id = getattr(g, "tab_id", None) if has_request_context() else None
        if not tab_id and has_request_context():
            tab_id = extract_valid_tab_id(request)
            if tab_id:
                g.tab_id = tab_id
        if tab_id:
            return f"{app.config['SESSION_COOKIE_NAME']}_{tab_id}"
        return super().get_cookie_name(app)

    def open_session(self, app: Flask, request):  # type: ignore[override]
        tab_id = extract_valid_tab_id(request)
        if has_request_context():
            g.tab_id = tab_id
            g.pop("_login_user", None)
        return super().open_session(app, request)


class TabAwareLoginManager(LoginManager):
    """Prevents global remember_token cookies from leaking across isolated browser tabs."""

    def _load_user_from_remember_cookie(self, cookie):
        if has_request_context() and getattr(g, "tab_id", None):
            return None
        return super()._load_user_from_remember_cookie(cookie)


# Initialize Flask extensions
db = SQLAlchemy()
login_manager = TabAwareLoginManager()
csrf = CSRFProtect()

# Configure Flask-Login defaults
login_manager.login_view = "auth.login"  # pyright: ignore[reportAttributeAccessIssue]
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"


def create_app(config_name: str = "default") -> Flask:
    """
    Flask application factory.
    Initializes extensions, registers blueprints, creates upload/instance directories,
    and automatically creates database tables.
    """
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration
    config_obj = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_obj)

    # Fail-loud check for insecure SECRET_KEY in production environments
    if config_name == "production" or os.environ.get("FLASK_ENV") == "production":
        insecure_keys = {"", "collab-learning-dev-key-change-in-prod-8f3a92"}
        if app.config.get("SECRET_KEY") in insecure_keys:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY must be set to a strong unique secret in production."
            )

    # Ensure required directories exist before any DB operations
    upload_folder = Path(app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)

    instance_folder = BASE_DIR / "instance"
    instance_folder.mkdir(parents=True, exist_ok=True)

    logs_folder = BASE_DIR / "logs"
    logs_folder.mkdir(parents=True, exist_ok=True)

    # Configure rotating file logging (Never log passwords, API keys, or raw message text)
    if not app.testing:
        log_file = logs_folder / "app.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)

    # Initialize extensions with app instance
    app.session_interface = TabAwareSessionInterface()
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    @app.url_defaults
    def inject_tab_id_in_urls(endpoint, values):
        """Automatically propagate the active tab's _tab session token in generated URLs."""
        if endpoint == "static" or endpoint.endswith(".static"):
            return
        tab_id = getattr(g, "tab_id", None) if has_request_context() else None
        if tab_id and "_tab" not in values:
            values["_tab"] = tab_id

    # Import models so SQLAlchemy metadata is aware of all tables
    from app import models  # noqa: F401

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.main.routes import main_bp
    from app.profile.routes import profile_bp
    from app.matches.routes import matches_bp
    from app.requests.routes import requests_bp
    from app.chat.routes import chat_bp
    from app.groups import groups_bp
    from app.doubts import doubts_bp
    from app.quiz import quiz_bp
    from app.learning import learning_bp
    from app.moderation import moderation_bp
    from app.exam import exam_bp
    from app.admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp, url_prefix="")
    app.register_blueprint(profile_bp, url_prefix="")
    app.register_blueprint(matches_bp, url_prefix="")
    app.register_blueprint(requests_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(doubts_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(learning_bp)
    app.register_blueprint(moderation_bp)
    app.register_blueprint(exam_bp)
    app.register_blueprint(admin_bp)

    # Context processor for navbar notification badges (requests, group invites, moderation queue)
    @app.context_processor
    def inject_notifications():
        counts = {
            "pending_requests_count": 0,
            "pending_group_invites_count": 0,
            "pending_moderation_count": 0,
        }
        if current_user.is_authenticated:
            if current_user.is_student:
                from app.models import BuddyRequest, GroupInvite
                counts["pending_requests_count"] = BuddyRequest.query.filter_by(
                    receiver_id=current_user.id,
                    status="pending",
                ).count()
                counts["pending_group_invites_count"] = GroupInvite.query.filter_by(
                    invited_user_id=current_user.id,
                    status="pending",
                ).count()
            elif current_user.is_teacher:
                from app.models import Message
                counts["pending_moderation_count"] = Message.query.filter_by(
                    review_status="pending",
                ).count()
        return counts

    # Register custom error handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def entity_too_large(error):
        if request.is_json or request.path.startswith("/chats/"):
            return jsonify({"error": "The uploaded file is too large. Maximum allowed size is 10MB."}), 413
        return render_template("errors/413.html"), 413

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    # System Health Check endpoint
    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint returning system status and DB connectivity."""
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify({
                "status": "ok",
                "database": "connected",
                "service": "AI-Powered Collaborative Learning Platform",
                "version": "1.0.0"
            }), 200
        except Exception:
            return jsonify({
                "status": "error",
                "database": "disconnected",
                "error": "Database ping failed"
            }), 503

    # Security headers and per-tab redirect/cookie isolation applied via after_request
    @app.after_request
    def apply_security_headers(response):
        """Inject strict security headers and maintain per-tab session isolation across redirects."""
        tab_id = getattr(g, "tab_id", None) if has_request_context() else None
        if tab_id:
            if response.status_code in (301, 302, 303, 307, 308) and "Location" in response.headers:
                loc = response.headers["Location"]
                parsed = urlsplit(loc)
                if not parsed.netloc or parsed.netloc == request.host:
                    query_params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "_tab"]
                    query_params.append(("_tab", tab_id))
                    response.headers["Location"] = urlunsplit((
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        urlencode(query_params),
                        parsed.fragment,
                    ))

            # Clear any legacy browser-wide session/remember cookies so new tabs never auto-login
            global_session_cookie = app.config.get("SESSION_COOKIE_NAME", "session")
            global_remember_cookie = app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
            if global_session_cookie in request.cookies:
                response.delete_cookie(global_session_cookie)
            if global_remember_cookie in request.cookies:
                response.delete_cookie(global_remember_cookie)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy allowing local assets and required CDNs
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "frame-ancestors 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        return response

    # Auto-create all database tables and perform safe schema migrations
    with app.app_context():
        db.create_all()
        # Safe incremental migration for SQLite tables across stages
        try:
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(db.engine)
            if inspector.has_table("chat_members"):
                cols = [c["name"] for c in inspector.get_columns("chat_members")]
                if "role" not in cols:
                    db.session.execute(
                        db.text("ALTER TABLE chat_members ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'")
                    )
                    db.session.commit()

            if inspector.has_table("messages"):
                msg_cols = [c["name"] for c in inspector.get_columns("messages")]
                if "is_system" not in msg_cols:
                    db.session.execute(
                        db.text("ALTER TABLE messages ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT 0")
                    )
                    db.session.commit()
                if "original_text" not in msg_cols:
                    db.session.execute(
                        db.text("ALTER TABLE messages ADD COLUMN original_text TEXT")
                    )
                    db.session.commit()
                if "flag_reason" not in msg_cols:
                    db.session.execute(
                        db.text("ALTER TABLE messages ADD COLUMN flag_reason VARCHAR(100)")
                    )
                    db.session.commit()
                if "review_status" not in msg_cols:
                    db.session.execute(
                        db.text("ALTER TABLE messages ADD COLUMN review_status VARCHAR(20) NOT NULL DEFAULT 'none'")
                    )
                    db.session.commit()
                if "reviewed_by" not in msg_cols:
                    db.session.execute(
                        db.text("ALTER TABLE messages ADD COLUMN reviewed_by INTEGER REFERENCES users(id)")
                    )
                    db.session.commit()
                if "reviewed_at" not in msg_cols:
                    db.session.execute(
                        db.text("ALTER TABLE messages ADD COLUMN reviewed_at DATETIME")
                    )
                    db.session.commit()

            if inspector.has_table("users"):
                user_cols = [c["name"] for c in inspector.get_columns("users")]
                if "moderation_strikes" not in user_cols:
                    db.session.execute(
                        db.text("ALTER TABLE users ADD COLUMN moderation_strikes INTEGER NOT NULL DEFAULT 0")
                    )
                for col_name, col_type in [
                    ("college_name", "VARCHAR(150)"),
                    ("bio", "VARCHAR(200)"),
                    ("enrollment_no", "VARCHAR(50)"),
                    ("program", "VARCHAR(50)"),
                    ("specialization", "VARCHAR(100)"),
                    ("semester", "INTEGER"),
                    ("section", "VARCHAR(20)"),
                    ("employee_id", "VARCHAR(50)"),
                    ("department", "VARCHAR(100)"),
                    ("designation", "VARCHAR(100)"),
                    ("qualification", "VARCHAR(100)"),
                    ("experience_years", "INTEGER"),
                    ("is_active", "BOOLEAN NOT NULL DEFAULT 1"),
                    ("last_login_at", "DATETIME"),
                ]:
                    if col_name not in user_cols:
                        db.session.execute(db.text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                db.session.commit()

            if inspector.has_table("message_reports"):
                rep_cols = [c["name"] for c in inspector.get_columns("message_reports")]
                if "note" not in rep_cols:
                    db.session.execute(
                        db.text("ALTER TABLE message_reports ADD COLUMN note VARCHAR(200)")
                    )
                    db.session.commit()

            if inspector.has_table("answers"):
                ans_cols = [c["name"] for c in inspector.get_columns("answers")]
                if "verified_by" not in ans_cols:
                    db.session.execute(
                        db.text("ALTER TABLE answers ADD COLUMN verified_by INTEGER REFERENCES users(id)")
                    )
                    db.session.commit()
                if "verified_at" not in ans_cols:
                    db.session.execute(
                        db.text("ALTER TABLE answers ADD COLUMN verified_at DATETIME")
                    )
                    db.session.commit()

            if inspector.has_table("doubts"):
                doubt_cols = [c["name"] for c in inspector.get_columns("doubts")]
                if "needs_human" not in doubt_cols:
                    db.session.execute(
                        db.text("ALTER TABLE doubts ADD COLUMN needs_human BOOLEAN NOT NULL DEFAULT 0")
                    )
                    db.session.commit()
                if "solved_answer_id" not in doubt_cols:
                    db.session.execute(
                        db.text("ALTER TABLE doubts ADD COLUMN solved_answer_id INTEGER REFERENCES answers(id)")
                    )
                    db.session.commit()
                db.session.execute(
                    db.text("CREATE INDEX IF NOT EXISTS ix_doubt_subject_created ON doubts (subject, created_at)")
                )
                db.session.commit()
        except Exception:
            db.session.rollback()

    return app

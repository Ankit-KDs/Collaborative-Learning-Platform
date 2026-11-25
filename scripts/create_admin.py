"""
Interactive CLI script to create an Administrator account.
Enforces minimum 10-character password and refuses to create a second admin
unless --force is explicitly passed.
"""

import argparse
import getpass
import io
import os
import subprocess
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.abspath(os.path.join(_script_dir, ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

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

from app import create_app, db  # noqa: E402
from app.models import User, AdminAuditLog  # noqa: E402


def create_admin(name: str | None = None, email: str | None = None, password: str | None = None, force: bool = False):
    """Create an administrator user."""
    app = create_app("development")
    with app.app_context():
        db.create_all()

        existing_admin = User.query.filter_by(role="admin").first()
        if existing_admin and not force:
            print("=" * 70, file=sys.stderr)
            print("ERROR: An administrator account already exists.", file=sys.stderr)
            print(f"Existing admin: {existing_admin.name} ({existing_admin.email})", file=sys.stderr)
            print("To create an additional administrator account, pass the --force flag.", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            sys.exit(1)

        # Collect inputs if not provided via flags
        if not name:
            try:
                name = input("Enter Admin Full Name: ").strip()
            except EOFError:
                name = ""
        if not name:
            print("Error: Administrator name cannot be empty.")
            sys.exit(1)

        if not email:
            try:
                email = input("Enter Admin Email: ").strip().lower()
            except EOFError:
                email = ""
        if not email or "@" not in email:
            print("Error: A valid email address is required.")
            sys.exit(1)
        email = email.strip().lower()

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"Error: A user with email '{email}' already exists (role: {existing_user.role}).")
            sys.exit(1)

        if not password:
            try:
                password = getpass.getpass("Enter Admin Password (min 10 characters): ")
                confirm_password = getpass.getpass("Confirm Admin Password: ")
                if password != confirm_password:
                    print("Error: Passwords do not match.")
                    sys.exit(1)
            except EOFError:
                password = ""

        if not password or len(password) < 10:
            print("Error: Password must be at least 10 characters long.")
            sys.exit(1)

        # Create administrator account
        admin = User(
            name=name,
            email=email,
            role="admin",
            college_name="Platform Administration",
            branch="Administration",
            is_active=True,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.flush()

        audit = AdminAuditLog(
            admin_id=admin.id,
            action="create_admin",
            target_type="user",
            target_id=str(admin.id),
            detail=f"Admin account created via CLI for {email}",
            ip="127.0.0.1",
        )
        db.session.add(audit)
        db.session.commit()

        print("=" * 70)
        print("SUCCESS: Administrator account created successfully!")
        print(f"Name : {admin.name}")
        print(f"Email: {admin.email}")
        print(f"Role : {admin.role}")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Create a platform administrator account.")
    parser.add_argument("--name", help="Admin Full Name")
    parser.add_argument("--email", help="Admin Email")
    parser.add_argument("--password", help="Admin Password (min 10 characters)")
    parser.add_argument("--force", action="store_true", help="Allow creating additional admin accounts")

    args = parser.parse_args()
    create_admin(name=args.name, email=args.email, password=args.password, force=args.force)


if __name__ == "__main__":
    main()

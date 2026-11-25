"""
Configuration module for AI-Powered Collaborative Learning Platform.
Loads environment variables from .env and configures database, security, and upload settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project root
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
load_dotenv(BASE_DIR / ".env")

# Canonical Platform Subject List (Dropdown selection to ensure matching consistency)
SUBJECTS = [
    "Data Structures",
    "DAA",
    "DBMS",
    "Operating Systems",
    "Computer Networks",
    "Mathematics",
    "Physics",
    "Python",
    "Java",
    "Machine Learning",
]

# Canonical Skill Levels
SKILL_LEVELS = ["Weak", "Average", "Strong"]

# Standard Programs, Durations, Semesters, and Specializations
PROGRAMS = {
    "B.Tech": {
        "name": "Bachelor of Technology (B.Tech)",
        "years": 4,
        "semesters": 8,
        "specializations": [
            "CSE",
            "CSE (AI & ML)",
            "CSE (Data Science)",
            "IT",
            "ECE",
            "Electrical",
            "Mechanical",
            "Civil",
            "Chemical",
            "Other",
        ],
    },
    "M.Tech": {
        "name": "Master of Technology (M.Tech)",
        "years": 2,
        "semesters": 4,
        "specializations": [
            "CSE",
            "VLSI",
            "Structural",
            "Thermal",
            "Other",
        ],
    },
    "BCA": {
        "name": "Bachelor of Computer Applications (BCA)",
        "years": 3,
        "semesters": 6,
        "specializations": [
            "General",
            "Data Science",
            "Cloud Computing",
            "Cyber Security",
            "Other",
        ],
    },
    "MCA": {
        "name": "Master of Computer Applications (MCA)",
        "years": 2,
        "semesters": 4,
        "specializations": [
            "General",
            "AI & ML",
            "Data Science",
            "Cyber Security",
            "Other",
        ],
    },
    "B.Sc": {
        "name": "Bachelor of Science (B.Sc)",
        "years": 3,
        "semesters": 6,
        "specializations": [
            "Computer Science",
            "IT",
            "Mathematics",
            "Physics",
            "Chemistry",
            "Electronics",
            "Other",
        ],
    },
    "M.Sc": {
        "name": "Master of Science (M.Sc)",
        "years": 2,
        "semesters": 4,
        "specializations": [
            "Computer Science",
            "IT",
            "Mathematics",
            "Physics",
            "Chemistry",
            "Other",
        ],
    },
    "BBA": {
        "name": "Bachelor of Business Administration (BBA)",
        "years": 3,
        "semesters": 6,
        "specializations": [
            "General",
            "Finance",
            "Marketing",
            "HR",
            "Business Analytics",
            "Other",
        ],
    },
    "MBA": {
        "name": "Master of Business Administration (MBA)",
        "years": 2,
        "semesters": 4,
        "specializations": [
            "Finance",
            "Marketing",
            "HR",
            "Business Analytics",
            "Operations",
            "IT",
            "Other",
        ],
    },
    "B.Com": {
        "name": "Bachelor of Commerce (B.Com)",
        "years": 3,
        "semesters": 6,
        "specializations": [
            "General",
            "Accounting",
            "Other",
        ],
    },
    "M.Com": {
        "name": "Master of Commerce (M.Com)",
        "years": 2,
        "semesters": 4,
        "specializations": [
            "General",
            "Accounting",
            "Other",
        ],
    },
    "Diploma": {
        "name": "Diploma in Engineering",
        "years": 3,
        "semesters": 6,
        "specializations": [
            "Computer",
            "Mechanical",
            "Electrical",
            "Civil",
            "Electronics",
            "Other",
        ],
    },
    "Other": {
        "name": "Other Academic Program",
        "years": 4,
        "semesters": 8,
        "specializations": [
            "General",
            "Other",
        ],
    },
}

# Standard Teacher/Faculty Departments
TEACHER_DEPARTMENTS = [
    "Computer Science",
    "IT",
    "Electronics",
    "Mechanical",
    "Civil",
    "Electrical",
    "Mathematics",
    "Physics",
    "Chemistry",
    "Management",
    "Commerce",
    "Other",
]

# Standard Teacher/Faculty Designations
TEACHER_DESIGNATIONS = [
    "Assistant Professor",
    "Associate Professor",
    "Professor",
    "HOD",
    "Lab Instructor",
    "Guest Faculty",
]

# Standard Teacher/Faculty Qualifications
TEACHER_QUALIFICATIONS = [
    "Ph.D",
    "M.Tech",
    "M.E",
    "MCA",
    "M.Sc",
    "MBA",
    "Other",
]

# Teacher Invite Code (Enforces faculty verification gate)
TEACHER_INVITE_CODE = os.environ.get("TEACHER_INVITE_CODE", "").strip()

# Allow dev seeding gate (Refuses to auto-seed in real world or tests without explicit flag)
ALLOW_DEMO_SEED = os.environ.get("ALLOW_DEMO_SEED", "false").strip().lower() == "true"

# Admin Panel & Privacy Controls (Stage 10)
ADMIN_CAN_VIEW_CHAT_CONTENT = os.environ.get("ADMIN_CAN_VIEW_CHAT_CONTENT", "false").lower() in ("true", "1")
ADMIN_IP_ALLOWLIST = os.environ.get("ADMIN_IP_ALLOWLIST", "").strip()

# Standard Engineering Branches / Departments (Legacy fallback)
BRANCHES = [
    ("Computer Science", "Computer Science & Engineering"),
    ("Information Technology", "Information Technology"),
    ("Electronics & Communication", "Electronics & Communication"),
    ("Electrical Engineering", "Electrical Engineering"),
    ("Mechanical Engineering", "Mechanical Engineering"),
    ("Civil Engineering", "Civil Engineering"),
    ("Applied Sciences", "Applied Sciences / Humanities"),
    ("Other", "Other"),
]

# Standard Academic Years (Legacy fallback)
ACADEMIC_YEARS = [
    (1, "1st Year"),
    (2, "2nd Year"),
    (3, "3rd Year"),
    (4, "4th Year"),
]

# Maximum Active Requests a Helper Can Receive Before Being Saturated (Load Balancing)
MAX_HELPER_LOAD = int(os.environ.get("MAX_HELPER_LOAD", 3))

# Study Group Capacity & Participation Constraints (Stage 4)
GROUP_MIN_SIZE = int(os.environ.get("GROUP_MIN_SIZE", 3))
GROUP_MAX_SIZE = int(os.environ.get("GROUP_MAX_SIZE", 5))
MAX_USER_GROUPS = int(os.environ.get("MAX_USER_GROUPS", 5))


def get_database_uri() -> str:
    """Resolve database URI, ensuring relative SQLite paths resolve to absolute paths on all OS."""
    db_env = os.environ.get("DATABASE_URL")
    if not db_env:
        instance_dir = BASE_DIR / "instance"
        instance_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(instance_dir / 'learning_platform.db').as_posix()}"

    # If relative SQLite URI like 'sqlite:///instance/learning_platform.db'
    if db_env.startswith("sqlite:///") and len(db_env) > 10 and db_env[10] != "/":
        relative_part = db_env[10:]
        if not (len(relative_part) > 2 and relative_part[1] == ":"):  # Not Windows drive letter
            target_path = (BASE_DIR / relative_part).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{target_path.as_posix()}"

    return db_env


class Config:
    """Base application configuration class."""

    # Security
    SECRET_KEY = os.environ.get(
        "SECRET_KEY", "collab-learning-dev-key-change-in-prod-8f3a92"
    )

    # Database
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File Uploads (Doubt attachments, answer images, chat images)
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", str(BASE_DIR / "uploads")
    )
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))  # 10 MB max payload
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

    # Cookie & Session Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1")
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7  # 7 days

    # Academic & Matching Settings
    SUBJECTS = SUBJECTS
    SKILL_LEVELS = SKILL_LEVELS
    PROGRAMS = PROGRAMS
    TEACHER_DEPARTMENTS = TEACHER_DEPARTMENTS
    TEACHER_DESIGNATIONS = TEACHER_DESIGNATIONS
    TEACHER_QUALIFICATIONS = TEACHER_QUALIFICATIONS
    TEACHER_INVITE_CODE = TEACHER_INVITE_CODE
    ALLOW_DEMO_SEED = ALLOW_DEMO_SEED
    BRANCHES = BRANCHES
    ACADEMIC_YEARS = ACADEMIC_YEARS
    MAX_HELPER_LOAD = MAX_HELPER_LOAD
    GROUP_MIN_SIZE = GROUP_MIN_SIZE
    GROUP_MAX_SIZE = GROUP_MAX_SIZE
    MAX_USER_GROUPS = MAX_USER_GROUPS

    # External AI Integration (Multi-provider: Gemini & Groq)
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip()
    AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", 20))
    AI_DAILY_LIMIT_HINT = int(os.environ.get("AI_DAILY_LIMIT_HINT", 20))
    AI_DAILY_LIMIT_QUIZ = int(os.environ.get("AI_DAILY_LIMIT_QUIZ", 10))
    AI_DAILY_LIMIT_PATH = int(os.environ.get("AI_DAILY_LIMIT_PATH", 5))

    # Admin Panel & Privacy Controls (Stage 10)
    ADMIN_CAN_VIEW_CHAT_CONTENT = (
        os.environ.get("ADMIN_CAN_VIEW_CHAT_CONTENT", "false").lower() in ("true", "1")
    )
    ADMIN_IP_ALLOWLIST = os.environ.get("ADMIN_IP_ALLOWLIST", "").strip()


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration with in-memory SQLite database."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}

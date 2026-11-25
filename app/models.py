"""
Database models for AI-Powered Collaborative Learning Platform.
Defines all SQLAlchemy models for Users, Skills, Buddy Matching,
Chat Rooms, Messages, Doubts, Answers, Votes, and Reputations.
"""

from datetime import datetime, timezone
from typing import Any

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


def utc_now() -> datetime:
    """Return timezone-naive UTC datetime for seamless SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BaseModel(db.Model):
    """Abstract base model adding keyword-argument typing support for IDEs and type checkers."""
    __abstract__ = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


@login_manager.user_loader
def load_user(user_id: str):
    """Flask-Login user loader callback."""
    return db.session.get(User, int(user_id))


class User(UserMixin, BaseModel):
    """
    User model representing students and teachers on the platform.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")  # 'student' | 'teacher'

    # Academic & Institutional attributes (Stage 9)
    college_name = db.Column(db.String(150), nullable=True, index=True)
    bio = db.Column(db.String(200), nullable=True)

    # Student-specific fields
    enrollment_no = db.Column(db.String(50), nullable=True, index=True)
    program = db.Column(db.String(50), nullable=True)
    specialization = db.Column(db.String(100), nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    section = db.Column(db.String(20), nullable=True)

    # Legacy mappings (kept compatible: branch = specialization, year = year)
    branch = db.Column(db.String(100), nullable=True)  # Department / Branch / Specialization
    year = db.Column(db.Integer, nullable=True)  # Academic year (1, 2, 3, 4)

    # Teacher-specific fields
    employee_id = db.Column(db.String(50), nullable=True, index=True)
    department = db.Column(db.String(100), nullable=True)
    designation = db.Column(db.String(100), nullable=True)
    qualification = db.Column(db.String(100), nullable=True)
    experience_years = db.Column(db.Integer, nullable=True)

    moderation_strikes = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    skills = db.relationship("Skill", back_populates="user", cascade="all, delete-orphan", lazy="dynamic")
    sent_buddy_requests = db.relationship(
        "BuddyRequest",
        foreign_keys="BuddyRequest.sender_id",
        back_populates="sender",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    received_buddy_requests = db.relationship(
        "BuddyRequest",
        foreign_keys="BuddyRequest.receiver_id",
        back_populates="receiver",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    chat_memberships = db.relationship(
        "ChatMember", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    messages = db.relationship(
        "Message",
        foreign_keys="Message.sender_id",
        back_populates="sender",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    reports_made = db.relationship(
        "MessageReport", back_populates="reporter", cascade="all, delete-orphan", lazy="dynamic"
    )
    doubts = db.relationship(
        "Doubt", foreign_keys="Doubt.user_id", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    answers = db.relationship(
        "Answer", foreign_keys="Answer.user_id", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    votes = db.relationship("AnswerVote", back_populates="user", cascade="all, delete-orphan", lazy="dynamic")
    reputations = db.relationship("Reputation", back_populates="user", cascade="all, delete-orphan", lazy="dynamic")
    received_group_invites = db.relationship(
        "GroupInvite",
        foreign_keys="GroupInvite.invited_user_id",
        back_populates="invited_user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    sent_group_invites = db.relationship(
        "GroupInvite",
        foreign_keys="GroupInvite.invited_by_id",
        back_populates="invited_by",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    ai_usages = db.relationship("AIUsage", back_populates="user", cascade="all, delete-orphan", lazy="dynamic")
    quiz_attempts = db.relationship(
        "QuizAttempt", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    learning_path = db.relationship(
        "LearningPath", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    teaching_subjects = db.relationship(
        "TeacherSubject", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    def set_password(self, password: str) -> None:
        """Hash and set user password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify user password against stored hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role == "admin"

    @property
    def is_teacher(self) -> bool:
        """Check if user has teacher role."""
        return self.role == "teacher"

    @property
    def is_student(self) -> bool:
        """Check if user has student role."""
        return self.role == "student"

    @property
    def teaching_subject_list(self) -> list[str]:
        """Return list of subject names taught by this faculty member."""
        if not self.is_teacher:
            return []
        return [ts.subject for ts in self.teaching_subjects.all()]

    @property
    def academic_summary(self) -> str:
        """Formatted summary string for cards and dashboard headers."""
        if self.is_teacher:
            parts = [p for p in (self.designation, self.department, self.college_name) if p]
            return " • ".join(parts) if parts else (self.department or "Faculty Member")
        else:
            parts = []
            if self.program:
                parts.append(self.program)
            if self.specialization:
                parts.append(self.specialization)
            if self.year:
                parts.append(f"Year {self.year}")
            if self.semester:
                parts.append(f"Sem {self.semester}")
            if self.college_name:
                parts.append(self.college_name)
            return " • ".join(parts) if parts else f"{self.branch or 'Student'} • Year {self.year or 1}"

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' role='{self.role}'>"


class TeacherSubject(BaseModel):
    """
    Subjects taught by faculty members.
    Used for filtering faculty dashboards, verification queues, and notifications.
    """
    __tablename__ = "teacher_subjects"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = db.Column(db.String(100), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship("User", back_populates="teaching_subjects")

    __table_args__ = (
        db.UniqueConstraint("user_id", "subject", name="uq_teacher_subject"),
    )

    def __repr__(self) -> str:
        return f"<TeacherSubject user_id={self.user_id} subject='{self.subject}'>"


class Skill(BaseModel):
    """
    Skill model representing a user's self-assessed proficiency in a subject.
    Used by the matching engine to pair weak students with strong students.
    """
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = db.Column(db.String(100), nullable=False, index=True)
    level = db.Column(db.String(20), nullable=False)  # 'Weak' | 'Average' | 'Strong'

    # Relationships
    user = db.relationship("User", back_populates="skills")

    __table_args__ = (
        db.UniqueConstraint("user_id", "subject", name="uq_user_subject_skill"),
    )

    def __repr__(self) -> str:
        return f"<Skill user_id={self.user_id} subject='{self.subject}' level='{self.level}'>"


class BuddyRequest(BaseModel):
    """
    BuddyRequest model representing 1-to-1 connection invitations between students.
    Chat rooms are unlocked only after request acceptance.
    """
    __tablename__ = "buddy_requests"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = db.Column(db.String(100), nullable=False, index=True)
    # Status: 'pending' | 'accepted' | 'rejected'
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    sender = db.relationship("User", foreign_keys=[sender_id], back_populates="sent_buddy_requests")
    receiver = db.relationship("User", foreign_keys=[receiver_id], back_populates="received_buddy_requests")

    __table_args__ = (
        db.Index("ix_buddy_request_pair", "sender_id", "receiver_id", "subject"),
    )

    def __repr__(self) -> str:
        return f"<BuddyRequest id={self.id} from={self.sender_id} to={self.receiver_id} status='{self.status}'>"


class ChatRoom(BaseModel):
    """
    ChatRoom model representing private 1-to-1 buddy chats or collaborative study group rooms.
    """
    __tablename__ = "chat_rooms"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False, default="private")  # 'private' | 'group'
    name = db.Column(db.String(120), nullable=True)  # Nullable for private chats, required for groups
    subject = db.Column(db.String(100), nullable=True)  # Optional study subject focus
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Relationships
    creator = db.relationship("User", foreign_keys=[created_by])
    members = db.relationship("ChatMember", back_populates="room", cascade="all, delete-orphan", lazy="dynamic")
    messages = db.relationship("Message", back_populates="room", cascade="all, delete-orphan", lazy="dynamic")
    invites = db.relationship("GroupInvite", back_populates="room", cascade="all, delete-orphan", lazy="dynamic")

    @property
    def is_group(self) -> bool:
        return self.type == "group"

    @property
    def is_private(self) -> bool:
        return self.type == "private"

    def __repr__(self) -> str:
        return f"<ChatRoom id={self.id} type='{self.type}' name='{self.name}'>"


class ChatMember(BaseModel):
    """
    ChatMember association model mapping users to chat rooms.
    Includes role ('admin' or 'member') for study groups.
    """
    __tablename__ = "chat_members"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default="member")  # 'admin' | 'member'
    joined_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    room = db.relationship("ChatRoom", back_populates="members")
    user = db.relationship("User", back_populates="chat_memberships")

    __table_args__ = (
        db.UniqueConstraint("room_id", "user_id", name="uq_room_member"),
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:
        return f"<ChatMember room_id={self.room_id} user_id={self.user_id} role='{self.role}'>"


class GroupInvite(BaseModel):
    """
    GroupInvite model representing invitations sent by group admins to prospective student members.
    Enforces uniqueness so a user cannot have two pending invitations for the same room.
    """
    __tablename__ = "group_invites"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Status: 'pending' | 'accepted' | 'declined' | 'cancelled'
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    room = db.relationship("ChatRoom", back_populates="invites")
    invited_user = db.relationship("User", foreign_keys=[invited_user_id], back_populates="received_group_invites")
    invited_by = db.relationship("User", foreign_keys=[invited_by_id], back_populates="sent_group_invites")

    __table_args__ = (
        db.UniqueConstraint("room_id", "invited_user_id", "status", name="uq_room_invited_status"),
        db.Index("ix_group_invite_room_user", "room_id", "invited_user_id"),
    )

    def __repr__(self) -> str:
        return f"<GroupInvite id={self.id} room_id={self.room_id} user={self.invited_user_id} status='{self.status}'>"


class Message(BaseModel):
    """
    Message model representing chat messages in private or group rooms.
    Supports optional image attachments, system broadcast notifications,
    moderation auto-masking, and teacher review status.
    """
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    text = db.Column(db.Text, nullable=False)
    original_text = db.Column(db.Text, nullable=True)  # Unmasked raw text when auto-flagged or hidden
    image_path = db.Column(db.String(255), nullable=True)  # Path relative to uploads directory
    is_system = db.Column(db.Boolean, default=False, nullable=False)  # Broadcast event (joins, leaves, etc.)
    is_flagged = db.Column(db.Boolean, default=False, nullable=False)  # Flagged by moderation or user reports
    flag_reason = db.Column(db.String(100), nullable=True)  # 'auto: profanity' | 'user: harassment' | etc.
    # 'none' | 'pending' | 'dismissed' | 'confirmed'
    review_status = db.Column(db.String(20), default="none", nullable=False, index=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    # Relationships
    room = db.relationship("ChatRoom", back_populates="messages")
    sender = db.relationship("User", foreign_keys=[sender_id], back_populates="messages")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    reports = db.relationship("MessageReport", back_populates="message", cascade="all, delete-orphan", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Message id={self.id} room_id={self.room_id} sender_id={self.sender_id} is_system={self.is_system}>"


class MessageReport(BaseModel):
    """
    MessageReport model for reporting abusive/inappropriate messages for moderation.
    Enforces uniqueness so a user cannot report the same message twice.
    """
    __tablename__ = "message_reports"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(50), nullable=False)  # 'abusive' | 'harassment' | 'spam' | 'inappropriate' | 'other'
    note = db.Column(db.String(200), nullable=True)  # Optional report note (max 200 chars)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    message = db.relationship("Message", back_populates="reports")
    reporter = db.relationship("User", back_populates="reports_made")

    __table_args__ = (
        db.UniqueConstraint("message_id", "reporter_id", name="uq_message_reporter"),
    )

    def __repr__(self) -> str:
        return f"<MessageReport id={self.id} msg={self.message_id} user={self.reporter_id} reason='{self.reason}'>"


class ModerationLog(BaseModel):
    """
    ModerationLog model recording automated content moderation actions (flagged or blocked).
    Privacy guarantee: Never stores matched keywords or full raw text.
    """
    __tablename__ = "moderation_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source = db.Column(db.String(20), nullable=False)  # 'chat' | 'doubt' | 'answer'
    action = db.Column(db.String(20), nullable=False)  # 'flagged' | 'blocked'
    matched_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    # Relationship
    user = db.relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<ModerationLog id={self.id} source='{self.source}' action='{self.action}' count={self.matched_count}>"


class Doubt(BaseModel):
    """
    Doubt model representing student questions posted to the community forum.
    Supports anonymous posting, image attachment, and subject categorization.
    """
    __tablename__ = "doubts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = db.Column(db.String(100), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)  # Optional attached diagram/screenshot
    is_anonymous = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.String(20), default="open", nullable=False, index=True)  # 'open' | 'solved'
    needs_human = db.Column(db.Boolean, default=False, nullable=False, index=True)  # True when student asks classmates
    solved_answer_id = db.Column(
        db.Integer,
        db.ForeignKey("answers.id", ondelete="SET NULL", use_alter=True, name="fk_doubts_solved_answer_id"),
        nullable=True,
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id], back_populates="doubts")
    answers = db.relationship(
        "Answer",
        foreign_keys="Answer.doubt_id",
        back_populates="doubt",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    solved_answer = db.relationship("Answer", foreign_keys=[solved_answer_id])
    ai_hint = db.relationship("AIHint", back_populates="doubt", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        db.Index("ix_doubt_subject_created", "subject", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Doubt id={self.id} subject='{self.subject}' status='{self.status}'>"


class Answer(BaseModel):
    """
    Answer model for peer/teacher replies to doubts.
    Ranked by upvotes and can be verified by teachers.
    """
    __tablename__ = "answers"

    id = db.Column(db.Integer, primary_key=True)
    doubt_id = db.Column(db.Integer, db.ForeignKey("doubts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    upvotes = db.Column(db.Integer, default=0, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)  # Verified by teacher
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    doubt = db.relationship("Doubt", foreign_keys=[doubt_id], back_populates="answers")
    user = db.relationship("User", foreign_keys=[user_id], back_populates="answers")
    verifier = db.relationship("User", foreign_keys=[verified_by])
    votes = db.relationship("AnswerVote", back_populates="answer", cascade="all, delete-orphan", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Answer id={self.id} doubt_id={self.doubt_id} upvotes={self.upvotes} verified={self.is_verified}>"


class AnswerVote(BaseModel):
    """
    AnswerVote model tracking which users upvoted which answers to prevent double voting.
    """
    __tablename__ = "answer_votes"

    id = db.Column(db.Integer, primary_key=True)
    answer_id = db.Column(db.Integer, db.ForeignKey("answers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    answer = db.relationship("Answer", back_populates="votes")
    user = db.relationship("User", back_populates="votes")

    __table_args__ = (
        db.UniqueConstraint("answer_id", "user_id", name="uq_answer_vote_user"),
    )

    def __repr__(self) -> str:
        return f"<AnswerVote answer_id={self.answer_id} user_id={self.user_id}>"


class Reputation(BaseModel):
    """
    Reputation model tracking a user's earned score and badges per subject.
    Points are earned when answers are upvoted or verified.
    """
    __tablename__ = "reputations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = db.Column(db.String(100), nullable=False, index=True)
    score = db.Column(db.Integer, default=0, nullable=False)
    badge = db.Column(db.String(50), nullable=True)  # e.g. 'Bronze Helper', 'Silver Scholar', 'Gold Mentor'

    # Relationships
    user = db.relationship("User", back_populates="reputations")

    __table_args__ = (
        db.UniqueConstraint("user_id", "subject", name="uq_user_subject_reputation"),
    )

    def __repr__(self) -> str:
        return f"<Reputation user_id={self.user_id} subject='{self.subject}' score={self.score}>"


class AIUsage(BaseModel):
    """
    Tracks daily per-user usage limits for AI features (hint, quiz, learning path).
    Enforces rate limits and quotas across sliding 24-hour windows.
    """
    __tablename__ = "ai_usages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    feature = db.Column(db.String(20), nullable=False, index=True)  # 'hint' | 'quiz' | 'path'
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    # Relationships
    user = db.relationship("User", back_populates="ai_usages")

    def __repr__(self) -> str:
        return f"<AIUsage user_id={self.user_id} feature='{self.feature}' created_at={self.created_at}>"


class AIHint(BaseModel):
    """
    Cached AI-generated hint for a specific doubt.
    Distinct from classmate answers, does not participate in ranking or upvotes.
    """
    __tablename__ = "ai_hints"

    id = db.Column(db.Integer, primary_key=True)
    doubt_id = db.Column(
        db.Integer, db.ForeignKey("doubts.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    hint_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    regenerated_count = db.Column(db.Integer, default=0, nullable=False)
    helpful = db.Column(db.Boolean, nullable=True)  # True = helped, False = still stuck

    # Relationships
    doubt = db.relationship("Doubt", back_populates="ai_hint")

    def __repr__(self) -> str:
        return f"<AIHint id={self.id} doubt_id={self.doubt_id} helpful={self.helpful}>"


class QuizAttempt(BaseModel):
    """
    Represents an AI-generated quiz practice session and subsequent grading result.
    Questions are stored as structured JSON; correct answers are withheld until submission.
    """
    __tablename__ = "quiz_attempts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = db.Column(db.String(100), nullable=False, index=True)
    topic = db.Column(db.String(100), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)  # 'Easy' | 'Medium' | 'Hard'
    num_questions = db.Column(db.Integer, nullable=False)
    questions_json = db.Column(db.Text, nullable=False)  # JSON list of question dicts
    answers_json = db.Column(db.Text, nullable=True)  # JSON dict of user selections {q_index: option_index}
    score = db.Column(db.Integer, nullable=True)  # Nullable until submitted
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    submitted_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship("User", back_populates="quiz_attempts")

    @property
    def is_submitted(self) -> bool:
        return self.submitted_at is not None

    def __repr__(self) -> str:
        return (
            f"<QuizAttempt id={self.id} user_id={self.user_id} subject='{self.subject}' "
            f"score={self.score}/{self.num_questions}>"
        )


class LearningPath(BaseModel):
    """
    Personalized study roadmap generated by AI based on weak-topic analytics.
    Features profile hashing to detect when student skills have changed since generation.
    """
    __tablename__ = "learning_paths"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    content_json = db.Column(db.Text, nullable=False)  # Structured plan JSON
    profile_hash = db.Column(db.String(64), nullable=False)  # SHA-256 fingerprint of student stats
    generated_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    user = db.relationship("User", back_populates="learning_path")

    def __repr__(self) -> str:
        return f"<LearningPath user_id={self.user_id} generated_at={self.generated_at}>"


class AdminAuditLog(BaseModel):
    """
    Audit trail for privileged administrative actions.
    Strictly append-only; records admin ID, action, target, IP, and timestamp.
    Never stores raw message content, passwords, or secrets.
    """
    __tablename__ = "admin_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    target_type = db.Column(db.String(50), nullable=True, index=True)
    target_id = db.Column(db.String(100), nullable=True)
    detail = db.Column(db.String(255), nullable=True)
    ip = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    admin = db.relationship("User", foreign_keys=[admin_id])

    def __repr__(self) -> str:
        return f"<AdminAuditLog id={self.id} action='{self.action}' admin_id={self.admin_id}>"

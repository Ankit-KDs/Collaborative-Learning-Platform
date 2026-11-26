"""
Flask-WTF forms for user authentication, role-specific registration, and credential management.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    SelectField,
    SelectMultipleField,
    IntegerField,
    TextAreaField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    EqualTo,
    ValidationError,
    NumberRange,
    Optional,
)
from app.models import User
from app.config import (
    SUBJECTS,
    BRANCHES,
    ACADEMIC_YEARS,
    PROGRAMS,
    TEACHER_DEPARTMENTS,
    TEACHER_DESIGNATIONS,
    TEACHER_QUALIFICATIONS,
)


def validate_password_complexity(form, field):
    """Enforce minimum 8 characters with at least one letter and at least one digit."""
    password = field.data or ""
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if not any(c.isalpha() for c in password):
        raise ValidationError("Password must contain at least one letter.")
    if not any(c.isdigit() for c in password):
        raise ValidationError("Password must contain at least one digit.")


class StudentRegistrationForm(FlaskForm):
    """Role-specific registration form for students."""

    name = StringField(
        "Full Name",
        validators=[
            DataRequired(message="Full name is required."),
            Length(min=2, max=100, message="Name must be between 2 and 100 characters."),
        ],
        render_kw={"placeholder": "e.g. Aarav Sharma"},
    )

    email = StringField(
        "College / Personal Email",
        validators=[
            DataRequired(message="Email address is required."),
            Email(message="Please provide a valid email address."),
            Length(max=120, message="Email must be under 120 characters."),
        ],
        render_kw={"placeholder": "student@college.edu"},
    )

    enrollment_no = StringField(
        "Enrollment / Roll Number",
        validators=[
            DataRequired(message="Enrollment / Roll number is required."),
            Length(min=2, max=50, message="Enrollment number must be between 2 and 50 characters."),
        ],
        render_kw={"placeholder": "e.g. 2024CS042"},
    )

    college_name = StringField(
        "College / Institute Name",
        validators=[
            DataRequired(message="College / Institute name is required."),
            Length(min=2, max=150, message="College name must be between 2 and 150 characters."),
        ],
        render_kw={"placeholder": "e.g. Delhi Technological University"},
    )

    program = SelectField(
        "Academic Program",
        choices=[(k, f"{k} - {v['name']}") for k, v in PROGRAMS.items()],
        validators=[DataRequired(message="Please select your degree program.")],
    )

    specialization = SelectField(
        "Specialization / Branch",
        choices=[],
        validate_choice=False,
        validators=[DataRequired(message="Please select your specialization/branch.")],
    )

    year = SelectField(
        "Academic Year",
        choices=[(i, f"Year {i}") for i in range(1, 5)],
        coerce=int,
        validate_choice=False,
        validators=[DataRequired(message="Please select your academic year.")],
    )

    semester = SelectField(
        "Current Semester",
        choices=[(i, f"Semester {i}") for i in range(1, 9)],
        coerce=int,
        validate_choice=False,
        validators=[DataRequired(message="Please select your current semester.")],
    )

    section = StringField(
        "Section / Division (Optional)",
        validators=[Optional(), Length(max=20, message="Section cannot exceed 20 characters.")],
        render_kw={"placeholder": "e.g. A or Section 2"},
    )

    bio = TextAreaField(
        "Short Bio / Academic Interests (Optional)",
        validators=[Optional(), Length(max=200, message="Bio cannot exceed 200 characters.")],
        render_kw={"placeholder": "e.g. Interested in competitive programming and system design.", "rows": 2},
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
            validate_password_complexity,
        ],
        render_kw={"placeholder": "Min 8 chars, 1 letter, 1 digit"},
    )

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="Passwords must match."),
        ],
        render_kw={"placeholder": "Repeat password"},
    )

    submit = SubmitField("Register as Student")

    def validate_email(self, field):
        """Ensure email is unique across the platform."""
        clean_email = (field.data or "").strip().lower()
        if User.query.filter_by(email=clean_email).first():
            raise ValidationError("An account with this email address already exists. Please sign in.")

    def validate_enrollment_no(self, field):
        """Ensure enrollment number is unique within the given college."""
        clean_enroll = (field.data or "").strip()
        clean_college = (self.college_name.data or "").strip()
        if clean_enroll and clean_college:
            existing = User.query.filter(
                User.college_name.ilike(clean_college),
                User.enrollment_no.ilike(clean_enroll),
            ).first()
            if existing:
                raise ValidationError("A student with this enrollment number is already registered at this college.")

    def validate_program(self, field):
        """Ensure program exists in config."""
        if field.data not in PROGRAMS:
            raise ValidationError("Selected program is not valid.")


class TeacherRegistrationForm(FlaskForm):
    """Role-specific registration form for teachers and faculty members."""

    name = StringField(
        "Full Name",
        validators=[
            DataRequired(message="Full name is required."),
            Length(min=2, max=100, message="Name must be between 2 and 100 characters."),
        ],
        render_kw={"placeholder": "e.g. Dr. Ramesh Kumar"},
    )

    email = StringField(
        "Official Institutional Email",
        validators=[
            DataRequired(message="Official email is required."),
            Email(message="Please provide a valid institutional email."),
            Length(max=120, message="Email must be under 120 characters."),
        ],
        render_kw={"placeholder": "faculty@college.edu"},
    )

    employee_id = StringField(
        "Employee / Faculty ID",
        validators=[
            DataRequired(message="Employee ID is required."),
            Length(min=2, max=50, message="Employee ID must be between 2 and 50 characters."),
        ],
        render_kw={"placeholder": "e.g. FAC-2024-089"},
    )

    college_name = StringField(
        "College / Institute Name",
        validators=[
            DataRequired(message="College / Institute name is required."),
            Length(min=2, max=150, message="College name must be between 2 and 150 characters."),
        ],
        render_kw={"placeholder": "e.g. Delhi Technological University"},
    )

    department = SelectField(
        "Academic Department",
        choices=[(d, d) for d in TEACHER_DEPARTMENTS],
        validators=[DataRequired(message="Please select your department.")],
    )

    designation = SelectField(
        "Designation",
        choices=[(d, d) for d in TEACHER_DESIGNATIONS],
        validators=[DataRequired(message="Please select your designation.")],
    )

    qualification = SelectField(
        "Highest Qualification",
        choices=[(q, q) for q in TEACHER_QUALIFICATIONS],
        validators=[DataRequired(message="Please select your highest qualification.")],
    )

    experience_years = IntegerField(
        "Teaching Experience (Years)",
        default=1,
        validators=[
            DataRequired(message="Years of experience is required."),
            NumberRange(min=0, max=60, message="Experience must be between 0 and 60 years."),
        ],
        render_kw={"placeholder": "e.g. 5"},
    )

    subjects = SelectMultipleField(
        "Subjects Taught (Select at least 1)",
        choices=[(s, s) for s in SUBJECTS],
        validators=[DataRequired(message="Please select at least one subject you teach.")],
    )

    bio = TextAreaField(
        "Faculty Bio / Research Interests (Optional)",
        validators=[Optional(), Length(max=200, message="Bio cannot exceed 200 characters.")],
        render_kw={"placeholder": "e.g. Specialization in distributed algorithms and operating systems.", "rows": 2},
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
            validate_password_complexity,
        ],
        render_kw={"placeholder": "Min 8 chars, 1 letter, 1 digit"},
    )

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="Passwords must match."),
        ],
        render_kw={"placeholder": "Repeat password"},
    )

    submit = SubmitField("Register as Faculty Member")

    def validate_email(self, field):
        """Ensure email is unique across the platform."""
        clean_email = (field.data or "").strip().lower()
        if User.query.filter_by(email=clean_email).first():
            raise ValidationError("An account with this email address already exists. Please sign in.")

    def validate_employee_id(self, field):
        """Ensure employee ID is unique within the given college."""
        clean_emp = (field.data or "").strip()
        clean_college = (self.college_name.data or "").strip()
        if clean_emp and clean_college:
            existing = User.query.filter(
                User.college_name.ilike(clean_college),
                User.employee_id.ilike(clean_emp),
            ).first()
            if existing:
                raise ValidationError("A faculty member with this employee ID is already registered at this college.")

    def validate_subjects(self, field):
        """Ensure at least one valid subject is chosen."""
        if not field.data or len(field.data) == 0:
            raise ValidationError("Please select at least one subject you teach.")
        for s in field.data:
            if s not in SUBJECTS:
                raise ValidationError(f"Invalid subject: '{s}'.")


class LoginForm(FlaskForm):
    """Form for existing user login."""

    email = StringField(
        "Email Address",
        validators=[
            DataRequired(message="Email is required."),
            Email(message="Please enter a valid email address."),
        ],
        render_kw={"placeholder": "name@college.edu"},
    )

    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password is required.")],
        render_kw={"placeholder": "Enter your password"},
    )

    remember = BooleanField("Remember Me", default=False)
    submit = SubmitField("Sign In")


# Backward compatibility alias
class RegistrationForm(StudentRegistrationForm):
    """Legacy registration form alias for tests and backward compatibility."""
    role = SelectField(
        "Role",
        choices=[("student", "Student"), ("teacher", "Teacher")],
        default="student",
        validators=[DataRequired(message="Please select your role.")],
    )
    branch = SelectField(
        "Branch / Department",
        choices=BRANCHES,
        validators=[Optional()],
    )

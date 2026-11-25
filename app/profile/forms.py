"""
WTForms for editing user profile information, academic curriculum, faculty teaching subjects,
and student subject skill proficiencies.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    SelectField,
    SelectMultipleField,
    IntegerField,
    TextAreaField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    AnyOf,
    Optional,
    NumberRange,
)
from app.config import (
    SUBJECTS,
    SKILL_LEVELS,
    BRANCHES,
    ACADEMIC_YEARS,
    PROGRAMS,
    TEACHER_DEPARTMENTS,
    TEACHER_DESIGNATIONS,
    TEACHER_QUALIFICATIONS,
)


class StudentProfileForm(FlaskForm):
    """Form to view and edit student profile and academic curriculum."""

    name = StringField(
        "Full Name",
        validators=[
            DataRequired(message="Name is required."),
            Length(min=2, max=100, message="Name must be between 2 and 100 characters."),
        ],
        render_kw={"placeholder": "Full Name"},
    )

    email = StringField(
        "Email Address (Read-only)",
        render_kw={"readonly": True, "disabled": True},
    )

    college_name = StringField(
        "College / Institute Name",
        validators=[
            DataRequired(message="College name is required."),
            Length(min=2, max=150, message="College name must be under 150 characters."),
        ],
    )

    enrollment_no = StringField(
        "Enrollment / Roll Number",
        validators=[
            DataRequired(message="Enrollment number is required."),
            Length(min=2, max=50, message="Enrollment number must be under 50 characters."),
        ],
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
        validators=[Optional(), Length(max=20)],
    )

    bio = TextAreaField(
        "Short Bio / Academic Focus (Optional)",
        validators=[Optional(), Length(max=200)],
        render_kw={"rows": 2},
    )

    submit = SubmitField("Save Academic Profile")


class TeacherProfileForm(FlaskForm):
    """Form to view and edit faculty professional details and teaching subjects."""

    name = StringField(
        "Full Name",
        validators=[
            DataRequired(message="Name is required."),
            Length(min=2, max=100, message="Name must be between 2 and 100 characters."),
        ],
    )

    email = StringField(
        "Official Email (Read-only)",
        render_kw={"readonly": True, "disabled": True},
    )

    college_name = StringField(
        "College / Institute Name",
        validators=[
            DataRequired(message="College name is required."),
            Length(min=2, max=150, message="College name must be under 150 characters."),
        ],
    )

    employee_id = StringField(
        "Employee / Faculty ID",
        validators=[
            DataRequired(message="Employee ID is required."),
            Length(min=2, max=50, message="Employee ID must be under 50 characters."),
        ],
    )

    department = SelectField(
        "Department",
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
        validators=[DataRequired(message="Please select your qualification.")],
    )

    experience_years = IntegerField(
        "Teaching Experience (Years)",
        validators=[
            DataRequired(message="Experience is required."),
            NumberRange(min=0, max=60, message="Experience must be between 0 and 60 years."),
        ],
    )

    subjects = SelectMultipleField(
        "Subjects You Teach (At least 1 required)",
        choices=[(s, s) for s in SUBJECTS],
        validators=[DataRequired(message="Please select at least one teaching subject.")],
    )

    bio = TextAreaField(
        "Faculty Bio / Research Interests (Optional)",
        validators=[Optional(), Length(max=200)],
        render_kw={"rows": 2},
    )

    submit = SubmitField("Save Faculty Profile")


# Backward compatibility alias
class ProfileForm(FlaskForm):
    """Legacy profile form alias."""
    name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("Email Address", render_kw={"readonly": True, "disabled": True})
    branch = SelectField("Department / Branch", choices=BRANCHES, validators=[DataRequired()])
    year = SelectField("Academic Year", choices=ACADEMIC_YEARS, coerce=int, validators=[DataRequired()])
    submit = SubmitField("Save Profile")


class SkillForm(FlaskForm):
    """Form for students to add or update subject proficiency ratings."""

    subject = SelectField(
        "Select Subject",
        choices=[(s, s) for s in SUBJECTS],
        validators=[
            DataRequired(message="Subject is required."),
            AnyOf(SUBJECTS, message="Selected subject is not in the allowed list."),
        ],
    )

    level = SelectField(
        "Proficiency Level",
        choices=[(lvl, lvl) for lvl in SKILL_LEVELS],
        validators=[
            DataRequired(message="Level is required."),
            AnyOf(SKILL_LEVELS, message="Selected skill level is not valid."),
        ],
    )

    submit = SubmitField("Add / Update Skill")


class DeleteSkillForm(FlaskForm):
    """CSRF-protected form for deleting a skill."""
    submit = SubmitField("Delete")

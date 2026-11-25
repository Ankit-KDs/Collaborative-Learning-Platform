"""
WTForms definitions for study groups.
"""

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length

from app.config import SUBJECTS


class CreateGroupForm(FlaskForm):
    """Form to create a new collaborative study group."""

    name = StringField(
        "Study Group Name",
        validators=[
            DataRequired(message="Please provide a group name."),
            Length(min=3, max=50, message="Group name must be between 3 and 50 characters."),
        ],
        render_kw={"placeholder": "e.g., Dynamic Programming Study Cohort"},
    )
    subject = SelectField(
        "Subject Focus",
        choices=[(s, s) for s in SUBJECTS],
        validators=[DataRequired(message="Please select an academic subject.")],
    )
    submit = SubmitField("Create Study Group")

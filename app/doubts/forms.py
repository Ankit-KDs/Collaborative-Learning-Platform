"""
Web forms for Doubt Resolution and Q&A.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length

from app.config import SUBJECTS


class AskDoubtForm(FlaskForm):
    """Form to submit a new student doubt."""

    subject = SelectField(
        "Subject Area",
        choices=[(s, s) for s in SUBJECTS],
        validators=[DataRequired(message="Please select a relevant subject area.")],
    )
    title = StringField(
        "Doubt Title",
        validators=[
            DataRequired(message="Please provide a concise title summarizing your question."),
            Length(min=5, max=150, message="Title must be between 5 and 150 characters."),
        ],
    )
    body = TextAreaField(
        "Detailed Explanation / Code / Question",
        validators=[
            DataRequired(message="Please explain what you are trying to solve and where you are stuck."),
            Length(min=10, max=3000, message="Description must be between 10 and 3000 characters."),
        ],
    )
    image = FileField(
        "Attach Diagram / Code Screenshot (Optional, Max 5MB)",
        validators=[
            FileAllowed(["jpg", "jpeg", "png"], message="Only JPG, JPEG, and PNG image files are allowed."),
        ],
    )
    is_anonymous = BooleanField("Post anonymously (hides your name from peers and instructors)")


class AnswerForm(FlaskForm):
    """Form to submit an answer to an existing doubt."""

    body = TextAreaField(
        "Your Solution / Explanation",
        validators=[
            DataRequired(message="Please write your solution or explanation."),
            Length(min=5, max=3000, message="Answer must be between 5 and 3000 characters."),
        ],
    )
    image = FileField(
        "Attach Diagram or Calculation (Optional, Max 5MB)",
        validators=[
            FileAllowed(["jpg", "jpeg", "png"], message="Only JPG, JPEG, and PNG image files are allowed."),
        ],
    )

"""
WTForms for AI Quiz Generator.
==============================
Validates subject selection, topic length, difficulty tier, and question quantity.
"""

from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange

from app.config import SUBJECTS


class QuizGeneratorForm(FlaskForm):
    """Form to configure and generate an AI multiple-choice quiz."""

    subject = SelectField(
        "Subject",
        choices=[(s, s) for s in SUBJECTS],
        validators=[DataRequired(message="Please select a subject.")],
    )
    topic = StringField(
        "Topic / Conceptual Focus",
        validators=[
            DataRequired(message="Please enter a specific topic."),
            Length(min=3, max=100, message="Topic must be between 3 and 100 characters."),
        ],
        render_kw={"placeholder": "e.g., Red-Black Tree Rotations, Transaction ACID, Bellman-Ford"},
    )
    difficulty = SelectField(
        "Difficulty Tier",
        choices=[("Easy", "Easy (Fundamentals)"), ("Medium", "Medium (Application)"), ("Hard", "Hard (Deep Analysis)")],
        default="Medium",
        validators=[DataRequired()],
    )
    num_questions = IntegerField(
        "Number of Questions",
        default=5,
        validators=[
            DataRequired(message="Please choose number of questions."),
            NumberRange(min=3, max=10, message="Questions must be between 3 and 10."),
        ],
    )
    submit = SubmitField("Generate AI Practice Quiz")

"""
Unit tests for AI Service (Multi-Provider Support: Gemini & Groq).
==================================================================
All tests mock external API calls completely (no network or live API tokens needed).
Verifies error resilience, schema validation, daily quota limits, Groq backend,
and automatic multi-provider fallback.
"""

import json
from unittest.mock import MagicMock
import pytest

from app import create_app, db
from app.models import User
from app.services.ai_service import (
    AIServiceError,
    check_and_record_usage,
    generate_hint,
    generate_learning_path,
    generate_quiz,
)


@pytest.fixture
def app_instance():
    """Create test application instance with in-memory SQLite database."""
    app = create_app("testing")
    app.config["GEMINI_API_KEY"] = "fake-test-key-12345"
    app.config["GROQ_API_KEY"] = ""
    app.config["AI_PROVIDER"] = "gemini"
    app.config["AI_DAILY_LIMIT_HINT"] = 3
    app.config["AI_DAILY_LIMIT_QUIZ"] = 2
    app.config["AI_DAILY_LIMIT_PATH"] = 2
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _create_student(email: str = "s1@test.com") -> User:
    u = User(name="Student One", email=email, role="student", branch="CS", year=2)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


def test_missing_api_key_raises_ai_service_error(app_instance, monkeypatch):
    """When all provider API keys are unset or empty, AIServiceError must be raised cleanly."""
    with app_instance.app_context():
        app_instance.config["GEMINI_API_KEY"] = ""
        app_instance.config["GROQ_API_KEY"] = ""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        with pytest.raises(AIServiceError, match="AI features are temporarily unavailable"):
            generate_hint("DAA", "Title", "Body")

        with pytest.raises(AIServiceError, match="AI features are temporarily unavailable"):
            generate_quiz("DAA", "Binary Search", "Medium", 5)

        with pytest.raises(AIServiceError, match="AI features are temporarily unavailable"):
            generate_learning_path({"priority_subjects": []})


def test_quiz_schema_validation_rejects_wrong_question_count(app_instance, monkeypatch):
    """Quiz parser must reject responses that do not match the exact requested question count."""
    with app_instance.app_context():
        mock_response = MagicMock()
        mock_response.text = (
            '['
            '  {"question": "Q1?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "E1"},'
            '  {"question": "Q2?", "options": ["A", "B", "C", "D"], "correct_index": 1, "explanation": "E2"}'
            ']'
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        monkeypatch.setattr("app.services.ai_service._get_gemini_client", lambda: mock_client)

        with pytest.raises(AIServiceError, match="Expected exactly 5 questions"):
            generate_quiz("DAA", "Sorting", "Medium", 5)


def test_quiz_schema_validation_rejects_non_4_options(app_instance, monkeypatch):
    """Quiz parser must reject questions with more or fewer than 4 choices."""
    with app_instance.app_context():
        mock_response = MagicMock()
        mock_response.text = (
            '['
            '  {"question": "Q1?", "options": ["A", "B", "C"], "correct_index": 0, "explanation": "E1"},'
            '  {"question": "Q2?", "options": ["A", "B", "C", "D"], "correct_index": 1, "explanation": "E2"},'
            '  {"question": "Q3?", "options": ["A", "B", "C", "D"], "correct_index": 2, "explanation": "E3"}'
            ']'
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        monkeypatch.setattr("app.services.ai_service._get_gemini_client", lambda: mock_client)

        with pytest.raises(AIServiceError, match="must have exactly 4 options"):
            generate_quiz("DAA", "Sorting", "Medium", 3)


def test_quiz_schema_validation_rejects_invalid_correct_index(app_instance, monkeypatch):
    """Quiz parser must reject non-integer or out-of-range correct_index values."""
    with app_instance.app_context():
        mock_response = MagicMock()
        mock_response.text = (
            '['
            '  {"question": "Q1?", "options": ["A", "B", "C", "D"], "correct_index": 4, "explanation": "E1"},'
            '  {"question": "Q2?", "options": ["A", "B", "C", "D"], "correct_index": 1, "explanation": "E2"},'
            '  {"question": "Q3?", "options": ["A", "B", "C", "D"], "correct_index": 2, "explanation": "E3"}'
            ']'
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        monkeypatch.setattr("app.services.ai_service._get_gemini_client", lambda: mock_client)

        with pytest.raises(AIServiceError, match="correct_index between 0 and 3"):
            generate_quiz("DAA", "Sorting", "Medium", 3)


def test_learning_path_validation_rejects_malformed_structure(app_instance, monkeypatch):
    """Learning path parser must strictly validate presence of motivation and subjects array."""
    with app_instance.app_context():
        mock_response = MagicMock()
        mock_response.text = '{"motivation": "Keep going!"}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        monkeypatch.setattr("app.services.ai_service._get_gemini_client", lambda: mock_client)

        with pytest.raises(AIServiceError, match="subjects"):
            generate_learning_path({"priority_subjects": [{"subject": "DAA"}]})


def test_usage_rate_limit_enforcement(app_instance):
    """Enforce daily rate limits per feature per user and block excessive requests."""
    with app_instance.app_context():
        student = _create_student("quota_student@test.com")

        # Quota for hint is 3
        check_and_record_usage(student.id, "hint")
        check_and_record_usage(student.id, "hint")
        check_and_record_usage(student.id, "hint")

        # 4th request must raise AIServiceError
        with pytest.raises(AIServiceError, match="Daily limit of 3 AI Doubt Hints reached"):
            check_and_record_usage(student.id, "hint")


def test_groq_backend_hint_generation(app_instance, monkeypatch):
    """Groq provider can generate hints, ignoring images gracefully."""
    with app_instance.app_context():
        app_instance.config["AI_PROVIDER"] = "groq"
        app_instance.config["GROQ_API_KEY"] = "fake-groq-key"

        mock_choice = MagicMock()
        mock_choice.message.content = "Focus on the base cases of recursion."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_groq_client = MagicMock()
        mock_groq_client.chat.completions.create.return_value = mock_completion
        monkeypatch.setattr("app.services.ai_service._get_groq_client", lambda: mock_groq_client)

        hint = generate_hint(
            "DAA", "Recursion Depth", "Stack overflow in recursive tree.",
            image_bytes=b"fake-image-bytes", mime="image/png"
        )
        assert hint == "Focus on the base cases of recursion."

        # Verify groq received text only in messages (no raw image bytes)
        call_kwargs = mock_groq_client.chat.completions.create.call_args[1]
        user_msg = next(m for m in call_kwargs["messages"] if m["role"] == "user")
        assert "Recursion Depth" in user_msg["content"]
        assert isinstance(user_msg["content"], str)


def test_groq_backend_quiz_generation(app_instance, monkeypatch):
    """Groq provider generates valid quizzes using JSON object mode."""
    with app_instance.app_context():
        app_instance.config["AI_PROVIDER"] = "groq"
        app_instance.config["GROQ_API_KEY"] = "fake-groq-key"

        quiz_json = json.dumps({
            "questions": [
                {"question": "What is 2+2?", "options": ["3", "4", "5", "6"], "correct_index": 1, "explanation": "E"},
                {"question": "What is 3+3?", "options": ["5", "6", "7", "8"], "correct_index": 1, "explanation": "E"},
                {"question": "What is 4+4?", "options": ["7", "8", "9", "10"], "correct_index": 1, "explanation": "E"},
            ]
        })

        mock_choice = MagicMock()
        mock_choice.message.content = quiz_json
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_groq_client = MagicMock()
        mock_groq_client.chat.completions.create.return_value = mock_completion
        monkeypatch.setattr("app.services.ai_service._get_groq_client", lambda: mock_groq_client)

        questions = generate_quiz("Mathematics", "Addition", "Easy", 3)
        assert len(questions) == 3
        assert questions[0]["question"] == "What is 2+2?"
        assert questions[0]["correct_index"] == 1


def test_automatic_fallback_from_gemini_to_groq(app_instance, monkeypatch):
    """If primary provider (Gemini) encounters transient failure, system automatically falls back to Groq."""
    with app_instance.app_context():
        app_instance.config["AI_PROVIDER"] = "gemini"
        app_instance.config["GEMINI_API_KEY"] = "fake-gemini-key"
        app_instance.config["GROQ_API_KEY"] = "fake-groq-key"

        # Mock Gemini failing with a 503 ServerError
        mock_gemini_client = MagicMock()
        mock_gemini_client.models.generate_content.side_effect = RuntimeError("503 Service Unavailable")
        monkeypatch.setattr("app.services.ai_service._get_gemini_client", lambda: mock_gemini_client)

        # Mock Groq succeeding
        mock_choice = MagicMock()
        mock_choice.message.content = "Hint generated by fallback Groq provider."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_groq_client = MagicMock()
        mock_groq_client.chat.completions.create.return_value = mock_completion
        monkeypatch.setattr("app.services.ai_service._get_groq_client", lambda: mock_groq_client)

        hint = generate_hint("DAA", "Fallback Test", "Testing multi-provider resiliency.")
        assert hint == "Hint generated by fallback Groq provider."

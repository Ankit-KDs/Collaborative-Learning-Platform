"""
Unit and integration tests for Content Moderation & Aho-Corasick Algorithm (Stage 7).
Tests cover:
- Hand-crafted Aho-Corasick automaton correctness (multiple, overlapping, suffix patterns, empty/no match)
- Leetspeak and separator evasion detection
- Scunthorpe problem resolution (innocent words are not flagged)
- Exact length preservation in masked strings
- Chat moderation flow (masked stored in text, unmasked in original_text, hidden from members)
- Zero-tolerance blocking for doubts and answers
- Privacy guarantee: ModerationLog never contains raw text or keywords
"""

import pytest

from app import create_app, db
from app.models import ChatMember, ChatRoom, Doubt, Message, ModerationLog, User
from app.services.doubts_service import DoubtServiceError, add_answer, create_doubt
from app.services.moderation import (
    AhoCorasickAutomaton,
    contains_profanity,
    scan_text,
    validate_content_profanity,
)


@pytest.fixture
def app_instance(tmp_path):
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _create_user(name: str, email: str, role: str = "student") -> User:
    u = User(name=name, email=email, role=role, branch="CS", year=2)
    u.set_password("pass123")
    db.session.add(u)
    db.session.commit()
    return u


# 1. Aho-Corasick Automaton Unit Tests
def test_aho_corasick_basic_and_multiple_patterns():
    automaton = AhoCorasickAutomaton(["bad", "evil", "toxic"])
    matches = automaton.search_all("This is a bad and evil world with toxic vibes")
    patterns_found = [m[2] for m in matches]
    assert "bad" in patterns_found
    assert "evil" in patterns_found
    assert "toxic" in patterns_found


def test_aho_corasick_overlapping_and_suffix_patterns():
    # 'he', 'she', 'his', 'hers'
    automaton = AhoCorasickAutomaton(["he", "she", "his", "hers"])
    matches = automaton.search_all("ushers")
    patterns_found = [m[2] for m in matches]
    assert "he" in patterns_found
    assert "she" in patterns_found
    assert "hers" in patterns_found


def test_aho_corasick_suffix_containment():
    # 'ass' and 'asshole'
    automaton = AhoCorasickAutomaton(["ass", "asshole"])
    matches = automaton.search_all("asshole")
    patterns_found = [m[2] for m in matches]
    assert "ass" in patterns_found
    assert "asshole" in patterns_found


def test_aho_corasick_empty_and_no_match():
    automaton = AhoCorasickAutomaton(["spam", "virus"])
    assert automaton.search_all("") == []
    assert automaton.search_all("Completely safe academic query") == []


# 2. Leetspeak and Separator Evasion Tests
def test_leetspeak_evasion_caught():
    res = scan_text("You are an @sshole and an 1di0t")
    assert res["is_flagged"] is True
    assert res["matched_count"] >= 1
    assert "*" in res["masked_text"]
    assert len(res["masked_text"]) == len("You are an @sshole and an 1di0t")


def test_separator_evasion_spaced_and_punctuated():
    t1 = "This is f u c k here"
    res1 = scan_text(t1)
    assert res1["is_flagged"] is True
    assert len(res1["masked_text"]) == len(t1)

    t2 = "This is f.u.c.k here"
    res2 = scan_text(t2)
    assert res2["is_flagged"] is True
    assert len(res2["masked_text"]) == len(t2)

    t3 = "This is f-u-c-k here"
    res3 = scan_text(t3)
    assert res3["is_flagged"] is True
    assert len(res3["masked_text"]) == len(t3)


def test_repeated_characters_evasion():
    t1 = "You fuuuuck"
    res1 = scan_text(t1)
    assert res1["is_flagged"] is True
    assert len(res1["masked_text"]) == len(t1)

    t2 = "This is shiiit"
    res2 = scan_text(t2)
    assert res2["is_flagged"] is True
    assert len(res2["masked_text"]) == len(t2)


# 3. Scunthorpe Problem Defense Tests
def test_scunthorpe_innocent_words_not_flagged():
    innocent_texts = [
        "Welcome to the algorithms class today.",
        "The classical complexity of this sort is O(n log n).",
        "Did you pass the final assessment test?",
        "Please read the attached document and assignment instructions.",
        "Use a compass to draw the geometry diagram.",
        "Assume that the graph is connected and undirected.",
    ]
    for text in innocent_texts:
        res = scan_text(text)
        assert res["is_flagged"] is False, f"Falsely flagged innocent text: {text}"
        assert res["masked_text"] == text
        assert not contains_profanity(text)


def test_masked_text_strictly_preserves_length():
    texts = [
        "You idiot",
        "f u c k this error",
        "Stop @sshole behavior",
        "Kutta kamina language",
    ]
    for t in texts:
        res = scan_text(t)
        if res["is_flagged"]:
            assert len(res["masked_text"]) == len(t), f"Length mismatch on: {t}"


# 4. Chat Moderation & Data Privacy Integration Tests
def test_chat_message_stored_masked_and_hidden_from_members(app_instance):
    with app_instance.app_context():
        s1 = _create_user("Alice", "alice@test.com")
        s2 = _create_user("Bob", "bob@test.com")

        room = ChatRoom(type="private", subject="Python", is_active=True)
        db.session.add(room)
        db.session.flush()
        db.session.add_all([
            ChatMember(room_id=room.id, user_id=s1.id),
            ChatMember(room_id=room.id, user_id=s2.id),
        ])
        db.session.commit()

        client = app_instance.test_client()

        # Alice logs in and sends an inappropriate message
        client.post("/auth/login", data={"email": "alice@test.com", "password": "pass123"})
        raw_msg = "Why is this idiot code failing?"
        resp = client.post(
            f"/chats/{room.id}/send",
            data={"text": raw_msg},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["text"] != raw_msg
        assert "*" in data["text"]
        assert "warning" in data
        assert "original_text" not in data

        # Verify DB representation
        msg_obj = Message.query.filter_by(room_id=room.id).first()
        assert msg_obj is not None
        assert msg_obj.text != raw_msg
        assert msg_obj.original_text == raw_msg
        assert msg_obj.is_flagged is True
        assert msg_obj.review_status == "pending"

        # Bob logs in and polls messages
        client.get("/auth/logout")
        client.post("/auth/login", data={"email": "bob@test.com", "password": "pass123"})
        poll_resp = client.get(f"/chats/{room.id}/messages?after_id=0")
        assert poll_resp.status_code == 200
        poll_data = poll_resp.get_json()
        assert len(poll_data["messages"]) == 1
        polled_msg = poll_data["messages"][0]
        assert polled_msg["text"] == msg_obj.text
        assert "original_text" not in polled_msg
        assert raw_msg not in poll_resp.get_data(as_text=True)


# 5. Doubts & Answers Rejection with ModerationLog Audit
def test_doubt_and_answer_with_profanity_rejected(app_instance):
    with app_instance.app_context():
        s1 = _create_user("Student One", "s1_mod@test.com")

        # Attempt to post a doubt with profanity
        with pytest.raises(DoubtServiceError, match="Inappropriate content detected"):
            create_doubt(
                user_id=s1.id,
                subject="Python",
                title="You are an idiot question",
                body="Explain why this function fails completely.",
            )

        # Ensure no doubt was persisted
        assert Doubt.query.count() == 0

        # Post a clean doubt
        doubt = create_doubt(
            user_id=s1.id,
            subject="Python",
            title="Clean question on decorators",
            body="How do Python function decorators work behind the scenes?",
        )
        assert doubt is not None

        # Attempt to post an answer with profanity
        with pytest.raises(DoubtServiceError, match="Inappropriate content detected"):
            add_answer(
                doubt_id=doubt.id,
                user_id=s1.id,
                body="This is an idiot answer with profanity.",
            )

        # Verify ModerationLog records
        logs = ModerationLog.query.all()
        assert len(logs) >= 2
        for log in logs:
            assert log.action == "blocked"
            assert log.source in {"doubt", "answer"}
            # Guarantee: no raw text is stored
            assert not hasattr(log, "raw_text")
            assert not hasattr(log, "matched_words")

        # Test direct validate_content_profanity helper
        with pytest.raises(Exception):
            validate_content_profanity("Direct profanity test idiot", source="chat", user_id=s1.id)

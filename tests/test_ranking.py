"""
Unit tests for the hand-implemented Merge Sort ranking algorithm (Stage 5).
Validates ranking hierarchy (Verified > Accepted > Upvotes > CreatedAt), stability,
and edge cases on empty/single lists without database dependency.
"""

from datetime import datetime, timedelta
from app.services.ranking import merge_sort, rank_answers


class MockAnswer:
    def __init__(self, id: int, upvotes: int, is_verified: bool, created_at: datetime):
        self.id = id
        self.upvotes = upvotes
        self.is_verified = is_verified
        self.created_at = created_at

    def __repr__(self):
        return f"<MockAnswer id={self.id} upvotes={self.upvotes} verified={self.is_verified}>"


def test_merge_sort_empty_and_single_element():
    """Empty and single-element lists must return immediately without modification."""
    assert rank_answers([]) == []

    now = datetime(2026, 1, 1, 10, 0, 0)
    single = [MockAnswer(1, 5, False, now)]
    ranked = rank_answers(single)
    assert len(ranked) == 1
    assert ranked[0].id == 1


def test_ranking_hierarchy():
    """
    Test strict precedence:
    1. Teacher-verified answers first
    2. Asker-accepted answer next
    3. Upvotes descending
    4. Older created_at first as tiebreaker
    """
    base_time = datetime(2026, 1, 1, 12, 0, 0)

    # 1. Normal answer with 2 upvotes
    a1 = MockAnswer(id=1, upvotes=2, is_verified=False, created_at=base_time)
    # 2. Answer with 10 upvotes (neither verified nor accepted)
    a2 = MockAnswer(id=2, upvotes=10, is_verified=False, created_at=base_time + timedelta(minutes=10))
    # 3. Accepted answer with only 1 upvote
    a3 = MockAnswer(id=3, upvotes=1, is_verified=False, created_at=base_time + timedelta(minutes=20))
    # 4. Teacher-verified answer with 0 upvotes
    a4 = MockAnswer(id=4, upvotes=0, is_verified=True, created_at=base_time + timedelta(minutes=30))
    # 5. Answer with 2 upvotes but created earlier than a1
    a5 = MockAnswer(id=5, upvotes=2, is_verified=False, created_at=base_time - timedelta(minutes=5))

    raw_list = [a1, a2, a3, a4, a5]
    # Mark a3 as accepted by the asker
    ranked = rank_answers(raw_list, accepted_answer_id=3)

    # Expected order:
    # 1st: a4 (Verified)
    # 2nd: a3 (Accepted)
    # 3rd: a2 (10 upvotes)
    # 4th: a5 (2 upvotes, older: 11:55)
    # 5th: a1 (2 upvotes, newer: 12:00)
    expected_ids = [4, 3, 2, 5, 1]
    actual_ids = [a.id for a in ranked]
    assert actual_ids == expected_ids, f"Expected {expected_ids}, got {actual_ids}"


def test_merge_sort_stability():
    """
    Merge sort must be strictly stable: answers with identical ranking keys
    must preserve their original input relative order.
    """
    now = datetime(2026, 1, 1, 10, 0, 0)

    # Three answers with identical verified=False, accepted=False, upvotes=5, created_at=now
    a1 = {"id": "first", "upvotes": 5, "is_verified": False, "created_at": now}
    a2 = {"id": "second", "upvotes": 5, "is_verified": False, "created_at": now}
    a3 = {"id": "third", "upvotes": 5, "is_verified": False, "created_at": now}

    ranked = rank_answers([a1, a2, a3])
    ids = [a["id"] for a in ranked]
    assert ids == ["first", "second", "third"], f"Stability violated: {ids}"


def test_merge_sort_with_custom_comparator():
    """Test merge_sort directly with an integer comparator."""
    # Descending sort
    nums = [5, 2, 8, 1, 9, 2, 7]
    sorted_nums = merge_sort(nums, lambda x, y: x > y)
    assert sorted_nums == [9, 8, 7, 5, 2, 2, 1]

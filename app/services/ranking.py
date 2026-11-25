"""
Answer Ranking Algorithm via Hand-Implemented Merge Sort
=========================================================

Design Analysis and Algorithm (DAA) Theoretical Foundation:
------------------------------------------------------------
In forum-based peer learning systems, the presentation order of candidate solutions
directly impacts pedagogical efficiency. Presenting authoritative or validated solutions
first prevents the propagation of misconceptions, while highlighting peer consensus (upvotes)
surfaces quality community contributions.

Algorithm Choice: Merge Sort
----------------------------
1. Divide and Conquer Strategy:
   Merge Sort recursively divides the list of answers of size n into two halves of size
   n/2 until sublists contain 1 or 0 elements (trivial base case). It then recombines
   (merges) the sorted sublists in linear O(n) time.

2. Recurrence Relation & Complexity:
   T(n) = 2T(n/2) + O(n)
   Applying Case 2 of the Master Theorem (a = 2, b = 2, f(n) = n):
   n^(log_b a) = n^(log_2 2) = n^1 = Theta(n)
   Since f(n) = Theta(n^(log_b a)), T(n) = Theta(n log n).

   - Best Case Time Complexity:    Omega(n log n)
   - Average Case Time Complexity: Theta(n log n)
   - Worst Case Time Complexity:   O(n log n)
   - Auxiliary Space Complexity:   O(n) for temporary merging arrays.

3. Stability Guarantee:
   An algorithm is 'stable' if elements with equal comparison keys preserve their original
   relative input order in the final output. In collaborative learning, if two peer answers
   have identical verification status, acceptance state, upvotes, and submission timestamps,
   Merge Sort preserves their natural posting sequence without arbitrary permutation.
   Neither Quick Sort (unstable in standard partitioning) nor Heap Sort (unstable) guarantees
   stability without synthetic index tiebreakers. Merge Sort naturally guarantees stability
   via the condition: choose left[i] whenever right[j] is not strictly superior.

Ranking Precedence Hierarchy:
-----------------------------
1. Teacher-Verified Answers: Certified by faculty as correct and authoritative.
2. Asker-Accepted Answer: Formally acknowledged by the original poster as solving their doubt.
3. Upvotes (Descending): Surfacing crowd-sourced peer endorsement and clarity.
4. Submission Timestamp (Ascending / Older First): First-mover advantage honoring early contributors.
"""

from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _is_better_answer(a: Any, b: Any, accepted_answer_id: int | None = None) -> bool:
    """
    Comparator predicate determining if answer 'a' should strictly precede answer 'b'.
    Supports SQLAlchemy Answer models, dictionary representations, and mock test objects.

    Returns:
        bool: True if 'a' has strictly higher ranking priority than 'b', False otherwise.
    """
    # 1. Teacher-Verified answers take absolute precedence
    a_ver = bool(getattr(a, "is_verified", False) or (isinstance(a, dict) and a.get("is_verified")))
    b_ver = bool(getattr(b, "is_verified", False) or (isinstance(b, dict) and b.get("is_verified")))
    if a_ver != b_ver:
        return a_ver > b_ver

    # 2. Asker-accepted solution takes secondary precedence
    a_id = getattr(a, "id", None) if not isinstance(a, dict) else a.get("id")
    b_id = getattr(b, "id", None) if not isinstance(b, dict) else b.get("id")
    a_acc = bool(accepted_answer_id is not None and a_id == accepted_answer_id)
    b_acc = bool(accepted_answer_id is not None and b_id == accepted_answer_id)
    if a_acc != b_acc:
        return a_acc > b_acc

    # 3. Community upvotes in descending order
    a_votes = (getattr(a, "upvotes", 0) if not isinstance(a, dict) else a.get("upvotes", 0)) or 0
    b_votes = (getattr(b, "upvotes", 0) if not isinstance(b, dict) else b.get("upvotes", 0)) or 0
    if a_votes != b_votes:
        return a_votes > b_votes

    # 4. Chronological tiebreaker: Older created_at first (smaller timestamp)
    a_time = getattr(a, "created_at", None) if not isinstance(a, dict) else a.get("created_at")
    b_time = getattr(b, "created_at", None) if not isinstance(b, dict) else b.get("created_at")
    if a_time is not None and b_time is not None and a_time != b_time:
        return a_time < b_time

    # Elements are equal under all 4 sorting criteria -> neither is strictly better
    return False


def merge_sort(items: list[T], is_better_fn: Callable[[T, T], bool]) -> list[T]:
    """
    Hand-implemented stable Merge Sort.
    Does NOT rely on Python's built-in sorted() or list.sort().

    Args:
        items: List of elements to sort.
        is_better_fn: Binary predicate returning True if first argument has strictly
                      higher sorting priority than second argument.

    Returns:
        list[T]: A newly allocated list containing all elements in sorted order.
    """
    n = len(items)
    if n <= 1:
        return list(items)

    mid = n // 2
    left = merge_sort(items[:mid], is_better_fn)
    right = merge_sort(items[mid:], is_better_fn)

    merged: list[T] = []
    i = 0
    j = 0

    # Merge two sorted sublists maintaining stability
    while i < len(left) and j < len(right):
        if is_better_fn(right[j], left[i]):
            merged.append(right[j])
            j += 1
        else:
            # Preserves stability: if left[i] is better or equal, take left[i] first
            merged.append(left[i])
            i += 1

    # Append remaining items
    if i < len(left):
        merged.extend(left[i:])
    if j < len(right):
        merged.extend(right[j:])

    return merged


def rank_answers(answers: list[Any], accepted_answer_id: int | None = None) -> list[Any]:
    """
    Public entrypoint to rank answers of a doubt using hand-implemented Merge Sort.
    Can be called with database models or standalone dictionary fixtures for unit testing.

    Args:
        answers: Collection of answer models or dictionaries.
        accepted_answer_id: Optional ID of the answer marked accepted by the asker.

    Returns:
        list[Any]: Ranked answers ordered by (Verified > Accepted > Upvotes > CreatedAt).
    """
    if not answers:
        return []

    def comparator(x: Any, y: Any) -> bool:
        return _is_better_answer(x, y, accepted_answer_id=accepted_answer_id)

    return merge_sort(list(answers), comparator)

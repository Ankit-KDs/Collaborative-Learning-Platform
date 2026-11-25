"""
Knuth-Morris-Pratt (KMP) Substring Search Algorithm
====================================================

Design Analysis and Algorithm (DAA) Theoretical Foundation:
------------------------------------------------------------
Substring searching is fundamental to information retrieval in student doubt forums.
Given a document text T of length n and a user query pattern P of length m:

1. Limitations of Naive String Matching:
   The naive string matcher compares P against T at every shift s in [0, n - m].
   When a character mismatch occurs at T[i] != P[j], the naive algorithm resets the text
   pointer i back to i - j + 1 and restarts at j = 0.
   - Worst-case time complexity: O(n * m) (e.g. searching P = "AAAB" in T = "AAAAAAAAAB").

2. The KMP Insight:
   Knuth, Morris, and Pratt (1977) observed that when a mismatch occurs after matching
   j characters, the matched segment T[i - j ... i - 1] is IDENTICAL to the pattern prefix P[0 ... j - 1].
   Therefore, knowledge about internal self-similarity within the pattern P can inform
   how far the pattern can slide WITHOUT EVER BACKTRACKING the text index i.

3. The Longest Prefix which is also a Suffix (LPS / Pi Table):
   We precompute an array lps of length m, where lps[j] is the length of the longest
   proper prefix of P[0 ... j] that is also a suffix of P[0 ... j].
   - Proper prefix: A prefix of P that is not equal to P itself.
   - Example for P = "ABABCABAB":
     Indices:  0  1  2  3  4  5  6  7  8
     Pattern:  A  B  A  B  C  A  B  A  B
     LPS:      0  0  1  2  0  1  2  3  4

4. Asymptotic Complexity:
   - Preprocessing Phase: Computes the LPS array in Theta(m) time and Theta(m) space.
   - Searching Phase: Matches characters monotonically; each mismatch shifts j to lps[j - 1],
     guaranteeing the text pointer i increases strictly in Theta(n) steps.
   - Total Time Complexity:  Theta(n + m) in best, average, and worst cases.
   - Auxiliary Space:        Theta(m) memory for the LPS table.
"""

from typing import Any


def build_kmp_lps(pattern: str) -> list[int]:
    """
    Construct the Longest Proper Prefix which is also a Suffix (LPS) table for the given pattern.
    Runs in Theta(m) time where m = len(pattern).

    Args:
        pattern: The search needle string.

    Returns:
        list[int]: Array of length m where lps[i] is the length of the longest proper prefix of
                   pattern[0..i] that matches a suffix of pattern[0..i].
    """
    m = len(pattern)
    if m == 0:
        return []

    lps = [0] * m
    length = 0  # length of previous longest prefix suffix
    i = 1

    while i < m:
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        else:
            if length != 0:
                # Fall back to the previous known prefix length without incrementing i
                length = lps[length - 1]
            else:
                lps[i] = 0
                i += 1

    return lps


def kmp_search(text: str, pattern: str) -> bool:
    """
    Perform case-insensitive substring search using the hand-implemented KMP algorithm.
    Guarantees O(n + m) linear execution without backtracking text indices.

    Args:
        text: Target document string (haystack) of length n.
        pattern: Query keyword string (needle) of length m.

    Returns:
        bool: True if pattern is found as a contiguous substring of text, False otherwise.
    """
    if not pattern:
        # An empty pattern is vacuously contained in any text
        return True

    if not text:
        return False

    # Normalize to lower-case for case-insensitive matching
    norm_text = text.lower()
    norm_pattern = pattern.lower()

    n = len(norm_text)
    m = len(norm_pattern)

    if m > n:
        return False

    lps = build_kmp_lps(norm_pattern)

    i = 0  # index for norm_text
    j = 0  # index for norm_pattern

    while i < n:
        if norm_pattern[j] == norm_text[i]:
            i += 1
            j += 1

        if j == m:
            # Full pattern match found
            return True
        elif i < n and norm_pattern[j] != norm_text[i]:
            if j != 0:
                # Use LPS table to skip redundant character re-evaluations
                j = lps[j - 1]
            else:
                i += 1

    return False


def filter_doubts_by_kmp(doubts: list[Any], query: str) -> list[Any]:
    """
    Filter candidate doubts where the search query matches the title or body using KMP.

    Args:
        doubts: List of Doubt objects or dictionaries.
        query: User keyword query.

    Returns:
        list[Any]: Sublist of doubts matching the keyword.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return doubts

    results: list[Any] = []
    for d in doubts:
        title = getattr(d, "title", "") if not isinstance(d, dict) else d.get("title", "")
        body = getattr(d, "body", "") if not isinstance(d, dict) else d.get("body", "")

        if kmp_search(title, clean_query) or kmp_search(body, clean_query):
            results.append(d)

    return results

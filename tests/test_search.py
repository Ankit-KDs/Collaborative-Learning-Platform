"""
Unit tests for the hand-implemented Knuth-Morris-Pratt (KMP) search algorithm (Stage 5).
Validates LPS table construction, edge cases, case-insensitivity, and tricky repetitive patterns.
"""

from app.services.search import build_kmp_lps, filter_doubts_by_kmp, kmp_search


def test_build_kmp_lps_table():
    """Verify LPS (Pi table) construction against known textbook values."""
    # 1. Empty pattern
    assert build_kmp_lps("") == []

    # 2. Single char
    assert build_kmp_lps("A") == [0]

    # 3. All identical characters
    assert build_kmp_lps("AAAA") == [0, 1, 2, 3]

    # 4. Classic DAA textbook pattern: "ABABCABAB"
    # A=0, B=0, A=1, B=2, C=0, A=1, B=2, A=3, B=4
    assert build_kmp_lps("ABABCABAB") == [0, 0, 1, 2, 0, 1, 2, 3, 4]

    # 5. Pattern with partial restarts: "AABAACAABAA"
    # A:0, A:1, B:0, A:1, A:2, C:0, A:1, A:2, B:3, A:4, A:5
    assert build_kmp_lps("AABAACAABAA") == [0, 1, 0, 1, 2, 0, 1, 2, 3, 4, 5]


def test_kmp_search_edge_cases():
    """Test boundary conditions for KMP substring search."""
    # Empty pattern matches any text
    assert kmp_search("Hello World", "") is True
    assert kmp_search("", "") is True

    # Empty text cannot match non-empty pattern
    assert kmp_search("", "hello") is False

    # Pattern longer than text cannot match
    assert kmp_search("short", "longer_pattern") is False

    # Exact string match
    assert kmp_search("database", "database") is True


def test_kmp_search_positions_and_cases():
    """Test start, middle, end positions and case-insensitivity."""
    haystack = "The quick brown fox jumps over the lazy dog"

    # Start
    assert kmp_search(haystack, "the") is True
    # Middle
    assert kmp_search(haystack, "brown fox") is True
    # End
    assert kmp_search(haystack, "lazy dog") is True
    # Not present
    assert kmp_search(haystack, "cat") is False

    # Case insensitivity
    assert kmp_search(haystack, "BrOwN FoX") is True
    assert kmp_search(haystack, "LAZY DOG") is True


def test_kmp_search_tricky_repetitive_patterns():
    """Verify tricky overlapping and repetitive sequences that trip naive algorithms."""
    # Repetitive character sequences
    assert kmp_search("aaaaab", "aaab") is True
    assert kmp_search("aaaaaa", "aaa") is True
    assert kmp_search("aaaaaa", "aaab") is False

    # Overlapping cycles
    assert kmp_search("ababcababx", "ababcabab") is True
    assert kmp_search("ababcababy", "ababab") is False
    assert kmp_search("mississippi", "issip") is True


def test_filter_doubts_by_kmp():
    """Verify filtering a list of candidate doubt objects using KMP."""
    class DummyDoubt:
        def __init__(self, id, title, body):
            self.id = id
            self.title = title
            self.body = body

    doubts = [
        DummyDoubt(1, "How does Dijkstra work?", "I need help with Dijkstra's algorithm."),
        DummyDoubt(2, "B+ Tree Indexing", "Explaining leaf nodes and range queries."),
        DummyDoubt(3, "Bellman-Ford vs Floyd-Warshall", "Comparing dynamic programming graphs."),
    ]

    # Search matches in title or body
    res_dijkstra = filter_doubts_by_kmp(doubts, "dijkstra")
    assert [d.id for d in res_dijkstra] == [1]

    res_queries = filter_doubts_by_kmp(doubts, "RANGE QUERIES")
    assert [d.id for d in res_queries] == [2]

    res_dynamic = filter_doubts_by_kmp(doubts, "dynamic programming")
    assert [d.id for d in res_dynamic] == [3]

    # Empty query returns full original list
    assert len(filter_doubts_by_kmp(doubts, "")) == 3

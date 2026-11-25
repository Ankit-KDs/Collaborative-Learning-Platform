"""
Content Moderation Service using the Aho-Corasick Automaton
============================================================
Provides multi-pattern profanity and abusive language detection across:
- Chat messages (auto-masking with asterisk replacement, preserving length)
- Doubts and answers (strict submission rejection)
- Study group names and quiz topics

Viva & Theoretical Overview of the Aho-Corasick Algorithm:
----------------------------------------------------------
1. Origin:
   Invented in 1975 by Alfred V. Aho and Margaret J. Corasick at Bell Laboratories.

2. Problem Statement:
   Given a dictionary of k keywords of total length m = sum(|p_i|), and an input text
   of length n, locate all occurrences of any keyword in the text.

3. Why Aho-Corasick is Superior to Naive Multi-Pattern Search:
   - Naive Search: Scanning the text for each of the k keywords independently takes
     O(n * k) or O(n * m) time. When the keyword list grows to hundreds or thousands
     of abusive words, this degrades response latency and throughput.
   - Aho-Corasick: Constructs a Deterministic Finite Automaton (DFA) combining a Trie,
     failure links (analogous to the KMP failure function), and output links.
     Searching takes O(n + m + z) time, where:
       * n = length of the input text
       * m = total length of all dictionary patterns (cost to construct the trie)
       * z = number of pattern occurrences reported
     Crucially, searching is strictly LINEAR with respect to text length, processing
     each input character in amortized O(1) time regardless of dictionary size.

4. Internal Architecture:
   - Trie (Goto function): Represents common prefixes of dictionary patterns in a rooted tree.
   - Failure links (Fail function): Built using Breadth-First Search (BFS). For node u,
     fail(u) points to the node whose path from root is the longest proper suffix of the
     string corresponding to u that is also a prefix in the trie.
   - Output links (Dict outputs): Collects all patterns ending at a node or any of its
     failure ancestors, allowing simultaneous detection of overlapping patterns
     (e.g., detecting both "ass" and "asshole" at the same locus).

5. Concrete Trace Example:
   Patterns: ["bad", "ad", "cat"]
   Text: "badvocat"
   - Transitions on 'b' -> node(b)
   - Transitions on 'a' -> node(ba)
   - Transitions on 'd' -> node(bad) [MATCH "bad", and follow fail link to node(ad) -> MATCH "ad"]
   - Transitions on 'v' -> no edge from 'bad', follows fail(bad)=ad, fail(ad)=root -> root
   - Continues linearly without backtracking in the input text.

6. Evasion Defense & Scunthorpe Mitigation:
   - Normalization: Leetspeak character mapping (@->a, 0->o, 1->i, 3->e, $->s, 5->s, 7->t).
   - Character repetition: Collapses 3+ consecutive identical characters.
   - Separator evasion: Detects and collapses spaced or punctuated single characters (e.g. "f u c k", "f.u.c.k").
   - Scunthorpe problem: Strict word boundary checking ensuring innocent words containing
     bad substrings (e.g. "classic", "pass", "document", "assignment") are NOT flagged.
   - Allowlist: Explicit lookup in app/data/allowlist.txt for academic/technical vocabulary.
"""

from collections import deque
from pathlib import Path
import re
from typing import TypedDict

from app import db
from app.models import ModerationLog, utc_now

# Paths to data files
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BADWORDS_PATH = DATA_DIR / "badwords.txt"
ALLOWLIST_PATH = DATA_DIR / "allowlist.txt"

# Leetspeak translation table
LEET_MAP = {
    "@": "a",
    "0": "o",
    "1": "i",
    "!": "i",
    "3": "e",
    "$": "s",
    "5": "s",
    "7": "t",
}


class ScanResult(TypedDict):
    is_flagged: bool
    matched_count: int
    masked_text: str


class ModerationBlockedError(Exception):
    """Raised when user-submitted content is blocked due to prohibited profanity."""

    def __init__(
        self,
        message: str = "Inappropriate content detected. Please remove prohibited language before submitting.",
        matched_count: int = 1,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.matched_count = matched_count


class AhoCorasickNode:
    """Node in the Aho-Corasick keyword trie with failure and output links."""

    __slots__ = ("children", "fail", "output")

    def __init__(self) -> None:
        self.children: dict[str, AhoCorasickNode] = {}
        self.fail: AhoCorasickNode | None = None
        self.output: list[str] = []


class AhoCorasickAutomaton:
    """
    Hand-crafted Aho-Corasick multi-pattern search automaton.
    Constructs a Trie with BFS failure transitions for O(n + m + z) matching.
    """

    def __init__(self, patterns: list[str]) -> None:
        self.root = AhoCorasickNode()
        self._build_trie(patterns)
        self._build_failure_links()

    def _build_trie(self, patterns: list[str]) -> None:
        for p in patterns:
            p_clean = p.strip().lower()
            if not p_clean:
                continue
            curr = self.root
            for char in p_clean:
                if char not in curr.children:
                    curr.children[char] = AhoCorasickNode()
                curr = curr.children[char]
            curr.output.append(p_clean)

    def _build_failure_links(self) -> None:
        queue: deque[AhoCorasickNode] = deque()

        # Direct children of root fail to root
        for child in self.root.children.values():
            child.fail = self.root
            queue.append(child)

        # BFS level-by-level traversal
        while queue:
            curr = queue.popleft()
            for char, child in curr.children.items():
                queue.append(child)
                f = curr.fail
                while f is not None and char not in f.children:
                    f = f.fail
                child.fail = f.children[char] if (f is not None and char in f.children) else self.root
                # Inherit outputs from the failure node
                if child.fail.output:
                    child.output.extend(child.fail.output)

    def search_all(self, text: str) -> list[tuple[int, int, str]]:
        """
        Scan text and return all pattern matches as (start_idx, end_idx, pattern) tuples,
        where end_idx is exclusive.
        """
        matches: list[tuple[int, int, str]] = []
        curr = self.root
        for idx, char in enumerate(text):
            while curr is not self.root and char not in curr.children:
                curr = curr.fail if curr.fail is not None else self.root
            curr = curr.children.get(char, self.root)
            for pat in curr.output:
                start = idx - len(pat) + 1
                end = idx + 1
                matches.append((start, end, pat))
        return matches


# Singleton caches
_AUTOMATON: AhoCorasickAutomaton | None = None
_ALLOWLIST: set[str] | None = None


def load_badwords() -> list[str]:
    """Load bad words list from disk. Ignores comments and blank lines."""
    if not BADWORDS_PATH.exists():
        return ["fuck", "shit", "bitch", "asshole", "chutiya", "bhosdike", "madarchod"]
    words: list[str] = []
    with open(BADWORDS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.strip()
            if clean and not clean.startswith("#"):
                words.append(clean.lower())
    return words


def load_allowlist() -> set[str]:
    """Load Scunthorpe allowlist from disk. Ignores comments and blank lines."""
    if not ALLOWLIST_PATH.exists():
        return {
            "class", "classes", "classic", "pass", "passage", "passed",
            "compass", "assess", "assessment", "asset", "assume", "assign",
            "assignment", "document", "hello", "button", "title",
        }
    allow: set[str] = set()
    with open(ALLOWLIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.strip().lower()
            if clean and not clean.startswith("#"):
                allow.add(clean)
    return allow


def get_automaton() -> AhoCorasickAutomaton:
    """Return cached Aho-Corasick automaton singleton."""
    global _AUTOMATON
    if _AUTOMATON is None:
        _AUTOMATON = AhoCorasickAutomaton(load_badwords())
    return _AUTOMATON


def get_allowlist() -> set[str]:
    """Return cached allowlist set singleton."""
    global _ALLOWLIST
    if _ALLOWLIST is None:
        _ALLOWLIST = load_allowlist()
    return _ALLOWLIST


def reset_moderation_caches() -> None:
    """Reset singletons for unit testing and hot-reloading."""
    global _AUTOMATON, _ALLOWLIST
    _AUTOMATON = None
    _ALLOWLIST = None


def _apply_leetspeak_and_collapse(text: str) -> tuple[str, list[int]]:
    """
    Apply leetspeak character normalization and collapse 3+ consecutive
    identical characters down to 2, tracking character index mapping
    back to original text indices.
    """
    collapsed_chars: list[str] = []
    index_map: list[int] = []

    for orig_idx, ch in enumerate(text):
        c_low = ch.lower()
        c_mapped = LEET_MAP.get(c_low, c_low)

        # Collapse 3+ repeats to 2
        if len(collapsed_chars) >= 2 and collapsed_chars[-1] == c_mapped and collapsed_chars[-2] == c_mapped:
            continue

        collapsed_chars.append(c_mapped)
        index_map.append(orig_idx)

    return "".join(collapsed_chars), index_map


def _is_word_boundary_match(
    text: str,
    start: int,
    end: int,
    allowlist: set[str],
) -> bool:
    """
    Check if a candidate match lies on word boundaries and is not an innocent word
    from the Scunthorpe allowlist.
    """
    # 1. Left boundary: must not be preceded by alphanumeric character
    if start > 0 and text[start - 1].isalnum():
        return False

    # 2. Right boundary: must not be followed by alphanumeric character
    if end < len(text) and text[end].isalnum():
        return False

    # 3. Check enclosing word against allowlist
    w_start = start
    while w_start > 0 and text[w_start - 1].isalnum():
        w_start -= 1
    w_end = end
    while w_end < len(text) and text[w_end].isalnum():
        w_end += 1

    enclosing = text[w_start:w_end].lower()
    if enclosing in allowlist:
        return False

    return True


def scan_text(text: str) -> ScanResult:
    """
    Scan text for prohibited words using Aho-Corasick.
    Detects direct matches, leetspeak, repeated letter evasion, and spaced/punctuated evasion.

    Returns:
        ScanResult dict:
            - is_flagged (bool): True if at least one profane term was detected.
            - matched_count (int): Number of distinct detected profanities.
            - masked_text (str): String with profane words replaced by asterisks (*),
                                 guaranteeing exact same length as original text.
    """
    if not text or not text.strip():
        return {
            "is_flagged": False,
            "matched_count": 0,
            "masked_text": text or "",
        }

    automaton = get_automaton()
    allowlist = get_allowlist()

    n = len(text)
    # Boolean mask: True at indices in text that must be masked
    mask = [False] * n

    # List of confirmed match spans in original text: (orig_start, orig_end)
    confirmed_spans: list[tuple[int, int]] = []

    # -------------------------------------------------------------
    # Pass 1: Direct scan with leetspeak & 3+ repeat collapsing
    # -------------------------------------------------------------
    norm_text, index_map = _apply_leetspeak_and_collapse(text)
    matches_p1 = automaton.search_all(norm_text)

    for start_norm, end_norm, pat in matches_p1:
        if _is_word_boundary_match(norm_text, start_norm, end_norm, allowlist):
            orig_start = index_map[start_norm]
            orig_end = index_map[end_norm - 1] + 1
            confirmed_spans.append((orig_start, orig_end))

    # Also check full collapse of consecutive repeating characters (e.g. fuuuuck -> fuck)
    # for words where repeated characters inflate the pattern length
    norm_chars_1: list[str] = []
    index_map_1: list[int] = []
    for orig_idx, ch in enumerate(text):
        c_low = ch.lower()
        c_mapped = LEET_MAP.get(c_low, c_low)
        if len(norm_chars_1) >= 1 and norm_chars_1[-1] == c_mapped:
            continue
        norm_chars_1.append(c_mapped)
        index_map_1.append(orig_idx)

    norm_text_1 = "".join(norm_chars_1)
    matches_p1_1 = automaton.search_all(norm_text_1)
    for start_norm, end_norm, pat in matches_p1_1:
        if _is_word_boundary_match(norm_text_1, start_norm, end_norm, allowlist):
            orig_start = index_map_1[start_norm]
            orig_end = index_map_1[end_norm - 1] + 1
            confirmed_spans.append((orig_start, orig_end))

    # -------------------------------------------------------------
    # Pass 2: Separator evasion scan (e.g. "f u c k", "f.u.c.k", "f-u-c-k")
    # -------------------------------------------------------------
    # Locate candidate spaced/punctuated letter sequences
    sep_pattern = re.compile(r"(?:[a-zA-Z0-9@$!30157][\s\.\-_*]+){2,}[a-zA-Z0-9@$!30157]")
    for match in sep_pattern.finditer(text):
        chunk = match.group(0)
        span_start = match.start()

        # Collapse separators and map characters back to original chunk offsets
        chunk_chars: list[str] = []
        chunk_orig_indices: list[int] = []
        for offset, ch in enumerate(chunk):
            if ch.isalnum() or ch in LEET_MAP:
                c_low = ch.lower()
                chunk_chars.append(LEET_MAP.get(c_low, c_low))
                chunk_orig_indices.append(span_start + offset)

        despaced = "".join(chunk_chars)
        matches_sep = automaton.search_all(despaced)
        for s_idx, e_idx, pat in matches_sep:
            orig_start = chunk_orig_indices[s_idx]
            orig_end = chunk_orig_indices[e_idx - 1] + 1
            # Check boundaries in the original text
            if _is_word_boundary_match(text, orig_start, orig_end, allowlist):
                confirmed_spans.append((orig_start, orig_end))

    if not confirmed_spans:
        return {
            "is_flagged": False,
            "matched_count": 0,
            "masked_text": text,
        }

    # Merge overlapping spans to count distinct profane instances
    confirmed_spans.sort(key=lambda s: (s[0], s[1]))
    merged_spans: list[tuple[int, int]] = []
    for s_start, s_end in confirmed_spans:
        if not merged_spans:
            merged_spans.append((s_start, s_end))
        else:
            prev_start, prev_end = merged_spans[-1]
            if s_start <= prev_end:
                merged_spans[-1] = (prev_start, max(prev_end, s_end))
            else:
                merged_spans.append((s_start, s_end))

    # Apply mask for every character within confirmed spans
    for m_start, m_end in merged_spans:
        for i in range(m_start, min(m_end, n)):
            mask[i] = True

    # Construct masked string (asterisks for masked chars, spaces/newlines preserved or masked)
    # Notice: we replace non-whitespace characters with '*' to preserve formatting,
    # or all matched characters with '*' if separator evasion.
    # To strictly preserve exact string length:
    masked_chars = [("*" if mask[i] and not text[i].isspace() else ("*" if mask[i] else text[i])) for i in range(n)]
    masked_str = "".join(masked_chars)

    return {
        "is_flagged": True,
        "matched_count": len(merged_spans),
        "masked_text": masked_str,
    }


def contains_profanity(text: str) -> bool:
    """Return True if the text contains prohibited profanity, False otherwise."""
    return scan_text(text)["is_flagged"]


def toxicity_score(text: str) -> float | None:
    """
    Optional hook for future ML toxicity classification (e.g. Perspective API or fine-tuned model).
    Currently a placeholder returning None as documented in Stage 7 specifications.
    """
    return None


def log_moderation_event(
    user_id: int | None,
    source: str,
    action: str,
    matched_count: int = 1,
) -> ModerationLog:
    """
    Persist an automated content moderation audit record.
    Security guarantee: Never stores matched keywords or full raw text.
    """
    log_entry = ModerationLog(
        user_id=user_id,
        source=source,
        action=action,
        matched_count=matched_count,
        created_at=utc_now(),
    )
    db.session.add(log_entry)
    db.session.commit()
    return log_entry


def validate_content_profanity(text: str, source: str, user_id: int | None = None) -> None:
    """
    Enforce zero-tolerance profanity policy for public content
    (doubts, answers, group names, quiz topics).
    Raises ModerationBlockedError and records a ModerationLog row if prohibited terms are found.
    """
    res = scan_text(text)
    if res["is_flagged"]:
        log_moderation_event(
            user_id=user_id,
            source=source,
            action="blocked",
            matched_count=res["matched_count"],
        )
        raise ModerationBlockedError(
            "Inappropriate content detected. Please remove offensive or abusive language.",
            matched_count=res["matched_count"],
        )

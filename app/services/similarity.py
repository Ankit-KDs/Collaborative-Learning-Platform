"""
Duplicate Doubt Detection Service using TF-IDF & Cosine Similarity and Cryptographic Hashing
=============================================================================================

Design Analysis and Algorithm (DAA) Theoretical Foundation:
------------------------------------------------------------
In large collaborative forums, students frequently encounter identical conceptual roadblocks.
Allowing duplicate questions causes forum fragmentation, duplicates answering effort, and dilutes
pedagogical peer feedback. This module combines two complementary algorithmic strategies:

1. Cryptographic Hashing for Exact-Duplicate Detection (O(L) time):
   -----------------------------------------------------------------
   - Normalization: Ingested text undergoes case-folding (lowercase), punctuation stripping,
     and whitespace normalization (collapsing multi-spaces into single delimiter).
   - Hash Function: SHA-256 (Secure Hash Algorithm 256-bit).
     SHA-256 is a cryptographic Merkle-Damgard hash that transforms an arbitrary-length message
     into a 256-bit digest with avalanche effect (a single character difference alters ~50%
     of output bits) and collision resistance (birthday paradox search requires ~2^128 operations).
   - Exact duplicate checks run in O(L) time where L is string length, avoiding database full-scans.

2. TF-IDF & Cosine Similarity for Semantic Near-Duplicate Detection:
   -----------------------------------------------------------------
   Near-duplicate questions often differ in phrasing (e.g., "How does Dijkstra algorithm work?" vs.
   "Explain Dijkstra shortest path logic in Python"). We map text to the Vector Space Model (VSM).

   a. Term Frequency (TF):
      Measures local importance: TF(t, d) = count(t in d) / total_words(d).
      Words appearing frequently in a specific question receive higher local weight.

   b. Inverse Document Frequency (IDF):
      Measures global discrimination:
      IDF(t, D) = log( (1 + |D|) / (1 + count(d in D containing t)) ) + 1
      Ubiquitous stop words ("the", "is", "explain") have low IDF.
      Domain-specific keywords ("Dijkstra", "B-Tree", "deadlock") have high IDF.

   c. TF-IDF Representation:
      Vector w(t, d) = TF(t, d) * IDF(t, D), normalized with Euclidean L2-norm: ||w||_2 = 1.

   d. Cosine Similarity:
      Measures angular orientation between query vector Q and document vector D:
      cos(theta) = (Q . D) / (||Q||_2 * ||D||_2)
      Since vectors are L2-normalized, cos(theta) simplifies to dot product: sum(Q_i * D_i).
      Similarity score ranges from 0.0 (orthogonal / zero lexical overlap) to 1.0 (identical distribution).
      A tuned threshold (default 0.35) balances precision and recall for student doubt discovery.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import Doubt


def normalize_text_for_hash(text: str) -> str:
    """
    Normalize text for exact hashing:
    1. Lowercase text.
    2. Strip punctuation marks.
    3. Collapse multiple whitespace characters into a single space.
    """
    if not text:
        return ""
    # Lowercase
    clean = text.lower()
    # Remove punctuation
    clean = re.sub(r"[^\w\s]", "", clean)
    # Collapse multiple whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def compute_doubt_hash(title: str, body: str) -> str:
    """
    Compute a deterministic SHA-256 digest of normalized title + body.
    """
    normalized_content = f"{normalize_text_for_hash(title)} {normalize_text_for_hash(body)}"
    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()


def check_exact_duplicate(user_id: int, title: str, body: str, days_window: int = 7) -> bool:
    """
    Check if the user has already posted an identical doubt within the recent window.

    Args:
        user_id: ID of student attempting to post.
        title: Doubt title.
        body: Doubt body content.
        days_window: Days back to inspect for duplicates.

    Returns:
        bool: True if an identical doubt hash already exists from this user.
    """
    candidate_hash = compute_doubt_hash(title, body)
    if not candidate_hash:
        return False

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_window)
    recent_doubts = Doubt.query.filter(
        Doubt.user_id == user_id,
        Doubt.created_at >= cutoff,
    ).all()

    for d in recent_doubts:
        existing_hash = compute_doubt_hash(d.title, d.body)
        if candidate_hash == existing_hash:
            return True

    return False


def find_similar_doubts(
    subject: str,
    title: str,
    body: str,
    limit: int = 5,
    threshold: float = 0.35,
    exclude_doubt_id: int | None = None,
) -> list[tuple[Any, float]]:
    """
    Find semantically similar doubts within the same subject using TF-IDF + Cosine Similarity.

    Args:
        subject: Subject category (must match existing doubts' subject).
        title: Query doubt title.
        body: Query doubt body.
        limit: Maximum number of similar doubts to return.
        threshold: Minimum cosine similarity score (0.0 to 1.0) to qualify as similar.
        exclude_doubt_id: Optional ID to exclude from comparison (e.g. during doubt editing).

    Returns:
        list of (Doubt, float similarity_score) sorted descending by score.
    """
    query_text = f"{title or ''} {body or ''}".strip()
    if len(query_text) < 5:
        return []

    # Query existing doubts strictly within the same subject
    query = Doubt.query.filter(Doubt.subject == subject)
    if exclude_doubt_id:
        query = query.filter(Doubt.id != exclude_doubt_id)

    candidate_doubts = query.order_by(Doubt.created_at.desc()).limit(100).all()
    if not candidate_doubts:
        return []

    corpus_texts: list[str] = [query_text]
    for d in candidate_doubts:
        corpus_texts.append(f"{d.title} {d.body}")

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            min_df=1,
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b\w+\b",
        )
        tfidf_matrix = vectorizer.fit_transform(corpus_texts)
    except (ValueError, TypeError):
        # Graceful fallback for empty vocabulary or malformed text
        return []

    # Query vector is row 0; document vectors are rows 1 to N
    query_vec = tfidf_matrix[0:1]
    doc_vecs = tfidf_matrix[1:]

    cos_scores = cosine_similarity(query_vec, doc_vecs)[0]

    matched: list[tuple[Any, float]] = []
    for idx, score in enumerate(cos_scores):
        float_score = float(score)
        if float_score >= threshold:
            matched.append((candidate_doubts[idx], round(float_score, 4)))

    # Sort descending by cosine similarity score
    matched.sort(key=lambda item: item[1], reverse=True)
    return matched[:limit]

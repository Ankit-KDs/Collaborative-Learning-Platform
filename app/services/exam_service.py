"""
Exam Mode & High-Yield Revision Service
=======================================
Provides pedagogical revision synthesis for students and faculty:
1. TF-IDF Keyword Extraction: Identifies the top 10 most frequently queried topics/concepts.
2. FAQ Near-Duplicate Clustering: Groups similar doubts via Cosine Similarity in Vector Space,
   surfacing representative questions, frequency count, and the highest-ranked answers.
3. Top Verified and Accepted Answers: Curates peer and faculty verified solutions.
4. Unanswered Hot Doubts: Identifies questions needing urgent peer peer-tutoring.
5. Strict Anonymity: Enforces anonymous labeling across all doubt cards and answer links.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import Answer, Doubt
from app.services.ranking import rank_answers
from app.services.similarity import normalize_text_for_hash


def get_display_asker(doubt: Doubt) -> str:
    """Return 'Anonymous' if doubt is posted anonymously, else student name."""
    if doubt.is_anonymous:
        return "Anonymous"
    return doubt.user.name if doubt.user else "Anonymous"


def fetch_subject_doubts(subject: str, time_range: str = "30") -> list[Doubt]:
    """
    Retrieve doubts for a given subject filtered by time window.
    time_range options: '30' (last 30 days), '90' (last 90 days), 'all'.
    """
    query = Doubt.query.filter_by(subject=subject)

    if time_range == "30":
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        query = query.filter(Doubt.created_at >= cutoff)
    elif time_range == "90":
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
        query = query.filter(Doubt.created_at >= cutoff)

    return query.order_by(Doubt.created_at.desc()).all()


def compute_most_asked_topics(doubts: list[Doubt], top_k: int = 10) -> list[dict[str, Any]]:
    """
    Extract top keywords/keyphrases from doubt titles and bodies using local TF-IDF.
    Returns normalized frequency percentages (up to 100%) for visualization bars.
    """
    if not doubts:
        return []

    corpus: list[str] = []
    for d in doubts:
        text = f"{normalize_text_for_hash(d.title)} {normalize_text_for_hash(d.body)}"
        if text.strip():
            corpus.append(text)

    if not corpus:
        return []

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=150,
            min_df=1,
            token_pattern=r"(?u)\b[a-zA-Z]{3,}\b",
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)
        feature_names = vectorizer.get_feature_names_out()

        # Aggregate mean TF-IDF weight for each term across all documents
        import numpy as np
        mean_weights = np.asarray(tfidf_matrix.mean(axis=0)).flatten()

        # Sort indices by descending score
        top_indices = mean_weights.argsort()[::-1]

        results: list[dict[str, Any]] = []
        max_score = 0.0

        for idx in top_indices:
            term = str(feature_names[idx])
            score = float(mean_weights[idx])
            if score <= 0.0:
                continue
            if not results:
                max_score = score
            percent = int(round((score / max_score) * 100)) if max_score > 0 else 100
            results.append({
                "term": term.title(),
                "score": round(score, 4),
                "percent": max(10, percent),
            })
            if len(results) >= top_k:
                break

        return results
    except Exception:
        # Fallback if corpus lacks vocabulary
        return []


def cluster_faq_doubts(
    doubts: list[Doubt],
    similarity_threshold: float = 0.45,
) -> list[dict[str, Any]]:
    """
    Group near-duplicate/similar doubts into semantic clusters using greedy Cosine Similarity.
    For each cluster:
    - Surfaces representative doubt title
    - Count of times asked (cluster size)
    - Highest-ranked answer across the cluster (via hand-crafted Merge Sort)
    - Total upvotes
    Clusters are sorted primarily by size (asked N times), secondarily by total upvotes.
    """
    if not doubts:
        return []

    corpus = [f"{normalize_text_for_hash(d.title)} {normalize_text_for_hash(d.body)}" for d in doubts]

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            token_pattern=r"(?u)\b[a-zA-Z]{2,}\b",
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)
    except Exception:
        # Fallback: each doubt forms its own individual cluster
        tfidf_matrix = None

    # Greedy clustering
    clusters: list[dict[str, Any]] = []

    for idx, doubt in enumerate(doubts):
        assigned_cluster = None
        best_sim = 0.0

        if tfidf_matrix is not None:
            doubt_vec = tfidf_matrix[idx]
            for cl in clusters:
                rep_idx = cl["rep_idx"]
                rep_vec = tfidf_matrix[rep_idx]
                sim = float(cosine_similarity(doubt_vec, rep_vec)[0][0])
                if sim >= similarity_threshold and sim > best_sim:
                    best_sim = sim
                    assigned_cluster = cl

        if assigned_cluster is not None:
            assigned_cluster["doubts"].append(doubt)
        else:
            clusters.append({
                "rep_idx": idx,
                "representative": doubt,
                "doubts": [doubt],
            })

    # Prepare cluster envelopes with answers ranked via Merge Sort
    cluster_results: list[dict[str, Any]] = []
    for cl in clusters:
        cluster_doubts = cl["doubts"]
        count = len(cluster_doubts)

        # Collect all answers from all doubts in cluster
        all_answers: list[Answer] = []
        for d in cluster_doubts:
            all_answers.extend(d.answers.all())

        # Find accepted answer id if any doubt in cluster was solved
        accepted_id = None
        for d in cluster_doubts:
            if d.solved_answer_id:
                accepted_id = d.solved_answer_id
                break

        # Rank answers via Merge Sort
        ranked = rank_answers(all_answers, accepted_answer_id=accepted_id)
        best_ans = ranked[0] if ranked else None

        total_upvotes = sum(a.upvotes for a in all_answers)

        cluster_results.append({
            "representative_title": cl["representative"].title,
            "representative_doubt": cl["representative"],
            "count": count,
            "total_upvotes": total_upvotes,
            "best_answer": best_ans,
            "all_doubts": cluster_doubts,
        })

    # Sort: cluster size descending, then total upvotes descending
    cluster_results.sort(key=lambda c: (c["count"], c["total_upvotes"]), reverse=True)
    return cluster_results


def get_top_verified_and_accepted_answers(
    subject: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Curate the highest-ranked verified and accepted answers for a subject.
    """
    # Fetch all doubts for this subject
    doubts = Doubt.query.filter_by(subject=subject).all()
    if not doubts:
        return []

    doubt_map = {d.id: d for d in doubts}
    doubt_ids = list(doubt_map.keys())

    # Find verified answers or answers marked as solved
    answers = (
        Answer.query.filter(Answer.doubt_id.in_(doubt_ids))
        .filter(
            (Answer.is_verified.is_(True))
            | (Answer.id.in_([d.solved_answer_id for d in doubts if d.solved_answer_id]))
        )
        .all()
    )

    ranked = rank_answers(answers)
    results: list[dict[str, Any]] = []

    for ans in ranked[:limit]:
        parent_doubt = doubt_map.get(ans.doubt_id)
        if not parent_doubt:
            continue
        is_accepted = bool(parent_doubt.solved_answer_id == ans.id)
        results.append({
            "answer": ans,
            "doubt": parent_doubt,
            "asker_name": get_display_asker(parent_doubt),
            "is_accepted": is_accepted,
            "is_verified": ans.is_verified,
        })

    return results


def get_unanswered_hot_doubts(
    subject: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Find open doubts with zero answers or marked needs_human=True, newest first.
    """
    doubts = (
        Doubt.query.filter_by(subject=subject, status="open")
        .order_by(Doubt.created_at.desc())
        .all()
    )

    unanswered: list[dict[str, Any]] = []
    for d in doubts:
        if d.answers.count() == 0 or d.needs_human:
            unanswered.append({
                "doubt": d,
                "asker_name": get_display_asker(d),
                "needs_human": d.needs_human,
                "answer_count": d.answers.count(),
            })
            if len(unanswered) >= limit:
                break

    return unanswered


def build_exam_revision_package(
    subject: str,
    time_range: str = "30",
) -> dict[str, Any]:
    """
    Orchestrate full Exam Mode revision package for a subject:
    1. Most asked topics (TF-IDF)
    2. FAQ doubt clusters (Cosine Similarity + Merge Sort)
    3. Top verified & accepted answers
    4. Unanswered hot doubts
    """
    doubts = fetch_subject_doubts(subject, time_range)
    topics = compute_most_asked_topics(doubts, top_k=10)
    clusters = cluster_faq_doubts(doubts, similarity_threshold=0.45)
    top_answers = get_top_verified_and_accepted_answers(subject, limit=10)
    hot_doubts = get_unanswered_hot_doubts(subject, limit=5)

    return {
        "subject": subject,
        "time_range": time_range,
        "total_doubts_in_window": len(doubts),
        "topics": topics,
        "faq_clusters": clusters,
        "top_answers": top_answers,
        "hot_doubts": hot_doubts,
    }

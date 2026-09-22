"""Relevance Gate for StudyAI - Deterministic filtering of candidate concepts.

This module implements lightweight relevance filtering before LLM coverage classification.
It separates the "is this relevant?" decision from the "how well covered?" decision.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from apps.ai_classroom.gap_candidates import GapCandidate, STOP_WORDS


@dataclass
class RelevanceResult:
    """Result of relevance gate evaluation."""

    candidate: GapCandidate
    is_relevant: bool
    relevance_score: float
    signals: Dict[str, float]
    reason: str


def extract_note_topics(user_note: str, max_topics: int = 10) -> List[str]:
    """Extract key topics from user note for topic similarity comparison."""
    words = re.findall(r"\b[a-zA-Z][a-zA-Z-]*\b", user_note.lower())
    filtered = [w for w in words if w not in STOP_WORDS and len(w) > 3]
    freq = Counter(filtered)
    scored = []
    for word, count in freq.items():
        score = count
        if any(kw in word for kw in (
            'algorithm', 'complexity', 'tree', 'graph', 'force', 'derivative',
            'analysis', 'proof', 'theorem', 'rule', 'hash', 'queue', 'heap',
            'vector', 'matrix', 'rotation', 'insertion', 'traversal'
        )):
            score += 5
        scored.append((word, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [w for w, _ in scored[:max_topics]]


def compute_embedding_similarity(text1: str, text2: str, embeddings: Optional[List[float]] = None) -> float:
    """Compute semantic similarity between two texts.

    If embeddings are provided, use them. Otherwise return a placeholder.
    In practice, this would use the embedding provider.
    """
    words1 = set(w for w in re.findall(r"\b\w+\b", text1.lower()) if w not in STOP_WORDS and len(w) > 2)
    words2 = set(w for w in re.findall(r"\b\w+\b", text2.lower()) if w not in STOP_WORDS and len(w) > 2)
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def compute_lexical_overlap(candidate: str, user_note: str) -> float:
    """Compute lexical overlap between candidate concept and user note."""
    cand_words = set(w for w in re.findall(r"\b\w+\b", candidate.lower()) if w not in STOP_WORDS and len(w) > 2)
    note_words = set(w for w in re.findall(r"\b\w+\b", user_note.lower()) if w not in STOP_WORDS and len(w) > 2)
    if not cand_words:
        return 0.0
    overlap = cand_words & note_words
    return len(overlap) / len(cand_words)


def compute_topic_similarity(candidate: str, note_topics: List[str]) -> float:
    """Compute similarity between candidate and note topics."""
    cand_words = set(w for w in re.findall(r"\b\w+\b", candidate.lower()) if w not in STOP_WORDS and len(w) > 2)
    if not cand_words or not note_topics:
        return 0.0
    topic_words = set(note_topics)
    overlap = cand_words & topic_words
    return len(overlap) / len(cand_words)


def compute_reference_context_signal(candidate: GapCandidate, user_note: str) -> float:
    """Evaluate if candidate is meaningfully supported by reference evidence for this note."""
    evidence = candidate.evidence_span.lower()
    note_lower = user_note.lower()
    ev_words = set(w for w in re.findall(r"\b\w+\b", evidence) if w not in STOP_WORDS and len(w) > 3)
    note_words = set(w for w in re.findall(r"\b\w+\b", note_lower) if w not in STOP_WORDS and len(w) > 3)
    if not ev_words:
        return 0.0
    overlap = ev_words & note_words
    return len(overlap) / len(ev_words)


def evaluate_relevance_strategy_a(candidate: GapCandidate, user_note: str, note_topics: List[str]) -> RelevanceResult:
    """Strategy A: Pure embedding similarity (proxied by lexical overlap)."""
    score = compute_embedding_similarity(candidate.concept, user_note)
    is_relevant = score >= 0.15
    return RelevanceResult(
        candidate=candidate,
        is_relevant=is_relevant,
        relevance_score=score,
        signals={'embedding_sim': score},
        reason=f"Embedding similarity: {score:.3f}" + (" (RELEVANT)" if is_relevant else " (IRRELEVANT)")
    )


def evaluate_relevance_strategy_b(candidate: GapCandidate, user_note: str, note_topics: List[str]) -> RelevanceResult:
    """Strategy B: Embedding similarity + lexical overlap."""
    emb_score = compute_embedding_similarity(candidate.concept, user_note)
    lex_score = compute_lexical_overlap(candidate.concept, user_note)
    combined = 0.6 * emb_score + 0.4 * lex_score
    is_relevant = combined >= 0.18
    return RelevanceResult(
        candidate=candidate,
        is_relevant=is_relevant,
        relevance_score=combined,
        signals={'embedding_sim': emb_score, 'lexical_overlap': lex_score},
        reason=f"Combined (0.6*emb + 0.4*lex): {combined:.3f}" + (" (RELEVANT)" if is_relevant else " (IRRELEVANT)")
    )


def evaluate_relevance_strategy_c(candidate: GapCandidate, user_note: str, note_topics: List[str]) -> RelevanceResult:
    """Strategy C: Embedding similarity + note-topic similarity."""
    emb_score = compute_embedding_similarity(candidate.concept, user_note)
    topic_score = compute_topic_similarity(candidate.concept, note_topics)
    combined = 0.5 * emb_score + 0.5 * topic_score
    is_relevant = combined >= 0.15
    return RelevanceResult(
        candidate=candidate,
        is_relevant=is_relevant,
        relevance_score=combined,
        signals={'embedding_sim': emb_score, 'topic_sim': topic_score},
        reason=f"Combined (0.5*emb + 0.5*topic): {combined:.3f}" + (" (RELEVANT)" if is_relevant else " (IRRELEVANT)")
    )


def evaluate_relevance_strategy_d(candidate: GapCandidate, user_note: str, note_topics: List[str]) -> RelevanceResult:
    """Strategy D: All signals combined."""
    emb_score = compute_embedding_similarity(candidate.concept, user_note)
    lex_score = compute_lexical_overlap(candidate.concept, user_note)
    topic_score = compute_topic_similarity(candidate.concept, note_topics)
    ref_score = compute_reference_context_signal(candidate, user_note)
    combined = 0.3 * emb_score + 0.2 * lex_score + 0.3 * topic_score + 0.2 * ref_score
    is_relevant = combined >= 0.2
    return RelevanceResult(
        candidate=candidate,
        is_relevant=is_relevant,
        relevance_score=combined,
        signals={
            'embedding_sim': emb_score,
            'lexical_overlap': lex_score,
            'topic_sim': topic_score,
            'reference_context': ref_score,
        },
        reason=f"Combined (0.3*emb + 0.2*lex + 0.3*topic + 0.2*ref): {combined:.3f}" + (" (RELEVANT)" if is_relevant else " (IRRELEVANT)")
    )


STRATEGIES = {
    'A': evaluate_relevance_strategy_a,
    'B': evaluate_relevance_strategy_b,
    'C': evaluate_relevance_strategy_c,
    'D': evaluate_relevance_strategy_d,
}


def apply_relevance_gate(
    candidates: List[GapCandidate],
    user_note: str,
    strategy: str = "D",
) -> Dict[str, Any]:
    """Apply relevance gate to filter candidates.

    Returns:
        Dict with 'relevant' and 'irrelevant' candidate lists
    """
    note_topics = extract_note_topics(user_note)
    evaluator = STRATEGIES.get(strategy, evaluate_relevance_strategy_d)
    relevant = []
    irrelevant = []
    for candidate in candidates:
        result = evaluator(candidate, user_note, note_topics)
        if result.is_relevant:
            relevant.append(candidate)
        else:
            irrelevant.append(candidate)
    return {
        'relevant': relevant,
        'irrelevant': irrelevant,
        'details': [evaluator(c, user_note, note_topics) for c in candidates],
    }


def get_relevance_stats(results: Dict[str, List[GapCandidate]]) -> Dict[str, Any]:
    """Compute statistics from relevance gate results."""
    relevant = results['relevant']
    irrelevant = results['irrelevant']
    total = len(relevant) + len(irrelevant)
    return {
        'total_candidates': total,
        'relevant_count': len(relevant),
        'irrelevant_count': len(irrelevant),
        'reduction_rate': len(irrelevant) / total if total > 0 else 0,
        'relevant_concepts': [c.concept for c in relevant],
        'irrelevant_concepts': [c.concept for c in irrelevant],
    }

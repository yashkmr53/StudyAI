"""Topic Research Node for Topic-Based Note Enrichment (PR 2).

Decoupled internal reference retrieval per topic using retrieve_reference_context,
evaluating raw dense cosine similarity, sentence-level embedding ranking, and
building the EvidenceItem manifest.
"""
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

import numpy as np
from django.conf import settings

from ai.langgraph.state.topic_enrichment_state import (
    EvidenceItem,
    TopicResearchResult,
)
from apps.documents.models import Document
from apps.profiles.models import Profile
from apps.references.services import retrieve_reference_context
from apps.subjects.models import Subject
from providers.registry import get_embedding_provider

logger = logging.getLogger(__name__)

EVIDENCE_TOKEN_BUDGET = 1500  # Approx 6000 characters
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

# In-memory sentence embedding cache by md5 hash to avoid redundant embeds
_SENTENCE_EMBEDDING_CACHE: Dict[str, List[float]] = {}


def _split_into_sentences(text: str) -> List[str]:
    """Split chunk content into clean sentences."""
    raw = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    cleaned = []
    for s in raw:
        # Avoid tiny punctuation fragments
        if len(s) > 15:
            cleaned.append(s)
    return cleaned or ([text.strip()] if text.strip() else [])


def topic_research_node(
    topic: Dict[str, Any],
    document: Document,
    profile: Optional[Profile] = None,
    all_lines_by_lineage: Optional[Dict[str, Dict[str, Any]]] = None,
) -> TopicResearchResult:
    """Execute decoupled internal research for a single topic (§3.3a)."""
    topic_id = topic.get("topic_id", "t1")
    title = topic.get("title", "")
    description = topic.get("description", "")
    lineage_ids = topic.get("lineage_ids", [])

    # Extract first ~60 words of topic transcript lines
    topic_words = []
    if all_lines_by_lineage:
        for lid in lineage_ids:
            line_data = all_lines_by_lineage.get(lid)
            if line_data:
                topic_words.extend(line_data.get("text", "").split())
            if len(topic_words) >= 60:
                break
    line_summary = " ".join(topic_words[:60])

    query = f"{title}. {description}. {line_summary}".strip()

    # Subject scoping: topic subject -> document subject
    subj = None
    subj_name = topic.get("subject")
    if subj_name:
        subj = Subject.objects.filter(name__iexact=subj_name).first()
    if not subj and document.subject:
        subj = document.subject

    # Retrieve candidates with top_k=6
    candidates = retrieve_reference_context(
        query=query,
        profile=profile,
        subject=subj,
        top_k=6,
    )

    # Subject Fallback: If 0 candidates, retry once without subject filter
    if not candidates and subj is not None:
        logger.info("Topic %s returned 0 chunks with subject %s; retrying global references", topic_id, subj.name)
        candidates = retrieve_reference_context(
            query=query,
            profile=profile,
            subject=None,
            top_k=6,
        )

    min_dense = float(getattr(settings, "RELEVANCE_MIN_DENSE", 0.45))

    # Filter candidates by raw dense cosine similarity
    relevant_chunks = [c for c in candidates if float(c.get("dense_score", 0.0)) >= min_dense]

    if not relevant_chunks:
        logger.info("Topic %s has no chunks meeting dense threshold %.2f", topic_id, min_dense)
        return TopicResearchResult(
            topic_id=topic_id,
            evidence_status="none",
            evidence_items=[],
            query_used=query,
            no_reference_found=True,
        )

    # Status determination: sufficient (>= 2 chunks), partial (1 chunk)
    evidence_status = "sufficient" if len(relevant_chunks) >= 2 else "partial"

    # Embed query to score individual sentences
    embed_provider = get_embedding_provider()
    model_version = getattr(embed_provider, "model_version", "v1")
    try:
        q_raw = embed_provider.embed([query], model_version=model_version)
        q_vec = list(q_raw[0]) if isinstance(q_raw, list) and q_raw else None
    except Exception as exc:
        logger.warning("Failed to embed query for sentence ranking: %s", exc)
        q_vec = None

    q_arr = np.array(q_vec, dtype=float) if q_vec else None
    q_norm = np.linalg.norm(q_arr) if q_arr is not None else 1.0

    evidence_items: List[EvidenceItem] = []
    total_tokens_accumulated = 0

    for idx, chunk in enumerate(relevant_chunks, start=1):
        citation_id = f"C{idx}"
        chunk_text = chunk.get("text", "")
        sentences = _split_into_sentences(chunk_text)

        best_sentence = chunk_text[:280]
        best_score = -1.0

        if q_arr is not None and sentences:
            # Check sentence cache or batch embed
            uncached = []
            uncached_hashes = []
            for s in sentences:
                h = hashlib.md5(s.encode("utf-8")).hexdigest()
                if h not in _SENTENCE_EMBEDDING_CACHE:
                    uncached.append(s)
                    uncached_hashes.append(h)

            if uncached:
                try:
                    res = embed_provider.embed(uncached, model_version=model_version)
                    for h, emb in zip(uncached_hashes, res):
                        _SENTENCE_EMBEDDING_CACHE[h] = list(emb)
                except Exception as exc:
                    logger.warning("Batch sentence embed failed: %s", exc)

            for s in sentences:
                h = hashlib.md5(s.encode("utf-8")).hexdigest()
                emb = _SENTENCE_EMBEDDING_CACHE.get(h)
                if emb:
                    e_arr = np.array(emb, dtype=float)
                    denom = q_norm * (np.linalg.norm(e_arr) or 1.0)
                    sim = float(np.dot(q_arr, e_arr) / denom)
                    if sim > best_score:
                        best_score = sim
                        best_sentence = s

        # Estimate token length (~4 chars per token)
        chunk_token_est = len(chunk_text) // 4
        if total_tokens_accumulated + chunk_token_est > EVIDENCE_TOKEN_BUDGET and len(evidence_items) >= 1:
            # Exceeded budget but already have at least 1 grounded chunk; stop adding
            break

        total_tokens_accumulated += chunk_token_est

        evidence_items.append(
            EvidenceItem(
                citation_id=citation_id,
                chunk_id=chunk.get("chunk_id", ""),
                source_type="book",
                document_id=chunk.get("document_id", ""),
                source_title=chunk.get("source_title", "Reference Textbook"),
                chapter=chunk.get("chapter") or "",
                section=chunk.get("section") or "",
                page_start=int(chunk.get("page_start", chunk.get("page", 1))),
                page_end=int(chunk.get("page_end", chunk.get("page", 1))),
                snippet=chunk_text[:600],
                dense_score=float(chunk.get("dense_score", 0.0)),
                rrf_score=float(chunk.get("rrf_score", chunk.get("score", 0.0))),
                best_sentence=best_sentence,
            )
        )

    return TopicResearchResult(
        topic_id=topic_id,
        evidence_status=evidence_status,
        evidence_items=evidence_items,
        query_used=query,
        no_reference_found=False,
    )

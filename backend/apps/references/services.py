"""Shared Reference Retrieval Service (Phase 11 §7, §8, §11).

One unified, reusable reference retrieval service for note enrichment, Ask StudyAI,
and agent tools. Embeds queries with canonical Qwen/Qwen3-Embedding-0.6B, executes
hybrid pgvector dense + full-text search with Reciprocal Rank Fusion, strictly
enforces profile and subject authorization, and returns full provenance metadata.
"""
import json
import logging
from typing import Optional, Union

import numpy as np
from django.conf import settings
from django.db import connection
from django.db.models import Q

from apps.references.models import ReferenceChunk, ReferenceDocument
from providers.registry import embedding_model_version, get_embedding_provider

logger = logging.getLogger(__name__)


def _rrf_k() -> int:
    return int(getattr(settings, "RETRIEVAL_RRF_K", 60))


def _candidate_depth() -> int:
    return int(getattr(settings, "RETRIEVAL_CANDIDATES", 50))


def retrieve_reference_context(
    query: str,
    *,
    profile=None,
    subject=None,
    subject_id=None,
    top_k: int = 5,
    min_score: float = 0.0,
    reference_document_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Shared Reference Retrieval Service (§7).

    Args:
        query: Search query text.
        profile: Active Profile instance (for profile-scoped isolation).
                 If provided, searches Profile's references + Global references.
                 If None, searches Global references only.
        subject: Optional Subject instance for subject-level filtering.
        subject_id: Optional Subject UUID or string ID.
        top_k: Number of reference chunks to return.
        min_score: Minimum RRF score threshold.
        reference_document_ids: Optional list of specific ReferenceDocument IDs to scope to.

    Returns:
        List of dicts preserving exact provenance:
        [
            {
                "chunk_id": str,
                "document_id": str,
                "source_title": str,
                "source_type": str,
                "page": int,
                "page_start": int,
                "page_end": int,
                "chapter": str,
                "section": str,
                "text": str,
                "content": str,
                "snippet": str,
                "score": float,
                "subject_name": Optional[str],
            },
            ...
        ]
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return []

    # Resolve subject if subject_id provided
    if subject is None and subject_id is not None:
        from apps.subjects.models import Subject
        try:
            subject = Subject.objects.filter(pk=subject_id).first()
        except Exception:
            subject = None

    # Build Scope Filter (§8: Profile Isolation & Global Reference Visibility)
    # 1. Status must be READY
    base_filter = Q(reference_document__status=ReferenceDocument.Status.READY)

    # 2. Profile scoping:
    # If profile is given: allow chunks from that profile OR global chunks (profile is null).
    # If profile is None: allow only global chunks.
    if profile is not None:
        base_filter &= (Q(reference_document__profile=profile) | Q(reference_document__profile__isnull=True))
    else:
        base_filter &= Q(reference_document__profile__isnull=True)

    # 3. Subject scoping:
    # If subject is specified: include documents for that subject OR documents with no subject (general).
    if subject is not None:
        base_filter &= (Q(reference_document__subject=subject) | Q(reference_document__subject__isnull=True))

    # 4. Explicit reference document IDs if requested
    if reference_document_ids:
        base_filter &= Q(reference_document_id__in=reference_document_ids)

    base_qs = ReferenceChunk.objects.filter(base_filter)
    if not base_qs.exists():
        return []

    rrf_k = _rrf_k()
    depth = max(_candidate_depth(), top_k)

    # 1. Embed query using canonical Qwen/Qwen3-Embedding-0.6B
    provider = get_embedding_provider()
    model_version = embedding_model_version()
    try:
        raw_vec = provider.embed([clean_query], model_version=model_version)
        if isinstance(raw_vec, list) and len(raw_vec) > 0 and isinstance(raw_vec[0], (list, tuple, np.ndarray)):
            qvec = list(raw_vec[0])
        elif isinstance(raw_vec, (list, tuple, np.ndarray)):
            qvec = list(raw_vec)
        else:
            qvec = None
    except Exception as exc:
        logger.error("Failed to embed query in retrieve_reference_context: %s", exc)
        qvec = None

    dense_scores: dict[str, float] = {}

    # Dense leg: pgvector on PostgreSQL; in-memory cosine fallback for SQLite unit tests
    if qvec is not None:
        if connection.vendor == "postgresql":
            from pgvector.django import CosineDistance

            dense_qs = (
                base_qs.exclude(embedding__isnull=True)
                .annotate(distance=CosineDistance("embedding", qvec))
                .order_by("distance")[:depth]
            )
            for rank, chunk in enumerate(dense_qs, start=1):
                dense_scores[str(chunk.pk)] = 1.0 / (rrf_k + rank)
        else:
            # Portable in-memory cosine ranking for SQLite unit tests
            candidates = list(base_qs.exclude(embedding__isnull=True)[:depth * 2])
            if candidates:
                q_arr = np.array(qvec, dtype=float)
                q_norm = np.linalg.norm(q_arr) or 1.0
                scored = []
                for ch in candidates:
                    emb = ch.embedding
                    if isinstance(emb, str):
                        try:
                            emb = json.loads(emb)
                        except Exception:
                            continue
                    if not emb:
                        continue
                    e_arr = np.array(emb, dtype=float)
                    sim = float(np.dot(q_arr, e_arr) / (q_norm * (np.linalg.norm(e_arr) or 1.0)))
                    scored.append((sim, ch))
                scored.sort(key=lambda x: x[0], reverse=True)
                for rank, (_, ch) in enumerate(scored[:depth], start=1):
                    dense_scores[str(ch.pk)] = 1.0 / (rrf_k + rank)

    # 2. Keyword leg: PostgreSQL tsvector search / SQLite icontains fallback
    keyword_scores: dict[str, float] = {}
    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchRank

        sq = SearchQuery(clean_query, config="english")
        keyword_qs = (
            base_qs.filter(tsvector_content__isnull=False)
            .annotate(kw_rank=SearchRank("tsvector_content", sq))
            .filter(kw_rank__gt=0.0)
            .order_by("-kw_rank")[:depth]
        )
    else:
        tokens = [t for t in clean_query.lower().split() if len(t) > 3][:6] or [clean_query]
        token_q = Q()
        for t in tokens:
            token_q |= Q(text__icontains=t)
        keyword_qs = base_qs.filter(token_q)[:depth]

    for rank, chunk in enumerate(keyword_qs, start=1):
        keyword_scores[str(chunk.pk)] = 1.0 / (rrf_k + rank)

    # 3. Reciprocal Rank Fusion (§14)
    fused: dict[str, float] = {}
    for source_map in (dense_scores, keyword_scores):
        for cid, score in source_map.items():
            fused[cid] = fused.get(cid, 0.0) + score

    if not fused:
        return []

    # Sort descending by fused score
    ordered_ids = [
        cid
        for cid, score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        if score >= min_score
    ][:top_k]

    if not ordered_ids:
        return []

    # Retrieve full records with related document & subject
    chunks = ReferenceChunk.objects.filter(pk__in=ordered_ids).select_related(
        "reference_document", "reference_document__subject"
    )
    by_id = {str(c.pk): c for c in chunks}

    results: list[dict] = []
    for cid in ordered_ids:
        chunk = by_id.get(cid)
        if not chunk:
            continue
        doc = chunk.reference_document
        results.append({
            "chunk_id": str(chunk.pk),
            "document_id": str(doc.pk),
            "source_title": doc.title,
            "source_type": doc.source_type,
            "page": chunk.page_number,
            "page_start": chunk.page_number,
            "page_end": chunk.page_number,
            "chapter": chunk.chapter,
            "section": chunk.section,
            "text": chunk.text,
            "content": chunk.text,
            "snippet": chunk.text[:280],
            "score": round(fused[cid], 6),
            "subject_name": doc.subject.name if doc.subject else None,
        })

    return results

"""Hybrid retrieval (architecture §14).

Dense (pgvector cosine) + keyword (tsvector rank) → Reciprocal Rank
Fusion → top-k evidence. Scoping is enforced in SQL: profile ownership,
optional subject, non-stale chunks only, and reference-book chunks only
when their book is READY (§15).

The dense leg requires PostgreSQL; on SQLite (unit settings) retrieval
falls back to keyword-only so suites stay portable.
"""
from dataclasses import dataclass

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db import connection
from django.db.models import Q


@dataclass
class Evidence:
    chunk_id: str
    document_id: str
    source_type: str
    page_start: int
    page_end: int
    content_snippet: str
    dense_rank: float | None
    keyword_rank: float | None
    rrf_score: float

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_type": self.source_type,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "snippet": self.content_snippet,
            "scores": {
                "dense": self.dense_rank,
                "keyword": self.keyword_rank,
                "rrf": round(self.rrf_score, 6),
            },
        }


def _rrf_k() -> int:
    return int(getattr(settings, "RETRIEVAL_RRF_K", 60))


def _candidate_depth() -> int:
    return int(getattr(settings, "RETRIEVAL_CANDIDATES", 50))


def _base_queryset(user, subject=None):
    from apps.profiles.models import Profile
    from apps.retrieval.models import NoteChunk

    profile_ids = list(Profile.objects.filter(user=user).values_list("id", flat=True))
    qs = NoteChunk.objects.filter(stale=False).filter(
        Q(profile_id__in=profile_ids) | Q(profile_id__isnull=True)
    )
    if subject is not None:
        qs = qs.filter(subject=subject)
    return qs


class RetrievalService:
    @staticmethod
    def search(user, query: str, *, subject=None, top_k: int = 8, include_reference: bool = True):
        """Returns list[Evidence]. The dense leg runs on PostgreSQL only;
        SQLite unit runs degrade to keyword-only."""
        from apps.retrieval.models import NoteChunk
        from providers.registry import embedding_model_version, get_embedding_provider

        query = (query or "").strip()
        if not query:
            return []

        base = _base_queryset(user, subject)
        if not include_reference:
            base = base.exclude(source_type="reference")

        rrf_k = _rrf_k()
        depth = max(_candidate_depth(), top_k)

        # --- dense channel (pgvector cosine) ---
        dense_ids: dict[str, float] = {}
        if connection.vendor == "postgresql":
            from pgvector.django import CosineDistance

            provider = get_embedding_provider()
            model_version = embedding_model_version()
            qvec = provider.embed([query], model_version=model_version)[0]

            dense_qs = (
                base.exclude(embedding__isnull=True)
                .annotate(distance=CosineDistance("embedding", qvec))
                .order_by("distance")[:depth]
            )
            for rank, chunk in enumerate(dense_qs, start=1):
                dense_ids[str(chunk.pk)] = 1.0 / (rrf_k + rank)

        # --- keyword channel (tsvector rank) ---
        keyword_ids: dict[str, float] = {}
        if connection.vendor == "postgresql":
            sq = SearchQuery(query, config="english")
            keyword_qs = (
                base.filter(tsvector_content__isnull=False)
                .annotate(kw_rank=SearchRank("tsvector_content", sq))
                .filter(kw_rank__gt=0.0)
                .order_by("-kw_rank")[:depth]
            )
        else:
            # portable fallback for unit runs: OR-match significant tokens
            from django.db.models import Q

            tokens = [t for t in query.lower().split() if len(t) > 3][:6]
            if not tokens:
                tokens = [query]
            token_q = Q()
            for t in tokens:
                token_q |= Q(content__icontains=t)
            keyword_qs = base.filter(token_q)[:depth]
        for chunk in keyword_qs:
            keyword_ids[str(chunk.pk)] = 1.0 / (rrf_k + len(keyword_ids) + 1)

        # --- Reciprocal Rank Fusion ---
        fused: dict[str, float] = {}
        for source_map in (dense_ids, keyword_ids):
            for cid, score in source_map.items():
                fused[cid] = fused.get(cid, 0.0) + score
        ordered_ids = [cid for cid, _ in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]]
        if not ordered_ids:
            return []

        rows = NoteChunk.objects.filter(pk__in=ordered_ids).select_related("document", "reference_book")
        by_id = {str(r.pk): r for r in rows}

        evidence: list[Evidence] = []
        for cid in ordered_ids:
            r = by_id.get(cid)
            if r is None:
                continue
            # READY-gate reference chunks defensively at read time too (§15)
            if r.source_type == "reference" and getattr(r.reference_book, "status", None) != "ready":
                continue
            evidence.append(
                Evidence(
                    chunk_id=cid,
                    document_id=str(r.document_id),
                    source_type=r.source_type,
                    page_start=r.page_start,
                    page_end=r.page_end,
                    content_snippet=r.content[:280],
                    dense_rank=dense_ids.get(cid),
                    keyword_rank=keyword_ids.get(cid),
                    rrf_score=fused[cid],
                )
            )
        return evidence

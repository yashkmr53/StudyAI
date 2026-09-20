"""Retrieval evaluation harness for StudyAI enrichment pipeline."""

import json
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.retrieval.retrieval import RetrievalService
from apps.retrieval.models import NoteChunk
from apps.documents.models import Document, DocumentPage, DocumentPageRevision
from apps.profiles.models import Profile
from apps.subjects.models import Subject

User = get_user_model()


@dataclass
class RetrievalCaseResult:
    case_id: str
    query: str
    expected_chunk_ids: List[str]
    retrieved_chunk_ids: List[str]
    retrieved_scores: List[float]
    recall_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    expected_rank: Optional[int]
    failure_reason: Optional[str] = None


@dataclass
class RetrievalAggregateMetrics:
    total_cases: int
    measurable_cases: int
    recall_at_k: Optional[float]
    precision_at_k: Optional[float]
    mrr: Optional[float]
    cases_with_hits: int
    failed_cases: List[Dict[str, Any]]


class RetrievalEvaluator:
    def __init__(self, user, k: int = 10, reference_book_mapping: Dict[str, str] = None):
        self.user = user
        self.k = k
        self.service = RetrievalService()
        self.reference_book_mapping = reference_book_mapping or {}

    def _get_reference_book_id(self, case_id: str, subject) -> Optional[str]:
        """Look up reference book ID by finding the reference book for this case."""
        from apps.references.models import ReferenceBook
        try:
            # Find the reference book for this evaluation case (title contains case_id)
            ref_book = ReferenceBook.objects.filter(
                subject=subject,
                title__icontains=case_id,
                status=ReferenceBook.Status.READY
            ).first()
            return str(ref_book.pk) if ref_book else None
        except Exception:
            return None

    def _get_reference_book_id_from_chunks(self, expected_uuids: set) -> Optional[str]:
        """Extract reference_book_id from the expected chunks."""
        from apps.retrieval.models import NoteChunk
        if not expected_uuids:
            return None
        chunk = NoteChunk.objects.filter(pk__in=list(expected_uuids)).first()
        if chunk and chunk.reference_book_id:
            return str(chunk.reference_book_id)
        return None

    def evaluate_case(self, case: Dict[str, Any]) -> RetrievalCaseResult:
        query = case["input_note"]
        expected_stable_keys = set(case.get("expected_retrieval_targets", []))
        
        # Map expected stable keys to actual chunk UUIDs
        expected_uuids = set()
        for stable_key in expected_stable_keys:
            chunk = NoteChunk.objects.filter(content_hash=f"eval_ref_{stable_key}").first()
            if chunk:
                expected_uuids.add(str(chunk.pk))
        
        # Get reference book ID for this case from expected chunks
        case_id = case["case_id"]
        profile = self.user.profiles.first()
        subject = profile.subjects.first() if profile and profile.subjects.exists() else None
        ref_book_id = self._get_reference_book_id_from_chunks(expected_uuids)
        
        # Fallback to title-based lookup if needed
        if not ref_book_id:
            ref_book_id = self._get_reference_book_id(case_id, subject)

        start = time.monotonic()
        evidence = self.service.search(
            self.user, 
            query, 
            top_k=self.k, 
            include_reference=True,
            reference_book_ids=[ref_book_id] if ref_book_id else None,
            reference_only=True
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        retrieved_ids = [str(e.chunk_id) for e in evidence]
        retrieved_scores = [float(e.rrf_score) if e.rrf_score else 0.0 for e in evidence]

        # Find first expected chunk in results
        expected_rank = None
        for i, cid in enumerate(retrieved_ids):
            if cid in expected_uuids:
                expected_rank = i + 1
                break

        # Recall@K: at least one expected chunk in top-K
        recall = 1.0 if expected_rank else 0.0

        # Precision@K: fraction of retrieved that are expected
        if retrieved_ids:
            precision = len(expected_uuids & set(retrieved_ids)) / len(retrieved_ids)
        else:
            precision = 0.0

        # Reciprocal rank
        rr = 1.0 / expected_rank if expected_rank else 0.0

        failure_reason = None
        if expected_uuids and not expected_rank:
            failure_reason = self._analyze_failure(query, expected_uuids, retrieved_ids, retrieved_scores)

        return RetrievalCaseResult(
            case_id=case["case_id"],
            query=query[:200],
            expected_chunk_ids=list(expected_uuids),
            retrieved_chunk_ids=retrieved_ids,
            retrieved_scores=retrieved_scores,
            recall_at_k=recall,
            precision_at_k=precision,
            reciprocal_rank=rr,
            expected_rank=expected_rank,
            failure_reason=failure_reason,
        )

    def _analyze_failure(self, query: str, expected_ids: set, retrieved_ids: List[str], scores: List[float]) -> str:
        reasons = []

        # Check if expected chunks exist in DB (by UUID)
        missing_in_db = []
        for eid in expected_ids:
            if not NoteChunk.objects.filter(pk=eid).exists():
                missing_in_db.append(eid)
        if missing_in_db:
            reasons.append(f"Expected chunks not in DB: {missing_in_db}")

        # Check if retrieved from wrong profile
        if retrieved_ids:
            retrieved_chunks = NoteChunk.objects.filter(pk__in=retrieved_ids).select_related("profile")
            user_profile = self.user.profiles.first()
            if user_profile:
                wrong_profile = [str(c.pk) for c in retrieved_chunks if c.profile_id != user_profile.id]
                if wrong_profile:
                    reasons.append(f"Wrong profile chunks retrieved: {wrong_profile}")

        # Check stale chunks
        stale_retrieved = NoteChunk.objects.filter(pk__in=retrieved_ids, stale=True)
        if stale_retrieved.exists():
            reasons.append(f"Stale chunks retrieved: {[str(c.pk) for c in stale_retrieved]}")

        # Lexical mismatch
        if not reasons:
            reasons.append("Lexical/embedding mismatch - expected chunks not ranked high enough")

        return "; ".join(reasons)

    def evaluate_dataset(self, cases: List[Dict[str, Any]]) -> tuple[List[RetrievalCaseResult], RetrievalAggregateMetrics]:
        results = []
        measurable_cases = 0
        for case in cases:
            result = self.evaluate_case(case)
            results.append(result)
            if case.get("expected_retrieval_targets"):
                measurable_cases += 1

        # Only compute metrics for cases with ground truth
        measurable_results = [r for r in results if r.expected_chunk_ids]
        m = len(measurable_results)
        
        if m > 0:
            recall_at_k = round(sum(r.recall_at_k for r in measurable_results) / m, 4)
            precision_at_k = round(sum(r.precision_at_k for r in measurable_results) / m, 4)
            mrr = round(sum(r.reciprocal_rank for r in measurable_results) / m, 4)
        else:
            recall_at_k = precision_at_k = mrr = 0.0
            # Mark as unmeasured
            recall_at_k = precision_at_k = mrr = None

        n = len(results)
        aggregate = RetrievalAggregateMetrics(
            total_cases=n,
            measurable_cases=m,
            recall_at_k=recall_at_k,
            precision_at_k=precision_at_k,
            mrr=mrr,
            cases_with_hits=sum(1 for r in measurable_results if r.recall_at_k > 0),
            failed_cases=[
                {
                    "case_id": r.case_id,
                    "query": r.query,
                    "expected": r.expected_chunk_ids,
                    "retrieved": r.retrieved_chunk_ids[:5],
                    "expected_rank": r.expected_rank,
                    "reason": r.failure_reason,
                }
                for r in measurable_results if r.recall_at_k == 0
            ],
        )
        return results, aggregate


def load_golden_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path) as f:
        data = json.load(f)
    return data["cases"]


def run_retrieval_evaluation(dataset_path: str, user, k: int = 10, output_dir: str = None) -> Dict[str, Any]:
    with open(dataset_path) as f:
        full_dataset = json.load(f)
    cases = full_dataset["cases"]
    reference_book_mapping = full_dataset.get("reference_book_mapping", {})
    
    evaluator = RetrievalEvaluator(user, k=k, reference_book_mapping=reference_book_mapping)
    results, aggregate = evaluator.evaluate_dataset(cases)

    output = {
        "dataset_version": "v1",
        "k": k,
        "aggregate_metrics": asdict(aggregate),
        "case_results": [asdict(r) for r in results],
    }

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(Path(output_dir) / "retrieval_results.json", "w") as f:
            json.dump(output, f, indent=2, default=str)

    return output


class RetrievalEvaluationTest(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Computer Science", slug="cs")
        self.user = User.objects.create_user(username="eval_user", email="eval@test.com", password="testpass")
        self.profile = Profile.objects.create(user=self.user, display_name="Eval User", subject=self.subject)

    def _create_chunks(self, document: Document, contents: List[str], source_type: str = "note") -> List[NoteChunk]:
        chunks = []
        for i, content in enumerate(contents):
            chunk = NoteChunk.objects.create(
                document=document,
                profile=self.profile,
                subject=self.subject,
                revision_id=document.pages.first().current_revision_id if document.pages.exists() else "00000000-0000-0000-0000-000000000000",
                revision_ids=[],
                page_start=1,
                page_end=1,
                chunk_index=i,
                content=content,
                content_hash=f"hash_{i}",
                source_type=source_type,
                stale=False,
            )
            chunks.append(chunk)
        return chunks

    def test_retrieval_baseline(self):
        # This test requires the golden dataset to be populated with actual chunk IDs
        # Run after dataset is seeded with real chunks
        pass
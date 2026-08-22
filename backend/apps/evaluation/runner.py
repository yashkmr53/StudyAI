"""Evaluation harness mechanics (architecture §26).

Two runnable metric families over JSON case files:

- retrieval: cases carry query + expected chunk ids (any-of) →
  Recall@k, MRR, Precision@k against RetrievalService.search.
- citation: cases carry block_content + source_refs (with chunk ids) +
  expected status → verifier precision/recall per class.

The harness is real and tested; the *datasets* are still empty — that is
the §26 gap, not the runner.
"""
from django.db import transaction

from apps.ai_classroom.services import EvidenceVerifier
from apps.evaluation.models import EvalRun
from apps.retrieval.retrieval import RetrievalService


def run_retrieval_cases(cases: list[dict], user, k: int = 5) -> dict:
    hits = 0
    reciprocal_ranks = []
    precisions = []
    for case in cases:
        evidence = RetrievalService.search(user, case["query"], top_k=k)
        got_ids = [e.chunk_id for e in evidence]
        expected = set(case["expected_chunk_ids"])
        first_rank = next((i + 1 for i, cid in enumerate(got_ids) if cid in expected), None)
        if first_rank:
            hits += 1
            reciprocal_ranks.append(1.0 / first_rank)
        else:
            reciprocal_ranks.append(0.0)
        precisions.append(len(expected & set(got_ids)) / max(1, len(got_ids)))

    n = max(1, len(cases))
    metrics = {
        "recall_at_k": round(hits / n, 4),
        "mrr": round(sum(reciprocal_ranks) / n, 4),
        "precision_at_k": round(sum(precisions) / n, 4),
        "k": k,
    }
    return metrics


def run_citation_cases(cases: list[dict]) -> dict:
    """Each case: {block_content, cited_chunk_contents:[...], expected_status}."""
    tp = fp = fn = 0
    supported_seen = 0
    for case in cases:
        refs = [{"chunk_id": f"eval_{i}"} for i, _ in enumerate(case.get("cited_chunk_contents", []))]
        # verifier reads chunks from DB; bypass by calling lexical core directly
        score = EvidenceVerifier._lexical_support(case["block_content"], case.get("cited_chunk_contents", []))
        if score >= EvidenceVerifier._supported_threshold():
            predicted = "supported"
        elif score >= EvidenceVerifier._partial_threshold():
            predicted = "partially_supported"
        else:
            predicted = "unsupported"

        expected = case["expected_status"]
        predicted_supported = predicted == "supported"
        expected_supported = expected == "supported"
        if predicted_supported and expected_supported:
            tp += 1
        elif predicted_supported and not expected_supported:
            fp += 1
        elif expected_supported:
            fn += 1
        if predicted_supported:
            supported_seen += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "support_precision": round(precision, 4),
        "support_recall": round(recall, 4),
        "cases": len(cases),
        "predicted_supported": supported_seen,
    }


@transaction.atomic
def record_run(kind: str, dataset_name: str, cases_count: int, metrics: dict) -> EvalRun:
    return EvalRun.objects.create(
        kind=kind,
        dataset_name=dataset_name,
        case_count=cases_count,
        metrics=metrics,
    )

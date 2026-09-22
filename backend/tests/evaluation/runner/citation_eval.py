"""Citation evaluation harness for StudyAI enrichment pipeline."""

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.ai_classroom.services import EvidenceVerifier
from apps.retrieval.models import NoteChunk
from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock, CitationBlock
from apps.references.models import ReferenceBook

User = get_user_model()


class ProvenanceCategory:
    USER_SOURCE = "user_source"
    REFERENCE_SOURCE = "reference_source"
    WRONG_DOCUMENT = "wrong_document"
    WRONG_REVISION = "wrong_revision"
    MISSING_SOURCE = "missing_source"


@dataclass
class CitationCaseResult:
    case_id: str
    block_index: int
    block_content: str
    block_type: str
    source_refs: List[Dict[str, Any]]
    verification_status: str
    verification_score: Optional[float]
    citation_validity: bool
    citation_provenance: str  # Now a category string
    citation_support: bool
    failure_reasons: List[str]


@dataclass
class CitationAggregateMetrics:
    total_citations: int
    validity_rate: float
    provenance_user_source_rate: float
    provenance_reference_source_rate: float
    provenance_wrong_document_rate: float
    provenance_wrong_revision_rate: float
    provenance_missing_source_rate: float
    support_rate: float
    partially_supported_rate: float
    unsupported_rate: float
    not_verified_rate: float
    unsupported_claims: List[Dict[str, Any]]
    invalid_citations: List[Dict[str, Any]]
    metric_status: Dict[str, str] = None  # Per-metric status


class CitationEvaluator:
    def __init__(self):
        self.verifier = EvidenceVerifier()

    def evaluate_enriched_note(self, enriched_note: EnrichedNote) -> tuple[List[CitationCaseResult], CitationAggregateMetrics]:
        blocks = EnrichedNoteBlock.objects.filter(enriched_note=enriched_note).prefetch_related("citation")
        results = []

        for block in blocks:
            citation = getattr(block, "citation", None)
            if not citation:
                results.append(CitationCaseResult(
                    case_id=str(enriched_note.document_id),
                    block_index=block.block_index,
                    block_content=block.content,
                    block_type=block.block_type,
                    source_refs=[],
                    verification_status="not_verified",
                    verification_score=None,
                    citation_validity=False,
                    citation_provenance=ProvenanceCategory.MISSING_SOURCE,
                    citation_support=False,
                    failure_reasons=["No citation block found"],
                ))
                continue

            refs = citation.source_refs or []
            validity, provenance, support, reasons = self._evaluate_citation(block, citation)

            results.append(CitationCaseResult(
                case_id=str(enriched_note.document_id),
                block_index=block.block_index,
                block_content=block.content,
                block_type=block.block_type,
                source_refs=refs,
                verification_status=citation.verification_status,
                verification_score=citation.verification_score,
                citation_validity=validity,
                citation_provenance=provenance,
                citation_support=support,
                failure_reasons=reasons,
            ))

        aggregate = self._compute_aggregate(results)
        return results, aggregate

    def _classify_provenance(self, block: EnrichedNoteBlock, chunks: List[NoteChunk]) -> str:
        """Classify the provenance of cited chunks."""
        doc_id = str(block.enriched_note.document_id)
        
        for chunk in chunks:
            # Check if chunk exists
            if not chunk:
                return ProvenanceCategory.MISSING_SOURCE
            
            # Check revision staleness
            if chunk.stale:
                return ProvenanceCategory.WRONG_REVISION
            
            # Check document
            if str(chunk.document_id) == doc_id:
                return ProvenanceCategory.USER_SOURCE
            
            # Check if it's a reference book chunk
            if chunk.source_type == "reference" and chunk.reference_book_id:
                return ProvenanceCategory.REFERENCE_SOURCE
            
            # Otherwise it's an unrelated document
            return ProvenanceCategory.WRONG_DOCUMENT
        
        return ProvenanceCategory.MISSING_SOURCE

    def _is_template_block(self, block: EnrichedNoteBlock) -> bool:
        """Check if a block is a template/meta block that shouldn't be evaluated for support."""
        content = block.content.lower().strip()
        template_patterns = [
            "structured overview generated from",
            "overview generated from",
            "summary generated from",
        ]
        return any(pattern in content for pattern in template_patterns)

    def _is_template_block_by_content(self, content: str) -> bool:
        """Check if content is a template/meta block."""
        content_lower = content.lower().strip()
        template_patterns = [
            "structured overview generated from",
            "overview generated from",
            "summary generated from",
        ]
        return any(pattern in content_lower for pattern in template_patterns)

    def _evaluate_citation(self, block: EnrichedNoteBlock, citation: CitationBlock) -> tuple[bool, str, bool, List[str]]:
        refs = citation.source_refs or []
        reasons = []

        # 1. Validity: referenced chunks exist
        chunk_ids = [ref.get("chunk_id") for ref in refs if ref.get("chunk_id")]
        existing_chunks = NoteChunk.objects.filter(pk__in=chunk_ids)
        existing_chunk_ids = set(str(c.pk) for c in existing_chunks)
        missing_chunks = set(chunk_ids) - existing_chunk_ids
        validity = len(missing_chunks) == 0
        if not validity:
            reasons.append(f"Missing chunks: {missing_chunks}")

        # 2. Provenance: classify each chunk
        provenance = ProvenanceCategory.MISSING_SOURCE
        if validity:
            chunks = list(existing_chunks)
            provenance = self._classify_provenance(block, chunks)
            if provenance in (ProvenanceCategory.WRONG_DOCUMENT, ProvenanceCategory.WRONG_REVISION, ProvenanceCategory.MISSING_SOURCE):
                reasons.append(f"Provenance issue: {provenance}")

        # 3. Support: verifier score indicates support
        # Exclude template blocks from support evaluation
        is_template = self._is_template_block(block)
        if is_template:
            support = True  # Template blocks don't need claim support
            # Don't add low support reasons for templates
        else:
            support = citation.verification_status == CitationBlock.VerificationStatus.SUPPORTED
            if not support and citation.verification_status != CitationBlock.VerificationStatus.NOT_VERIFIED:
                reasons.append(f"Low support: status={citation.verification_status}, score={citation.verification_score}")

        # 4. Completeness: block has citations if it makes claims
        # (Heuristic: non-gap_fill blocks with content should have refs)
        if not is_template and block.block_type != "gap_fill" and block.content and not refs:
            reasons.append("Block has content but no citations")

        return validity, provenance, support, reasons

    def _compute_aggregate(self, results: List[CitationCaseResult]) -> CitationAggregateMetrics:
        n = len(results)
        if n == 0:
            return CitationAggregateMetrics(
                total_citations=0,
                validity_rate=0.0,
                provenance_user_source_rate=0.0,
                provenance_reference_source_rate=0.0,
                provenance_wrong_document_rate=0.0,
                provenance_wrong_revision_rate=0.0,
                provenance_missing_source_rate=0.0,
                support_rate=0.0,
                partially_supported_rate=0.0,
                unsupported_rate=0.0,
                not_verified_rate=0.0,
                unsupported_claims=[],
                invalid_citations=[],
            )

        validity_rate = sum(1 for r in results if r.citation_validity) / n
        
        provenance_counts = {}
        for r in results:
            provenance_counts[r.citation_provenance] = provenance_counts.get(r.citation_provenance, 0) + 1
        
        provenance_user_source_rate = provenance_counts.get(ProvenanceCategory.USER_SOURCE, 0) / n
        provenance_reference_source_rate = provenance_counts.get(ProvenanceCategory.REFERENCE_SOURCE, 0) / n
        provenance_wrong_document_rate = provenance_counts.get(ProvenanceCategory.WRONG_DOCUMENT, 0) / n
        provenance_wrong_revision_rate = provenance_counts.get(ProvenanceCategory.WRONG_REVISION, 0) / n
        provenance_missing_source_rate = provenance_counts.get(ProvenanceCategory.MISSING_SOURCE, 0) / n

        # Support rate: exclude template blocks from denominator
        non_template_results = [r for r in results if not self._is_template_block_by_content(r.block_content)]
        if non_template_results:
            support_rate = sum(1 for r in non_template_results if r.citation_support) / len(non_template_results)
        else:
            support_rate = 0.0

        status_counts = {}
        for r in results:
            status_counts[r.verification_status] = status_counts.get(r.verification_status, 0) + 1

        return CitationAggregateMetrics(
            total_citations=n,
            validity_rate=round(validity_rate, 4),
            provenance_user_source_rate=round(provenance_user_source_rate, 4),
            provenance_reference_source_rate=round(provenance_reference_source_rate, 4),
            provenance_wrong_document_rate=round(provenance_wrong_document_rate, 4),
            provenance_wrong_revision_rate=round(provenance_wrong_revision_rate, 4),
            provenance_missing_source_rate=round(provenance_missing_source_rate, 4),
            support_rate=round(support_rate, 4),
            partially_supported_rate=round(status_counts.get("partially_supported", 0) / n, 4),
            unsupported_rate=round(status_counts.get("unsupported", 0) / n, 4),
            not_verified_rate=round(status_counts.get("not_verified", 0) / n, 4),
            unsupported_claims=[
                {"case_id": r.case_id, "block_index": r.block_index, "content": r.block_content[:100], "score": r.verification_score}
                for r in results if r.verification_status == "unsupported"
            ],
            invalid_citations=[
                {"case_id": r.case_id, "block_index": r.block_index, "reasons": r.failure_reasons}
                for r in results if not r.citation_validity or r.citation_provenance in (ProvenanceCategory.WRONG_DOCUMENT, ProvenanceCategory.WRONG_REVISION, ProvenanceCategory.MISSING_SOURCE)
            ],
            metric_status={
                "validity": "VALID",
                "provenance": "VALID" if provenance_wrong_document_rate == 0 and provenance_missing_source_rate == 0 else "QUESTIONABLE",
                "support": "QUESTIONABLE" if support_rate < 0.7 else "VALID",
            },
        )

    def evaluate_verifier_against_golden(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluate the verifier against hand-labeled golden cases."""
        tp = fp = fn = tn = 0
        results = []

        for case in cases:
            block_content = case["block_content"]
            cited_contents = case["cited_chunk_contents"]
            expected = case["expected_status"]

            score = self.verifier._lexical_support(block_content, cited_contents)
            if score >= self.verifier._supported_threshold():
                predicted = "supported"
            elif score >= self.verifier._partial_threshold():
                predicted = "partially_supported"
            else:
                predicted = "unsupported"

            expected_supported = expected == "supported"
            predicted_supported = predicted == "supported"

            if predicted_supported and expected_supported:
                tp += 1
            elif predicted_supported and not expected_supported:
                fp += 1
            elif not predicted_supported and expected_supported:
                fn += 1
            else:
                tn += 1

            results.append({
                "case_id": case.get("case_id", ""),
                "predicted": predicted,
                "expected": expected,
                "score": round(score, 4),
                "correct": predicted == expected,
            })

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) else 0.0

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "accuracy": round(accuracy, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "thresholds": {
                "supported": self.verifier._supported_threshold(),
                "partial": self.verifier._partial_threshold(),
            },
            "case_results": results,
        }


def run_citation_evaluation(enriched_note_ids: List[str], output_dir: str = None) -> Dict[str, Any]:
    all_results = []
    all_aggregates = []

    for note_id in enriched_note_ids:
        note = EnrichedNote.objects.get(pk=note_id)
        evaluator = CitationEvaluator()
        results, aggregate = evaluator.evaluate_enriched_note(note)
        all_results.extend(results)
        all_aggregates.append(aggregate)

    # Combine aggregates
    total_citations = sum(a.total_citations for a in all_aggregates)
    combined = CitationAggregateMetrics(
        total_citations=total_citations,
        validity_rate=round(sum(a.validity_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        provenance_user_source_rate=round(sum(a.provenance_user_source_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        provenance_reference_source_rate=round(sum(a.provenance_reference_source_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        provenance_wrong_document_rate=round(sum(a.provenance_wrong_document_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        provenance_wrong_revision_rate=round(sum(a.provenance_wrong_revision_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        provenance_missing_source_rate=round(sum(a.provenance_missing_source_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        support_rate=round(sum(a.support_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        partially_supported_rate=round(sum(a.partially_supported_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        unsupported_rate=round(sum(a.unsupported_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        not_verified_rate=round(sum(a.not_verified_rate * a.total_citations for a in all_aggregates) / max(1, total_citations), 4),
        unsupported_claims=[c for a in all_aggregates for c in a.unsupported_claims],
        invalid_citations=[c for a in all_aggregates for c in a.invalid_citations],
        metric_status=all_aggregates[0].metric_status if all_aggregates else {},
    )

    output = {
        "aggregate_metrics": asdict(combined),
        "case_results": [asdict(r) for r in all_results],
    }

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(Path(output_dir) / "citation_results.json", "w") as f:
            json.dump(output, f, indent=2, default=str)

    return output
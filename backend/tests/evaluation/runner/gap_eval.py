"""Gap detection and gap filling evaluation harness for StudyAI enrichment pipeline."""

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock
from apps.retrieval.models import NoteChunk

User = get_user_model()


@dataclass
class GapDetectionResult:
    case_id: str
    expected_gaps: List[Dict[str, str]]
    detected_gaps: List[Dict[str, Any]]
    true_positives: List[Dict[str, Any]]
    false_positives: List[Dict[str, Any]]
    false_negatives: List[Dict[str, Any]]
    precision: float
    recall: float
    f1: float


@dataclass
class GapFillResult:
    case_id: str
    gap_topic: str
    reference_chunk_id: str
    fill_block: Optional[Dict[str, Any]]
    quality: str  # correct_strong, correct_shallow, partially_correct, incorrect, missing
    addresses_gap: bool
    relevant_to_note: bool
    no_contradiction: bool
    grounded: bool
    appropriate_attribution: bool
    notes: str


@dataclass
class GapAggregateMetrics:
    total_expected_gaps: int
    total_detected_gaps: int
    detection_precision: float
    detection_recall: float
    detection_f1: float
    fill_correct_strong: int
    fill_correct_shallow: int
    fill_partially_correct: int
    fill_incorrect: int
    fill_missing: int
    fill_rate: float
    metric_status: str = "VALID"  # VALID, QUESTIONABLE, UNVALIDATED, UNMEASURED, INVALID


class GapEvaluator:
    def __init__(self, reference_book_mapping: Dict[str, Dict[str, str]] = None):
        self.reference_book_mapping = reference_book_mapping or {}
        # Build reverse lookup: content -> stable_key
        self._content_to_stable_key = {}
        for case_id, mapping in self.reference_book_mapping.items():
            for stable_key, content in mapping.items():
                # Use first 100 chars as key for matching
                self._content_to_stable_key[content[:100].lower()] = stable_key

    def _normalize_gap_topic(self, topic: str) -> str:
        return topic.lower().strip()

    def _topic_similarity(self, topic1: str, topic2: str) -> float:
        """Compute Jaccard similarity between topic word sets."""
        words1 = set(self._normalize_gap_topic(topic1).split())
        words2 = set(self._normalize_gap_topic(topic2).split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def _resolve_stable_key(self, chunk_id: str) -> Optional[str]:
        """Try to resolve a runtime chunk UUID to a stable reference key."""
        if not chunk_id:
            return None
        try:
            chunk = NoteChunk.objects.get(pk=chunk_id)
            # Check if content_hash contains stable key pattern
            if chunk.content_hash.startswith("eval_ref_"):
                return chunk.content_hash.replace("eval_ref_", "")
            # Try to match content to mapping
            content_prefix = chunk.content[:100].lower()
            return self._content_to_stable_key.get(content_prefix)
        except NoteChunk.DoesNotExist:
            return None

    def _gap_matches(self, expected: Dict[str, str], detected: Dict[str, Any]) -> bool:
        exp_topic = self._normalize_gap_topic(expected["topic"])
        det_topic = self._normalize_gap_topic(detected.get("topic", ""))
        
        # Semantic topic matching using Jaccard similarity
        topic_sim = self._topic_similarity(exp_topic, det_topic)
        topic_match = topic_sim >= 0.3  # Threshold for semantic match
        
        # Reference key matching: try to resolve both to stable keys
        exp_ref = expected.get("reference_chunk_id", "")
        det_ref = detected.get("reference_chunk_id", "")
        
        exp_stable = exp_ref  # Expected already uses stable keys
        det_stable = self._resolve_stable_key(det_ref)
        
        ref_match = exp_stable == det_stable if exp_stable and det_stable else True
        
        return topic_match and ref_match

    def evaluate_gap_detection(self, case: Dict[str, Any], enriched_note: EnrichedNote) -> GapDetectionResult:
        expected_gaps = case.get("expected_gaps", [])

        fill_blocks = EnrichedNoteBlock.objects.filter(
            enriched_note=enriched_note,
            block_type="gap_fill"
        )

        detected_gaps = []
        for block in fill_blocks:
            source_ids = block.source_chunk_ids or []
            if source_ids:
                detected_gaps.append({
                    "topic": block.title or "unknown",
                    "reference_chunk_id": source_ids[0],
                    "block_index": block.block_index,
                })

        # Match expected to detected
        matched_expected = set()
        matched_detected = set()
        true_positives = []
        false_positives = []
        false_negatives = []

        for i, exp in enumerate(expected_gaps):
            match_found = False
            for j, det in enumerate(detected_gaps):
                if j in matched_detected:
                    continue
                if self._gap_matches(exp, det):
                    matched_expected.add(i)
                    matched_detected.add(j)
                    true_positives.append({"expected": exp, "detected": det})
                    match_found = True
                    break
            if not match_found:
                false_negatives.append(exp)

        for j, det in enumerate(detected_gaps):
            if j not in matched_detected:
                false_positives.append(det)

        tp = len(true_positives)
        fp = len(false_positives)
        fn = len(false_negatives)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return GapDetectionResult(
            case_id=case["case_id"],
            expected_gaps=expected_gaps,
            detected_gaps=detected_gaps,
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
        )

    def evaluate_gap_filling(self, case: Dict[str, Any], enriched_note: EnrichedNote) -> List[GapFillResult]:
        expected_gaps = case.get("expected_gaps", [])
        fill_blocks = EnrichedNoteBlock.objects.filter(
            enriched_note=enriched_note,
            block_type="gap_fill"
        )

        results = []
        for exp_gap in expected_gaps:
            # Find corresponding fill block
            fill_block = None
            for block in fill_blocks:
                if block.source_chunk_ids and block.source_chunk_ids[0] == exp_gap.get("reference_chunk_id"):
                    fill_block = {
                        "block_index": block.block_index,
                        "title": block.title,
                        "content": block.content,
                        "source_chunk_ids": block.source_chunk_ids,
                        "generation_method": block.generation_method,
                    }
                    break

            if not fill_block:
                results.append(GapFillResult(
                    case_id=case["case_id"],
                    gap_topic=exp_gap["topic"],
                    reference_chunk_id=exp_gap.get("reference_chunk_id", ""),
                    fill_block=None,
                    quality="missing",
                    addresses_gap=False,
                    relevant_to_note=False,
                    no_contradiction=True,
                    grounded=False,
                    appropriate_attribution=False,
                    notes="No gap_fill block found for this expected gap",
                ))
                continue

            # Evaluate quality (manual rubric - for baseline we use heuristics)
            quality, addresses, relevant, no_contradiction, grounded, attribution, notes = self._evaluate_fill_quality(
                exp_gap, fill_block, enriched_note
            )

            results.append(GapFillResult(
                case_id=case["case_id"],
                gap_topic=exp_gap["topic"],
                reference_chunk_id=exp_gap.get("reference_chunk_id", ""),
                fill_block=fill_block,
                quality=quality,
                addresses_gap=addresses,
                relevant_to_note=relevant,
                no_contradiction=no_contradiction,
                grounded=grounded,
                appropriate_attribution=attribution,
                notes=notes,
            ))

        return results

    def _evaluate_fill_quality(self, expected_gap: Dict[str, str], fill_block: Dict[str, Any], enriched_note: EnrichedNote) -> tuple:
        content = fill_block.get("content", "").lower()
        topic = expected_gap.get("topic", "").lower()
        ref_chunk_id = expected_gap.get("reference_chunk_id", "")

        # Check if fill block cites the expected reference chunk
        attribution = ref_chunk_id in (fill_block.get("source_chunk_ids") or [])

        # Simple keyword overlap for addressing gap
        topic_keywords = set(topic.split())
        content_words = set(content.split())
        overlap = topic_keywords & content_words
        addresses = len(overlap) > 0 or topic in content

        # Relevance to note: check if fill content relates to document
        doc_chunks = NoteChunk.objects.filter(document=enriched_note.document, stale=False)
        doc_text = " ".join(c.content.lower() for c in doc_chunks)
        relevant = any(w in doc_text for w in content_words if len(w) > 4)

        # No contradiction: simple check
        no_contradiction = True  # Would need more sophisticated check

        # Grounded: check if cited chunk supports the claim
        grounded = attribution  # Proxy: if it cites the right chunk, assume grounded

        # Determine quality
        if not addresses:
            quality = "incorrect"
            notes = "Fill content does not address the gap topic"
        elif not attribution:
            quality = "partially_correct"
            notes = "Addresses gap but doesn't cite expected reference chunk"
        elif len(content) < 50:
            quality = "correct_shallow"
            notes = "Addresses gap with minimal detail"
        else:
            quality = "correct_strong"
            notes = "Addresses gap well with appropriate detail"

        return quality, addresses, relevant, no_contradiction, grounded, attribution, notes

    def evaluate_case(self, case: Dict[str, Any], enriched_note: EnrichedNote) -> tuple[GapDetectionResult, List[GapFillResult]]:
        detection = self.evaluate_gap_detection(case, enriched_note)
        filling = self.evaluate_gap_filling(case, enriched_note)
        return detection, filling


def run_gap_evaluation(cases: List[Dict[str, Any]], enriched_note_ids: List[str], dataset_path: str = None, output_dir: str = None) -> Dict[str, Any]:
    from apps.ai_classroom.models import EnrichedNote
    
    # Load reference_book_mapping from dataset
    reference_book_mapping = {}
    if dataset_path:
        with open(dataset_path) as f:
            full_dataset = json.load(f)
        reference_book_mapping = full_dataset.get("reference_book_mapping", {})

    evaluator = GapEvaluator(reference_book_mapping)
    all_detections = []
    all_fillings = []

    for case, note_id in zip(cases, enriched_note_ids):
        note = EnrichedNote.objects.get(pk=note_id)
        detection, filling = evaluator.evaluate_case(case, note)
        all_detections.append(detection)
        all_fillings.extend(filling)

    # Aggregate detection metrics
    total_expected = sum(len(d.expected_gaps) for d in all_detections)
    total_detected = sum(len(d.detected_gaps) for d in all_detections)
    total_tp = sum(len(d.true_positives) for d in all_detections)
    total_fp = sum(len(d.false_positives) for d in all_detections)
    total_fn = sum(len(d.false_negatives) for d in all_detections)

    detection_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    detection_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    detection_f1 = 2 * detection_precision * detection_recall / (detection_precision + detection_recall) if (detection_precision + detection_recall) > 0 else 0.0

    # Aggregate fill metrics
    fill_counts = {"correct_strong": 0, "correct_shallow": 0, "partially_correct": 0, "incorrect": 0, "missing": 0}
    for f in all_fillings:
        fill_counts[f.quality] = fill_counts.get(f.quality, 0) + 1

    fill_rate = (fill_counts["correct_strong"] + fill_counts["correct_shallow"] + fill_counts["partially_correct"]) / max(1, len(all_fillings))

    # Determine metric status based on ground truth availability and matching quality
    if total_expected == 0:
        metric_status = "UNMEASURED"
    elif detection_f1 < 0.3:
        metric_status = "QUESTIONABLE"  # Low F1 suggests matching issues
    else:
        metric_status = "VALID"

    aggregate = GapAggregateMetrics(
        total_expected_gaps=total_expected,
        total_detected_gaps=total_detected,
        detection_precision=round(detection_precision, 4),
        detection_recall=round(detection_recall, 4),
        detection_f1=round(detection_f1, 4),
        fill_correct_strong=fill_counts["correct_strong"],
        fill_correct_shallow=fill_counts["correct_shallow"],
        fill_partially_correct=fill_counts["partially_correct"],
        fill_incorrect=fill_counts["incorrect"],
        fill_missing=fill_counts["missing"],
        fill_rate=round(fill_rate, 4),
        metric_status=metric_status,
    )

    output = {
        "aggregate_metrics": asdict(aggregate),
        "detection_results": [asdict(d) for d in all_detections],
        "fill_results": [asdict(f) for f in all_fillings],
    }

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(Path(output_dir) / "gap_results.json", "w") as f:
            json.dump(output, f, indent=2, default=str)

    return output
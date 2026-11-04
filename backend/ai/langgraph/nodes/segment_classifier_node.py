"""Segment Classifier Node for Topic-Based Note Enrichment (PR 2).

Processes approved transcript lines in 60-line windows with local labels L1..Ln,
classifies ranges into segment types, merges boundaries, normalizes gaps/overlaps,
tracks excluded segments, and maps subject guesses.
"""
import logging
from typing import Any, Dict, List, Optional

from django.conf import settings

from ai.langgraph.state.topic_enrichment_state import (
    ExcludedSegment,
    TopicEnrichmentState,
    TranscriptSegment,
    TranscriptSegmentationResult,
)
from apps.documents.models import Document
from apps.subjects.models import Subject
from providers.base import Prompt
from providers.registry import get_llm_provider

logger = logging.getLogger(__name__)

WINDOW_SIZE = 60


def _escape_xml_delimiters(text: str) -> str:
    """Escape XML delimiters to prevent prompt injection."""
    return (
        text.replace("</student_transcript>", "&lt;/student_transcript&gt;")
        .replace("<student_transcript>", "&lt;student_transcript&gt;")
        .replace("</reference_evidence>", "&lt;/reference_evidence&gt;")
        .replace("<reference_evidence>", "&lt;reference_evidence&gt;")
    )


def _resolve_subject(name_or_slug: Optional[str]) -> Optional[Subject]:
    """Map free-text subject guess against existing Subject objects."""
    if not name_or_slug or not str(name_or_slug).strip():
        return None
    query = str(name_or_slug).strip().lower()
    return Subject.objects.filter(name__iexact=query).first()


def segment_classifier_node(state: TopicEnrichmentState) -> Dict[str, Any]:
    """Execute windowed transcript classification (§3.1)."""
    approved_lines = state.get("approved_lines", [])
    if not approved_lines:
        return {
            "segments": [],
            "excluded_segments": [],
            "outcome": "no_study_content",
            "error_code": "NO_STUDY_CONTENT",
        }

    document_id = state.get("document_id")
    force_include_line_ids = set(state.get("force_include_line_ids") or [])
    min_confidence = float(getattr(settings, "SEGMENT_MIN_CONFIDENCE", 0.70))

    llm = get_llm_provider()
    total_lines = len(approved_lines)
    all_raw_segments: List[Dict[str, Any]] = []

    # Process in windows of 60 lines
    for win_start in range(0, total_lines, WINDOW_SIZE):
        win_end = min(win_start + WINDOW_SIZE, total_lines)
        window_lines = approved_lines[win_start:win_end]
        n_win = len(window_lines)

        formatted_lines = []
        for i, line_data in enumerate(window_lines, start=1):
            escaped_text = _escape_xml_delimiters(line_data.get("text", ""))
            formatted_lines.append(f"L{i}: {escaped_text}")

        prompt_body = (
            "You are an academic segment classifier. Analyze the following transcript lines labeled L1 to L{count}.\n"
            "Identify contiguous line ranges and classify each into one of:\n"
            "  - study_notes: Lecture content, technical explanations, definitions, derivations, formulas, algorithms, or code.\n"
            "  - general_info: Course logistics, exam dates, office hours, syllabus info.\n"
            "  - personal: Personal reminders, unrelated thoughts, social conversations.\n"
            "  - task_list: Homework assignments, to-do lists, checklist items.\n"
            "  - other: Non-study banter, unreadable noise, formatting artifacts.\n\n"
            "Rules:\n"
            "1. Every line from 1 to {count} must be covered.\n"
            "2. Provide start_line_number and end_line_number as 1-based local integers (e.g. 1 to {count}).\n"
            "3. Guess the academic subject (e.g. 'Computer Science', 'Linear Algebra') if study_notes, or null.\n"
            "4. Assign a confidence score from 0.0 to 1.0.\n"
            "5. CRITICAL: Student study notes frequently contain errors, misconceptions, or incorrect formulas. "
            "You MUST classify all technical or lecture content as 'study_notes', even if the student statement is factually wrong. "
            "Never classify study notes as 'other' because of factual errors; 'other' is strictly for non-academic noise or banter.\n\n"
            "<student_transcript>\n{lines}\n</student_transcript>"
        ).format(count=n_win, lines="\n".join(formatted_lines))

        prompt = Prompt(
            name="segment_classifier",
            version="v1",
            user=prompt_body,
        )

        try:
            # Explicitly disable thinking mode to protect latency and JSON compliance
            result = llm.generate_structured(
                prompt=prompt,
                schema=TranscriptSegmentationResult,
                request_id=f"enrich:{state.get('job_id')}:classify:{win_start}",
                disable_fallback=True,
                think=False,
            )
            data = result.data
            if isinstance(data, dict):
                segs = data.get("segments", [])
            elif hasattr(data, "segments"):
                segs = [s.model_dump() if hasattr(s, "model_dump") else s.__dict__ for s in data.segments]
            else:
                segs = []
        except Exception as exc:
            logger.warning("Segment classifier window %d-%d failed: %s; falling back to study_notes", win_start, win_end, exc)
            segs = [{
                "segment_type": "study_notes",
                "start_line_number": 1,
                "end_line_number": n_win,
                "topic_description": "Transcript notes",
                "confidence": 1.0,
                "subject": None,
            }]

        # Map local 1-based indices to global 0-based indices
        for s in segs:
            loc_start = max(1, min(int(s.get("start_line_number", 1)), n_win))
            loc_end = max(loc_start, min(int(s.get("end_line_number", n_win)), n_win))
            glob_start = win_start + (loc_start - 1)
            glob_end = win_start + (loc_end - 1)

            all_raw_segments.append({
                "segment_type": s.get("segment_type", "study_notes"),
                "global_start": glob_start,
                "global_end": glob_end,
                "orig_start": glob_start,
                "orig_end": glob_end,
                "topic_description": s.get("topic_description", ""),
                "subject": s.get("subject"),
                "confidence": float(s.get("confidence", 1.0)),
                "rationale": s.get("rationale", ""),
            })

    # Sort raw segments by global_start
    all_raw_segments.sort(key=lambda s: s["global_start"])

    # Normalization: Handle overlaps and gaps across 0..total_lines-1
    normalized_segments: List[Dict[str, Any]] = []
    current_idx = 0

    for s in all_raw_segments:
        start = s["global_start"]
        end = s["global_end"]

        # If there is a gap between current_idx and start
        if start > current_idx:
            # Gaps assigned to 'other' with confidence 0.0 (never default to study_notes)
            normalized_segments.append({
                "segment_type": "other",
                "global_start": current_idx,
                "global_end": start - 1,
                "orig_start": current_idx,
                "orig_end": start - 1,
                "topic_description": "Unclassified gap",
                "subject": None,
                "confidence": 0.0,
                "rationale": "Deterministic gap fill",
            })
            current_idx = start

        # If overlapping with previous
        if start < current_idx:
            start = current_idx
            if start > end:
                continue  # fully swallowed

        s["global_start"] = start
        s["global_end"] = end
        normalized_segments.append(s)
        current_idx = end + 1

    # Fill trailing gap if any
    if current_idx < total_lines:
        normalized_segments.append({
            "segment_type": "other",
            "global_start": current_idx,
            "global_end": total_lines - 1,
            "orig_start": current_idx,
            "orig_end": total_lines - 1,
            "topic_description": "Unclassified trailing gap",
            "subject": None,
            "confidence": 0.0,
            "rationale": "Deterministic trailing gap fill",
        })

    # Boundary Merging: Adjacent segments sharing same segment_type
    merged_segments: List[Dict[str, Any]] = []
    for s in normalized_segments:
        if (
            merged_segments
            and merged_segments[-1]["segment_type"] == s["segment_type"]
            and merged_segments[-1]["global_end"] + 1 == s["global_start"]
        ):
            merged_segments[-1]["global_end"] = s["global_end"]
            if not merged_segments[-1]["subject"] and s.get("subject"):
                merged_segments[-1]["subject"] = s["subject"]
            merged_segments[-1]["confidence"] = min(merged_segments[-1]["confidence"], s["confidence"])
        else:
            merged_segments.append(s)

    # Resolve document default subject
    doc_subject = None
    try:
        doc = Document.objects.get(pk=document_id)
        doc_subject = doc.subject
    except Exception:
        pass

    # Filtering & Excluded Segments Tracking
    final_study_segments: List[Dict[str, Any]] = []
    excluded_segments_list: List[Dict[str, Any]] = []

    for s in merged_segments:
        g_start = s["global_start"]
        g_end = s["global_end"]
        seg_lines = approved_lines[g_start : g_end + 1]
        lineage_ids = [line["lineage_id"] for line in seg_lines]

        # Check if any line in this segment is force-included
        has_force_include = any(lid in force_include_line_ids for lid in lineage_ids)

        # Shift measurement: heavily modified if boundary shifted by > 3 lines during repair
        start_shift = abs(s["global_start"] - s.get("orig_start", s["global_start"]))
        end_shift = abs(s["global_end"] - s.get("orig_end", s["global_end"]))
        heavily_modified = start_shift > 3 or end_shift > 3

        # Exclude reasons
        exclude_reason = None
        if s["segment_type"] != "study_notes":
            exclude_reason = f"non_study_{s['segment_type']}"
        elif s["confidence"] < min_confidence:
            exclude_reason = "low_confidence"
        elif heavily_modified:
            exclude_reason = "boundary_shift"

        if exclude_reason and not has_force_include:
            excluded_segments_list.append({
                "segment_type": s["segment_type"],
                "start_line_number": g_start + 1,
                "end_line_number": g_end + 1,
                "topic_description": s.get("topic_description", ""),
                "reason": exclude_reason,
                "lineage_ids": lineage_ids,
            })
        else:
            # Qualifies for study notes (either naturally or forced)
            resolved_subj = _resolve_subject(s.get("subject")) or doc_subject
            final_study_segments.append({
                "segment_type": "study_notes",
                "start_line_number": g_start + 1,
                "end_line_number": g_end + 1,
                "global_start": g_start,
                "global_end": g_end,
                "topic_description": s.get("topic_description", "Study Section"),
                "subject_id": str(resolved_subj.id) if resolved_subj else None,
                "subject_name": resolved_subj.name if resolved_subj else None,
                "confidence": s["confidence"],
                "lineage_ids": lineage_ids,
            })

    if not final_study_segments:
        logger.info("Document %s contains no qualifying study content after filtering", document_id)
        return {
            "segments": [],
            "excluded_segments": excluded_segments_list,
            "outcome": "no_study_content",
            "error_code": "NO_STUDY_CONTENT",
        }

    return {
        "segments": final_study_segments,
        "excluded_segments": excluded_segments_list,
    }

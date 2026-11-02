"""Evaluation and Quality Calibration Harness for Topic-Based Note Enrichment (PR 2).

Executes the pipeline end-to-end across the 25-note evaluation set:
- 14 clean multi-topic STEM notes
- 6 mistake notes containing >= 15 seeded mistakes and hard negatives
- 5 edge cases (code-only, formulas, and out-of-corpus topics)

Computes quantitative quality scorecard:
- Student Preservation Rate (Target = 100%)
- Silent Correction Rate (Target = 0%)
- False Correction Count (Target <= 1)
- Missed Correction Count (Target <= 2)
- Addition Support Accuracy (Target >= 85%)
- Cross-Topic Duplication Rate (Target < 5%)
- Planner Fallback Rate (Target < 10%)
- LLM Call Budget (assert <= 25 calls per note)
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import uuid
from typing import Any, Dict, List

# Django setup
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.ci")

import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock
from apps.ai_classroom.services import run_enrichment_job
from apps.documents.models import Document, DocumentLine, DocumentPage, DocumentPageRevision
from apps.jobs.models import Job, JobExecutionState
from apps.profiles.models import Profile
from apps.references.models import ReferenceChunk, ReferenceDocument
from apps.references.services import retrieve_reference_context
from apps.subjects.models import Subject
from providers.registry import get_embedding_provider, get_llm_provider

User = get_user_model()

# Correction-language detection (mirrors verification_node._contains_correction_language)
_DEICTIC_RE = re.compile(
    r'(?i)\b(?:this\s+(?:statement|claim|assertion|formula|equation|definition|answer|line|idea|notion|concept)'
    r'|the\s+(?:above|preceding)\s+(?:statement|claim|line|formula|equation)'
    r'|your\s+(?:note|statement|claim|answer))\b'
)
_CORRECTION_WORD_RE = re.compile(
    r'(?i)\b(?:incorrect|wrong|false|inaccurate|erroneous|mistake[ns]?|misconception'
    r'|not\s+(?:correct|accurate|true|right|valid))\b'
)


def _text_is_correction(text: str) -> bool:
    """Return True if the addition text asserts a student line is wrong."""
    return bool(_DEICTIC_RE.search(text) and _CORRECTION_WORD_RE.search(text))


def load_reference_corpus(fixtures_dir: str, subject_map: Dict[str, Subject]) -> int:
    """Load and index JSON reference textbooks from fixtures into the database."""
    corpus_files = glob.glob(os.path.join(fixtures_dir, "reference_corpus", "*.json"))
    total_chunks = 0
    embedder = get_embedding_provider()

    print(f"\n[Corpus Loader] Found {len(corpus_files)} reference document files.")
    for file_path in corpus_files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        subject_name = data.get("subject", "General")
        subject = subject_map.get(subject_name)

        ref_doc, _ = ReferenceDocument.objects.get_or_create(
            title=data["title"],
            defaults={
                "source_type": ReferenceDocument.SourceType.TEXTBOOK,
                "status": ReferenceDocument.Status.READY,
                "subject": subject,
            },
        )
        if ref_doc.subject != subject:
            ref_doc.subject = subject
            ref_doc.save(update_fields=("subject",))

        chunks_data = data.get("chunks", [])
        chunk_texts = [c["text"] for c in chunks_data]
        embeddings = embedder.embed(chunk_texts, model_version=embedder.model_version) if chunk_texts else []

        for idx, c in enumerate(chunks_data):
            emb_vec = embeddings[idx] if idx < len(embeddings) else None
            # Pad or truncate if dimensions differ
            expected_dim = int(getattr(settings, "EMBEDDING_DIMENSIONS", 1024))
            if emb_vec and len(emb_vec) != expected_dim:
                if len(emb_vec) < expected_dim:
                    emb_vec = emb_vec + [0.0] * (expected_dim - len(emb_vec))
                else:
                    emb_vec = emb_vec[:expected_dim]

            ReferenceChunk.objects.update_or_create(
                reference_document=ref_doc,
                chunk_index=c.get("chunk_index", idx),
                defaults={
                    "text": c["text"],
                    "chapter": c.get("chapter", ""),
                    "section": c.get("section", ""),
                    "page_number": c.get("page_number", idx + 1),
                    "embedding": emb_vec,
                    "embedding_model": embedder.name,
                    "embedding_version": embedder.model_version,
                },
            )
            total_chunks += 1

    print(f"[Corpus Loader] Successfully indexed {total_chunks} chunks.")
    return total_chunks


def run_evaluation(fixtures_dir: str, sweep: bool = False, note_filter: str = None, limit: int = None, eval_set_file: str = None) -> Dict[str, Any]:
    """Execute evaluation run across the evaluation notes."""
    eval_file = eval_set_file or os.path.join(fixtures_dir, "enrichment_eval_set.json")
    with open(eval_file, "r", encoding="utf-8") as f:
        eval_notes = json.load(f)

    if note_filter:
        eval_notes = [n for n in eval_notes if note_filter in n["id"]]
    if limit:
        eval_notes = eval_notes[:limit]

    user, _ = User.objects.get_or_create(email="eval_runner@studyai.internal")
    profile, _ = Profile.objects.get_or_create(user=user, defaults={"name": "Eval Runner"})

    subjects = {
        "Computer Science": Subject.objects.filter(name="Computer Science", profile=profile).first()
        or Subject.objects.create(name="Computer Science", profile=profile),
        "Physics": Subject.objects.filter(name="Physics", profile=profile).first()
        or Subject.objects.create(name="Physics", profile=profile),
        "Chemistry": Subject.objects.filter(name="Chemistry", profile=profile).first()
        or Subject.objects.create(name="Chemistry", profile=profile),
        "Biology": Subject.objects.filter(name="Biology", profile=profile).first()
        or Subject.objects.create(name="Biology", profile=profile),
    }

    load_reference_corpus(fixtures_dir, subjects)

    if sweep:
        run_relevance_calibration_sweep(subjects)

    print(f"\n[Evaluator] Running pipeline evaluation across {len(eval_notes)} notes...")
    results: List[Dict[str, Any]] = []

    total_student_lines = 0
    preserved_student_lines = 0
    silent_corrections = 0
    false_corrections = 0
    detected_corrections = 0
    seeded_mistakes_total = 0
    addition_support_correct = 0
    addition_support_total = 0
    cross_topic_duplications = 0
    planner_fallbacks = 0
    total_llm_calls = 0
    notes_with_budget_breach = 0
    academic_notes_count = 0
    classifier_correct_notes = 0
    total_additions_generated = 0
    total_additions_persisted = 0
    dropped_low_cosine = 0
    dropped_uncited = 0
    dropped_neutral_entailment = 0
    dropped_student_entailed = 0
    dropped_correction_leak = 0
    dropped_for_budget_total = 0
    # Text-based correction tracking (what students actually see)
    text_corrections_on_clean = 0      # false corrections: correction language on clean notes
    text_corrections_on_mistake = 0    # detected corrections: correction language on mistake notes
    text_corrections_total = 0         # all additions with correction language that reached persist

    for idx, test_note in enumerate(eval_notes, start=1):
        note_id = test_note["id"]
        category = test_note.get("category", "clean")
        subject = subjects.get(test_note.get("subject", "Computer Science"))
        lines = test_note.get("lines", [])
        seeded_mistakes = test_note.get("seeded_mistakes", [])
        seeded_mistakes_total += len(seeded_mistakes)

        # Create Document
        doc = Document.objects.create(
            profile=profile,
            subject=subject,
            title=f"Eval Note: {test_note.get('title', note_id)}",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.PDF,
        )

        page = DocumentPage.objects.create(
            document=doc,
            page_number=1,
            ocr_status=DocumentPage.OcrStatus.COMPLETED,
            review_status=DocumentPage.ReviewStatus.APPROVED,
            is_approved=True,
            is_ignored=False,
            approved_by=user,
            approved_at=timezone.now(),
        )

        rev = DocumentPageRevision.objects.create(
            page=page,
            revision_number=1,
            created_by=user,
            text_hash=f"eval_hash_{note_id}",
        )
        page.current_revision_id = rev.id
        page.save(update_fields=("current_revision_id",))

        doc_lines = []
        for l_idx, text in enumerate(lines):
            dl = DocumentLine.objects.create(
                page_revision=rev,
                line_index=l_idx,
                lineage_id=uuid.uuid4(),
                text=text,
                original_text=text,
            )
            doc_lines.append(dl)

        # Create Job and run
        job = Job.objects.create(
            job_type="enrich",
            resource_type="document",
            resource_id=str(doc.pk),
            profile_id=profile.id,
            idempotency_key=f"eval_job_{note_id}_{uuid.uuid4().hex[:8]}",
            status=Job.Status.RUNNING,
            started_at=timezone.now(),
            heartbeat_at=timezone.now(),
        )

        start_time = time.perf_counter()
        run_enrichment_job(job)
        elapsed_sec = time.perf_counter() - start_time

        job.refresh_from_db()
        note = EnrichedNote.objects.filter(document=doc, superseded=False).first()

        # Evaluate Note
        note_res: Dict[str, Any] = {
            "id": note_id,
            "category": category,
            "elapsed_sec": round(elapsed_sec, 3),
            "job_outcome": job.metadata.get("outcome", ""),
            "has_note": note is not None,
            "student_preservation": 1.0,
            "corrections_flagged": 0,
        }

        total_student_lines += len(lines)
        if category in ("clean", "mistake"):
            academic_notes_count += 1
            if job.metadata.get("outcome") != "no_study_content":
                classifier_correct_notes += 1

        # Track verification drop statistics from JobExecutionState
        v_state = JobExecutionState.objects.filter(job=job, completed_node__startswith="verify").order_by("-created_at").first()
        if v_state and isinstance(v_state.state_json, dict):
            ds = v_state.state_json.get("dropped_verification", {})
            total_additions_generated += ds.get("total_generated", 0)
            total_additions_persisted += ds.get("total_persisted", 0)
            dropped_low_cosine += ds.get("low_cosine", 0)
            dropped_uncited += ds.get("uncited", 0)
            dropped_neutral_entailment += ds.get("neutral_entailment", 0)
            dropped_student_entailed += ds.get("student_entailed", 0)
            dropped_correction_leak += ds.get("correction_leak", 0)

        s_state = JobExecutionState.objects.filter(job=job, completed_node__startswith="sanitize_dedupe").order_by("-created_at").first()
        if s_state and isinstance(s_state.state_json, dict):
            b_val = s_state.state_json.get("dropped_for_budget", 0)
            dropped_for_budget_total += len(b_val) if isinstance(b_val, list) else int(b_val or 0)

        if note:
            blocks = list(note.blocks.all().order_by("block_index"))
            student_blocks = [b for b in blocks if b.block_kind == EnrichedNoteBlock.BlockKind.STUDENT]
            addition_blocks = [b for b in blocks if b.block_kind == EnrichedNoteBlock.BlockKind.ADDITION]

            # 1. Student line preservation
            student_block_texts = "\n".join([b.content for b in student_blocks])
            matched_lines = 0
            for l in lines:
                if l.strip() in student_block_texts:
                    matched_lines += 1
            preserved_student_lines += matched_lines
            note_res["student_preservation"] = (matched_lines / len(lines)) if lines else 1.0

            # 2. Silent correction rate (check if any student block text was modified)
            for b in student_blocks:
                if any(err["student_claim"] in b.content and "Correction:" in b.content for err in seeded_mistakes):
                    silent_corrections += 1

            # 3. Corrections verification: count by BOTH addition_kind AND text content
            # addition_kind-based (the formal path)
            possible_issues = [b for b in addition_blocks if b.addition_kind == "possible_issue"]
            note_res["corrections_flagged"] = len(possible_issues)

            # Text-based detection (what students actually see — catches correction leaks)
            text_corrections_in_note = [b for b in addition_blocks if _text_is_correction(b.content)]
            note_res["text_corrections"] = len(text_corrections_in_note)

            if category == "clean":
                if len(possible_issues) > 0:
                    false_corrections += len(possible_issues)
                # Text-based: any correction language on a clean note is a false correction
                text_corrections_on_clean += len(text_corrections_in_note)
            elif category == "mistake":
                detected_corrections += len(possible_issues)
                text_corrections_on_mistake += len(text_corrections_in_note)
            text_corrections_total += len(text_corrections_in_note)

            # 4. Support status accuracy
            for b in addition_blocks:
                addition_support_total += 1
                if b.support_status in ("supported", "partial"):
                    addition_support_correct += 1

            # 5. Planner fallback check
            if note.diagnostics.get("planner_fallback", False):
                planner_fallbacks += 1

            # 6. Calls used check
            calls_used = job.metadata.get("calls_used", len(note.blocks.all()))
            total_llm_calls += calls_used
            if calls_used > 25:
                notes_with_budget_breach += 1
        else:
            note_res["student_preservation"] = 0.0

        results.append(note_res)
        print(f"  [{idx:02d}/{len(eval_notes)}] {note_id} ({category}) -> outcome={job.metadata.get('outcome')} in {elapsed_sec:.2f}s")

    # Metrics Summary
    preservation_rate = (preserved_student_lines / total_student_lines * 100.0) if total_student_lines else 100.0
    missed_corrections = max(0, seeded_mistakes_total - detected_corrections)
    support_accuracy = (addition_support_correct / addition_support_total * 100.0) if addition_support_total else 100.0
    planner_fallback_rate = (planner_fallbacks / len(eval_notes) * 100.0)
    flag_precision = (detected_corrections / max(1, detected_corrections + false_corrections) * 100.0) if (detected_corrections + false_corrections) else 100.0
    classifier_acc = (classifier_correct_notes / max(1, academic_notes_count) * 100.0) if academic_notes_count else 100.0

    scorecard = {
        "notes_evaluated": len(eval_notes),
        "student_preservation_rate_pct": round(preservation_rate, 2),
        "silent_correction_rate_pct": round(silent_corrections / max(1, total_student_lines) * 100.0, 2),
        "classifier_accuracy_pct": round(classifier_acc, 2),
        "false_correction_count": false_corrections,
        "missed_correction_count": missed_corrections,
        "seeded_mistakes_total": seeded_mistakes_total,
        "detected_corrections": detected_corrections,
        "flag_precision_pct": round(flag_precision, 2),
        # Text-based correction metrics (what students actually see)
        "text_corrections_on_clean": text_corrections_on_clean,
        "text_corrections_on_mistake": text_corrections_on_mistake,
        "text_corrections_total": text_corrections_total,
        "dropped_correction_leak": dropped_correction_leak,
        "total_additions_generated": total_additions_generated,
        "total_additions_persisted": total_additions_persisted,
        "dropped_low_cosine": dropped_low_cosine,
        "dropped_neutral_entailment": dropped_neutral_entailment,
        "dropped_uncited": dropped_uncited,
        "dropped_for_budget": dropped_for_budget_total,
        "addition_support_accuracy_pct": round(support_accuracy, 2),
        "planner_fallback_rate_pct": round(planner_fallback_rate, 2),
        "notes_with_budget_breach": notes_with_budget_breach,
        "average_calls_per_note": round(total_llm_calls / max(1, len(eval_notes)), 1),
    }

    print("\n" + "=" * 60)
    print("TOPIC ENRICHMENT EVALUATION SCORECARD (PR 2)")
    print("=" * 60)
    for k, v in scorecard.items():
        print(f"  {k:<35}: {v}")
    print("=" * 60 + "\n")

    return scorecard


def run_relevance_calibration_sweep(subjects: Dict[str, Subject]) -> None:
    """Run off-topic control queries to verify RELEVANCE_MIN_DENSE separates relevant vs noise."""
    print("\n[Calibration Sweep] Testing dense cosine similarity for relevant vs off-topic queries...")
    cs_sub = subjects.get("Computer Science")
    off_topic_queries = [
        "How do you prepare sourdough bread crust?",
        "19th century Victorian architecture in London",
        "Deep sea volcanic hydrothermal vent ecosystems",
    ]
    on_topic_queries = [
        "virtual memory paging and page tables",
        "deadlock prevention four Coffman conditions",
        "balanced binary search tree operations",
    ]

    on_topic_scores = []
    for q in on_topic_queries:
        ctx = retrieve_reference_context(q, subject=cs_sub, top_k=3)
        dense_scores = [c.get("dense_score", 0.0) for c in ctx]
        if dense_scores:
            on_topic_scores.append(max(dense_scores))

    off_topic_scores = []
    for q in off_topic_queries:
        ctx = retrieve_reference_context(q, subject=cs_sub, top_k=3)
        dense_scores = [c.get("dense_score", 0.0) for c in ctx]
        if dense_scores:
            off_topic_scores.append(max(dense_scores))

    avg_on = sum(on_topic_scores) / max(1, len(on_topic_scores))
    avg_off = sum(off_topic_scores) / max(1, len(off_topic_scores))
    print(f"  Average On-Topic Dense Cosine  : {avg_on:.4f}")
    print(f"  Average Off-Topic Dense Cosine : {avg_off:.4f}")
    calibrated_threshold = round((avg_on + avg_off) / 2.0, 2)
    print(f"  Calibrated RELEVANCE_MIN_DENSE : {calibrated_threshold}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate PR 2 Topic Enrichment Pipeline")
    parser.add_argument("--sweep", action="store_true", help="Run relevance calibration sweep")
    parser.add_argument("--note", type=str, default=None, help="Filter to specific note id")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of notes evaluated")
    parser.add_argument("--holdout", action="store_true", help="Run held-out evaluation set instead of primary set")
    args = parser.parse_args()

    fixtures_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests",
        "eval",
        "fixtures",
    )

    eval_set = None
    if args.holdout:
        eval_set = os.path.join(fixtures_dir, "enrichment_eval_set_holdout.json")
        print("\n[Holdout Mode] Using held-out evaluation set (not tuned on).\n")

    run_evaluation(fixtures_dir, sweep=args.sweep, note_filter=args.note, limit=args.limit, eval_set_file=eval_set)

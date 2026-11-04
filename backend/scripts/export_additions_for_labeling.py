"""Export script for PR 3 manual labeling sheet (Part 2).

Reads the final persisted notes from both evaluation sets:
- 25-note baseline set (backend/tests/eval/fixtures/enrichment_eval_set.json)
- 12-note held-out set (backend/tests/eval/fixtures/enrichment_eval_set_holdout.json)

Outputs with fixed random seed (42):
1. to_label.csv: Sampled additions for blind human evaluation.
2. answers.csv: System support status and verifier scores.
3. seeded_mistakes.csv: Seeded mistakes across all mistake notes.
"""
import argparse
import csv
import json
import os
import random
import sys
from typing import Any, Dict, List, Optional

# Django setup
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.ci")

import django
django.setup()

from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock
from apps.documents.models import Document, DocumentPageRevision
from apps.jobs.models import Job, JobExecutionState
from apps.references.models import ReferenceChunk


def get_latest_eval_note(note_id: str) -> Optional[EnrichedNote]:
    """Find the latest active EnrichedNote generated for an evaluation note."""
    rev = DocumentPageRevision.objects.filter(text_hash=f"eval_hash_{note_id}").order_by("-created_at").first()
    if rev and rev.page and rev.page.document:
        doc = rev.page.document
        return EnrichedNote.objects.filter(document=doc, superseded=False).order_by("-created_at").first()
    # Fallback: check document title
    doc = Document.objects.filter(title__contains=note_id, profile__name="Eval Runner").order_by("-created_at").first()
    if doc:
        return EnrichedNote.objects.filter(document=doc, superseded=False).order_by("-created_at").first()
    return None


def export_labeling_sheets(output_dir: str, fixtures_dir: str, seed: int = 42) -> None:
    random.seed(seed)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load eval sets
    eval_set_path = os.path.join(fixtures_dir, "enrichment_eval_set.json")
    holdout_set_path = os.path.join(fixtures_dir, "enrichment_eval_set_holdout.json")

    eval_notes = []
    if os.path.exists(eval_set_path):
        with open(eval_set_path, "r", encoding="utf-8") as f:
            eval_notes.extend(json.load(f))
    if os.path.exists(holdout_set_path):
        with open(holdout_set_path, "r", encoding="utf-8") as f:
            eval_notes.extend(json.load(f))

    print(f"Loaded {len(eval_notes)} evaluation note definitions.")

    # 2. Collect seeded mistakes
    seeded_mistakes_rows = []
    for note_def in eval_notes:
        note_id = note_def["id"]
        mistakes = note_def.get("seeded_mistakes", [])
        for m in mistakes:
            line_text = m.get("student_claim") or m.get("text") or str(m)
            seeded_mistakes_rows.append({
                "note_id": note_id,
                "mistake_line_text": line_text,
                "addressed_by_an_addition": "",
                "addition_row_id": "",
                "addition_is_right": "",
            })

    # 3. Collect all additions from persisted notes
    all_additions: List[Dict[str, Any]] = []

    for note_def in eval_notes:
        note_id = note_def["id"]
        category = note_def.get("category", "clean")
        title = note_def.get("title", note_id)
        note = get_latest_eval_note(note_id)
        if not note:
            continue

        job = note.generation_job
        render_state = None
        global_citations_map = {}
        sections_by_topic = {}
        if job:
            r_state_row = JobExecutionState.objects.filter(job=job, completed_node="render").first()
            if r_state_row and r_state_row.state_json:
                render_state = r_state_row.state_json
                for gc in render_state.get("global_citations", []):
                    cnum = gc.get("citation_number")
                    if cnum is not None:
                        global_citations_map[f"[^{cnum}]"] = gc
                        global_citations_map[str(cnum)] = gc
                sections_by_topic = render_state.get("sections_by_topic", {})

        # Walk through topics and blocks
        # First gather student lines per topic
        student_lines_by_topic: Dict[str, List[str]] = {}
        for tid, sec in sections_by_topic.items():
            s_lines = [b.get("text", "") for b in sec.get("blocks", []) if b.get("type") == "student"]
            student_lines_by_topic[tid] = s_lines

        # Also fallback to DB blocks if sections_by_topic empty
        db_blocks = list(note.blocks.all().order_by("block_index"))
        if not student_lines_by_topic:
            for b in db_blocks:
                if b.block_kind == EnrichedNoteBlock.BlockKind.STUDENT:
                    student_lines_by_topic.setdefault(b.topic_id, []).append(b.content)

        # Iterate through blocks to extract additions and anchors
        for tid, sec in sections_by_topic.items():
            topic_title = sec.get("title", tid)
            blocks = sec.get("blocks", [])
            last_student_text = ""
            for b in blocks:
                b_type = b.get("type")
                if b_type == "student":
                    last_student_text = b.get("text", "")
                elif b_type == "addition":
                    add_text = b.get("text", "")
                    c_ids = b.get("citation_ids", [])
                    support_status = b.get("support_status") or "supported"
                    addition_kind = b.get("addition_kind") or "explanation"
                    verification_score = b.get("verification_score")

                    # Resolve cited passage
                    cited_passage = ""
                    primary_cid = c_ids[0] if c_ids else ""
                    gc = global_citations_map.get(primary_cid)
                    if gc:
                        snippet = gc.get("snippet", "")
                        chunk_id = gc.get("chunk_id")
                        chunk_full_text = ""
                        if chunk_id:
                            chunk_obj = ReferenceChunk.objects.filter(pk=chunk_id).first()
                            if chunk_obj:
                                chunk_full_text = chunk_obj.text

                        if chunk_full_text and snippet:
                            cited_passage = f"Best-matching sentence:\n{snippet}\n\nFull cited chunk:\n{chunk_full_text}"
                        elif chunk_full_text:
                            cited_passage = chunk_full_text
                        elif snippet:
                            cited_passage = snippet
                    else:
                        cited_passage = "(No matching reference passage recorded)"

                    # Entailment verdict
                    if support_status == "supported":
                        entailment_v = "ENTAILED" if (verification_score or 0) >= 0.75 else "PARTIALLY_ENTAILED"
                    elif support_status == "partial":
                        entailment_v = "PARTIALLY_ENTAILED"
                    else:
                        entailment_v = "NEUTRAL"

                    all_additions.append({
                        "note_id": note_id,
                        "note_category": category,
                        "topic_title": topic_title,
                        "student_lines_in_topic": "\n".join(student_lines_by_topic.get(tid, [])),
                        "anchor_line_text": last_student_text,
                        "addition_text": add_text,
                        "cited_passage_text": cited_passage,
                        "system_support_status": support_status,
                        "addition_kind": addition_kind,
                        "citation_id": primary_cid,
                        "cosine": verification_score if verification_score is not None else "",
                        "entailment_verdict": entailment_v,
                    })

    print(f"Extracted {len(all_additions)} total persisted additions.")

    # 4. Sampling (§Part 2.A)
    # Sampling specification:
    # - all additions on mistake notes
    # - 10 supported additions and 10 partial additions chosen at random from other notes
    # - 5 additions chosen at random from clean notes

    mistake_additions = [a for a in all_additions if a["note_category"] == "mistake"]
    other_additions = [a for a in all_additions if a["note_category"] != "mistake"]

    other_supported = [a for a in other_additions if a["system_support_status"] == "supported"]
    other_partial = [a for a in other_additions if a["system_support_status"] == "partial"]

    sampled_other_supported = random.sample(other_supported, min(10, len(other_supported)))
    sampled_other_partial = random.sample(other_partial, min(10, len(other_partial)))

    sampled_ids = {id(a) for a in (mistake_additions + sampled_other_supported + sampled_other_partial)}

    clean_additions_remaining = [
        a for a in other_additions if a["note_category"] == "clean" and id(a) not in sampled_ids
    ]
    sampled_clean = random.sample(clean_additions_remaining, min(5, len(clean_additions_remaining)))

    final_sample = mistake_additions + sampled_other_supported + sampled_other_partial + sampled_clean
    # Shuffle deterministically to prevent category clustering
    random.shuffle(final_sample)

    print(f"Sampled {len(final_sample)} additions for labeling:")
    print(f"  - Mistake notes additions: {len(mistake_additions)}")
    print(f"  - Other supported additions: {len(sampled_other_supported)}")
    print(f"  - Other partial additions: {len(sampled_other_partial)}")
    print(f"  - Clean additions: {len(sampled_clean)}")

    # 5. Write to_label.csv
    to_label_path = os.path.join(output_dir, "to_label.csv")
    with open(to_label_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "row_id",
            "note_id",
            "note_category",
            "topic_title",
            "student_lines_in_topic",
            "anchor_line_text",
            "addition_text",
            "cited_passage_text",
            "L1_true",
            "L2_in_passage",
            "L3_contradicts_student",
            "L3_addition_is_right",
            "L4_placement_ok",
            "comment",
        ])
        for idx, item in enumerate(final_sample, start=1):
            item["row_id"] = idx
            writer.writerow([
                idx,
                item["note_id"],
                item["note_category"],
                item["topic_title"],
                item["student_lines_in_topic"],
                item["anchor_line_text"],
                item["addition_text"],
                item["cited_passage_text"],
                "",  # L1_true
                "",  # L2_in_passage
                "",  # L3_contradicts_student
                "",  # L3_addition_is_right
                "",  # L4_placement_ok
                "",  # comment
            ])

    # 6. Write answers.csv
    answers_path = os.path.join(output_dir, "answers.csv")
    with open(answers_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "row_id",
            "system_support_status",
            "addition_kind",
            "citation_id",
            "cosine",
            "entailment_verdict",
        ])
        for item in final_sample:
            writer.writerow([
                item["row_id"],
                item["system_support_status"],
                item["addition_kind"],
                item["citation_id"],
                item["cosine"],
                item["entailment_verdict"],
            ])

    # 7. Write seeded_mistakes.csv
    seeded_mistakes_path = os.path.join(output_dir, "seeded_mistakes.csv")
    with open(seeded_mistakes_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "note_id",
            "mistake_line_text",
            "addressed_by_an_addition",
            "addition_row_id",
            "addition_is_right",
        ])
        for m_row in seeded_mistakes_rows:
            writer.writerow([
                m_row["note_id"],
                m_row["mistake_line_text"],
                m_row["addressed_by_an_addition"],
                m_row["addition_row_id"],
                m_row["addition_is_right"],
            ])

    print(f"\nSuccessfully generated labeling sheets in {output_dir}:")
    print(f"  - {to_label_path} ({len(final_sample)} rows)")
    print(f"  - {answers_path} ({len(final_sample)} rows)")
    print(f"  - {seeded_mistakes_path} ({len(seeded_mistakes_rows)} rows)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export additions for manual PR 3 labeling")
    parser.add_argument("--output-dir", default="backend/reports/labeling", help="Directory to save CSV sheets")
    parser.add_argument("--fixtures-dir", default="backend/tests/eval/fixtures", help="Fixtures directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    export_labeling_sheets(args.output_dir, args.fixtures_dir, seed=args.seed)

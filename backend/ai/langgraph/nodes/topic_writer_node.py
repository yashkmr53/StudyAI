"""Topic Writer Node for Topic-Based Note Enrichment (PR 2).

Assembles verbatim student blocks deterministically in code with single-source-of-truth
code/prose classification (render_as), generates additions only via LLM (thinking disabled),
enforces the restatement filter with correction exemption, and anchors additions.
"""
import logging
import re
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

import numpy as np
from django.conf import settings

from ai.langgraph.state.topic_enrichment_state import (
    AdditionDraft,
    EnrichedSection,
    EvidenceItem,
    SectionBlock,
    TopicResearchResult,
    TopicWriterOutput,
)
from providers.base import Prompt
from providers.registry import get_embedding_provider, get_llm_provider

logger = logging.getLogger(__name__)

# Deictic reference detection: additions that reference a student line
_DEICTIC_RE = re.compile(
    r'(?i)\b(?:this\s+(?:statement|claim|assertion|formula|equation|definition|answer|line|idea|notion|concept)'
    r'|the\s+(?:above|preceding)\s+(?:statement|claim|line|formula|equation)'
    r'|your\s+(?:note|statement|claim|answer))\b'
)

# Heuristic patterns for code line detection
STRONG_CODE_START_RE = re.compile(r"^\s*(def\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+\s+import|function\s+\w+)")
CODE_SYNTAX_RE = re.compile(r"(;\s*$|[{}()\[\]=+\-*/<>!&|^~%]{2,})")


def _is_code_line(text: str, prev_was_code: bool) -> bool:
    """Classify an individual line text as code or prose."""
    s = text.rstrip()
    if not s.strip():
        return prev_was_code

    # Strong keyword starter
    if STRONG_CODE_START_RE.match(s):
        return True

    # Indentation of >= 4 spaces or tab directly following another code line
    has_indent = (s.startswith("    ") or s.startswith("\t")) and prev_was_code

    # Ending in semicolon with an assignment or function call
    has_semi_stmt = s.endswith(";") and ("=" in s or "(" in s)

    return has_indent or has_semi_stmt


def classify_line_render_as(lines: List[Dict[str, Any]]) -> List[Literal["prose", "code"]]:
    """Single source of truth: Classify consecutive lines into prose vs code."""
    n = len(lines)
    raw_is_code = [False] * n

    prev = False
    for i, line in enumerate(lines):
        t = line.get("text", "")
        is_code = _is_code_line(t, prev)
        raw_is_code[i] = is_code
        prev = is_code

    # Refine: Real code typically comes in runs of >= 2 lines (or a single strong keyword line)
    render_as: List[Literal["prose", "code"]] = ["prose"] * n
    for i in range(n):
        t = lines[i].get("text", "").strip()
        strong = bool(STRONG_CODE_START_RE.match(t))
        run_with_next = (i + 1 < n and raw_is_code[i] and raw_is_code[i + 1])
        run_with_prev = (i > 0 and raw_is_code[i] and raw_is_code[i - 1])

        if strong or run_with_next or run_with_prev:
            render_as[i] = "code"
        else:
            render_as[i] = "prose"

    return render_as


def _escape_xml(text: str) -> str:
    return (
        text.replace("</student_transcript>", "&lt;/student_transcript&gt;")
        .replace("<student_transcript>", "&lt;student_transcript&gt;")
        .replace("</reference_evidence>", "&lt;/reference_evidence&gt;")
        .replace("<reference_evidence>", "&lt;reference_evidence&gt;")
    )


def topic_writer_node(
    topic: Dict[str, Any],
    research: TopicResearchResult,
    all_lines_by_lineage: Dict[str, Dict[str, Any]],
    job_id: str = "",
    repair_pass: int = 0,
    llm_temperature: float = 0.0,
) -> EnrichedSection:
    """Execute writer stage for a topic (§3.3)."""
    topic_id = topic.get("topic_id", "t1")
    title = topic.get("title", f"Topic {topic_id}")
    lineage_ids = topic.get("lineage_ids", [])

    # Order topic transcript lines
    topic_lines = []
    for lid in lineage_ids:
        if lid in all_lines_by_lineage:
            topic_lines.append(all_lines_by_lineage[lid])

    line_kinds = classify_line_render_as(topic_lines)

    # 1. Check Evidence Status: If "none", skip writer entirely and return student blocks only
    if research.evidence_status == "none" or not research.evidence_items:
        logger.info("Topic %s has no evidence; skipping writer and returning student blocks only", topic_id)
        blocks = _assemble_student_blocks(topic_lines, line_kinds, additions=[])
        return EnrichedSection(
            topic_id=topic_id,
            title=title,
            blocks=blocks,
            evidence_status="none",
            writer_failed=False,
            no_reference_found=True,
        )

    # 2. Formulate Prompt for Additions Only
    enable_possible_issue = getattr(settings, "ENRICHMENT_ENABLE_POSSIBLE_ISSUE", False)
    if isinstance(enable_possible_issue, str):
        enable_possible_issue = enable_possible_issue.lower() in ("1", "true", "yes")

    # In repair pass, supply top-2 evidence items only
    evidence_to_use = research.evidence_items[:2] if repair_pass > 0 else research.evidence_items[:6]

    evidence_manifest_text = []
    valid_citation_ids = set()
    for item in evidence_to_use:
        valid_citation_ids.add(item.citation_id)
        escaped_snip = _escape_xml(item.snippet)
        evidence_manifest_text.append(
            f"[{item.citation_id}] ({item.source_title}, Ch: {item.chapter}, pp. {item.page_start}-{item.page_end}):\n{escaped_snip}"
        )

    formatted_transcript = []
    for line in topic_lines:
        lid = line["lineage_id"]
        escaped_t = _escape_xml(line.get("text", ""))
        formatted_transcript.append(f"LineID: {lid} | {escaped_t}")

    kind_guidance = (
        "- 'explanation': Adds definitions, context, formula derivations, or clarifications.\n"
        "- 'possible_issue': Constructive margin note flagging a factual mistake, imprecise formula, or contradictory statement in the student note."
        if enable_possible_issue
        else "- 'explanation': Adds definitions, context, formula derivations, or clarifications."
    )

    prompt_body = (
        "You are an academic textbook tutor augmenting student lecture notes.\n"
        "Review the student transcript lines and the provided reference evidence.\n"
        "Propose 1 to 2 concise, high-value ADDITIONS (1 to 2 sentences each) to supplement the student's notes.\n\n"
        "STRICT CONSTRAINTS:\n"
        "1. DO NOT rewrite, summarize, or repeat the student's text.\n"
        "2. Additions must specify 'after_line_id' (the exact LineID after which to insert, or null for top of section).\n"
        "3. Each addition must have kind: \n{kind_guidance}\n"
        "4. Each addition MUST cite 1 or more citation IDs (e.g. ['C1']) from the reference evidence.\n"
        "5. An addition of kind 'explanation' must NEVER merely restate what the student wrote.\n"
        "6. An 'explanation' must NEVER assert that a student line is wrong, incorrect, or contains an error. "
        "Do NOT use phrases like 'this statement is incorrect', 'this is wrong', 'this claim is false', "
        "'not correct', or any other correction. Only add supplementary context, definitions, derivations, "
        "or clarifications that enrich the student's understanding.\n"
        "7. 'after_line_id' must reference a student line that the addition relates to. "
        "Do NOT set after_line_id to null if the addition references a specific student line with 'this', 'the above', or similar.\n"
        "8. CONFLICTS WITH REFERENCE: If a student statement conflicts with, contradicts, or contains a misconception "
        "refuted by the reference evidence (such as potential energy increasing during descent, FIFO avoiding Belady's anomaly, "
        "or a necessary condition being the only eliminable one), DO NOT accept, echo, repeat, or build upon the student's false premise. "
        "Either skip the addition entirely, or state what the reference explicitly says with a citation without validating the student's false premise.\n\n"
        "<student_transcript>\n{transcript}\n</student_transcript>\n\n"
        "<reference_evidence>\n{evidence}\n</reference_evidence>"
    ).format(
        kind_guidance=kind_guidance,
        transcript="\n".join(formatted_transcript),
        evidence="\n\n".join(evidence_manifest_text),
    )

    prompt = Prompt(
        name="topic_writer",
        version="v1",
        user=prompt_body,
    )

    llm = get_llm_provider()
    writer_failed = False
    raw_additions: List[AdditionDraft] = []

    try:
        result = llm.generate_structured(
            prompt=prompt,
            schema=TopicWriterOutput,
            request_id=f"enrich:{job_id}:write:{topic_id}:{repair_pass}",
            disable_fallback=True,
            think=False,
            temperature=llm_temperature,
        )
        data = result.data
        if hasattr(data, "additions"):
            raw_additions = data.additions
        elif isinstance(data, dict):
            raw_additions = [AdditionDraft(**a) for a in data.get("additions", [])]
        else:
            raw_additions = []
    except Exception as exc:
        logger.warning("Topic writer for %s (pass %d) failed: %s", topic_id, repair_pass, exc)
        writer_failed = True
        raw_additions = []

    # 3. Filter Additions: Citations validity, Feature Flag, and Restatement Filter
    valid_additions: List[AdditionDraft] = []
    known_line_ids = set(lineage_ids)

    # Prepare student texts for restatement comparison
    student_texts = [l.get("text", "").strip() for l in topic_lines if l.get("text", "").strip()]
    restate_cosine_thresh = float(getattr(settings, "RESTATE_COSINE", 0.88))
    embed_provider = get_embedding_provider()

    student_embs = []
    if student_texts:
        try:
            s_raw = embed_provider.embed(student_texts)
            for vec in s_raw:
                v_arr = np.array(vec, dtype=float)
                student_embs.append(v_arr / (np.linalg.norm(v_arr) or 1.0))
        except Exception:
            pass

    for add in raw_additions[:4]:  # Cap at 4 additions per topic
        # Citation ground check: must cite at least 1 valid citation ID
        grounded_cits = [c for c in add.citation_ids if c in valid_citation_ids]
        if not grounded_cits:
            continue
        add.citation_ids = grounded_cits

        # Feature flag check
        if not enable_possible_issue and add.kind == "possible_issue":
            continue

        # Anchor validation: if after_line_id unknown or outside topic, append to end (None)
        if add.after_line_id and add.after_line_id not in known_line_ids:
            # Fallback anchor: last line of topic
            add.after_line_id = lineage_ids[-1] if lineage_ids else None

        # Deictic anchor fix: if addition references a student line ("this statement…")
        # but has no anchor (None = top of section), re-anchor to last line of topic
        if add.after_line_id is None and lineage_ids and _DEICTIC_RE.search(add.text):
            add.after_line_id = lineage_ids[-1]

        # Restatement Filter (§3.3):
        # Exemption: 'possible_issue' additions are EXEMPT from restatement filtering!
        if add.kind == "explanation" and student_embs:
            try:
                a_raw = embed_provider.embed([add.text])
                if a_raw:
                    a_arr = np.array(a_raw[0], dtype=float)
                    a_norm = a_arr / (np.linalg.norm(a_arr) or 1.0)
                    is_restatement = any(float(np.dot(a_norm, s_norm)) >= restate_cosine_thresh for s_norm in student_embs)
                    if is_restatement:
                        logger.info("Dropping explanation addition for %s as restatement", topic_id)
                        continue
            except Exception:
                pass

        valid_additions.append(add)

    # 4. Assemble Final Section Blocks
    blocks = _assemble_student_blocks(topic_lines, line_kinds, additions=valid_additions)

    return EnrichedSection(
        topic_id=topic_id,
        title=title,
        blocks=blocks,
        evidence_status=research.evidence_status,
        writer_failed=writer_failed,
        no_reference_found=False,
    )


def _assemble_student_blocks(
    topic_lines: List[Dict[str, Any]],
    line_kinds: List[Literal["prose", "code"]],
    additions: List[AdditionDraft],
) -> List[SectionBlock]:
    """Interleave student lines into contiguous blocks (by render_as and anchor points) with additions."""
    # Group additions by anchor after_line_id
    additions_by_anchor: Dict[Optional[str], List[AdditionDraft]] = {}
    for add in additions:
        additions_by_anchor.setdefault(add.after_line_id, []).append(add)

    blocks: List[SectionBlock] = []

    # Insert top-of-section additions (after_line_id is None)
    for add in additions_by_anchor.get(None, []):
        blocks.append(
            SectionBlock(
                type="addition",
                text=add.text,
                render_as="prose",
                citation_ids=add.citation_ids,
                addition_kind=add.kind,
                support_status="unverified",
            )
        )

    # Accumulate student lines into contiguous runs sharing the same render_as
    curr_run_lines: List[Dict[str, Any]] = []
    curr_run_kind: Optional[Literal["prose", "code"]] = None

    def flush_student_block():
        nonlocal curr_run_lines, curr_run_kind
        if not curr_run_lines:
            return
        joined_text = "\n".join(l.get("text", "") for l in curr_run_lines)
        line_ids = [l["lineage_id"] for l in curr_run_lines]
        blocks.append(
            SectionBlock(
                type="student",
                text=joined_text,
                render_as=curr_run_kind or "prose",
                line_ids=line_ids,
            )
        )
        curr_run_lines = []
        curr_run_kind = None

    for line, kind in zip(topic_lines, line_kinds):
        lid = line["lineage_id"]

        # If render_as changes, flush current student block
        if curr_run_kind is not None and curr_run_kind != kind:
            flush_student_block()

        curr_run_lines.append(line)
        curr_run_kind = kind

        # If there are additions anchored after this line, flush student block and insert additions
        if lid in additions_by_anchor:
            flush_student_block()
            for add in additions_by_anchor[lid]:
                blocks.append(
                    SectionBlock(
                        type="addition",
                        text=add.text,
                        render_as="prose",
                        citation_ids=add.citation_ids,
                        addition_kind=add.kind,
                        support_status="unverified",
                    )
                )

    # Flush any remaining student lines
    flush_student_block()

    return blocks

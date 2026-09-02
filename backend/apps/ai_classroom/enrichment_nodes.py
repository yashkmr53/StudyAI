"""Enrichment graph nodes for AI Classroom LangGraph workflow."""
import json
import logging
import time

from ai.langgraph.state.enrichment_state import EnrichmentState
from ai.tracing.config import log_llm_call
from ai.tracing.decorators import traced_node
from apps.ai_classroom.prompts import active_prompt, validate_stage_output, SCHEMAS
from apps.retrieval.models import NoteChunk
from apps.documents.models import Document
from providers.registry import get_llm_provider
from providers.base import Prompt

logger = logging.getLogger(__name__)


@traced_node("studyai.enrichment.retrieve", feature="enrichment")
def retrieve_chunks_node(state: EnrichmentState, config=None) -> dict:
    document = Document.objects.select_related("profile").get(pk=state["document_id"])

    user_chunks = list(
        NoteChunk.objects.filter(document=document, stale=False)
        .select_related("reference_book")
        .order_by("chunk_index")[:8]
    )
    reference_chunks = list(
        NoteChunk.objects.filter(
            source_type="reference",
            stale=False,
            reference_book__status="ready",
        ).exclude(reference_book__isnull=True)
        .select_related("reference_book")
        .order_by("?")[:6]
    )

    def as_evidence(chunks):
        return [{"chunk_id": str(c.pk), "content": c.content} for c in chunks]

    evidence_payload = {
        "user_chunks": as_evidence(user_chunks),
        "reference_chunks": as_evidence(reference_chunks),
    }

    return {
        "user_chunks": [{"chunk_id": str(c.pk), "content": c.content, "source_type": c.source_type,
                         "document_id": str(c.document_id), "page_start": c.page_start,
                         "page_end": c.page_end, "revision_ids": c.revision_ids} for c in user_chunks],
        "reference_chunks": [{"chunk_id": str(c.pk), "content": c.content, "source_type": c.source_type,
                               "document_id": str(c.document_id), "page_start": c.page_start,
                               "page_end": c.page_end, "revision_ids": c.revision_ids} for c in reference_chunks],
        "evidence_payload": evidence_payload,
    }


@traced_node("studyai.enrichment.draft", feature="enrichment")
def draft_node(state: EnrichmentState, config=None) -> dict:
    llm = get_llm_provider()
    prompt_template = active_prompt("enrichment_draft")
    evidence_payload = state["evidence_payload"]

    prompt = Prompt(
        name="enrichment_draft",
        version=prompt_template.version,
        user=prompt_template.template + "\nEVIDENCE_JSON:" + json.dumps(evidence_payload),
    )

    started = time.monotonic()
    result = llm.generate_structured(
        prompt=prompt,
        schema=SCHEMAS.get("enrichment_draft"),
        request_id=f"enrich:{state.get('job_id')}:draft",
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    validate_stage_output("enrichment_draft", result.data)

    log_llm_call(
        model=result.model,
        provider=llm.name,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
        success=True,
    )

    return {"draft_result": result.data}


@traced_node("studyai.enrichment.gap_detection", feature="enrichment")
def gap_detection_node(state: EnrichmentState, config=None) -> dict:
    llm = get_llm_provider()
    prompt_template = active_prompt("gap_detection")
    evidence_payload = state["evidence_payload"]

    prompt = Prompt(
        name="gap_detection",
        version=prompt_template.version,
        user=prompt_template.template + "\nEVIDENCE_JSON:" + json.dumps(evidence_payload),
    )

    started = time.monotonic()
    result = llm.generate_structured(
        prompt=prompt,
        schema=SCHEMAS.get("gap_detection"),
        request_id=f"enrich:{state.get('job_id')}:gaps",
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    validate_stage_output("gap_detection", result.data)

    log_llm_call(
        model=result.model,
        provider=llm.name,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
        success=True,
    )

    return {"gaps_result": result.data}


@traced_node("studyai.enrichment.gap_fill", feature="enrichment")
def gap_fill_node(state: EnrichmentState, config=None) -> dict:
    llm = get_llm_provider()
    prompt_template = active_prompt("gap_filling")
    evidence_payload = state["evidence_payload"]
    gaps = state.get("gaps_result", {}).get("gaps", [])
    fill_evidence = {**evidence_payload, "gaps": gaps}

    prompt = Prompt(
        name="gap_filling",
        version=prompt_template.version,
        user=prompt_template.template + "\nEVIDENCE_JSON:" + json.dumps(fill_evidence),
    )

    started = time.monotonic()
    result = llm.generate_structured(
        prompt=prompt,
        schema=SCHEMAS.get("gap_filling"),
        request_id=f"enrich:{state.get('job_id')}:fill",
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    validate_stage_output("gap_filling", result.data)

    log_llm_call(
        model=result.model,
        provider=llm.name,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
        success=True,
    )

    return {"fill_result": result.data}


@traced_node("studyai.enrichment.stitch", feature="enrichment")
def citation_stitch_node(state: EnrichmentState, config=None) -> dict:
    user_chunks = state.get("user_chunks", [])
    reference_chunks = state.get("reference_chunks", [])
    all_chunks = {c["chunk_id"]: c for c in user_chunks + reference_chunks}

    draft_blocks = state.get("draft_result", {}).get("blocks", [])
    fill_blocks = state.get("fill_result", {}).get("blocks", [])
    all_blocks = draft_blocks + fill_blocks

    stitched = []
    for i, block in enumerate(all_blocks):
        refs = []
        for cid in block.get("source_chunk_ids", []):
            chunk = all_chunks.get(cid)
            if chunk is None:
                continue
            revision_id = chunk.get("revision_ids", [None])[0] if chunk.get("revision_ids") else None
            refs.append({
                "source_type": chunk["source_type"],
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "page_number": chunk["page_start"],
                "revision_id": revision_id,
                "retrieval_score": None,
                "content": chunk.get("content", ""),
            })
        stitched.append({"index": i, **block, "refs": refs})

    return {"all_blocks": all_blocks, "stitched_blocks": stitched}


@traced_node("studyai.enrichment.verify", feature="enrichment")
def evidence_verification_node(state: EnrichmentState, config=None) -> dict:
    from apps.ai_classroom.services import EvidenceVerifier

    stitched = state.get("stitched_blocks", [])
    verified = []

    for item in stitched:
        refs = item.get("refs", [])
        status, score = EvidenceVerifier.verify(item["content"], refs)
        verified.append({"index": item["index"], **item, "status": status, "score": score})

    return {"stitched_blocks": verified}


@traced_node("studyai.enrichment.format", feature="enrichment")
def format_output_node(state: EnrichmentState, config=None) -> dict:
    return {
        "all_blocks": state.get("all_blocks", []),
        "stitched_blocks": state.get("stitched_blocks", []),
        "draft_result": state.get("draft_result", {}),
        "gaps_result": state.get("gaps_result", {}),
        "fill_result": state.get("fill_result", {}),
    }

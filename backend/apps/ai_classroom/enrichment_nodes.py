"""Enrichment graph nodes for AI Classroom LangGraph workflow."""
import json
import logging
import re
import time

from ai.langgraph.state.enrichment_state import EnrichmentState
from ai.tracing.config import log_llm_call
from ai.tracing.decorators import traced_node
from apps.ai_classroom.prompts import active_prompt, validate_stage_output, SCHEMAS
from apps.documents.models import Document
from apps.retrieval.retrieval import RetrievalService
from apps.retrieval.models import NoteChunk
from providers.registry import get_llm_provider
from providers.base import Prompt

logger = logging.getLogger(__name__)


# Common stop words to filter out when extracting query terms
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
    'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
    'might', 'must', 'can', 'this', 'that', 'these', 'those', 'it', 'its', 'their',
    'them', 'they', 'we', 'us', 'you', 'your', 'i', 'me', 'my', 'our', 'he', 'him',
    'his', 'she', 'her', 'hers', 'it', 'what', 'which', 'who', 'whom', 'whose',
    'where', 'when', 'why', 'how', 'there', 'here', 'then', 'than', 'so', 'very',
    'just', 'only', 'also', 'not', 'no', 'yes', 'if', 'else', 'then', 'than', 'such',
    'each', 'every', 'all', 'some', 'any', 'both', 'few', 'many', 'more', 'most',
    'other', 'another', 'one', 'two', 'three', 'first', 'second', 'third', 'last',
    'new', 'old', 'same', 'different', 'such', 'own', 'same', 'very', 'too', 'also',
    'even', 'still', 'yet', 'already', 'just', 'only', 'really', 'quite', 'rather',
    'says', 'said', 'say', 'says', 'according', 'accordingly', 'also', 'although',
    'always', 'am', 'among', 'an', 'and', 'another', 'any', 'anybody', 'anyone',
    'anything', 'anywhere', 'are', 'around', 'as', 'at', 'be', 'became', 'because',
    'become', 'becomes', 'becoming', 'been', 'before', 'being', 'below', 'between',
    'both', 'but', 'by', 'came', 'can', 'cannot', 'come', 'comes', 'could', 'did',
    'do', 'does', 'doing', 'done', 'down', 'during', 'each', 'few', 'for', 'from',
    'further', 'get', 'gets', 'getting', 'got', 'had', 'has', 'have', 'having', 'he',
    'her', 'here', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'however',
    'i', 'if', 'in', 'into', 'is', 'it', 'its', 'itself', 'just', 'me', 'more',
    'most', 'my', 'myself', 'no', 'nor', 'not', 'now', 'of', 'off', 'on', 'once',
    'only', 'or', 'other', 'others', 'our', 'ours', 'ourselves', 'out', 'over',
    'own', 'same', 'she', 'should', 'so', 'some', 'such', 'than', 'that', 'the',
    'their', 'theirs', 'them', 'themselves', 'then', 'there', 'these', 'they',
    'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very', 'was',
    'we', 'were', 'what', 'when', 'where', 'which', 'while', 'who', 'whom', 'why',
    'will', 'with', 'would', 'you', 'your', 'yours', 'yourself', 'yourselves'
}


def extract_query_terms(text: str, max_terms: int = 12) -> str:
    """Extract key terms from text for focused retrieval query.
    
    Extracts meaningful terms (nouns, technical terms) by:
    1. Splitting into words
    2. Filtering stop words and short tokens
    3. Preferring capitalized terms and longer tokens
    4. Returning top terms as a space-separated query string
    """
    if not text:
        return ""
    
    # Split on word boundaries, keep alphanumeric + hyphens
    words = re.findall(r'\b[\w\-]+\b', text.lower())
    
    # Filter: remove stop words, short tokens, pure numbers
    filtered = [
        w for w in words
        if len(w) >= 3 and w not in STOP_WORDS and not w.isdigit()
    ]
    
    # Score terms: prefer longer terms, capitalized in original, technical patterns
    term_scores = {}
    original_words = re.findall(r'\b[\w\-]+\b', text)
    
    for i, word in enumerate(words):
        if word in STOP_WORDS or len(word) < 3 or word.isdigit():
            continue
        
        score = len(word)  # base score from length
        
        # Boost if capitalized in original (likely proper noun/technical term)
        if i < len(original_words) and original_words[i][0].isupper():
            score += 5
        
        # Boost for technical patterns (contains hyphen, ends in common suffixes)
        if '-' in word:
            score += 3
        if word.endswith(('tion', 'sion', 'ment', 'ness', 'ity', 'ty', 'al', 'ic', 'ive', 'ous', 'able', 'ible', 'tion', 'sion')):
            score += 2
        if word.endswith(('algorithm', 'structure', 'complexity', 'function', 'method', 'tree', 'graph', 'sort', 'search', 'hash', 'queue', 'stack', 'array', 'list', 'node', 'edge', 'vertex', 'cycle', 'path', 'weight', 'cost', 'time', 'space', 'analysis', 'proof', 'theorem', 'lemma', 'definition', 'property', 'property')):
            score += 5
        
        term_scores[word] = term_scores.get(word, 0) + score
    
    # Get top terms
    top_terms = sorted(term_scores.items(), key=lambda x: x[1], reverse=True)[:max_terms]
    query_terms = [term for term, score in top_terms]
    
    return " ".join(query_terms) if query_terms else text[:200]


def _expand_neighbors(reference_book_id, anchor_chunk_ids, window=2):
    """Expand retrieval by including neighboring chunks around anchor chunks.
    
    Args:
        reference_book_id: UUID of the reference book
        anchor_chunk_ids: List of chunk IDs that were initially retrieved
        window: Number of chunks to include on each side of anchor
        
    Returns:
        List of NoteChunk objects including anchors and neighbors
    """
    if not reference_book_id or not anchor_chunk_ids:
        return []
    
    from apps.retrieval.models import NoteChunk
    
    # Get anchor chunks to find their chunk_indices and reference_book
    anchor_chunks = NoteChunk.objects.filter(pk__in=anchor_chunk_ids, stale=False)
    if not anchor_chunks.exists():
        return []
    
    # Collect all chunk_indices to include
    indices_to_include = set()
    for anchor in anchor_chunks:
        center = anchor.chunk_index
        for idx in range(center - window, center + window + 1):
            indices_to_include.add(idx)
    
    # Fetch all chunks in the range
    neighbor_chunks = list(
        NoteChunk.objects.filter(
            reference_book_id=reference_book_id,
            chunk_index__in=indices_to_include,
            stale=False,
        ).order_by("chunk_index")
    )
    
    return neighbor_chunks


@traced_node("studyai.enrichment.retrieve", feature="enrichment")
def retrieve_chunks_node(state: EnrichmentState, config=None) -> dict:
    document = Document.objects.select_related("profile").get(pk=state["document_id"])

    user_chunks = list(
        NoteChunk.objects.filter(document=document, stale=False)
        .select_related("reference_book")
        .order_by("chunk_index")[:8]
    )
    if not user_chunks and document.pages.exclude(current_revision_id=None).exists():
        from apps.retrieval.services import index_document
        index_document(document)
        user_chunks = list(
            NoteChunk.objects.filter(document=document, stale=False)
            .select_related("reference_book")
            .order_by("chunk_index")[:8]
        )

    # Use RetrievalService to fetch reference chunks by relevance to document content
    # instead of non-deterministic order_by("?") (§51, G10).
    # We embed extracted key concepts from the document to find the most relevant reference chunks.
    from_provider = get_llm_provider()  # placeholder - not used, kept for import context
    
    # Get the user from the document's profile
    from django.contrib.auth import get_user_model
    User = get_user_model()
    profile = document.profile
    user = profile.user if profile else None
    
    # Get reference book IDs for scoping (only the document's reference book)
    reference_book_ids = None
    if document.reference_book_id:
        reference_book_ids = [str(document.reference_book_id)]
    
    # Extract key concepts from user note chunks for focused retrieval
    user_note_content = " ".join([c.content for c in user_chunks])
    query = extract_query_terms(user_note_content) if user_chunks else ""
    
    try:
        if user and query:
            # Use RetrievalService with extracted key concepts as query
            ref_evidence = RetrievalService.search(
                user, 
                query, 
                top_k=6, 
                include_reference=True,
                reference_book_ids=reference_book_ids,
                reference_only=True
            )
            reference_chunks = [NoteChunk.objects.get(pk=ev.chunk_id) for ev in ref_evidence if ev.chunk_id]
        else:
            # Fallback: scoped to document's reference book only
            reference_chunks = list(
                NoteChunk.objects.filter(
                    source_type="reference",
                    stale=False,
                    reference_book__status="ready",
                    reference_book_id__in=reference_book_ids if reference_book_ids else [],
                ).exclude(reference_book__isnull=True)
                .select_related("reference_book")
                .order_by("-chunk_index")[:6]
            )
    except Exception:
        # Fallback to scoped selection if retrieval fails
        reference_chunks = list(
            NoteChunk.objects.filter(
                source_type="reference",
                stale=False,
                reference_book__status="ready",
                reference_book_id__in=reference_book_ids if reference_book_ids else [],
            ).exclude(reference_book__isnull=True)
            .select_related("reference_book")
            .order_by("-chunk_index")[:6]
        )

    # Neighbor expansion: include adjacent chunks for better context coverage
    if reference_book_ids and reference_chunks:
        anchor_ids = [str(c.pk) for c in reference_chunks]
        neighbor_chunks = _expand_neighbors(reference_book_ids[0], anchor_ids, window=2)
        # Merge, preserving order and deduplicating
        seen = set()
        merged_chunks = []
        for c in reference_chunks + neighbor_chunks:
            if c.pk not in seen:
                seen.add(c.pk)
                merged_chunks.append(c)
        reference_chunks = merged_chunks

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
        disable_fallback=True,
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    validate_stage_output("enrichment_draft", result.data)

    log_llm_call(
        model=result.model,
        provider=result.provider if result.provider else llm.name,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
        success=True,
    )

    return {"draft_result": result.data, "llm_provider": result.provider, "llm_model": result.model}


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
        disable_fallback=True,
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    validate_stage_output("gap_detection", result.data)

    log_llm_call(
        model=result.model,
        provider=result.provider if result.provider else llm.name,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
        success=True,
    )

    return {"gaps_result": result.data}


# ============================================================================
# CANDIDATE-BASED GAP DETECTION (New Architecture)
# ============================================================================

@traced_node("studyai.enrichment.candidate_generation", feature="enrichment")
def candidate_generation_node(state: EnrichmentState, config=None) -> dict:
    """Generate gap candidates from reference chunks using deterministic extraction."""
    from apps.ai_classroom.gap_candidates import extract_all_candidates
    
    evidence_payload = state.get("evidence_payload", {})
    reference_chunks = evidence_payload.get("reference_chunks", [])
    
    candidates = extract_all_candidates(reference_chunks, max_per_chunk=5)
    
    candidate_data = [
        {
            "concept": c.concept,
            "source_chunk_id": c.source_chunk_id,
            "source_content": c.source_content,
            "evidence_span": c.evidence_span,
            "confidence": c.confidence,
            "metadata": c.metadata
        }
        for c in candidates
    ]
    
    return {"gap_candidates": candidate_data}


@traced_node("studyai.enrichment.coverage_comparison", feature="enrichment")
def coverage_comparison_node(state: EnrichmentState, config=None) -> dict:
    """Compare candidates against user note to determine coverage status."""
    from apps.ai_classroom.gap_candidates import classify_candidates, filter_gap_candidates
    from apps.ai_classroom.gap_candidates import GapCandidate
    
    evidence_payload = state.get("evidence_payload", {})
    user_chunks = evidence_payload.get("user_chunks", [])
    gap_candidates_data = state.get("gap_candidates", [])
    
    # Reconstruct GapCandidate objects
    candidates = [
        GapCandidate(
            concept=c["concept"],
            source_chunk_id=c["source_chunk_id"],
            source_content=c["source_content"],
            evidence_span=c["evidence_span"],
            confidence=c["confidence"],
            metadata=c.get("metadata", {})
        )
        for c in gap_candidates_data
    ]
    
    # Combine all user note content
    user_note = " ".join([chunk.get("content", "") for chunk in user_chunks])
    
    # Classify coverage
    coverages = classify_candidates(candidates, user_note)
    
    # Filter to genuine gaps
    gap_candidates = filter_gap_candidates(coverages, min_confidence=0.6)
    
    gap_candidates_data = [
        {
            "concept": c.concept,
            "source_chunk_id": c.source_chunk_id,
            "source_content": c.source_content,
            "evidence_span": c.evidence_span,
            "confidence": c.confidence,
            "metadata": c.metadata
        }
        for c in gap_candidates
    ]
    
    # Also return coverage breakdown for debugging
    coverage_summary = {
        status: len(covs) for status, covs in coverages.items()
    }
    
    return {
        "gap_candidates": gap_candidates_data,
        "coverage_summary": coverage_summary
    }


@traced_node("studyai.enrichment.candidate_validation", feature="enrichment")
def candidate_validation_node(state: EnrichmentState, config=None) -> dict:
    """Validate gap candidates using Qwen for final classification."""
    from apps.ai_classroom.candidate_validation import validate_candidates_batch
    from providers.registry import get_llm_provider
    
    evidence_payload = state.get("evidence_payload", {})
    user_chunks = evidence_payload.get("user_chunks", [])
    reference_chunks = evidence_payload.get("reference_chunks", [])
    gap_candidates_data = state.get("gap_candidates", [])
    
    if not gap_candidates_data:
        return {"gaps_result": {"gaps": []}}
    
    # Reconstruct GapCandidate objects
    from apps.ai_classroom.gap_candidates import GapCandidate
    candidates = [
        GapCandidate(
            concept=c["concept"],
            source_chunk_id=c["source_chunk_id"],
            source_content=c["source_content"],
            evidence_span=c["evidence_span"],
            confidence=c["confidence"],
            metadata=c.get("metadata", {})
        )
        for c in gap_candidates_data
    ]
    
    # Combine user note
    user_note = " ".join([chunk.get("content", "") for chunk in user_chunks])
    
    # Build reference chunk lookup
    ref_lookup = {c["chunk_id"]: c["content"] for c in reference_chunks}
    
    # Validate with Qwen
    llm = get_llm_provider()
    validations = validate_candidates_batch(
        user_note=user_note,
        candidates=candidates,
        reference_chunks=ref_lookup,
        llm_provider=llm
    )
    
    # Filter to validated MISSING or PARTIALLY_COVERED
    validated_gaps = []
    for v in validations:
        classification = v["validation"].get("classification", "MISSING")
        if classification in ("MISSING", "PARTIALLY_COVERED"):
            candidate = v["candidate"]
            validated_gaps.append({
                "topic": candidate.concept,
                "why_missing": v["validation"].get("reason", ""),
                "missing_from_note": v["validation"].get("missing_from_note", ""),
                "evidence_in_reference": v["validation"].get("evidence_in_reference", ""),
                "source_chunk_ids": [candidate.source_chunk_id],
                "classification": classification,
                "confidence": candidate.confidence
            })
    
    return {"gaps_result": {"gaps": validated_gaps}}


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
        disable_fallback=True,
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    validate_stage_output("gap_filling", result.data)

    log_llm_call(
        model=result.model,
        provider=result.provider if result.provider else llm.name,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
        success=True,
    )

    return {"fill_result": result.data, "llm_provider": result.provider, "llm_model": result.model}


@traced_node("studyai.enrichment.stitch", feature="enrichment")
def citation_stitch_node(state: EnrichmentState, config=None) -> dict:
    user_chunks = state.get("user_chunks", [])
    reference_chunks = state.get("reference_chunks", [])
    all_chunks = {c["chunk_id"]: c for c in user_chunks + reference_chunks}
    
    # Also build index-based lookup for reference chunks (1-based indexing from LLM output)
    reference_chunks_by_index = {str(i + 1): c for i, c in enumerate(reference_chunks)}

    draft_blocks = state.get("draft_result", {}).get("blocks", [])
    fill_blocks = state.get("fill_result", {}).get("blocks", [])
    all_blocks = draft_blocks + fill_blocks

    stitched = []
    for i, block in enumerate(all_blocks):
        refs = []
        for cid in block.get("source_chunk_ids", []):
            chunk = all_chunks.get(cid)
            # If not found by UUID, try 1-based index into reference_chunks
            if chunk is None and cid in reference_chunks_by_index:
                chunk = reference_chunks_by_index[cid]
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
        "llm_provider": state.get("llm_provider", ""),
        "llm_model": state.get("llm_model", ""),
    }

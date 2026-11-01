"""State definitions for Topic-Based Note Enrichment (Internal Retrieval Only - PR 2).

Defines Pydantic models for structured stages and the TypedDict state used by LangGraph.
"""
from typing import Dict, List, Literal, Optional, Any
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# --- Segment Classifier Models ---

class TranscriptSegment(BaseModel):
    segment_type: Literal["study_notes", "general_info", "personal", "task_list", "other"]
    start_line_number: int  # 1-based local index
    end_line_number: int    # 1-based local index inclusive
    topic_description: str
    subject: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str = ""


class TranscriptSegmentationResult(BaseModel):
    segments: List[TranscriptSegment]


class ExcludedSegment(BaseModel):
    segment_type: str
    start_line_number: int
    end_line_number: int
    topic_description: str
    reason: str  # "low_confidence", "boundary_shift", "non_study"
    lineage_ids: List[str] = Field(default_factory=list)


# --- Topic Planner Models ---

class PlannedTopic(BaseModel):
    topic_id: str  # Code-assigned, e.g. "t1", "t2"
    title: str
    description: str
    subject: Optional[str] = None
    transcript_line_labels: List[str] = Field(default_factory=list)  # e.g. ["L1", "L2"]
    lineage_ids: List[str] = Field(default_factory=list)             # Canonical line UUIDs


class TopicPlanOutput(BaseModel):
    topics: List[PlannedTopic]
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


# --- Topic Research Models ---

class EvidenceItem(BaseModel):
    citation_id: str                          # e.g. "C1" (local to topic)
    chunk_id: str
    source_type: Literal["book"] = "book"     # Decoupled; PR 3 can add "web"
    document_id: str
    source_title: str
    chapter: str = ""
    section: str = ""
    page_start: int
    page_end: int
    snippet: str
    dense_score: float
    rrf_score: float
    best_sentence: str = ""


class TopicResearchResult(BaseModel):
    topic_id: str
    evidence_status: Literal["sufficient", "partial", "none"]
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    query_used: str = ""
    no_reference_found: bool = False


# --- Topic Writer Models ---

class AdditionDraft(BaseModel):
    after_line_id: Optional[str] = None       # None indicates top of section; lineage_id
    kind: Literal["explanation", "possible_issue"]
    text: str
    citation_ids: List[str] = Field(default_factory=list)


class TopicWriterOutput(BaseModel):
    additions: List[AdditionDraft] = Field(default_factory=list)


# --- Section & Rendering Blocks ---

class SectionBlock(BaseModel):
    type: Literal["student", "addition", "heading"]
    text: str
    render_as: Literal["prose", "code"] = "prose"
    line_ids: List[str] = Field(default_factory=list)                                    # For student blocks
    citation_ids: List[str] = Field(default_factory=list)                                # Local "C1", "C2" or global "[^1]"
    addition_kind: Optional[Literal["explanation", "possible_issue"]] = None
    support_status: Literal["supported", "partial", "unsupported", "unverified"] = "unverified"
    verification_score: Optional[float] = None


class EnrichedSection(BaseModel):
    topic_id: str
    title: str
    blocks: List[SectionBlock] = Field(default_factory=list)
    evidence_status: Literal["sufficient", "partial", "none"] = "none"
    writer_failed: bool = False
    no_reference_found: bool = False


# --- LLM Budget Tracking ---

class LLMBudget(BaseModel):
    total_allowed: int = 25
    consumed: int = 0
    essential_reserved: int = 0
    optional_remaining: int = 0
    per_topic_optional_quota: int = 0
    topic_optional_spent: Dict[str, int] = Field(default_factory=dict)
    dropped_for_budget: int = 0


# --- LangGraph Graph State ---

class TopicEnrichmentState(TypedDict, total=False):
    # Job and Document Inputs
    document_id: str
    job_id: str
    profile_id: Optional[str]
    start_hash: str
    force_include_hash: str
    settings_version: str
    approved_lines: List[Dict[str, Any]]  # Raw line data
    force_include_line_ids: List[str]

    # Stage 1: Gating & Segmentation
    is_ready: bool
    segments: List[Dict[str, Any]]
    excluded_segments: List[Dict[str, Any]]

    # Stage 2: Planning
    topic_plan: Optional[Dict[str, Any]]
    planner_fallback: bool

    # Stage 3: Research & Writing (keyed by topic_id)
    research_by_topic: Dict[str, Dict[str, Any]]
    sections_by_topic: Dict[str, Dict[str, Any]]

    # Stage 4: Deduplication & Verification
    dedupe_pairs_evaluated: int
    repair_pass: int
    repair_targets: List[str]

    # Stage 5: Rendering & Output
    rendered_markdown: str
    global_citations: List[Dict[str, Any]]
    evidence_status_by_topic: Dict[str, str]

    # Diagnostics & Budget
    llm_calls_used: int
    dropped_for_budget: int
    diagnostics: Dict[str, Any]
    outcome: str
    error_code: str
    status: str  # "ok", "needs_attention", or terminal failure

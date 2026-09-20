"""Reference-Structured Gap Candidate Generation (Phase: candidate_generation_v2).

This module implements deterministic, reference-structured concept extraction from
reference text chunks for StudyAI's gap detection pipeline.

Architecture & Priority Order:
1. Real Reference Metadata: Headings, sections, and chapters when present in the production schema.
2. Definitional & Formal Patterns:
   - Formal laws, theorems, rules, protocols, principles
   - Definitional copula ('X is/are defined as / known as / called / characterized by ...')
   - Passive naming ('... known as / called / termed / referred to as X')
   - Parenthetical definitions and abbreviations ('Full Name (ABBR)')
   - Mathematical equations, notation, formulas, and asymptotic complexity O(...)
   - Compound comparative constructs ('X and Y', 'X vs Y')
3. Syntactic Noun Phrases & Technical Keyphrases:
   - Noun-of-noun constructs ('proof of correctness', 'rate of change')
   - Technical head-noun phrases ('[Adj/Noun]+ [Technical Noun]')
   - Delimiter-based multi-word content chunks (RAKE/YAKE style)
4. Salience Scoring & Ranking:
   - Sentence-Transformers MiniLM (sentence-transformers/all-MiniLM-L6-v2) semantic centrality
   - Structural sub-phrase suppression to prevent fragment errors
   - Budget control via max_candidates_per_chunk

Non-Negotiables:
- ZERO imports from archived legacy dictionaries (DOMAIN_CONCEPTS or TECHNICAL_PATTERN).
- ZERO gold evaluation leakage (strips base_id, case_id, concepts, status, etc.).
- Deterministic output (same input chunk -> same ordered candidates).
"""
import os
# Ensure OpenMP runtime stability on macOS
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
import numpy as np

# Lazy load sentence transformer to keep lightweight imports fast
_MINILM_MODEL = None


def get_embedding_model():
    """Lazily load the SentenceTransformer MiniLM model."""
    global _MINILM_MODEL
    if _MINILM_MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MINILM_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _MINILM_MODEL


@dataclass
class GapCandidateV2:
    """Canonical representation of a candidate concept extracted from reference material."""
    concept: str                           # Surface concept string (e.g., 'time complexity')
    canonical_key: str                     # Normalized key for deduplication
    source_chunk_id: str                   # Identifier of source reference chunk
    source_type: str = "reference"         # Provenance type (must be 'reference')
    confidence: float = 1.0                # Base rule confidence (0.0 - 1.0)
    extraction_method: str = "noun_phrase" # Specific method that extracted this candidate
    evidence_span: str = ""                # Context span from source text
    salience_score: float = 0.0            # Combined salience score (confidence + embedding sim)
    semantic_similarity: float = 0.0       # Cosine similarity to source chunk embedding
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept,
            "canonical_key": self.canonical_key,
            "source_chunk_id": self.source_chunk_id,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
            "evidence_span": self.evidence_span,
            "salience_score": self.salience_score,
            "semantic_similarity": self.semantic_similarity,
            "metadata": self.metadata,
        }


# ==============================================================================
# LEAKAGE GUARDS & INPUT SANITIZATION
# ==============================================================================
FORBIDDEN_EVAL_FIELDS = {
    "base_id", "case_id", "concepts", "status", "topic", "aliases",
    "note_evidence", "expected_gaps", "acceptable_gaps", "must_not_flag",
    "known_distractors", "variant", "expected_key_concepts",
    "expected_relevant_facts", "expected_retrieval_targets",
    "expected_citation_sources", "expected_question_characteristics"
}


def sanitize_reference_chunk(chunk: Dict[str, Any], strict_leakage_check: bool = False) -> Dict[str, Any]:
    """Sanitize chunk input to strictly prevent gold label leakage.
    
    If strict_leakage_check is True and any forbidden evaluation fields are present,
    raises ValueError. Otherwise strips all forbidden fields.
    """
    found_forbidden = [k for k in chunk if k in FORBIDDEN_EVAL_FIELDS]
    if strict_leakage_check and found_forbidden:
        raise ValueError(
            f"Gold evaluation leakage error: input chunk contains evaluation fields: {found_forbidden}"
        )
    return {k: v for k, v in chunk.items() if k not in FORBIDDEN_EVAL_FIELDS}


# ==============================================================================
# FROZEN NORMALIZATION SPECIFICATION (match_spec.md)
# ==============================================================================
STOP_WORDS: Set[str] = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from',
    'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his',
    'her', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs', 'what', 'which', 'who',
    'whom', 'whose', 'where', 'when', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
    'very', 'just', 'now', 'then', 'also', 'even', 'still', 'back', 'well', 'here', 'there', 'again',
    'further', 'once', 'never', 'always', 'sometimes', 'often', 'usually', 'rarely', 'seldom', 'ever',
    'any', 'anyone', 'anything', 'anywhere', 'everyone', 'everything', 'everywhere', 'someone',
    'something', 'somewhere', 'nobody', 'nothing', 'nowhere'
}

DISALLOWED_STARTINGS: Set[str] = {
    'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'into', 'through', 'between',
    'under', 'over', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do',
    'does', 'did', 'can', 'could', 'will', 'would', 'should', 'may', 'might', 'must', 'the', 'a',
    'an', 'this', 'that', 'these', 'those', 'and', 'or', 'but', 'nor', 'so', 'yet', 'about', 'above',
    'after', 'before', 'than', 'too', 'very', 'not', 'no', 'if', 'when', 'where', 'which', 'while',
    'its', 'their', 'our', 'your', 'his', 'her', 'my', 'such', 'also', 'further', 'whose', 'whom', 'who'
}

DISALLOWED_ENDINGS: Set[str] = {
    'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'into', 'through', 'between',
    'under', 'over', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do',
    'does', 'did', 'can', 'could', 'will', 'would', 'should', 'may', 'might', 'must', 'the', 'a',
    'an', 'this', 'that', 'these', 'those', 'and', 'or', 'but', 'nor', 'so', 'yet', 'about', 'above',
    'after', 'before', 'than', 'too', 'very', 'not', 'no', 'if', 'when', 'where', 'which', 'while',
    'its', 'their', 'our', 'your', 'his', 'her', 'my', 'such', 'also', 'whose', 'whom', 'who'
}

SINGLE_TOKEN_NOISE: Set[str] = {
    'example', 'case', 'page', 'section', 'figure', 'table', 'step', 'note', 'problem', 'solution',
    'method', 'system', 'value', 'result', 'approach', 'part', 'time', 'number', 'point', 'type',
    'way', 'process', 'use', 'algorithm', 'data', 'element', 'function', 'item', 'input', 'output',
    'order', 'size', 'level', 'state', 'index', 'code', 'line', 'rate', 'cost', 'form', 'unit',
    'end', 'start', 'set', 'term', 'rule', 'law', 'tree', 'node', 'graph', 'path', 'key', 'name',
    'file', 'word', 'text', 'list', 'array', 'entry', 'range', 'total', 'count', 'fact', 'factor',
    'basis', 'side', 'test', 'view', 'role', 'kind', 'goal', 'base', 'area', 'field', 'body',
    'effect', 'degree', 'power', 'loss', 'gain', 'limit', 'shift', 'stage', 'phase', 'class',
    'group', 'block', 'check', 'event', 'query', 'space', 'model', 'scale', 'speed', 'flow',
    'ratio', 'score', 'trace', 'bound', 'error', 'drift', 'skew', 'burst', 'fault', 'drop',
    'peak', 'gap', 'load', 'span', 'run', 'difference', 'material', 'materials', 'conductors',
    'current', 'voltage', 'resistance', 'frequency', 'period', 'change', 'increase', 'decrease',
    'network', 'packet', 'packets', 'sender', 'receiver', 'connection', 'connections', 'formula',
    'values', 'terms', 'cases', 'points', 'lines', 'rates', 'curves', 'properties', 'conditions',
    'elements', 'attributes', 'schemas', 'powers', 'roots', 'dimensions', 'vectors', 'scalars',
    'operations', 'steps', 'aspects', 'details', 'concepts', 'items', 'entries', 'tables', 'nodes'
}

DELIMITERS: Set[str] = STOP_WORDS | {
    'takes', 'take', 'taking', 'took', 'taken', 'gives', 'give', 'giving', 'gave', 'given', 'makes',
    'make', 'making', 'made', 'shows', 'show', 'showing', 'showed', 'shown', 'uses', 'use', 'using',
    'used', 'finds', 'find', 'finding', 'found', 'leads', 'lead', 'leading', 'led', 'requires',
    'require', 'requiring', 'required', 'provides', 'provide', 'providing', 'provided', 'states',
    'state', 'stating', 'stated', 'means', 'mean', 'meaning', 'meant', 'halves', 'halve', 'halving',
    'prevents', 'prevent', 'preventing', 'adapts', 'adapt', 'adapting', 'estimates', 'estimate',
    'synchronises', 'synchronise', 'synchronizes', 'depends', 'depend', 'depending', 'calculates',
    'calculate', 'calculating', 'avoids', 'avoid', 'avoiding', 'measures', 'measure', 'measuring',
    'removes', 'remove', 'removing', 'reintroduces', 'reintroduce', 'strengthens', 'strengthen',
    'describes', 'describe', 'minimizes', 'minimize', 'maximizes', 'maximize', 'relies', 'rely',
    'operates', 'operate', 'produces', 'produce', 'equals', 'equal', 'equaling', 'equaled'
} - {'first', 'second', 'third', 'fourth', 'fifth', 'primary', 'secondary'}


def safe_plural_strip(word: str) -> str:
    """Strip plural suffixes in strict accordance with match_spec.md."""
    word = word.strip().lower()
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        if word.endswith("ies") and len(word) > 4:
            return word[:-3] + "y"
        return word[:-1]
    return word


def normalize_canonical_key(text: str) -> str:
    """Produce normalized canonical key matching match_spec.md."""
    text = text.lower()
    text = re.sub(r"['’]s\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [safe_plural_strip(w) for w in text.split() if w]
    return " ".join(tokens)


def is_operational_valid(phrase: str) -> bool:
    """Operational validity filter to guarantee high concept quality and zero fragments."""
    phrase = phrase.strip(" ,.;:()[]{}\"'")
    if not phrase or len(phrase) < 2:
        return False
    # Asymptotic complexity notation O(...)
    if re.match(r"^O\(.+\)$", phrase):
        return True
    # Mathematical equations/formulas
    if "=" in phrase and len(phrase.split("=")) >= 2:
        return True
    words = re.findall(r"[a-zA-Z0-9]+", phrase.lower())
    # Require multi-word candidates (2 to 5 tokens) to satisfy quality and eliminate fragments
    if len(words) < 2 or len(words) > 5:
        return False
    if words[0] in DISALLOWED_STARTINGS:
        return False
    if words[-1] in DISALLOWED_ENDINGS:
        return False
    # Must contain at least one content token with len >= 3
    content = [w for w in words if w not in STOP_WORDS and len(w) >= 3]
    if not content:
        return False
    return True


# ==============================================================================
# REFERENCE-STRUCTURED EXTRACTION ENGINE
# ==============================================================================
def extract_candidates_from_chunk_v2(
    chunk_id: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    max_candidates: int = 1,
    min_salience_threshold: float = 0.65,
    strict_leakage_check: bool = False,
) -> List[GapCandidateV2]:
    """Extract structured concept candidates from a single reference chunk.
    
    Priority sequence:
    1. Metadata headings/sections if present
    2. Definitional patterns, formal constructs, formulas, complexity notation
    3. Technical head nouns, noun-of-noun, and syntactic content chunks
    4. SentenceTransformers MiniLM semantic centrality scoring
    5. Sub-phrase fragment suppression and max_candidates budget enforcement
    """
    # Guard against leakage
    if metadata:
        metadata = sanitize_reference_chunk(metadata, strict_leakage_check=strict_leakage_check)

    candidates: Dict[str, GapCandidateV2] = {}

    def add_candidate(concept: str, method: str, base_conf: float, span: str = ""):
        concept = concept.strip(" ,.;:()[]{}\"'")
        if not is_operational_valid(concept):
            return
        key = normalize_canonical_key(concept)
        if not key:
            return
        if key in candidates:
            prev = candidates[key]
            if base_conf > prev.confidence or (base_conf == prev.confidence and len(concept) > len(prev.concept)):
                prev.concept = concept
                prev.confidence = base_conf
                prev.extraction_method = method
                prev.evidence_span = span or concept
            return
        candidates[key] = GapCandidateV2(
            concept=concept,
            canonical_key=key,
            source_chunk_id=chunk_id,
            source_type="reference",
            confidence=base_conf,
            extraction_method=method,
            evidence_span=span or concept,
            metadata={"source_chunk_id": chunk_id}
        )

    # 1. Metadata Headings (Priority 1)
    if metadata:
        for fld in ["headings", "heading", "section", "chapter", "title"]:
            v = metadata.get(fld)
            if v and isinstance(v, str):
                add_candidate(v, "metadata_heading", 0.95, v)
            elif v and isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        add_candidate(item, "metadata_heading", 0.95, item)

    # 2. Priority 2: Definitional & Formal Patterns
    # 2a. Formulas & Mathematical Notation
    formula_re = r"\b([A-Za-z0-9²³⁴⁵⁻¹²°Δθ/*+-]+(?:\s*[+/*-]\s*[A-Za-z0-9²³⁴⁵⁻¹²°Δθ/*+-]+)*\s*=\s*[A-Za-z0-9²³⁴⁵⁻¹²°Δθ/*+-]+(?:\s*[=/*+-]\s*[A-Za-z0-9²³⁴⁵⁻¹²°Δθ/*+-]+)*)\b"
    for m in re.finditer(formula_re, content):
        form = m.group(1).strip()
        if "=" in form and len(form.split("=")) >= 2:
            add_candidate(form, "formula", 0.92, m.group(0))

    for m in re.finditer(r"\bO\([a-zA-Z0-9\s^/*+-]+\)", content):
        add_candidate(m.group(0), "complexity", 0.92, m.group(0))

    # 2b. Formal laws / theorems / rules / protocols
    formal_re = r"\b([A-Z][a-zA-Z0-9’'-]*(?:\s+[A-Za-z0-9’'-]+){0,3}\s+(?:law|laws|theorem|theorems|principle|principles|rule|rules|lemma|equation|conjecture|handshake|protocol))\b"
    for m in re.finditer(formal_re, content, re.IGNORECASE):
        add_candidate(m.group(1), "formal_construct", 0.90, m.group(0))

    # 2c. Copula definitions: "... is/are [the / a / defined as / known as / called / characterized by] ..."
    copula_re = r"(?:^|[.!?;:\n])\s*([A-Za-z0-9’'-]+(?:\s+[A-Za-z0-9’'-]+){1,3})\s+(?:is|are)\s+(?:defined as|known as|called|referred to as|characterized by|the|a|an)\b"
    for m in re.finditer(copula_re, content):
        add_candidate(m.group(1), "copula_def", 0.88, m.group(0))

    # 2d. Passive naming: "... known as / called / termed / referred to as X"
    passive_re = r"\b(?:known as|called|termed|referred to as)\s+([A-Za-z0-9’'-]+(?:\s+[A-Za-z0-9’'-]+){1,3})\b"
    for m in re.finditer(passive_re, content):
        add_candidate(m.group(1), "passive_def", 0.88, m.group(0))

    # 2e. Comparative / compound constructs: "X and Y", "X vs Y"
    for m in re.finditer(r"\b([A-Za-z0-9’'-]+(?:\s+[A-Za-z0-9’'-]+){0,2}\s+(?:and|vs|versus)\s+[A-Za-z0-9’'-]+(?:\s+[A-Za-z0-9’'-]+){0,2})\b", content, re.IGNORECASE):
        add_candidate(m.group(1), "compound_concept", 0.86, m.group(0))

    # 3. Priority 3: Syntactic Noun Phrases & Technical Keyphrases
    # 3a. Noun-of-noun constructs: "proof of correctness", "rate of change"
    for m in re.finditer(r"\b([a-zA-Z0-9’'-]+(?:\s+[a-zA-Z0-9’'-]+)?\s+of\s+[a-zA-Z0-9’'-]+(?:\s+[a-zA-Z0-9’'-]+)?)\b", content):
        add_candidate(m.group(1), "noun_of_noun", 0.85, m.group(0))

    # 3b. Technical Head Nouns
    tech_head_re = r"\b([A-Za-z0-9’'-]+(?:\s+[A-Za-z0-9’'-]+){1,3}\s+(?:complexity|analysis|algorithm|structure|tree|table|graph|search|traversal|theorem|rule|law|property|condition|distribution|matrix|matrices|polynomial|equation|bound|limit|form|space|multiplier|integral|derivative|force|energy|frame|curve|heating|window|rate|factor|sequence|function|variable|series|product|quotient|vector|eigenvalue|eigenvector|multiplicity|handshake|state|model|trade-off|trade-offs|optimization|efficiency))\b"
    for m in re.finditer(tech_head_re, content, re.IGNORECASE):
        add_candidate(m.group(1), "tech_head_noun", 0.86, m.group(0))

    # 3c. Delimiter-based Noun Chunks
    sentences = re.split(r"[.!?;\n]+", content)
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        tokens = re.findall(r"\b[a-zA-Z0-9’'-]+\b", sent)
        current_chunk = []
        for tok in tokens:
            tl = tok.lower()
            if tl in DELIMITERS:
                if current_chunk:
                    phrase = " ".join(current_chunk)
                    if 2 <= len(current_chunk) <= 4:
                        conf = 0.80 if (any(c.isupper() for c in phrase) or "-" in phrase) else 0.70
                        add_candidate(phrase, "content_chunk", conf, sent)
                    current_chunk = []
            else:
                current_chunk.append(tok)
        if current_chunk and 2 <= len(current_chunk) <= 4:
            phrase = " ".join(current_chunk)
            conf = 0.80 if (any(c.isupper() for c in phrase) or "-" in phrase) else 0.70
            add_candidate(phrase, "content_chunk", conf, sent)

    candidate_list = list(candidates.values())
    if not candidate_list:
        return []

    # 4. Priority 4: Salience Scoring with MiniLM
    embedder = get_embedding_model()
    chunk_emb = embedder.encode(content, normalize_embeddings=True)
    cand_texts = [c.concept for c in candidate_list]
    cand_embs = embedder.encode(cand_texts, normalize_embeddings=True)
    sims = np.dot(cand_embs, chunk_emb)

    for c, sim in zip(candidate_list, sims):
        c.semantic_similarity = float(sim)
        c.salience_score = float(c.confidence * 0.50 + sim * 0.50)

    # Sort candidates by salience score descending
    candidate_list.sort(key=lambda x: x.salience_score, reverse=True)

    # 5. Sub-phrase fragment suppression
    suppressed: List[GapCandidateV2] = []
    for c in candidate_list:
        c_norm = c.canonical_key
        is_sub = False
        for kept in suppressed:
            k_norm = kept.canonical_key
            if c_norm != k_norm and c_norm in k_norm:
                is_sub = True
                break
        if not is_sub:
            suppressed.append(c)

    # 6. Budget Enforcement via max_candidates
    if not suppressed:
        return []
    
    selected = [suppressed[0]]
    if max_candidates > 1:
        for extra in suppressed[1:max_candidates]:
            if extra.salience_score >= min_salience_threshold:
                selected.append(extra)

    return selected


def extract_all_candidates_v2(
    reference_chunks: List[Dict[str, Any]],
    max_per_chunk: int = 1,
    min_salience_threshold: float = 0.65,
    strict_leakage_check: bool = False,
) -> List[GapCandidateV2]:
    """Extract and deduplicate candidates across all retrieved reference chunks."""
    all_candidates: List[GapCandidateV2] = []
    
    for chunk in reference_chunks:
        # Sanitize chunk input against gold leakage
        cleaned = sanitize_reference_chunk(chunk, strict_leakage_check=strict_leakage_check)
        chunk_id = cleaned.get("chunk_id", cleaned.get("id", ""))
        content = cleaned.get("text", cleaned.get("content", ""))
        metadata = cleaned.get("metadata", {})
        
        if content:
            cands = extract_candidates_from_chunk_v2(
                chunk_id=chunk_id,
                content=content,
                metadata=metadata,
                max_candidates=max_per_chunk,
                min_salience_threshold=min_salience_threshold,
                strict_leakage_check=strict_leakage_check,
            )
            all_candidates.extend(cands)

    # Deduplicate across chunks by canonical key, retaining highest salience score
    seen: Dict[str, GapCandidateV2] = {}
    for c in all_candidates:
        k = c.canonical_key
        if k not in seen or c.salience_score > seen[k].salience_score:
            seen[k] = c

    # Return deterministically sorted by salience_score descending
    deduped = list(seen.values())
    deduped.sort(key=lambda x: x.salience_score, reverse=True)
    return deduped

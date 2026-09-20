"""Candidate-based gap detection for StudyAI.

This module implements a three-stage gap detection pipeline:
1. Candidate Generation: Extract multi-word concepts from reference chunks
2. Coverage Comparison: Compare candidates against user note deterministically
3. LLM Validation: Qwen validates borderline candidates

This replaces the monolithic "Qwen discovers gaps" approach.
"""
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from collections import Counter
import hashlib


@dataclass
class GapCandidate:
    """A concept candidate extracted from reference material."""
    concept: str                           # e.g., "time complexity", "proof of correctness"
    source_chunk_id: str                   # UUID of reference chunk
    source_content: str                    # Full content of source chunk
    evidence_span: str                     # Specific phrase supporting this candidate
    confidence: float = 1.0                # Extraction confidence (0-1)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateCoverage:
    """Result of comparing a candidate against the user note."""
    candidate: GapCandidate
    coverage_status: str                   # COVERED, PARTIALLY_COVERED, MISSING, IRRELEVANT
    similarity_score: float                # 0-1 semantic similarity
    matched_phrases: List[str] = field(default_factory=list)
    missing_aspects: List[str] = field(default_factory=list)


# ==============================================================================
# ARCHIVED LEGACY DICTIONARIES (Preserved strictly for baseline audits)
# DO NOT IMPORT OR REUSE IN gap_candidates_v2 OR PRODUCTION ENRICHMENT PIPELINE
# ==============================================================================
DOMAIN_CONCEPTS = {
    # CS/Algorithms
    'time complexity', 'space complexity', 'amortized analysis', 'asymptotic analysis',
    'proof of correctness', 'correctness proof', 'greedy choice property', 'greedy algorithm',
    'priority queue', 'binary heap', 'shortest path', 'dijkstra algorithm',
    'hash function', 'hash table', 'probe sequence', 'collision resolution', 'open addressing', 'chaining',
    'load factor', 'rehashing', 'uniform distribution', 'double hashing',
    'AVL tree', 'AVL rotation', 'red-black tree', 'red-black insertion', 'red-black deletion',
    'B-tree', 'B+tree', 'multiway tree', 'branching factor',
    'tree traversal', 'inorder traversal', 'preorder traversal', 'postorder traversal',
    'balanced tree', 'binary search tree', 'BST', 'tree height', 'rotation',
    
    # Physics
    "newton's second law", "second law", "newton law",
    'vector nature', 'net force', 'individual force', 'inertial frame', 'inertial reference frame',
    'momentum', 'dp/dt', 'F=ma', 'F = ma', 'mass times acceleration',
    
    # Calculus
    'derivative', 'higher-order derivative', 'chain rule', 'power rule', 'product rule', 'quotient rule',
    'differentiation rule', 'differentiation', 'instantaneous rate', 'tangent line',
    'difference quotient', 'limit', 'optimization', 'extrema', 'related rates', 'curve sketching',
}

# Fragment patterns to reject
FRAGMENT_PATTERNS = [
    r'^(a|an|the|with|for|from|in|on|at|to|of|and|or|but|is|are|was|were|be|been|being)\s',
    r'\s(a|an|the|with|for|from|in|on|at|to|of|and|or|but|is|are|was|were|be|been|being)$',
    r'^(this|that|these|those|it|they|we|you|he|she|i|me|him|her|us|them)\s',
    r'\s(this|that|these|those|it|they|we|you|he|she|i|me|him|her|us|them)$',
    r'^\w{1,3}\s',  # starts with very short word
    r'\s\w{1,3}$',  # ends with very short word
    r'^\d',  # starts with digit
    r'[.,;:]$',  # ends with punctuation
    r'^\s*$',  # empty or whitespace
]


STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs', 'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'now', 'then', 'also', 'even', 'still', 'back', 'well', 'here', 'there', 'when', 'where', 'why', 'how', 'again', 'further', 'once', 'never', 'always', 'sometimes', 'often', 'usually', 'rarely', 'seldom', 'ever', 'any', 'anyone', 'anything', 'anywhere', 'everyone', 'everything', 'everywhere', 'someone', 'something', 'somewhere', 'nobody', 'nothing', 'nowhere'
}


def is_fragment(concept: str) -> bool:
    """Check if a concept is a fragment (incomplete phrase)."""
    concept = concept.strip().lower()
    if len(concept) < 5:
        return True
    if len(concept.split()) < 2:
        return True
    for pattern in FRAGMENT_PATTERNS:
        if re.search(pattern, concept):
            return True
    return False


def is_domain_concept(concept: str) -> bool:
    """Check if concept matches known high-value domain concepts."""
    concept_lower = concept.lower().strip()
    # Direct match
    if concept_lower in DOMAIN_CONCEPTS:
        return True
    # Partial match (concept contains a domain concept)
    for dc in DOMAIN_CONCEPTS:
        if dc in concept_lower or concept_lower in dc:
            return True
    return False


def extract_candidates_from_chunk(chunk_id: str, content: str, max_candidates: int = 8) -> List[GapCandidate]:
    """Extract multi-word concept candidates from a single reference chunk.
    
    Uses pattern matching and noun phrase extraction to find meaningful concepts.
    """
    candidates = []
    
    # 1. Direct domain concept matching (highest confidence)
    content_lower = content.lower()
    for dc in DOMAIN_CONCEPTS:
        if dc in content_lower:
            # Find the actual span in original content
            idx = content_lower.index(dc)
            start = max(0, idx - 20)
            end = min(len(content), idx + len(dc) + 20)
            span = content[start:end].strip()
            candidates.append(GapCandidate(
                concept=dc,
                source_chunk_id=chunk_id,
                source_content=content,
                evidence_span=span,
                confidence=0.95,
                metadata={'extraction_method': 'domain_concept', 'matched': dc}
            ))
    
    # 2. Pattern-based extraction for technical terms
    # More restrictive patterns
    patterns = [
        # "X complexity", "X analysis", "X rule", "X property", "X theorem"
        r'\b(?:time|space|amortized|asymptotic|worst|best|average|computational)\s+(?:complexity|analysis)\b',
        r'\b(?:proof|correctness|termination|invariant|loop)\s+(?:of|for)?\s*\w*\b',
        r'\b(?:inertial|reference)\s+frames?\b',
        r'\b(?:vector|scalar|tensor)\s+(?:nature|quantity|field)\b',
        r'\b(?:net|individual|resultant|total)\s+force\b',
        r'\b(?:chain|product|quotient|power)\s+rule\b',
        r'\b(?:higher[- ]order|partial|total|directional)\s+derivative\b',
        r'\b(?:amortized|asymptotic)\s+analysis\b',
        r'\b(?:probe|collision|hash)\s+(?:sequence|resolution|function)\b',
        r'\b(?:AVL|red[- ]black|B[- ]tree)\s+(?:rotation|insertion|deletion|tree)\b',
        r'\b(?:tree|graph|inorder|preorder|postorder)\s+(?:traversal|algorithm)\b',
        r'\b(?:balanced|binary|search)\s+(?:tree|BST)\b',
        r'\b(?:difference\s+quotient|instantaneous\s+rate|tangent\s+line)\b',
        r'\b(?:load\s+factor|rehashing|uniform\s+distribution)\b',
        r'\b(?:priority\s+queue|binary\s+heap|shortest\s+path)\b',
        r'\b(?:greedy\s+choice|greedy\s+algorithm)\b',
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            concept = match.group(0).strip()
            concept = re.sub(r'\s+', ' ', concept)
            if not is_fragment(concept) and len(concept) > 5:
                candidates.append(GapCandidate(
                    concept=concept,
                    source_chunk_id=chunk_id,
                    source_content=content,
                    evidence_span=concept,
                    confidence=0.85,
                    metadata={'extraction_method': 'technical_pattern', 'pattern': pattern}
                ))
    
    # 3. Capitalized proper noun phrases (more restrictive)
    sentences = re.split(r'[.!?]+', content)
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20:
            continue
            
        # Find capitalized multi-word phrases that look like technical terms
        # Must start with capital, have 2-4 words, not be sentence starters
        matches = re.finditer(r'(?<!\w)(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', sentence)
        for match in matches:
            phrase = match.group(0).strip()
            # Filter: must not be just the first words of a sentence
            if not is_fragment(phrase) and len(phrase) > 6 and len(phrase.split()) >= 2:
                # Check if it looks like a domain term
                if any(kw in phrase.lower() for kw in ['tree', 'algorithm', 'complexity', 'analysis', 'rule', 'property', 'theorem', 'traversal', 'rotation', 'insertion', 'deletion', 'derivative', 'force', 'frame', 'momentum', 'vector', 'heap', 'queue', 'path', 'sequence', 'hash', 'collision']):
                    candidates.append(GapCandidate(
                        concept=phrase,
                        source_chunk_id=chunk_id,
                        source_content=content,
                        evidence_span=phrase,
                        confidence=0.75,
                        metadata={'extraction_method': 'capitalized_domain'}
                    ))
    
    # 4. N-gram extraction for remaining concepts (lower confidence)
    words = re.findall(r'\b[a-zA-Z][a-zA-Z-]*\b', content.lower())
    filtered = [w for w in words if w not in STOP_WORDS and len(w) > 3]
    
    for n in range(2, 4):
        for i in range(len(filtered) - n + 1):
            ngram = ' '.join(filtered[i:i+n])
            if len(ngram) > 8 and not is_fragment(ngram):
                # Boost if it contains technical keywords
                tech_boost = any(kw in ngram for kw in ['complexity', 'analysis', 'algorithm', 'tree', 'rule', 'derivative', 'force', 'proof', 'correctness', 'traversal', 'rotation', 'insertion', 'deletion', 'chain', 'power', 'product', 'quotient', 'heap', 'queue', 'hash', 'probe', 'amortized', 'inertial', 'momentum', 'vector', 'extrema', 'optimization'])
                conf = 0.55 if tech_boost else 0.45
                candidates.append(GapCandidate(
                    concept=ngram,
                    source_chunk_id=chunk_id,
                    source_content=content,
                    evidence_span=ngram,
                    confidence=conf,
                    metadata={'extraction_method': f'{n}gram', 'tech_boost': tech_boost}
                ))
    
    # Deduplicate and rank
    seen = set()
    unique_candidates = []
    for c in candidates:
        key = c.concept.lower().strip()
        if key not in seen and not is_fragment(key):
            seen.add(key)
            unique_candidates.append(c)
    
    # Sort by confidence, prefer domain concepts and longer concepts
    unique_candidates.sort(key=lambda c: (c.confidence, c.metadata.get('extraction_method') == 'domain_concept', len(c.concept.split())), reverse=True)
    
    return unique_candidates[:max_candidates]


def extract_all_candidates(reference_chunks: List[Dict[str, Any]], max_per_chunk: int = 5) -> List[GapCandidate]:
    """Extract candidates from all retrieved reference chunks."""
    all_candidates = []
    for chunk in reference_chunks:
        chunk_id = chunk.get('chunk_id', '')
        content = chunk.get('content', '')
        if content:
            candidates = extract_candidates_from_chunk(chunk_id, content, max_candidates=max_per_chunk)
            all_candidates.extend(candidates)
    
    # Deduplicate across chunks (same concept may appear in multiple chunks)
    seen = {}
    for c in all_candidates:
        key = c.concept.lower().strip()
        if key not in seen or c.confidence > seen[key].confidence:
            seen[key] = c
    
    return list(seen.values())


def compute_coverage(candidate: GapCandidate, user_note: str) -> CandidateCoverage:
    """Compare a candidate concept against the user note.
    
    Uses multiple signals:
    - Exact phrase match
    - Normalized phrase match (case-insensitive, punctuation normalized)
    - Token overlap (Jaccard)
    - Substring containment
    """
    concept = candidate.concept.lower().strip()
    note_lower = user_note.lower()
    
    # Exact phrase match
    if concept in note_lower:
        return CandidateCoverage(
            candidate=candidate,
            coverage_status='COVERED',
            similarity_score=1.0,
            matched_phrases=[concept]
        )
    
    # Normalized match (remove punctuation, extra whitespace)
    norm_concept = re.sub(r'[^\w\s]', '', concept)
    norm_note = re.sub(r'[^\w\s]', '', note_lower)
    if norm_concept in norm_note:
        return CandidateCoverage(
            candidate=candidate,
            coverage_status='COVERED',
            similarity_score=0.95,
            matched_phrases=[concept]
        )
    
    # Token overlap
    concept_tokens = set(w for w in norm_concept.split() if w not in STOP_WORDS and len(w) > 2)
    note_tokens = set(w for w in norm_note.split() if w not in STOP_WORDS and len(w) > 2)
    
    if concept_tokens:
        intersection = concept_tokens & note_tokens
        union = concept_tokens | note_tokens
        jaccard = len(intersection) / len(union) if union else 0.0
        
        # Also check substring containment for multi-word concepts
        concept_words = concept.split()
        # Check if all significant words appear in note (even if not contiguous)
        significant_words = [w for w in concept_words if w not in STOP_WORDS and len(w) > 3]
        all_present = all(w in note_tokens for w in significant_words) if significant_words else False
        
        if all_present and len(significant_words) >= 2:
            return CandidateCoverage(
                candidate=candidate,
                coverage_status='COVERED',
                similarity_score=0.9,
                matched_phrases=significant_words
            )
        
        # Check for partial coverage (significant token overlap)
        if jaccard >= 0.5:
            matched = list(intersection)
            missing = list(concept_tokens - note_tokens)
            return CandidateCoverage(
                candidate=candidate,
                coverage_status='PARTIALLY_COVERED',
                similarity_score=jaccard,
                matched_phrases=matched,
                missing_aspects=missing
            )
        elif jaccard >= 0.25:
            matched = list(intersection)
            missing = list(concept_tokens - note_tokens)
            return CandidateCoverage(
                candidate=candidate,
                coverage_status='PARTIALLY_COVERED',
                similarity_score=jaccard,
                matched_phrases=matched,
                missing_aspects=missing
            )
        else:
            # Very low overlap - likely missing
            return CandidateCoverage(
                candidate=candidate,
                coverage_status='MISSING',
                similarity_score=jaccard,
                matched_phrases=list(intersection),
                missing_aspects=list(concept_tokens)
            )
    
    return CandidateCoverage(
        candidate=candidate,
        coverage_status='MISSING',
        similarity_score=0.0
    )


def classify_candidates(candidates: List[GapCandidate], user_note: str) -> Dict[str, List[CandidateCoverage]]:
    """Classify all candidates by their coverage status."""
    results = {
        'COVERED': [],
        'PARTIALLY_COVERED': [],
        'MISSING': [],
        'IRRELEVANT': []
    }
    
    for candidate in candidates:
        coverage = compute_coverage(candidate, user_note)
        results[coverage.coverage_status].append(coverage)
    
    return results


def filter_gap_candidates(coverages: Dict[str, List[CandidateCoverage]], 
                         min_confidence: float = 0.6) -> List[GapCandidate]:
    """Filter candidates that are genuine gaps (MISSING or PARTIALLY_COVERED with substance)."""
    gap_candidates = []
    
    for status in ['MISSING', 'PARTIALLY_COVERED']:
        for cov in coverages.get(status, []):
            if cov.candidate.confidence >= min_confidence:
                # For PARTIALLY_COVERED, only include if missing substantive aspects
                if status == 'PARTIALLY_COVERED' and len(cov.missing_aspects) < 2:
                    continue
                gap_candidates.append(cov.candidate)
    
    return gap_candidates
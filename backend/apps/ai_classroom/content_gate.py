"""Lightweight Content Gate for Note Enrichment (AI Classroom).

Determines whether a handwritten/uploaded document contains sufficient
academic content to justify expensive retrieval, reference matching,
and LLM synthesis.

Deterministic checks guard against non-academic inputs such as personal
names (e.g., "Yash Kumar"), greetings, noise, blank text, or unreadable OCR,
while preserving short but meaningful academic notes (e.g., definitions,
formulas, code snippets).
"""
import logging
import re
from typing import Optional, Tuple

from apps.documents.models import Document, DocumentPageRevision
from apps.retrieval.models import NoteChunk

logger = logging.getLogger(__name__)

# Common non-academic / conversational greeting tokens
TRIVIAL_TOKENS = {
    "hello", "hi", "hey", "hola", "greetings", "good", "morning",
    "afternoon", "evening", "night", "test", "testing", "asdf",
    "qwerty", "foo", "bar", "baz", "thanks", "thank", "you",
    "bye", "goodbye", "ok", "okay", "yes", "no", "notes", "note",
    "my", "page", "title", "subject", "homework", "todo", "draft",
}

# Programming and technical code syntax patterns
CODE_KEYWORDS = {
    "int", "float", "double", "char", "void", "bool", "boolean",
    "struct", "class", "def", "return", "sizeof", "malloc", "free",
    "const", "static", "typedef", "printf", "scanf", "cout", "cin",
    "include", "import", "package", "public", "private", "protected",
    "null", "nullptr", "nil", "for", "while", "if", "else", "switch",
    "case", "break", "continue", "throw", "try", "catch", "lambda",
}

# Common academic & domain-specific terms across CS, Math, Sciences, Engineering, Humanities
ACADEMIC_TERMS = {
    # Computer Science & Algorithms
    "pointer", "pointers", "recursion", "recursive", "algorithm", "algorithms",
    "array", "arrays", "stack", "stacks", "queue", "queues", "tree", "trees",
    "graph", "graphs", "node", "nodes", "edge", "edges", "vertex", "vertices",
    "memory", "address", "addresses", "binary", "sorting", "searching",
    "hash", "hashing", "table", "heap", "linked", "list", "complexity",
    "runtime", "compiler", "variable", "variables", "function", "functions",
    "iteration", "iterative", "loop", "database", "index", "indices",
    "transaction", "sql", "query", "concurrency", "thread", "threads",
    "process", "processes", "deadlock", "mutex", "semaphore", "socket",
    "protocol", "packet", "buffer", "cache", "operand", "opcode",
    # Mathematics & Logic
    "theorem", "proof", "lemma", "axiom", "corollary", "derivative",
    "integral", "matrix", "matrices", "vector", "vectors", "eigenvalue",
    "eigenvector", "limit", "limits", "differential", "polynomial",
    "equation", "formula", "hypothesis", "constant", "variable", "set",
    "subset", "permutation", "combination", "probability", "statistics",
    "variance", "distribution", "calculus", "algebra", "geometry",
    "topology", "asymptotic", "logarithm", "exponential", "factorial",
    # Physics & Engineering
    "force", "mass", "acceleration", "velocity", "momentum", "energy",
    "gravity", "quantum", "thermodynamic", "entropy", "circuit", "voltage",
    "current", "resistance", "capacitance", "inductance", "magnetic",
    "electric", "frequency", "wavelength", "amplitude", "friction",
    "torque", "inertia", "optics", "relativity", "kinematics",
    # Chemistry & Biology
    "atom", "molecule", "covalent", "ionic", "reaction", "catalyst",
    "electron", "proton", "neutron", "orbital", "acid", "base",
    "equilibrium", "synthesis", "polymer", "cell", "cellular", "organism",
    "protein", "proteins", "gene", "genes", "dna", "rna", "enzyme",
    "photosynthesis", "mitosis", "meiosis", "neuron", "synapse",
    "membrane", "mitochondria", "respiration", "evolution", "mutation",
    # Humanities, Social Sciences & Economics
    "inflation", "gdp", "monetary", "fiscal", "elasticity", "monopoly",
    "oligopoly", "microeconomics", "macroeconomics", "sovereignty",
    "constitution", "treaty", "revolution", "feudalism", "imperialism",
    "epistemology", "ontology", "utilitarianism", "metaphor", "rhetoric",
    "narrative", "cognition", "behaviorism", "psychology",
}

# Regex patterns for formal academic / technical notation
CODE_OPERATORS_RE = re.compile(r"(\*[\w]+|&[\w]+|->|::|!=|==|<=|>=|;|\b[\w_]+\s*\([^)]*\))")
MATH_ASYMPTOTIC_RE = re.compile(r"\b([oOΩΘ]\s*\([^)]+\)|omega\([^)]+\)|theta\([^)]+\))", re.IGNORECASE)
FORMULA_EQUATION_RE = re.compile(r"\b[a-zA-Z]\s*=\s*[\w\+\-\*\/\^]{2,}|\b(dx|dy|dt|lim|log|ln|sin|cos|tan)\b")
EXPLANATION_PATTERN_RE = re.compile(
    r"\b(is defined as|refers to|means that|characterized by|caused by|results in|consists of|stores|represents|computes)\b",
    re.IGNORECASE,
)
ACADEMIC_QUESTION_RE = re.compile(
    r"\b(what is|how does|why does|explain|define|derive|differentiate between|compare)\b",
    re.IGNORECASE,
)
ACADEMIC_SUFFIXES = ("tion", "sion", "ment", "ology", "ism", "ity", "ance", "ence", "ysis")


def extract_document_text(document: Document) -> str:
    """Extract ordered text lines from the latest revisions of a document's pages."""
    text_chunks = []
    pages = document.pages.exclude(current_revision_id=None).order_by("page_number")
    for page in pages:
        rev_id = page.current_revision_id
        if not rev_id:
            continue
        try:
            revision = DocumentPageRevision.objects.get(pk=rev_id)
        except DocumentPageRevision.DoesNotExist:
            continue

        lines = list(revision.lines.order_by("line_index").values_list("text", flat=True))
        if lines:
            text_chunks.append("\n".join(lines))
        elif revision.content_snapshot and isinstance(revision.content_snapshot.get("lines"), list):
            snapshot_lines = [
                l.get("text", "")
                for l in revision.content_snapshot["lines"]
                if isinstance(l, dict) and l.get("text")
            ]
            if snapshot_lines:
                text_chunks.append("\n".join(snapshot_lines))

    if not text_chunks:
        # Fallback to indexed NoteChunk content if revisions had no lines
        chunks = list(
            NoteChunk.objects.filter(document=document, stale=False)
            .order_by("chunk_index")
            .values_list("content", flat=True)
        )
        if chunks:
            text_chunks = chunks

    return "\n\n".join(text_chunks).strip()


def validate_text_academic_content(text: str) -> Tuple[bool, str, dict]:
    """Pure deterministic validation of note text for academic sufficiency.

    Returns:
        (is_valid, reason, details)
        where reason is "" on success, or one of:
          - "blank_content"
          - "unreadable_content"
          - "insufficient_content"
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return False, "blank_content", {"detail": "No text content found in document."}

    # Count alphanumeric characters
    alnum_count = sum(c.isalnum() for c in clean_text)
    if alnum_count < 3:
        return False, "unreadable_content", {"detail": "Fewer than 3 alphanumeric characters."}

    words = re.findall(r"\b[\w'-]+\b", clean_text)
    word_count = len(words)
    if word_count == 0:
        return False, "blank_content", {"detail": "No words found in text."}

    lower_words = [w.lower() for w in words]

    # Check for trivial tokens only (greetings, placeholder tokens)
    if all(w in TRIVIAL_TOKENS for w in lower_words):
        return False, "insufficient_content", {
            "detail": "Note contains only conversational greetings or placeholder tokens.",
        }

    # Check for explicit code syntax / keywords
    code_keyword_hits = [w for w in lower_words if w in CODE_KEYWORDS]
    if code_keyword_hits:
        return True, "", {"matched_signal": "code_keywords", "keywords": code_keyword_hits[:5]}

    if CODE_OPERATORS_RE.search(clean_text):
        return True, "", {"matched_signal": "code_operators"}

    # Check for mathematical / algorithmic notation
    if MATH_ASYMPTOTIC_RE.search(clean_text):
        return True, "", {"matched_signal": "asymptotic_notation"}

    if FORMULA_EQUATION_RE.search(clean_text):
        return True, "", {"matched_signal": "math_formula"}

    # Check for conceptual explanations or questions
    if EXPLANATION_PATTERN_RE.search(clean_text):
        return True, "", {"matched_signal": "explanation_pattern"}

    if ACADEMIC_QUESTION_RE.search(clean_text) and word_count >= 4:
        return True, "", {"matched_signal": "academic_question"}

    # Check academic vocabulary
    academic_hits = [w for w in lower_words if w in ACADEMIC_TERMS]
    if academic_hits:
        return True, "", {"matched_signal": "academic_terms", "terms": academic_hits[:5]}

    # Check technical suffixes for longer words
    suffix_hits = [w for w in lower_words if len(w) >= 6 and any(w.endswith(s) for s in ACADEMIC_SUFFIXES)]
    if suffix_hits:
        return True, "", {"matched_signal": "technical_suffixes", "terms": suffix_hits[:5]}

    # If note has fewer than 20 words and matched none of the above academic signals:
    # It is insufficient (e.g. personal name "Yash Kumar", non-academic phrases like "Meeting tomorrow")
    if word_count < 20:
        return False, "insufficient_content", {
            "detail": "Note has fewer than 20 words and contains no recognizable academic concepts, code, or formulas.",
            "word_count": word_count,
        }

    # For longer notes (>= 20 words), check repetition ratio
    unique_words = set(lower_words)
    if len(unique_words) / word_count < 0.25:
        return False, "insufficient_content", {
            "detail": "Repetitive non-academic text.",
            "word_count": word_count,
        }

    # Sufficient prose text
    return True, "", {"matched_signal": "prose_text", "word_count": word_count}


def validate_note_academic_content(document: Document) -> Tuple[bool, str, dict]:
    """Validates whether a document's latest revisions contain sufficient academic content."""
    text = extract_document_text(document)
    return validate_text_academic_content(text)

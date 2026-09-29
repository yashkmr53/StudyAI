"""Deterministic textbook chunking (Phase 11 §6).

Preserves document structure, chapter, section, page, and chunk ordering.
Flushes chunks at chapter/section boundaries to avoid combining unrelated concepts.
Generates one retrieval chunk per unit (~150-250 words with sliding overlap).
"""
import hashlib
import re
from typing import Optional

CHAPTER_PATTERNS = [
    re.compile(r"^(?:Chapter|CHAPTER)\s+([0-9IVXLCDM]+)(?:\s*[:.\-—]\s*(.*))?$", re.IGNORECASE),
    re.compile(r"^Module\s+([0-9IVXLCDM]+)(?:\s*[:.\-—]\s*(.*))?$", re.IGNORECASE),
]

SECTION_PATTERNS = [
    re.compile(r"^(\d+\.\d+(?:\.\d+)?)\s+(.+)$"),
    re.compile(r"^(?:Section|SECTION)\s+([0-9\.]+)(?:\s*[:.\-—]\s*(.*))?$", re.IGNORECASE),
]


def _detect_heading(line: str) -> tuple[Optional[str], Optional[str]]:
    """Detect whether line contains a chapter or section heading."""
    clean = line.strip()
    if not clean or len(clean) > 120:
        return None, None

    for pattern in CHAPTER_PATTERNS:
        match = pattern.match(clean)
        if match:
            num = match.group(1)
            title = match.group(2) or ""
            return (f"Chapter {num}: {title}".strip(": "), None)

    for pattern in SECTION_PATTERNS:
        match = pattern.match(clean)
        if match:
            sec_num = match.group(1)
            sec_title = match.group(2) or ""
            return (None, f"{sec_num} {sec_title}".strip())

    return None, None


def chunk_extracted_pages(
    pages: list[dict],
    *,
    target_words: int = 200,
    overlap_words: int = 35,
) -> list[dict]:
    """Chunk extracted pages deterministically.

    Args:
        pages: List of {"page_number": int, "text": str, ...}
        target_words: Target word count per chunk (~150-250).
        overlap_words: Words carried over from the end of the previous chunk.

    Returns:
        List of dicts: [
            {
                "chunk_index": int,
                "text": str,
                "content_hash": str,
                "page_number": int,
                "chapter": str,
                "section": str,
                "metadata": dict,
            },
            ...
        ]
    """
    chunks: list[dict] = []
    current_chapter = ""
    current_section = ""

    body_units: list[tuple[int, str]] = []  # (page_number, text)
    carry_units: list[tuple[int, str]] = []

    def flush_chunk():
        nonlocal body_units, carry_units
        if not body_units:
            return

        all_units = carry_units + body_units
        content = "\n\n".join(t for _, t in all_units).strip()
        if not content:
            body_units = []
            return

        pages_in_chunk = [p for p, _ in all_units]
        primary_page = pages_in_chunk[0] if pages_in_chunk else 1

        chunk_idx = len(chunks)
        c_hash = hashlib.sha256(content.encode()).hexdigest()

        chunks.append({
            "chunk_index": chunk_idx,
            "text": content,
            "content_hash": c_hash,
            "page_number": primary_page,
            "chapter": current_chapter,
            "section": current_section,
            "metadata": {
                "pages": sorted(set(pages_in_chunk)),
                "word_count": len(content.split()),
            },
        })

        # Calculate carry-over units for boundary overlap
        carry_units = []
        if overlap_words > 0 and len(body_units) > 1:
            remaining_words = overlap_words
            for p_num, text in reversed(body_units):
                words = len(text.split())
                carry_units.insert(0, (p_num, text))
                remaining_words -= words
                if remaining_words <= 0 or len(carry_units) >= 2:
                    break

        body_units = []

    for page in pages:
        p_num = page.get("page_number", 1)
        raw_text = page.get("text", "")
        if not raw_text.strip():
            continue

        # Split into paragraphs
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [raw_text.strip()]

        for p in paragraphs:
            # Check for chapter/section heading
            first_line = p.splitlines()[0] if p else ""
            chap, sec = _detect_heading(first_line)
            if chap:
                # Chapter boundary -> flush immediately and clear carry
                flush_chunk()
                carry_units = []
                current_chapter = chap
                current_section = ""
            elif sec:
                # Section boundary -> flush immediately
                flush_chunk()
                carry_units = []
                current_section = sec

            p_words = len(p.split())
            current_words = sum(len(t.split()) for _, t in (carry_units + body_units))

            if body_units and (current_words + p_words > target_words):
                flush_chunk()

            body_units.append((p_num, p))

    flush_chunk()
    return chunks

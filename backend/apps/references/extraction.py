"""PDF text extraction with qwen3.5:4b vision OCR fallback (Phase 11 §5).

Extracts text from normal PDFs directly via pypdf page-by-page.
For scanned or image-only pages where extracted text is insufficient (< 30 chars),
falls back to qwen3.5:4b vision OCR on the embedded page image.
Preserves page numbers (1-indexed).
"""
import io
import logging
import os
import time
from typing import Any, Optional, Union

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS_THRESHOLD = 30
MAX_OCR_RETRIES = 2


def check_ocr_availability(timeout: float = 3.0) -> bool:
    """Pre-flight check to verify Ollama connectivity before running OCR."""
    base_url = (
        os.environ.get("OLLAMA_BASE_URL")
        or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    )
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception as exc:
        logger.warning("Ollama preflight health check failed at %s: %s", base_url, exc)
        return False


def extract_pdf_pages(
    pdf_input: Union[bytes, bytearray, io.BytesIO, any],
    *,
    request_id: str = "pdf_extract",
    ocr_fallback: bool = True,
    fail_on_ocr_error: bool = False,
) -> list[dict]:
    """Extract text from PDF pages, falling back to vision OCR for scanned pages.

    Args:
        pdf_input: Raw bytes or file-like object of the PDF file.
        request_id: Tracing/request identifier.
        ocr_fallback: Whether to attempt qwen3.5:4b vision OCR on pages with no direct text.
        fail_on_ocr_error: If True, raises RuntimeError if OCR fails on any scanned page.

    Returns:
        List of dicts: [
            {"page_number": int, "text": str, "method": "direct" | "vision_ocr" | "empty"},
            ...
        ]
    """
    import pypdf

    if isinstance(pdf_input, (bytes, bytearray)):
        stream = io.BytesIO(pdf_input)
    elif hasattr(pdf_input, "read"):
        if hasattr(pdf_input, "seek"):
            pdf_input.seek(0)
        stream = pdf_input
    else:
        stream = io.BytesIO(bytes(pdf_input))

    reader = pypdf.PdfReader(stream)
    page_count = len(reader.pages)
    logger.info("Extracting %d pages from PDF (request_id=%s)", page_count, request_id)

    ocr_checked = False
    ocr_available = True
    failed_ocr_pages: list[int] = []

    results = []
    for idx, page in enumerate(reader.pages):
        page_number = idx + 1
        direct_text = ""
        try:
            direct_text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("pypdf extract_text failed on page %d: %s", page_number, exc)

        clean_text = direct_text.strip()
        if len(clean_text) >= MIN_TEXT_CHARS_THRESHOLD:
            results.append({
                "page_number": page_number,
                "text": clean_text,
                "method": "direct",
            })
            continue

        # Page has insufficient text -> check for image-only page and attempt OCR
        ocr_text = ""
        if ocr_fallback:
            if not ocr_checked:
                ocr_available = check_ocr_availability()
                ocr_checked = True
                if not ocr_available:
                    logger.warning("Ollama unavailable during preflight check; OCR fallback will be attempted with retries.")

            try:
                images = getattr(page, "images", [])
                if images:
                    # Use the largest image on the page
                    best_img_data = None
                    max_len = 0
                    for img in images:
                        data = getattr(img, "data", None)
                        if data and len(data) > max_len:
                            max_len = len(data)
                            best_img_data = data

                    if best_img_data:
                        from providers.registry import get_ocr_provider
                        ocr_provider = get_ocr_provider()

                        for attempt in range(MAX_OCR_RETRIES + 1):
                            try:
                                ocr_res = ocr_provider.recognize(
                                    best_img_data,
                                    request_id=f"{request_id}:p{page_number}",
                                )
                                lines = getattr(ocr_res, "lines", [])
                                ocr_text = "\n".join(lines).strip()
                                break
                            except Exception as attempt_err:
                                if attempt < MAX_OCR_RETRIES:
                                    logger.warning(
                                        "OCR attempt %d failed on page %d: %s; retrying...",
                                        attempt + 1,
                                        page_number,
                                        attempt_err,
                                    )
                                    time.sleep(1.0 * (attempt + 1))
                                else:
                                    logger.error(
                                        "OCR failed after %d attempts on page %d: %s",
                                        MAX_OCR_RETRIES + 1,
                                        page_number,
                                        attempt_err,
                                    )
                                    failed_ocr_pages.append(page_number)

            except Exception as ocr_err:
                logger.warning("OCR processing error on page %d: %s", page_number, ocr_err)
                failed_ocr_pages.append(page_number)

        final_text = ocr_text or clean_text
        method = "vision_ocr" if ocr_text else ("direct" if clean_text else "empty")
        results.append({
            "page_number": page_number,
            "text": final_text,
            "method": method,
        })

    if failed_ocr_pages:
        logger.warning(
            "PDF extraction completed with %d OCR failures on pages: %s",
            len(failed_ocr_pages),
            failed_ocr_pages,
        )
        if fail_on_ocr_error:
            raise RuntimeError(
                f"OCR failed for {len(failed_ocr_pages)} pages: {failed_ocr_pages}. Check Ollama service."
            )

    return results

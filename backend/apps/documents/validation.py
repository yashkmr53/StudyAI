"""Heuristic validation module for OCR and transcript review gating (architecture §6, §48).

Computes image metrics and validates transcript lines against quality heuristics
to determine whether a page requires manual human review (NEEDS_REVIEW) or is
ready for pending review (PENDING_REVIEW).
"""
import io
import logging
from typing import Any

from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)


def compute_image_metrics(image_bytes: bytes) -> dict[str, Any]:
    """Compute basic dimensional and ink density metrics from raw image bytes.

    Placeholders (300x300, 0.005, 0.15) to calibrate on real handwritten validation sets.
    """
    if not image_bytes:
        return {"width": 0, "height": 0, "ink_ratio": 0.0}

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            if width == 0 or height == 0:
                return {"width": 0, "height": 0, "ink_ratio": 0.0}

            # Sample/convert to grayscale to measure dark ink on light background
            gray = img.convert("L")
            total_pixels = width * height

            def _get_pixel_data(im):
                if hasattr(im, "get_flattened_data"):
                    return im.get_flattened_data()
                return im.getdata()

            # For large images, thumbnail to save CPU while computing ink ratio
            if total_pixels > 1000 * 1000:
                gray.thumbnail((1000, 1000))
                thumb_w, thumb_h = gray.size
                thumb_pixels = thumb_w * thumb_h
                dark_pixels = sum(1 for p in _get_pixel_data(gray) if p < 200)
                ink_ratio = dark_pixels / thumb_pixels if thumb_pixels > 0 else 0.0
            else:
                dark_pixels = sum(1 for p in _get_pixel_data(gray) if p < 200)
                ink_ratio = dark_pixels / total_pixels

            return {
                "width": width,
                "height": height,
                "ink_ratio": ink_ratio,
            }
    except Exception as exc:
        logger.warning("Failed to compute image metrics: %s", exc)
        return {"width": 0, "height": 0, "ink_ratio": 0.0}


def evaluate_page_review_status(
    lines: list[dict[str, Any]],
    image_metrics: dict[str, Any] | None = None,
    source_type: str = "",
) -> tuple[str, list[str]]:
    """Evaluate transcript lines and image metrics to assign review status and reasons.

    Returns:
        (review_status, review_reasons)
        review_status: 'needs_review' or 'pending_review'
        review_reasons: list of triggered heuristic reason codes
    """
    reasons: list[str] = []
    total_lines = len(lines)

    illegible_thresh = float(getattr(settings, "OCR_ILLEGIBLE_THRESHOLD", 0.15))
    uncertain_thresh = float(getattr(settings, "OCR_UNCERTAIN_THRESHOLD", 0.30))
    line_uncertain_thresh = float(getattr(settings, "OCR_LINE_UNCERTAIN_THRESHOLD", 0.80))

    # Rule 1: [illegible] marker appears in more than 15% of lines
    if total_lines > 0:
        illegible_count = sum(
            1 for l in lines if "[illegible]" in str(l.get("text", "")).lower()
        )
        if (illegible_count / total_lines) > illegible_thresh:
            reasons.append("high_illegible_ratio")

    # Rule 2: More than 30% of lines are flagged uncertain
    if total_lines > 0:
        uncertain_count = 0
        for l in lines:
            conf = l.get("confidence") if l.get("confidence") is not None else l.get("confidence_score")
            if conf is not None and float(conf) < line_uncertain_thresh:
                uncertain_count += 1
        if (uncertain_count / total_lines) > uncertain_thresh:
            reasons.append("high_uncertain_ratio")

    # Rule 3: Repetition loop (4 or more identical consecutive lines)
    if total_lines >= 4:
        consecutive = 1
        for i in range(1, total_lines):
            t_curr = str(lines[i].get("text", "")).strip()
            t_prev = str(lines[i - 1].get("text", "")).strip()
            if t_curr and t_curr == t_prev:
                consecutive += 1
                if consecutive >= 4:
                    reasons.append("repetition_loop")
                    break
            else:
                consecutive = 1

    # Rule 4: Blank page or very low image resolution
    is_canvas = source_type in ("canvas_page", "canvas")
    if is_canvas:
        if total_lines == 0:
            reasons.append("blank_page")
    else:
        if image_metrics:
            w = image_metrics.get("width", 0)
            h = image_metrics.get("height", 0)
            ink = image_metrics.get("ink_ratio", 0.0)
            # Low resolution placeholder: < 300x300
            if (0 < w < 300) or (0 < h < 300):
                reasons.append("low_resolution")
            # Blank ink placeholder: < 0.005 when validly decoded
            if (w > 0 and h > 0) and ink < 0.005:
                reasons.append("blank_page")
        if total_lines == 0 and "blank_page" not in reasons:
            reasons.append("blank_page")

    # Rule 5: Heavy ink with almost no recognized text
    if not is_canvas and image_metrics:
        ink = image_metrics.get("ink_ratio", 0.0)
        # Heavy ink placeholder: > 0.15 with < 3 lines recognized
        if ink > 0.15 and total_lines < 3:
            reasons.append("heavy_ink_low_text")

    if reasons:
        return "needs_review", reasons
    return "pending_review", []

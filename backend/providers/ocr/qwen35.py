"""Canonical Qwen3.5:4B Handwritten-Note OCR Provider (StudyAI Phased Migration).

Replaces legacy Tesseract / PaddleOCR / mock providers with qwen3.5:4b vision.
Processes note images directly, faithfully transcribes handwritten notes,
preserves formulas, equations, structure, and terms line by line.
"""
import logging
import os
import re
from typing import Optional, Union

from providers.base import OCRProvider, OCRResult, Prompt
from providers.llm.qwen35 import Qwen35Provider

logger = logging.getLogger(__name__)

OCR_SYSTEM_PROMPT = """You are a high-precision handwritten note transcription and OCR engine.
Your sole purpose is to faithfully transcribe all text, mathematical formulas, equations, symbols, and bullet points from the provided note image verbatim.

Strict rules:
1. Transcribe line-by-line exactly as written in the image.
2. Maintain the original reading order, visual structure, indentation, and list hierarchies.
3. Faithfully transcribe math equations and scientific formulas (e.g., dU = dQ - dW, KE = 0.5 * m * v^2, C6H12O6 + 6O2 -> 6CO2 + 6H2O + ATP, fractions, superscripts).
4. Preserve exact spelling, punctuation, abbreviations, and capitalization.
5. Do NOT summarize, explain, correct mistakes, or add any commentary.
6. If any word is completely illegible or obscured, transcribe it as [illegible].
7. Output ONLY the transcribed lines, without conversational filler, introductory remarks, or markdown backticks/code blocks."""

OCR_USER_PROMPT = "Transcribe all handwritten and printed text from this note image line by line verbatim."


class Qwen35OCRProvider:
    """Canonical production OCR provider for StudyAI using Ollama qwen3.5:4b vision."""

    name = "qwen35"

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        confidence: float = 0.95,
        fail: bool = False,
        name: str = "qwen35",
        num_ctx: Optional[int] = None,
        num_predict: Optional[int] = None,
    ):
        self.name = name
        self.confidence = confidence
        self.fail = fail
        target_model = model or os.environ.get("OCR_MODEL") or "qwen3.5:4b"
        self._llm = Qwen35Provider(
            model=target_model,
            base_url=base_url,
            num_ctx=num_ctx or 16384,
            num_predict=num_predict or 4096,
        )

    def recognize(self, image_uri: Union[str, bytes], *, request_id: str) -> OCRResult:
        """Recognize handwritten/printed text from image using qwen3.5:4b vision.

        Args:
            image_uri: Local file path, file:// URI, object storage key, data URI, or raw bytes.
            request_id: Request identifier for tracing.

        Returns:
            OCRResult with parsed lines, confidence, provider info, and raw reference.
        """
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")

        prompt = Prompt(
            name="ocr",
            version="qwen35-v1",
            system=OCR_SYSTEM_PROMPT,
            user=OCR_USER_PROMPT,
        )

        try:
            llm_result = self._llm.generate_with_image(
                prompt=prompt,
                image=image_uri,
                request_id=request_id,
                think=False,  # OCR must be direct verbatim transcription without thinking tokens
                temperature=0.0,
            )
        except Exception as e:
            logger.exception("Qwen3.5 OCR generation failed for %s", image_uri if isinstance(image_uri, str) else "<bytes>")
            raise RuntimeError(f"Qwen3.5 OCR failed: {e}") from e

        text = llm_result.text or ""

        # Strip markdown fences if present
        text = re.sub(r"^```(?:markdown|text)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
        text = re.sub(r"\n?```\s*$", "", text.strip())

        raw_lines = [line.strip() for line in text.splitlines()]
        parsed_lines = [l for l in raw_lines if l]

        if not parsed_lines:
            return OCRResult(
                lines=[],
                confidence=0.0,
                provider=self.name,
                raw_ref=str(image_uri) if isinstance(image_uri, str) else None,
            )

        lines = []
        total_confidence = 0.0
        for i, line_text in enumerate(parsed_lines):
            line_conf = self.confidence
            if "[illegible]" in line_text.lower():
                line_conf = max(0.40, line_conf - 0.20)
            lines.append({
                "line_index": i,
                "text": line_text,
                "bbox": None,
                "confidence": round(line_conf, 4),
            })
            total_confidence += line_conf

        avg_confidence = round(total_confidence / len(lines), 4)

        return OCRResult(
            lines=lines,
            confidence=avg_confidence,
            provider=self.name,
            raw_ref=str(image_uri) if isinstance(image_uri, str) else None,
        )

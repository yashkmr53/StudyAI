"""Gemini Handwritten-Note OCR Provider (StudyAI Cloud API Integration).

Provides high-precision handwritten note transcription using Google Gemini Multimodal Vision:
- Faithful verbatim line-by-line transcription
- Preserves math formulas, scientific equations, and list structure
- High-confidence multimodal recognition
"""
import logging
import os
import re
from typing import Optional, Union

from providers.base import OCRProvider, OCRResult, Prompt
from providers.llm.gemini import GeminiProvider

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


class GeminiOCRProvider:
    """Production OCR provider for StudyAI using Gemini Multimodal Vision."""

    name = "gemini"

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        confidence: float = 0.98,
        fail: bool = False,
        name: str = "gemini",
    ):
        self.name = name
        self.confidence = confidence
        self.fail = fail
        target_model = model or os.environ.get("GEMINI_OCR_MODEL") or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
        self._llm = GeminiProvider(
            model=target_model,
            api_key=api_key,
            temperature=0.0,
        )

    def recognize(self, image_uri: Union[str, bytes], *, request_id: str) -> OCRResult:
        """Recognize handwritten/printed text from image using Gemini vision.

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
            version="gemini-v1",
            system=OCR_SYSTEM_PROMPT,
            user=OCR_USER_PROMPT,
        )

        try:
            llm_result = self._llm.generate_with_image(
                prompt=prompt,
                image=image_uri,
                request_id=request_id,
                temperature=0.0,
            )
        except Exception as e:
            logger.exception("Gemini OCR generation failed for %s", image_uri if isinstance(image_uri, str) else "<bytes>")
            raise RuntimeError(f"Gemini OCR failed: {e}") from e

        text = llm_result.text or ""

        # Strip markdown code blocks if the model wrapped them
        text = re.sub(r"^```(?:markdown|text)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
        text = re.sub(r"\n?```\s*$", "", text.strip())

        raw_lines = [line.strip() for line in text.splitlines()]
        parsed_lines = [l for l in raw_lines if l]

        if not parsed_lines:
            logger.warning("Gemini OCR produced empty transcription for %s", image_uri if isinstance(image_uri, str) else "<bytes>")
            return OCRResult(
                lines=[],
                confidence=0.0,
                provider=self.name,
                raw_ref=str(image_uri)[:256] if isinstance(image_uri, str) else None,
            )

        lines = [{"text": line, "confidence": self.confidence} for line in parsed_lines]

        return OCRResult(
            lines=lines,
            confidence=self.confidence,
            provider=self.name,
            raw_ref=str(image_uri)[:256] if isinstance(image_uri, str) else None,
        )

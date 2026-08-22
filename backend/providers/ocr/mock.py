"""Mock OCR provider (development/tests only — §30 leaves the real
handwriting provider undecided).

Produces deterministic, plausible lines derived from the image key so the
full ingestion pipeline is exercisable without external services. NOT for
production use.
"""
import hashlib

from providers.base import OCRResult


class MockOCRProvider:
    def __init__(self, *, confidence: float = 0.97, fail: bool = False, name: str = "mock"):
        self.name = name
        self.confidence = confidence
        self.fail = fail

    def recognize(self, image_uri: str, *, request_id: str) -> OCRResult:
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        digest = hashlib.sha256(f"{image_uri}:{request_id}".encode()).hexdigest()
        words = [digest[i : i + 6] for i in range(0, 24, 6)]
        lines = [
            {
                "text": f"Recognized line {i + 1}: {words[i % len(words)]}",
                "bbox": [40.0, 60.0 + i * 48.0, 520.0, 36.0],
                "confidence": round(self.confidence - 0.01 * (i % 3), 4),
            }
            for i in range(3)
        ]
        avg = sum(l["confidence"] for l in lines) / len(lines)
        return OCRResult(lines=lines, confidence=round(avg, 4), provider=self.name)

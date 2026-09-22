"""OCR service behavior tests (Phase 11)."""
import pytest
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from providers.ocr.mock import MockOCRProvider
from providers.ocr.chain import OCRChainProvider
from providers.base import OCRResult


class TestOCRServiceBehavior(TestCase):
    """Test OCR provider behavior."""

    def test_mock_ocr_returns_deterministic_results(self):
        """Mock OCR should return deterministic results for same input."""
        provider = MockOCRProvider(confidence=0.95)
        
        result1 = provider.recognize("image.jpg", request_id="req-1")
        result2 = provider.recognize("image.jpg", request_id="req-1")
        
        assert result1.lines == result2.lines
        assert result1.confidence == result2.confidence

    def test_mock_ocr_different_requests_different_results(self):
        """Different request IDs should produce different results."""
        provider = MockOCRProvider()
        
        result1 = provider.recognize("image.jpg", request_id="req-1")
        result2 = provider.recognize("image.jpg", request_id="req-2")
        
        # Lines should be different (based on request_id hash)
        assert result1.lines != result2.lines

    def test_mock_ocr_confidence_configurable(self):
        """Mock OCR confidence should be configurable."""
        provider_high = MockOCRProvider(confidence=0.99)
        provider_low = MockOCRProvider(confidence=0.50)
        
        result_high = provider_high.recognize("img.jpg", request_id="req-1")
        result_low = provider_low.recognize("img.jpg", request_id="req-1")
        
        assert result_high.confidence > result_low.confidence

    def test_mock_ocr_can_fail(self):
        """Mock OCR can simulate failures."""
        provider = MockOCRProvider(fail=True)
        
        with self.assertRaises(RuntimeError):
            provider.recognize("img.jpg", request_id="req-1")

    def test_ocr_chain_fallback(self):
        """OCR chain should fall back to secondary provider."""
        primary = MockOCRProvider(fail=True, name="failing-primary")
        fallback = MockOCRProvider(confidence=0.90, name="fallback")
        
        chain = OCRChainProvider([primary, fallback])
        
        result, attempted = chain.recognize("img.jpg", request_id="req-1")
        
        assert "failing-primary" in attempted
        assert "fallback" in attempted
        assert result.provider == "fallback"
        # Average of 0.90, 0.89, 0.88 = 0.89
        assert result.confidence == 0.89

    def test_ocr_chain_all_fail_raises(self):
        """OCR chain should raise if all providers fail."""
        primary = MockOCRProvider(fail=True, name="fail-1")
        fallback = MockOCRProvider(fail=True, name="fail-2")
        
        chain = OCRChainProvider([primary, fallback])
        
        from shared.exceptions import ProviderError
        with self.assertRaises(ProviderError) as cm:
            chain.recognize("img.jpg", request_id="req-1")
        
        assert "All OCR providers failed" in str(cm.exception)
        assert cm.exception.details["attempted"] == ["fail-1", "fail-2"]

    def test_ocr_result_structure(self):
        """OCR result should have expected structure."""
        provider = MockOCRProvider()
        result = provider.recognize("img.jpg", request_id="req-1")
        
        assert isinstance(result, OCRResult)
        assert isinstance(result.lines, list)
        assert len(result.lines) > 0
        
        line = result.lines[0]
        assert "text" in line
        assert "bbox" in line
        assert "confidence" in line
        assert len(line["bbox"]) == 4
        assert 0 <= line["confidence"] <= 1.0
        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 1.0
        assert result.provider == "mock"
        assert result.raw_ref == "img.jpg"


class TestTesseractOCRProvider(TestCase):
    """Test Tesseract OCR provider (when available)."""

    def test_tesseract_provider_initialization_skipped(self):
        """Skip if tesserocr not available or API incompatible."""
        import importlib.util
        if importlib.util.find_spec("tesserocr") is None:
            self.skipTest("tesserocr not installed")
        
        import tesserocr
        if not hasattr(tesserocr, "get_tesseract_version"):
            self.skipTest("tesserocr API incompatible (missing get_tesseract_version)")
        
        from providers.ocr.local import TesseractOCRProvider
        provider = TesseractOCRProvider(languages="eng")
        
        assert provider.name == "tesseract"
        assert provider.languages == "eng"

    def test_tesseract_recognize_skipped(self):
        """Skip if tesserocr not available or API incompatible."""
        import importlib.util
        if importlib.util.find_spec("tesserocr") is None:
            self.skipTest("tesserocr not installed")
        
        import tesserocr
        if not hasattr(tesserocr, "get_tesseract_version") or not hasattr(tesserocr, "PyTessBaseAPI"):
            self.skipTest("tesserocr API incompatible")
        
        from providers.ocr.local import TesseractOCRProvider
        provider = TesseractOCRProvider()
        
        # Just verify it can be instantiated without error
        assert provider.name == "tesseract"


class TestPaddleOCRProvider(TestCase):
    """Test PaddleOCR provider (when available)."""

    def test_paddleocr_provider_initialization_skipped(self):
        """Skip if paddleocr not available."""
        import importlib.util
        if importlib.util.find_spec("paddleocr") is None:
            self.skipTest("paddleocr not installed")
        
        from providers.ocr.local import PaddleOCRProvider
        provider = PaddleOCRProvider(languages="en")
        
        assert provider.name == "paddleocr"
        assert provider.languages == "en"

    def test_paddleocr_recognize_skipped(self):
        """Skip if paddleocr not available."""
        import importlib.util
        if importlib.util.find_spec("paddleocr") is None:
            self.skipTest("paddleocr not installed")
        
        from providers.ocr.local import PaddleOCRProvider
        provider = PaddleOCRProvider()
        
        # Just verify it can be instantiated without error
        assert provider.name == "paddleocr"


class TestQwen35OCRProvider(TestCase):
    """Test canonical Qwen3.5:4B OCR provider."""

    def test_qwen35_ocr_initialization(self):
        from providers.ocr.qwen35 import Qwen35OCRProvider
        provider = Qwen35OCRProvider(confidence=0.95)
        assert provider.name == "qwen35"
        assert provider.confidence == 0.95
        assert provider.fail is False

    def test_qwen35_ocr_recognize_parses_lines(self):
        from providers.ocr.qwen35 import Qwen35OCRProvider
        from providers.base import LLMResult

        provider = Qwen35OCRProvider()
        mock_output = (
            "Title: Cell Biology\n"
            "Mitochondria is the powerhouse of the cell.\n"
            "ATP synthesis occurs in cristae.\n"
            "C6H12O6 + 6O2 -> 6CO2 + 6H2O"
        )
        provider._llm.generate_with_image = MagicMock(
            return_value=LLMResult(text=mock_output, model="qwen3.5:4b", provider="ollama")
        )

        result = provider.recognize("dummy_image.png", request_id="req-test-1")
        assert result.provider == "qwen35"
        assert len(result.lines) == 4
        assert result.confidence == 0.95
        assert result.raw_ref == "dummy_image.png"

        assert result.lines[0]["line_index"] == 0
        assert result.lines[0]["text"] == "Title: Cell Biology"
        assert result.lines[0]["bbox"] is None
        assert result.lines[0]["confidence"] == 0.95

        assert result.lines[3]["text"] == "C6H12O6 + 6O2 -> 6CO2 + 6H2O"

    def test_qwen35_ocr_strips_markdown_fences(self):
        from providers.ocr.qwen35 import Qwen35OCRProvider
        from providers.base import LLMResult

        provider = Qwen35OCRProvider()
        mock_output = "```markdown\nLine 1: E = mc^2\nLine 2: F = ma\n```"
        provider._llm.generate_with_image = MagicMock(
            return_value=LLMResult(text=mock_output, model="qwen3.5:4b", provider="ollama")
        )

        result = provider.recognize("dummy.png", request_id="req-fence")
        assert len(result.lines) == 2
        assert result.lines[0]["text"] == "Line 1: E = mc^2"
        assert result.lines[1]["text"] == "Line 2: F = ma"

    def test_qwen35_ocr_handles_illegible_words(self):
        from providers.ocr.qwen35 import Qwen35OCRProvider
        from providers.base import LLMResult

        provider = Qwen35OCRProvider(confidence=0.95)
        mock_output = "Line 1: Clear text\nLine 2: Some [illegible] handwriting"
        provider._llm.generate_with_image = MagicMock(
            return_value=LLMResult(text=mock_output, model="qwen3.5:4b", provider="ollama")
        )

        result = provider.recognize("dummy.png", request_id="req-illegible")
        assert len(result.lines) == 2
        assert result.lines[0]["confidence"] == 0.95
        assert result.lines[1]["confidence"] == 0.75  # 0.95 - 0.20
        assert result.confidence == 0.85

    def test_qwen35_ocr_empty_output(self):
        from providers.ocr.qwen35 import Qwen35OCRProvider
        from providers.base import LLMResult

        provider = Qwen35OCRProvider()
        provider._llm.generate_with_image = MagicMock(
            return_value=LLMResult(text="", model="qwen3.5:4b", provider="ollama")
        )

        result = provider.recognize("empty.png", request_id="req-empty")
        assert len(result.lines) == 0
        assert result.confidence == 0.0

    def test_qwen35_ocr_simulated_failure(self):
        from providers.ocr.qwen35 import Qwen35OCRProvider

        provider = Qwen35OCRProvider(fail=True)
        with self.assertRaises(RuntimeError):
            provider.recognize("img.png", request_id="req-fail")

    @override_settings(OCR_PROVIDER_CHAIN="qwen35", LLM_DISABLE_FALLBACK=1)
    def test_ocr_chain_with_qwen35_no_fallback(self):
        from providers.registry import get_ocr_provider
        chain = get_ocr_provider()
        assert chain.disable_fallback is True
        assert chain.providers[0].name == "qwen35"
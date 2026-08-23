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

    @patch("tesserocr")
    def test_tesseract_provider_initialization(self, mock_tesserocr):
        """Test Tesseract provider can be initialized."""
        mock_tesserocr.get_tesseract_version.return_value = "5.3.0"
        
        from providers.ocr.local import TesseractOCRProvider
        provider = TesseractOCRProvider(languages="eng")
        
        assert provider.name == "tesseract"
        assert provider.languages == "eng"
        mock_tesserocr.get_tesseract_version.assert_called_once()

    @patch("tesserocr")
    def test_tesseract_recognize(self, mock_tesserocr):
        """Test Tesseract recognize method."""
        # Mock the API
        mock_api = MagicMock()
        mock_tesserocr.PyTessBaseAPI.return_value.__enter__.return_value = mock_api
        mock_api.GetIterator.return_value = MagicMock()
        
        # Configure iterator
        iterator = mock_api.GetIterator.return_value
        iterator.IsAtBeginningOf.return_value = False
        iterator.GetUTF8Text.return_value = "Test line"
        iterator.Confidence.return_value = 95
        iterator.BoundingBox.return_value = (10, 20, 100, 30)
        iterator.Next.return_value = False
        
        from providers.ocr.local import TesseractOCRProvider
        provider = TesseractOCRProvider()
        
        with patch.object(provider, '_resolve_image_path') as mock_resolve:
            mock_resolve.return_value = MagicMock(exists=True)
            result = provider.recognize("test.jpg", request_id="req-1")
        
        assert isinstance(result, OCRResult)
        assert len(result.lines) == 1
        assert result.lines[0]["text"] == "Test line"
        assert result.confidence == 0.95


class TestPaddleOCRProvider(TestCase):
    """Test PaddleOCR provider (when available)."""

    @patch("paddleocr.PaddleOCR")
    def test_paddleocr_provider_initialization(self, mock_paddleocr):
        """Test PaddleOCR provider can be initialized."""
        from providers.ocr.local import PaddleOCRProvider
        provider = PaddleOCRProvider(languages="en")
        
        assert provider.name == "paddleocr"
        assert provider.languages == "en"

    @patch("paddleocr.PaddleOCR")
    def test_paddleocr_recognize(self, mock_paddleocr_class):
        """Test PaddleOCR recognize method."""
        mock_ocr = MagicMock()
        mock_paddleocr_class.return_value = mock_ocr
        mock_ocr.ocr.return_value = [[
            ([(10, 20), (110, 20), (110, 50), (10, 50)], ("Test line", 0.95))
        ]]
        
        from providers.ocr.local import PaddleOCRProvider
        provider = PaddleOCRProvider()
        provider._ocr = mock_ocr
        
        with patch.object(provider, '_resolve_image_path') as mock_resolve:
            mock_resolve.return_value = MagicMock(exists=True)
            result = provider.recognize("test.jpg", request_id="req-1")
        
        assert isinstance(result, OCRResult)
        assert len(result.lines) == 1
        assert result.lines[0]["text"] == "Test line"
        assert result.confidence == 0.95
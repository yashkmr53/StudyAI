"""OCR providers package."""
from providers.ocr.local import TesseractOCRProvider, PaddleOCRProvider
from providers.ocr.mock import MockOCRProvider
from providers.ocr.chain import OCRChainProvider

__all__ = [
    "MockOCRProvider",
    "OCRChainProvider",
    "TesseractOCRProvider",
    "PaddleOCRProvider",
]
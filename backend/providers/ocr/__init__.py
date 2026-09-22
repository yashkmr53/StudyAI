"""OCR providers package."""
from providers.ocr.local import TesseractOCRProvider, PaddleOCRProvider
from providers.ocr.mock import MockOCRProvider
from providers.ocr.chain import OCRChainProvider
from providers.ocr.qwen35 import Qwen35OCRProvider

__all__ = [
    "MockOCRProvider",
    "OCRChainProvider",
    "Qwen35OCRProvider",
    "TesseractOCRProvider",
    "PaddleOCRProvider",
]
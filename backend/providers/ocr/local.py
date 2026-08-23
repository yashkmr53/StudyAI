"""Local Tesseract OCR provider (Phase 11).

Runs Tesseract OCR locally via the tesserocr Python bindings.
Falls back gracefully if Tesseract is not available.
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional

from providers.base import OCRResult

logger = logging.getLogger(__name__)


class TesseractOCRProvider:
    """Local Tesseract OCR provider using tesserocr bindings."""
    
    name = "tesseract"
    languages = "eng"
    
    def __init__(self, *, languages: str = "eng", fail: bool = False, name: str = "tesseract"):
        self.name = name
        self.languages = languages
        self.fail = fail
        self._check_tesseract()
    
    def _check_tesseract(self) -> None:
        """Verify Tesseract is available."""
        try:
            import tesserocr
            self._tesserocr = tesserocr
            # Test that tesseract can run
            version = tesserocr.get_tesseract_version()
            logger.info("Tesseract OCR initialized (version %s, languages: %s)", version, self.languages)
        except ImportError:
            logger.warning("tesserocr not installed; TesseractOCRProvider will not work")
            self._tesserocr = None
        except Exception as e:
            logger.warning("Tesseract initialization failed: %s", e)
            self._tesserocr = None
    
    def recognize(self, image_uri: str, *, request_id: str) -> OCRResult:
        """Recognize text from an image using Tesseract.
        
        Args:
            image_uri: Local file path or URL to the image
            request_id: Request identifier for tracing
            
        Returns:
            OCRResult with recognized lines, confidence, and provider info
        """
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        if self._tesserocr is None:
            raise RuntimeError("Tesseract OCR not available (tesserocr not installed)")
        
        # Resolve image path
        image_path = self._resolve_image_path(image_uri)
        if not image_path or not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_uri}")
        
        try:
            with self._tesserocr.PyTessBaseAPI(lang=self.languages) as api:
                api.SetImageFile(str(image_path))
                api.Recognize()
                
                # Get iterator for line-level results
                iterator = api.GetIterator()
                if iterator is None:
                    return OCRResult(
                        lines=[],
                        confidence=0.0,
                        provider=self.name,
                        raw_ref=image_uri,
                    )
                
                lines = []
                total_confidence = 0.0
                line_count = 0
                
                level = self._tesserocr.RIL.TEXTLINE
                while True:
                    if iterator.IsAtBeginningOf(level):
                        if line_count > 0:
                            break
                    try:
                        text = iterator.GetUTF8Text(level).strip()
                        confidence = iterator.Confidence(level)
                        
                        if text:
                            # Get bounding box
                            bbox = iterator.BoundingBox(level)
                            if bbox:
                                x, y, w, h = bbox
                            else:
                                x, y, w, h = 0, 0, 0, 0
                            
                            lines.append({
                                "text": text,
                                "bbox": [float(x), float(y), float(w), float(h)],
                                "confidence": round(confidence / 100.0, 4),
                            })
                            total_confidence += confidence / 100.0
                            line_count += 1
                    except Exception:
                        pass
                    
                    if not iterator.Next(level):
                        break
                
                avg_confidence = total_confidence / line_count if line_count > 0 else 0.0
                
                return OCRResult(
                    lines=lines,
                    confidence=round(avg_confidence, 4),
                    provider=self.name,
                    raw_ref=image_uri,
                )
        except Exception as e:
            logger.exception("Tesseract OCR failed for %s", image_uri)
            raise RuntimeError(f"Tesseract OCR failed: {e}") from e
    
    def _resolve_image_path(self, image_uri: str) -> Optional[Path]:
        """Resolve image URI to local filesystem path."""
        # Handle local file paths
        if image_uri.startswith("file://"):
            return Path(image_uri[7:])
        
        # Handle local paths
        path = Path(image_uri)
        if path.exists():
            return path
        
        # Handle relative to object storage
        from django.conf import settings
        storage_root = Path(getattr(settings, "OBJECT_STORAGE_LOCAL_DIR", "/app/var/objectstore"))
        full_path = (storage_root / image_uri).resolve()
        if full_path.exists() and str(full_path).startswith(str(storage_root.resolve())):
            return full_path
        
        return None


class PaddleOCRProvider:
    """Local PaddleOCR provider (alternative to Tesseract).
    
    Better for: complex layouts, tables, handwriting, CJK languages.
    Heavier dependency (~1GB model download on first run).
    """
    
    name = "paddleocr"
    languages = "en"
    
    def __init__(self, *, languages: str = "en", fail: bool = False, name: str = "paddleocr"):
        self.name = name
        self.languages = languages
        self.fail = fail
        self._ocr = None
        self._check_paddleocr()
    
    def _check_paddleocr(self) -> None:
        """Verify PaddleOCR is available."""
        try:
            from paddleocr import PaddleOCR
            self._PaddleOCR = PaddleOCR
            logger.info("PaddleOCR initialized (languages: %s)", self.languages)
        except ImportError:
            logger.warning("paddleocr not installed; PaddleOCRProvider will not work")
            self._PaddleOCR = None
    
    def _get_ocr(self):
        """Lazy initialization of PaddleOCR."""
        if self._ocr is None and self._PaddleOCR is not None:
            self._ocr = self._PaddleOCR(use_angle_cls=True, lang=self.languages, show_log=False)
        return self._ocr
    
    def recognize(self, image_uri: str, *, request_id: str) -> OCRResult:
        """Recognize text from an image using PaddleOCR."""
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        ocr = self._get_ocr()
        if ocr is None:
            raise RuntimeError("PaddleOCR not available (paddleocr not installed)")
        
        # Resolve image path
        image_path = self._resolve_image_path(image_uri)
        if not image_path or not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_uri}")
        
        try:
            result = ocr.ocr(str(image_path), cls=True)
            
            lines = []
            total_confidence = 0.0
            line_count = 0
            
            for page_result in result:
                if page_result:
                    for line in page_result:
                        bbox, (text, confidence) = line
                        if text.strip():
                            # Convert bbox to [x, y, w, h] format
                            x_coords = [p[0] for p in bbox]
                            y_coords = [p[1] for p in bbox]
                            x, y = min(x_coords), min(y_coords)
                            w, h = max(x_coords) - x, max(y_coords) - y
                            
                            lines.append({
                                "text": text,
                                "bbox": [float(x), float(y), float(w), float(h)],
                                "confidence": round(confidence, 4),
                            })
                            total_confidence += confidence
                            line_count += 1
            
            avg_confidence = total_confidence / line_count if line_count > 0 else 0.0
            
            return OCRResult(
                lines=lines,
                confidence=round(avg_confidence, 4),
                provider=self.name,
                raw_ref=image_uri,
            )
        except Exception as e:
            logger.exception("PaddleOCR failed for %s", image_uri)
            raise RuntimeError(f"PaddleOCR failed: {e}") from e
    
    def _resolve_image_path(self, image_uri: str) -> Optional[Path]:
        """Resolve image URI to local filesystem path."""
        if image_uri.startswith("file://"):
            return Path(image_uri[7:])
        
        path = Path(image_uri)
        if path.exists():
            return path
        
        from django.conf import settings
        storage_root = Path(getattr(settings, "OBJECT_STORAGE_LOCAL_DIR", "/app/var/objectstore"))
        full_path = (storage_root / image_uri).resolve()
        if full_path.exists() and str(full_path).startswith(str(storage_root.resolve())):
            return full_path
        
        return None
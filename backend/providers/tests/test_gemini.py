"""Tests for Gemini LLM and OCR providers and registry switching."""
import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from providers.base import LLMResult, OCRResult, Prompt, StructuredLLMResult
from providers.llm.gemini import GeminiProvider
from providers.ocr.gemini import GeminiOCRProvider
from providers.registry import get_llm_provider, get_ocr_provider


class SampleSchema(BaseModel):
    summary: str = Field(description="A brief summary")
    points: list[str] = Field(default_factory=list, description="Key bullet points")


class TestGeminiProvider:
    """Unit tests for GeminiProvider."""

    def test_init_defaults(self):
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        assert provider.name == "gemini"
        assert provider.model == "gemini-2.5-flash"
        assert provider.api_key == "test-key"

    def test_init_strips_models_prefix(self):
        provider = GeminiProvider(api_key="test-key", model="models/gemini-1.5-pro")
        assert provider.model == "gemini-1.5-pro"

    @patch("providers.llm.gemini.requests.post")
    def test_generate_plain_text(self, mock_post):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Photosynthesis produces glucose and oxygen."}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 15,
                "candidatesTokenCount": 10,
                "totalTokenCount": 25,
            },
        }
        mock_post.return_value = mock_response

        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        prompt = Prompt(name="test_prompt", version="v1", user="Explain photosynthesis.")
        result = provider.generate(prompt=prompt, request_id="req-123")

        assert isinstance(result, LLMResult)
        assert result.text == "Photosynthesis produces glucose and oxygen."
        assert result.provider == "gemini"
        assert result.model == "gemini-2.5-flash"
        assert result.input_tokens == 15
        assert result.output_tokens == 10
        assert result.total_tokens == 25
        assert result.estimated_cost_usd > 0.0

    @patch("providers.llm.gemini.requests.post")
    def test_generate_structured_with_pydantic(self, mock_post):
        json_output = json.dumps({"summary": "Cellular respiration breakdown", "points": ["Glycolysis", "Krebs cycle"]})
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": f"```json\n{json_output}\n```"}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 50,
                "candidatesTokenCount": 30,
                "totalTokenCount": 80,
            },
        }
        mock_post.return_value = mock_response

        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        result = provider.generate_structured(
            prompt="Summarize cellular respiration",
            schema=SampleSchema,
            request_id="req-struct-1",
        )

        assert isinstance(result, StructuredLLMResult)
        assert isinstance(result.data, dict)
        assert result.data["summary"] == "Cellular respiration breakdown"
        assert len(result.data["points"]) == 2
        assert result.input_tokens == 50
        assert result.output_tokens == 30

    @patch("providers.llm.gemini.requests.post")
    def test_generate_with_image_bytes(self, mock_post):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Line 1: dU = dQ - dW\nLine 2: Conservation of energy"}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120},
        }
        mock_post.return_value = mock_response

        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        result = provider.generate_with_image(
            prompt="Transcribe this image",
            image=dummy_png,
            request_id="req-img-1",
        )

        assert isinstance(result, LLMResult)
        assert "dU = dQ - dW" in result.text
        # Verify payload sent to Gemini API contained inlineData
        sent_payload = mock_post.call_args[1]["json"]
        user_parts = sent_payload["contents"][0]["parts"]
        assert any("inlineData" in part for part in user_parts)

    @patch("providers.llm.gemini.requests.post")
    def test_generate_structured_with_image(self, mock_post):
        json_output = json.dumps({"summary": "Handwritten thermodynamics", "points": ["First Law: dU = dQ - dW"]})
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json_output}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 40, "totalTokenCount": 160},
        }
        mock_post.return_value = mock_response

        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        result = provider.generate_structured_with_image(
            prompt="Analyze note",
            image=dummy_png,
            schema=SampleSchema,
            request_id="req-struct-img-1",
        )

        assert isinstance(result, StructuredLLMResult)
        assert result.data["summary"] == "Handwritten thermodynamics"
        assert result.data["points"][0] == "First Law: dU = dQ - dW"

    @patch("providers.llm.gemini.requests.post")
    def test_missing_api_key_raises(self, mock_post):
        provider = GeminiProvider(api_key="", model="gemini-2.5-flash")
        with pytest.raises(ValueError, match="Gemini API key is missing"):
            provider.generate("Hello")


class TestGeminiOCRProvider:
    """Unit tests for GeminiOCRProvider."""

    @patch("providers.llm.gemini.requests.post")
    def test_ocr_recognize_lines(self, mock_post):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Heading: Thermodynamics\n1. First law: dU = dQ - dW\n2. Isobaric process: W = P*dV"}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 200, "candidatesTokenCount": 35, "totalTokenCount": 235},
        }
        mock_post.return_value = mock_response

        ocr = GeminiOCRProvider(api_key="test-key", model="gemini-2.5-flash")
        dummy_png = b"\x89PNG\r\n\x1a\n"
        result = ocr.recognize(dummy_png, request_id="ocr-123")

        assert isinstance(result, OCRResult)
        assert result.provider == "gemini"
        assert len(result.lines) == 3
        assert result.lines[0]["text"] == "Heading: Thermodynamics"
        assert result.lines[1]["text"] == "1. First law: dU = dQ - dW"
        assert result.lines[2]["text"] == "2. Isobaric process: W = P*dV"
        assert result.confidence == 0.98

    def test_ocr_simulated_failure(self):
        ocr = GeminiOCRProvider(api_key="test-key", fail=True)
        with pytest.raises(RuntimeError, match="simulated provider failure"):
            ocr.recognize(b"dummy", request_id="fail-req")


class TestRegistrySwitching:
    """Unit tests for single-toggle USE_GEMINI in provider registry."""

    @patch.dict("os.environ", {"USE_GEMINI": "true", "GEMINI_API_KEY": "test-key-123", "GEMINI_MODEL": "gemini-2.5-flash"})
    def test_get_llm_provider_when_use_gemini_true(self):
        chain = get_llm_provider()
        assert chain.providers[0].name == "gemini"
        assert chain.disable_fallback is True

    @patch.dict("os.environ", {"USE_GEMINI": "true", "GEMINI_API_KEY": "test-key-123"})
    def test_get_ocr_provider_when_use_gemini_true(self):
        chain = get_ocr_provider()
        assert chain.providers[0].name == "gemini"
        assert chain.disable_fallback is True

    @patch.dict("os.environ", {"USE_GEMINI": "false", "LLM_PROVIDER": "mock", "OCR_PROVIDER_CHAIN": "mock"})
    def test_get_llm_provider_when_use_gemini_false(self):
        chain = get_llm_provider()
        assert chain.providers[0].name == "mock"

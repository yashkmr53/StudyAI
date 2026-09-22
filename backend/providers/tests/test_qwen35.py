"""Unit tests for canonical Qwen35Provider (Phase 2)."""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from providers.base import LLMResult, Prompt, StructuredLLMResult
from providers.llm.qwen35 import Qwen35Provider
from providers.registry import get_llm_provider


class TestQwen35Provider(TestCase):
    """Tests for the canonical Qwen35Provider."""

    @patch("providers.llm.qwen35.requests.get")
    def setUp(self, mock_get):
        mock_get.return_value.json.return_value = {
            "models": [
                {"name": "qwen3.5:4b"},
                {"name": "qwen3-vl:4b"},
            ]
        }
        mock_get.return_value.raise_for_status = MagicMock()
        self.provider = Qwen35Provider(
            base_url="http://mock-ollama:11434",
            model="qwen3.5:4b",
            num_ctx=16384,
            num_predict=4096,
        )

    def test_provider_provenance_and_attributes(self):
        """Verify provider name, model, context, predict, and base attributes."""
        assert self.provider.name == "ollama"
        assert self.provider.model == "qwen3.5:4b"
        assert self.provider.base_url == "http://mock-ollama:11434"
        assert self.provider.num_ctx == 16384
        assert self.provider.num_predict == 4096

    def test_stage_based_thinking_resolution(self):
        """Verify thinking mode resolves correctly per stage from settings/env."""
        # By default: all thinking defaults to False (think=0)
        assert self.provider._resolve_think("ocr") is False
        assert self.provider._resolve_think("transcribe") is False
        assert self.provider._resolve_think("chat") is False
        assert self.provider._resolve_think("unknown_stage") is False

        # Stage-specific settings resolution
        with patch.object(self.provider, "_get_setting") as mock_setting:
            mock_setting.side_effect = lambda k: "1" if k in ("LLM_THINK_ENRICHMENT", "LLM_THINK_GAP_DETECTION") else "0"
            assert self.provider._resolve_think("enrichment") is True
            assert self.provider._resolve_think("enrichment_draft") is True
            assert self.provider._resolve_think("gap_detection") is True
            assert self.provider._resolve_think("ocr") is False

        # Caller explicit override always takes precedence
        assert self.provider._resolve_think("enrichment", explicit_think=False) is False
        assert self.provider._resolve_think("ocr", explicit_think=True) is True

    @patch("providers.llm.qwen35.ChatOllama")
    def test_text_generation(self, mock_chat_ollama_cls):
        """Verify plain text generation through generate(). Content only, no thinking texts."""
        mock_client = MagicMock()
        mock_chat_ollama_cls.return_value = mock_client
        mock_client.invoke.return_value = AIMessage(
            content="Newton's second law is F = ma.",
            usage_metadata={"input_tokens": 25, "output_tokens": 10, "total_tokens": 35},
        )

        prompt = Prompt(
            name="physics_concept",
            version="v1",
            system="You are a physics tutor.",
            user="State Newton's second law.",
        )
        result = self.provider.generate(prompt=prompt, request_id="req-text-1")

        assert isinstance(result, LLMResult)
        assert result.text == "Newton's second law is F = ma."
        assert result.model == "qwen3.5:4b"
        assert result.provider == "ollama"
        assert result.prompt_name == "physics_concept"
        assert result.prompt_version == "v1"
        assert result.input_tokens == 25
        assert result.output_tokens == 10
        assert result.total_tokens == 35

        mock_client.invoke.assert_called_once()
        invoked_msgs = mock_client.invoke.call_args[0][0]
        assert len(invoked_msgs) == 2
        assert invoked_msgs[0].content == "You are a physics tutor."
        assert invoked_msgs[1].content == "State Newton's second law."

    @patch("providers.llm.qwen35.ChatOllama")
    def test_structured_generation_with_pydantic(self, mock_chat_ollama_cls):
        """Verify structured generation validates and returns dict using Pydantic schema."""
        class GapItem(BaseModel):
            topic: str
            status: str
            explanation: str

        class GapResult(BaseModel):
            gaps: list[GapItem]

        mock_client = MagicMock()
        mock_chat_ollama_cls.return_value = mock_client

        mock_structured = MagicMock()
        mock_client.with_structured_output.return_value = mock_structured

        parsed_gap = GapResult(gaps=[GapItem(topic="Chain Rule", status="MISSING", explanation="Missing rule")])
        raw_msg = AIMessage(
            content=json.dumps({"gaps": [{"topic": "Chain Rule", "status": "MISSING", "explanation": "Missing rule"}]}),
            usage_metadata={"input_tokens": 50, "output_tokens": 30, "total_tokens": 80},
        )
        mock_structured.invoke.return_value = {"raw": raw_msg, "parsed": parsed_gap}

        prompt = Prompt(name="gap_detection", version="v2", user="Analyze gaps.")
        result = self.provider.generate_structured(
            prompt=prompt,
            schema=GapResult,
            request_id="req-struct-1",
        )

        assert isinstance(result, StructuredLLMResult)
        assert len(result.data["gaps"]) == 1
        assert result.data["gaps"][0]["topic"] == "Chain Rule"
        assert result.data["gaps"][0]["status"] == "MISSING"
        assert result.input_tokens == 50
        assert result.output_tokens == 30
        assert result.total_tokens == 80
        assert result.model == "qwen3.5:4b"
        assert result.provider == "ollama"

    @patch("providers.llm.qwen35.ChatOllama")
    def test_structured_generation_retry_on_failure(self, mock_chat_ollama_cls):
        """Verify retry loop catches parse/validation errors and succeeds on subsequent try."""
        class Tags(BaseModel):
            tags: list[str]

        mock_client = MagicMock()
        mock_chat_ollama_cls.return_value = mock_client

        mock_structured = MagicMock()
        mock_client.with_structured_output.return_value = mock_structured

        raw_success = AIMessage(
            content='{"tags": ["Calculus"]}',
            usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
        )
        # Attempt 1 fails, Attempt 2 succeeds
        mock_structured.invoke.side_effect = [
            ValueError("Parse failure: malformed response"),
            {"raw": raw_success, "parsed": Tags(tags=["Calculus"])},
        ]

        result = self.provider.generate_structured(
            prompt="Generate tags",
            schema=Tags,
            retries=2,
        )

        assert isinstance(result, StructuredLLMResult)
        assert result.data == {"tags": ["Calculus"]}
        assert mock_structured.invoke.call_count == 2

    @patch("providers.llm.qwen35.ChatOllama")
    def test_structured_generation_raises_after_max_retries(self, mock_chat_ollama_cls):
        """Verify RuntimeError is raised when all retries are exhausted."""
        mock_client = MagicMock()
        mock_chat_ollama_cls.return_value = mock_client

        mock_structured = MagicMock()
        mock_client.with_structured_output.return_value = mock_structured
        mock_structured.invoke.side_effect = ValueError("Persistent parse error")

        with self.assertRaises(RuntimeError) as ctx:
            self.provider.generate_structured(
                prompt="Generate tags",
                schema=dict,
                retries=1,
            )

        assert "Structured generation failed after 2 attempts" in str(ctx.exception)

    @patch("providers.llm.qwen35.ChatOllama")
    def test_multimodal_image_generation(self, mock_chat_ollama_cls):
        """Verify multimodal text generation from image input."""
        mock_client = MagicMock()
        mock_chat_ollama_cls.return_value = mock_client
        mock_client.invoke.return_value = AIMessage(
            content="Line 1: Calculus Differentiation Rules",
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )

        raw_image_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        result = self.provider.generate_with_image(
            prompt="Transcribe the handwritten text from this image.",
            image=raw_image_bytes,
            request_id="req-vision-1",
        )

        assert isinstance(result, LLMResult)
        assert "Calculus Differentiation Rules" in result.text
        assert result.model == "qwen3.5:4b"
        assert result.provider == "ollama"

        invoked_msgs = mock_client.invoke.call_args[0][0]
        human_msg = invoked_msgs[-1]
        assert isinstance(human_msg.content, list)
        assert human_msg.content[0]["type"] == "text"
        assert human_msg.content[1]["type"] == "image_url"
        assert human_msg.content[1]["image_url"].startswith("data:image/png;base64,")

    @patch("providers.llm.qwen35.ChatOllama")
    def test_multimodal_structured_image_generation(self, mock_chat_ollama_cls):
        """Verify structured JSON output from multimodal image input."""
        class LineData(BaseModel):
            line_number: int
            text: str

        class OCRTranscription(BaseModel):
            lines: list[LineData]
            confidence: float

        mock_client = MagicMock()
        mock_chat_ollama_cls.return_value = mock_client

        mock_structured = MagicMock()
        mock_client.with_structured_output.return_value = mock_structured

        parsed = OCRTranscription(
            lines=[LineData(line_number=1, text="Calculus Rules")],
            confidence=0.98,
        )
        raw_msg = AIMessage(
            content='{"lines": [{"line_number": 1, "text": "Calculus Rules"}], "confidence": 0.98}',
            usage_metadata={"input_tokens": 150, "output_tokens": 40, "total_tokens": 190},
        )
        mock_structured.invoke.return_value = {"raw": raw_msg, "parsed": parsed}

        result = self.provider.generate_structured_with_image(
            prompt="Extract text lines from this handwritten page.",
            image=b"fake_image_bytes",
            schema=OCRTranscription,
            request_id="req-struct-vision-1",
        )

        assert isinstance(result, StructuredLLMResult)
        assert len(result.data["lines"]) == 1
        assert result.data["lines"][0]["text"] == "Calculus Rules"
        assert result.data["confidence"] == 0.98
        assert result.model == "qwen3.5:4b"


class TestQwen35Registry(TestCase):
    """Verify registry factory behavior with Qwen35Provider."""

    @patch("providers.llm.qwen35.requests.get")
    def test_get_llm_provider_resolves_qwen35(self, mock_get):
        """Verify get_llm_provider creates chain targeting Qwen35Provider when configured."""
        mock_get.return_value.json.return_value = {"models": [{"name": "qwen3.5:4b"}]}
        mock_get.return_value.raise_for_status = MagicMock()

        with override_settings(LLM_PROVIDER="ollama", LLM_MODEL="qwen3.5:4b", LLM_PROVIDER_CHAIN="ollama", LLM_DISABLE_FALLBACK=True):
            with patch.dict("os.environ", {"LLM_PROVIDER": "ollama", "LLM_MODEL": "qwen3.5:4b", "LLM_PROVIDER_CHAIN": "ollama", "LLM_DISABLE_FALLBACK": "1"}):
                chain = get_llm_provider()
                assert chain.disable_fallback is True
                assert len(chain.providers) == 1
                primary = chain.providers[0]
                assert isinstance(primary, Qwen35Provider)
                assert primary.model == "qwen3.5:4b"
                assert primary.name == "ollama"

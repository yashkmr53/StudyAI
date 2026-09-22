"""Canonical Qwen3.5:4B LLM & Multimodal Provider (StudyAI Phased Migration).

Centralizes all generative AI operations across the application:
- Plain text generation
- Structured JSON generation with schema validation and retry loop
- Multimodal handwriting OCR and image analysis
- Multimodal structured JSON extraction

Target Model: qwen3.5:4b (via native host Ollama with GPU/Metal acceleration)
No production fallback to other models or mocks.
"""
import base64
import json
import logging
import os
import re
import time
from typing import Any, Optional, Union

import requests
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from providers.base import LLMResult, Prompt, StructuredLLMResult

logger = logging.getLogger(__name__)

# Map prompt names / stages to environment setting flags
STAGE_THINKING_SETTINGS: dict[str, str] = {
    "ocr": "LLM_THINK_OCR",
    "transcribe": "LLM_THINK_OCR",
    "transcription": "LLM_THINK_OCR",
    "enrichment": "LLM_THINK_ENRICHMENT",
    "enrichment_draft": "LLM_THINK_ENRICHMENT",
    "gap_detection": "LLM_THINK_GAP_DETECTION",
    "gap_filling": "LLM_THINK_GAP_DETECTION",
    "question_generation": "LLM_THINK_QUESTION_GEN",
    "question_gen": "LLM_THINK_QUESTION_GEN",
    "chat": "LLM_THINK_CHAT",
    "tagging": "LLM_THINK_TAGGING",
    "tags": "LLM_THINK_TAGGING",
    "classification": "LLM_THINK_TAGGING",
    "verification": "LLM_THINK_VERIFICATION",
    "verify_evidence": "LLM_THINK_VERIFICATION",
    "verify_citations": "LLM_THINK_VERIFICATION",
}


class Qwen35Provider:
    """Canonical production LLM provider for StudyAI using Ollama qwen3.5:4b."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 180,
        max_retries: int = 2,
        temperature: float = 0.0,
        seed: int = 42,
        num_ctx: Optional[int] = None,
        num_predict: Optional[int] = None,
    ):
        dj = self._get_django_settings()
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL")
            or getattr(dj, "OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.model = (
            model
            or os.environ.get("LLM_MODEL")
            or getattr(dj, "LLM_MODEL", "qwen3.5:4b")
        )
        self.timeout = int(
            os.environ.get("OLLAMA_TIMEOUT_SECONDS")
            or os.environ.get("LLM_TIMEOUT_SECONDS")
            or (getattr(dj, "LLM_TIMEOUT_SECONDS", None) if dj else None)
            or timeout
        )
        self.max_retries = max_retries
        self.default_temperature = temperature
        self.default_seed = seed
        self.num_ctx = int(
            num_ctx
            or os.environ.get("LLM_NUM_CTX")
            or (getattr(dj, "LLM_NUM_CTX", None) if dj else None)
            or 16384
        )
        self.num_predict = int(
            num_predict
            or os.environ.get("LLM_NUM_PREDICT")
            or (getattr(dj, "LLM_NUM_PREDICT", None) if dj else None)
            or 4096
        )
        self._verified = False

        self._verify_connection()
        logger.info(
            "Qwen35Provider initialized (base_url=%s, model=%s, num_ctx=%d, num_predict=%d)",
            self.base_url,
            self.model,
            self.num_ctx,
            self.num_predict,
        )

    @staticmethod
    def _get_django_settings():
        try:
            from django.conf import settings
            return settings
        except Exception:
            return None

    def _get_setting(self, name: str) -> Optional[Any]:
        dj = self._get_django_settings()
        if dj and hasattr(dj, name):
            return getattr(dj, name)
        return os.environ.get(name)

    def _verify_connection(self) -> bool:
        """Verify Ollama server is reachable and target model exists."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]

            model_base = self.model.split(":")[0]
            matched = any(
                m == self.model or m.startswith(f"{model_base}:") or m.startswith("qwen3-vl:")
                for m in models
            )
            if not matched:
                logger.warning(
                    "Target model '%s' not found in Ollama tags. Available: %s. Run: ollama pull %s",
                    self.model,
                    models,
                    self.model,
                )
            self._verified = True
            return True
        except Exception as exc:
            # Container-to-host auto-detection for Docker environments
            if self.base_url != "http://host.docker.internal:11434":
                try:
                    alt_url = "http://host.docker.internal:11434"
                    resp = requests.get(f"{alt_url}/api/tags", timeout=3)
                    if resp.status_code == 200:
                        logger.info("Ollama auto-detected at %s, switching base_url", alt_url)
                        self.base_url = alt_url
                        self._verified = True
                        return True
                except Exception:
                    pass
            logger.warning("Ollama connection check failed (%s): %s", self.base_url, exc)
            self._verified = False
            return False

    def _resolve_think(self, prompt_name: str, explicit_think: Optional[bool] = None) -> bool:
        """Resolve thinking mode (on/off) per stage according to settings and caller override."""
        if explicit_think is not None:
            return explicit_think

        stage = (prompt_name or "").lower().strip()
        setting_name = STAGE_THINKING_SETTINGS.get(stage)
        if setting_name:
            val = self._get_setting(setting_name)
            if val is not None:
                return str(val).strip().lower() in ("1", "true", "yes")

        default_val = self._get_setting("LLM_THINK_DEFAULT")
        if default_val is not None:
            return str(default_val).strip().lower() in ("1", "true", "yes")

        return False

    def _get_client(self, *, think: bool, temperature: Optional[float] = None) -> ChatOllama:
        """Build ChatOllama client configured with specified thinking and temperature."""
        temp = self.default_temperature if temperature is None else temperature
        return ChatOllama(
            model=self.model,
            base_url=self.base_url,
            temperature=temp,
            reasoning=think,
            num_ctx=self.num_ctx,
            num_predict=self.num_predict,
        )

    def _normalize_prompt(self, prompt: Union[Prompt, str], system: Optional[str] = None) -> tuple[str, str, str, str]:
        """Normalize Prompt object or string into (prompt_name, prompt_version, system_prompt, user_content)."""
        if isinstance(prompt, Prompt):
            p_name = prompt.name
            p_version = prompt.version
            sys_text = prompt.system or ""
            user_text = prompt.user or ""
        else:
            p_name = "direct"
            p_version = "v1"
            sys_text = ""
            user_text = str(prompt)

        if system:
            sys_text = f"{sys_text}\n\n{system}".strip() if sys_text else system

        return p_name, p_version, sys_text, user_text

    def _resolve_image_base64(self, image: Union[bytes, str]) -> str:
        """Convert bytes, local filepath, object storage key, or data URL to raw base64 string."""
        if isinstance(image, bytes):
            return base64.b64encode(image).decode("utf-8")

        from pathlib import Path
        if isinstance(image, Path):
            image = str(image)

        if not isinstance(image, str):
            raise ValueError(f"Unsupported image type: {type(image)}")

        # File URL format
        if image.startswith("file://"):
            image = image[7:]

        # Data URL format
        if image.startswith("data:image"):
            if "," in image:
                return image.split(",", 1)[1]
            return image

        # Existing local file
        if os.path.exists(image):
            with open(image, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

        # Object storage lookup
        try:
            from providers.registry import get_object_storage
            storage = get_object_storage()
            if storage.exists(image):
                raw_bytes = storage.read_bytes(image)
                return base64.b64encode(raw_bytes).decode("utf-8")
        except Exception:
            pass

        # Raw base64 string
        clean_str = image.strip()
        if re.match(r"^[A-Za-z0-9+/=]+$", clean_str) and len(clean_str) > 20:
            return clean_str

        raise ValueError(f"Could not resolve image input from source: {image[:100]}")

    def generate(
        self,
        prompt: Union[Prompt, str],
        *,
        request_id: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,
        **kwargs,
    ) -> LLMResult:
        """Generate plain text output. Model output is read from content only."""
        p_name, p_version, sys_text, user_text = self._normalize_prompt(prompt, system)
        should_think = self._resolve_think(p_name, think)
        client = self._get_client(think=should_think, temperature=temperature)

        messages = []
        if sys_text:
            messages.append(SystemMessage(content=sys_text))
        messages.append(HumanMessage(content=user_text))

        started = time.monotonic()
        res = client.invoke(messages)
        latency_ms = int((time.monotonic() - started) * 1000)

        usage = getattr(res, "usage_metadata", {}) or {}
        in_tokens = usage.get("input_tokens", 0)
        out_tokens = usage.get("output_tokens", 0)

        content = res.content if isinstance(res.content, str) else str(res.content)

        return LLMResult(
            text=content.strip(),
            model=self.model,
            provider=self.name,
            prompt_name=p_name,
            prompt_version=p_version,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            total_tokens=in_tokens + out_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=0.0,
        )

    def generate_structured(
        self,
        prompt: Union[Prompt, str],
        *,
        schema: Optional[Union[type, dict]] = None,
        request_id: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,
        retries: Optional[int] = None,
        disable_fallback: bool = False,
        **kwargs,
    ) -> StructuredLLMResult:
        """Generate structured JSON response validated against schema with retry loop."""
        p_name, p_version, sys_text, user_text = self._normalize_prompt(prompt, system)
        should_think = self._resolve_think(p_name, think)
        client = self._get_client(think=should_think, temperature=temperature)

        target_schema = schema if schema is not None else dict
        from pydantic import BaseModel
        is_pydantic = isinstance(target_schema, type) and issubclass(target_schema, BaseModel)
        method = "json_schema" if is_pydantic else "json_mode"
        structured_llm = client.with_structured_output(target_schema, method=method, include_raw=True)

        messages = []
        if sys_text:
            messages.append(SystemMessage(content=sys_text))
        messages.append(HumanMessage(content=user_text))

        max_attempts = (retries if retries is not None else self.max_retries) + 1
        last_err = None
        started = time.monotonic()

        for attempt in range(max_attempts):
            try:
                inv_res = structured_llm.invoke(messages)
                latency_ms = int((time.monotonic() - started) * 1000)

                raw_msg = inv_res.get("raw") if isinstance(inv_res, dict) else None
                parsed = inv_res.get("parsed") if isinstance(inv_res, dict) else inv_res

                if parsed is None and raw_msg:
                    raw_text = raw_msg.content if hasattr(raw_msg, "content") else str(raw_msg)
                    if not raw_text and hasattr(raw_msg, "additional_kwargs"):
                        raw_text = raw_msg.additional_kwargs.get("thinking", "")
                    if raw_text:
                        clean_json = re.sub(r"^```(?:json)?\s*\n?", "", str(raw_text).strip(), flags=re.IGNORECASE)
                        clean_json = re.sub(r"\n?```\s*$", "", clean_json.strip())
                        match = re.search(r"(\{.*\}|\[.*\])", clean_json, re.DOTALL)
                        candidate_str = match.group(1) if match else clean_json
                        try:
                            parsed = json.loads(candidate_str)
                        except Exception:
                            pass
                    if parsed is None:
                        raise ValueError(f"Failed to parse structured output from model content: {str(raw_text)[:200]}")

                if hasattr(parsed, "model_dump"):
                    data_dict = parsed.model_dump()
                elif isinstance(parsed, dict):
                    data_dict = parsed
                else:
                    data_dict = {"result": parsed}

                raw_text = raw_msg.content if raw_msg and hasattr(raw_msg, "content") else json.dumps(data_dict)

                usage = getattr(raw_msg, "usage_metadata", {}) or {}
                in_tokens = usage.get("input_tokens", 0)
                out_tokens = usage.get("output_tokens", 0)

                return StructuredLLMResult(
                    data=data_dict,
                    raw_text=raw_text,
                    model=self.model,
                    provider=self.name,
                    prompt_name=p_name,
                    prompt_version=p_version,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    total_tokens=in_tokens + out_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=0.0,
                )
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "Structured generation attempt %d/%d failed (%s): %s",
                    attempt + 1, max_attempts, type(exc).__name__, exc,
                )

        raise RuntimeError(f"Structured generation failed after {max_attempts} attempts: {last_err}") from last_err

    def generate_with_image(
        self,
        prompt: Union[Prompt, str],
        image: Union[bytes, str],
        *,
        system: Optional[str] = None,
        request_id: Optional[str] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,
        **kwargs,
    ) -> LLMResult:
        """Generate text from multimodal image + text input (OCR / visual analysis)."""
        p_name, p_version, sys_text, user_text = self._normalize_prompt(prompt, system)
        should_think = self._resolve_think(p_name, think)
        client = self._get_client(think=should_think, temperature=temperature)
        b64 = self._resolve_image_base64(image)

        human_content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
        ]
        messages = []
        if sys_text:
            messages.append(SystemMessage(content=sys_text))
        messages.append(HumanMessage(content=human_content))

        started = time.monotonic()
        res = client.invoke(messages)
        latency_ms = int((time.monotonic() - started) * 1000)

        usage = getattr(res, "usage_metadata", {}) or {}
        in_tokens = usage.get("input_tokens", 0)
        out_tokens = usage.get("output_tokens", 0)

        content = res.content if isinstance(res.content, str) else str(res.content)

        return LLMResult(
            text=content.strip(),
            model=self.model,
            provider=self.name,
            prompt_name=p_name,
            prompt_version=p_version,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            total_tokens=in_tokens + out_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=0.0,
        )

    def generate_structured_with_image(
        self,
        prompt: Union[Prompt, str],
        image: Union[bytes, str],
        *,
        schema: Optional[Union[type, dict]] = None,
        system: Optional[str] = None,
        request_id: Optional[str] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,
        retries: Optional[int] = None,
        **kwargs,
    ) -> StructuredLLMResult:
        """Generate structured JSON from multimodal image + text input with retry loop."""
        p_name, p_version, sys_text, user_text = self._normalize_prompt(prompt, system)
        should_think = self._resolve_think(p_name, think)
        client = self._get_client(think=should_think, temperature=temperature)
        b64 = self._resolve_image_base64(image)

        target_schema = schema if schema is not None else dict
        from pydantic import BaseModel
        is_pydantic = isinstance(target_schema, type) and issubclass(target_schema, BaseModel)
        method = "json_schema" if is_pydantic else "json_mode"
        structured_llm = client.with_structured_output(target_schema, method=method, include_raw=True)

        human_content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
        ]
        messages = []
        if sys_text:
            messages.append(SystemMessage(content=sys_text))
        messages.append(HumanMessage(content=human_content))

        max_attempts = (retries if retries is not None else self.max_retries) + 1
        last_err = None
        started = time.monotonic()

        for attempt in range(max_attempts):
            try:
                inv_res = structured_llm.invoke(messages)
                latency_ms = int((time.monotonic() - started) * 1000)

                raw_msg = inv_res.get("raw") if isinstance(inv_res, dict) else None
                parsed = inv_res.get("parsed") if isinstance(inv_res, dict) else inv_res

                if parsed is None and raw_msg:
                    raw_text = raw_msg.content if hasattr(raw_msg, "content") else str(raw_msg)
                    if not raw_text and hasattr(raw_msg, "additional_kwargs"):
                        raw_text = raw_msg.additional_kwargs.get("thinking", "")
                    if raw_text:
                        clean_json = re.sub(r"^```(?:json)?\s*\n?", "", str(raw_text).strip(), flags=re.IGNORECASE)
                        clean_json = re.sub(r"\n?```\s*$", "", clean_json.strip())
                        match = re.search(r"(\{.*\}|\[.*\])", clean_json, re.DOTALL)
                        candidate_str = match.group(1) if match else clean_json
                        try:
                            parsed = json.loads(candidate_str)
                        except Exception:
                            pass
                    if parsed is None:
                        raise ValueError(f"Failed to parse structured output from multimodal model content: {str(raw_text)[:200]}")

                if hasattr(parsed, "model_dump"):
                    data_dict = parsed.model_dump()
                elif isinstance(parsed, dict):
                    data_dict = parsed
                else:
                    data_dict = {"result": parsed}

                raw_text = raw_msg.content if raw_msg and hasattr(raw_msg, "content") else json.dumps(data_dict)

                usage = getattr(raw_msg, "usage_metadata", {}) or {}
                in_tokens = usage.get("input_tokens", 0)
                out_tokens = usage.get("output_tokens", 0)

                return StructuredLLMResult(
                    data=data_dict,
                    raw_text=raw_text,
                    model=self.model,
                    provider=self.name,
                    prompt_name=p_name,
                    prompt_version=p_version,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    total_tokens=in_tokens + out_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=0.0,
                )
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "Multimodal structured generation attempt %d/%d failed (%s): %s",
                    attempt + 1, max_attempts, type(exc).__name__, exc,
                )

        raise RuntimeError(f"Multimodal structured generation failed after {max_attempts} attempts: {last_err}") from last_err

"""Gemini LLM & Multimodal Provider (StudyAI Cloud API Integration).

Centralizes all generative AI operations via Google AI Studio's Gemini REST API:
- Plain text generation
- Structured JSON generation with schema validation and retry loop
- Multimodal handwriting OCR and image analysis
- Multimodal structured JSON extraction

Target Models: gemini-2.5-flash (default), gemini-1.5-flash, gemini-1.5-pro, etc.
Requires: GEMINI_API_KEY environment variable or Django setting.
"""
import base64
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from pydantic import BaseModel

from providers.base import LLMResult, Prompt, StructuredLLMResult

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Estimated cost per 1M tokens (USD)
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    # model_prefix: (input_per_million, output_per_million)
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-2.0-flash": (0.075, 0.30),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.5-pro": (1.25, 5.00),
}


class GeminiProvider:
    """Production-grade LLM and Multimodal provider using Google Gemini API."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 2,
        temperature: float = 0.0,
    ):
        dj = self._get_django_settings()
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or (getattr(dj, "GEMINI_API_KEY", None) if dj else None)
            or ""
        ).strip()
        raw_model = (
            model
            or os.environ.get("GEMINI_MODEL")
            or (getattr(dj, "GEMINI_MODEL", None) if dj else None)
            or "gemini-2.5-flash"
        ).strip()
        # Strip "models/" prefix if present
        self.model = raw_model.split("/")[-1]
        self.timeout = int(
            os.environ.get("GEMINI_TIMEOUT_SECONDS")
            or os.environ.get("LLM_TIMEOUT_SECONDS")
            or (getattr(dj, "LLM_TIMEOUT_SECONDS", None) if dj else None)
            or timeout
        )
        self.max_retries = max_retries
        self.default_temperature = temperature

        if not self.api_key:
            logger.warning(
                "GeminiProvider initialized without GEMINI_API_KEY. Calls will fail unless an API key is provided."
            )
        else:
            logger.info("GeminiProvider initialized (model=%s, timeout=%ds)", self.model, self.timeout)

    @staticmethod
    def _get_django_settings():
        try:
            from django.conf import settings
            return settings
        except Exception:
            return None

    def _normalize_prompt(
        self, prompt: Union[Prompt, str], system: Optional[str] = None
    ) -> tuple[str, str, str, str]:
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

    def _resolve_image_base64_and_mime(self, image: Union[bytes, str]) -> Tuple[str, str]:
        """Convert bytes, local filepath, object storage key, or data URL to (base64_string, mime_type)."""
        from pathlib import Path

        if isinstance(image, Path):
            image = str(image)

        # Raw bytes
        if isinstance(image, bytes):
            b64_str = base64.b64encode(image).decode("utf-8")
            mime_type = "image/png"
            if image.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            elif image.startswith(b"RIFF") and b"WEBP" in image[:16]:
                mime_type = "image/webp"
            return b64_str, mime_type

        if not isinstance(image, str):
            raise ValueError(f"Unsupported image type: {type(image)}")

        # Data URL format: data:image/jpeg;base64,...
        if image.startswith("data:image/"):
            parts = image.split(",", 1)
            header = parts[0]
            data_str = parts[1] if len(parts) > 1 else ""
            mime_match = re.search(r"data:(image/[a-zA-Z0-9.-]+);base64", header)
            mime_type = mime_match.group(1) if mime_match else "image/png"
            return data_str, mime_type

        # File URL format
        if image.startswith("file://"):
            image = image[7:]

        # Existing local file
        if os.path.exists(image):
            mime_type = "image/jpeg" if image.lower().endswith((".jpg", ".jpeg")) else "image/png"
            if image.lower().endswith(".webp"):
                mime_type = "image/webp"
            with open(image, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8"), mime_type

        # Object storage lookup
        try:
            from providers.registry import get_object_storage
            storage = get_object_storage()
            if storage.exists(image):
                raw_bytes = storage.read_bytes(image)
                mime_type = "image/jpeg" if image.lower().endswith((".jpg", ".jpeg")) else "image/png"
                return base64.b64encode(raw_bytes).decode("utf-8"), mime_type
        except Exception:
            pass

        # Raw base64 string
        clean_str = image.strip()
        if re.match(r"^[A-Za-z0-9+/=]+$", clean_str) and len(clean_str) > 20:
            return clean_str, "image/png"

        raise ValueError(f"Could not resolve image input from source: {image[:100]}")

    def _calculate_cost(self, in_tokens: int, out_tokens: int) -> float:
        """Estimate USD cost based on token counts."""
        pricing = (0.10, 0.40)
        for prefix, price in MODEL_PRICING.items():
            if self.model.startswith(prefix) or prefix in self.model:
                pricing = price
                break
        in_cost = (in_tokens / 1_000_000.0) * pricing[0]
        out_cost = (out_tokens / 1_000_000.0) * pricing[1]
        return round(in_cost + out_cost, 6)

    def _build_request_payload(
        self,
        *,
        sys_text: str,
        user_text: str,
        prompt_messages: Optional[List[Dict[str, Any]]] = None,
        image_part: Optional[Tuple[str, str]] = None,
        temperature: Optional[float] = None,
        json_mode: bool = False,
        response_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Construct standard Gemini REST API generateContent request body."""
        contents: List[Dict[str, Any]] = []

        if prompt_messages:
            # Map multi-turn conversation
            for i, msg in enumerate(prompt_messages):
                role = msg.get("role", "user")
                gemini_role = "user" if role == "user" else "model"
                text_content = msg.get("content", "")
                parts: List[Dict[str, Any]] = [{"text": text_content}]

                # If image is attached, attach it to the last user message
                if image_part and i == len(prompt_messages) - 1 and gemini_role == "user":
                    b64, mime = image_part
                    parts.append({"inlineData": {"mimeType": mime, "data": b64}})

                contents.append({"role": gemini_role, "parts": parts})
        else:
            parts = [{"text": user_text}]
            if image_part:
                b64, mime = image_part
                parts.append({"inlineData": {"mimeType": mime, "data": b64}})
            contents.append({"role": "user", "parts": parts})

        payload: Dict[str, Any] = {"contents": contents}

        if sys_text:
            payload["systemInstruction"] = {"parts": [{"text": sys_text}]}

        temp = self.default_temperature if temperature is None else temperature
        generation_config: Dict[str, Any] = {"temperature": temp}

        if json_mode:
            generation_config["responseMimeType"] = "application/json"
            if response_schema:
                generation_config["responseSchema"] = response_schema

        payload["generationConfig"] = generation_config
        return payload

    def _execute_api_call(self, payload: Dict[str, Any], request_id: Optional[str] = None) -> Tuple[Dict[str, Any], int]:
        """Send HTTP POST request to Gemini API with exponential backoff on transient errors."""
        if not self.api_key:
            raise ValueError(
                "Gemini API key is missing. Please set GEMINI_API_KEY in your .env or Django settings."
            )

        url = f"{GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                latency_ms = int((time.monotonic() - started) * 1000)

                # Rate limiting (429) or transient server errors (500, 503) -> retry with backoff
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    wait_time = (2 ** attempt) + 0.5
                    logger.warning(
                        "Gemini API returned status %d on attempt %d/%d (req=%s). Retrying in %.1fs...",
                        resp.status_code, attempt + 1, self.max_retries + 1, request_id, wait_time,
                    )
                    time.sleep(wait_time)
                    continue

                if not resp.ok:
                    err_msg = resp.text
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("error", {}).get("message", resp.text)
                    except Exception:
                        pass
                    raise RuntimeError(f"Gemini API HTTP {resp.status_code}: {err_msg}")

                return resp.json(), latency_ms

            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait_time = (2 ** attempt) + 0.5
                    logger.warning(
                        "Gemini API network error on attempt %d/%d: %s. Retrying in %.1fs...",
                        attempt + 1, self.max_retries + 1, exc, wait_time,
                    )
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"Gemini API network failure: {exc}") from exc

        raise RuntimeError(f"Gemini API request failed after {self.max_retries + 1} attempts: {last_exc}")

    def _extract_text_and_usage(self, response_data: Dict[str, Any]) -> Tuple[str, int, int, int]:
        """Parse text response and usage metadata from Gemini response payload."""
        candidates = response_data.get("candidates", [])
        if not candidates:
            # Check for prompt feedback blocking
            feedback = response_data.get("promptFeedback", {})
            block_reason = feedback.get("blockReason")
            if block_reason:
                raise RuntimeError(f"Gemini generation blocked by safety filters: {block_reason}")
            raise RuntimeError("Gemini API returned no candidates.")

        first_cand = candidates[0]
        content_parts = first_cand.get("content", {}).get("parts", [])
        text_parts = [p.get("text", "") for p in content_parts if "text" in p]
        text_result = "".join(text_parts).strip()

        usage = response_data.get("usageMetadata", {})
        in_tokens = usage.get("promptTokenCount", 0)
        out_tokens = usage.get("candidatesTokenCount", 0)
        total_tokens = usage.get("totalTokenCount", in_tokens + out_tokens)

        return text_result, in_tokens, out_tokens, total_tokens

    def generate(
        self,
        prompt: Union[Prompt, str],
        *,
        request_id: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> LLMResult:
        """Generate plain text output from Gemini."""
        p_name, p_version, sys_text, user_text = self._normalize_prompt(prompt, system)
        prompt_msgs = getattr(prompt, "messages", None) if isinstance(prompt, Prompt) else None

        payload = self._build_request_payload(
            sys_text=sys_text,
            user_text=user_text,
            prompt_messages=prompt_msgs,
            temperature=temperature,
            json_mode=False,
        )

        resp_json, latency_ms = self._execute_api_call(payload, request_id=request_id)
        text, in_tokens, out_tokens, total_tokens = self._extract_text_and_usage(resp_json)
        cost = self._calculate_cost(in_tokens, out_tokens)

        return LLMResult(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_name=p_name,
            prompt_version=p_version,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=cost,
        )

    def generate_structured(
        self,
        prompt: Union[Prompt, str],
        *,
        schema: Optional[Union[type, dict]] = None,
        request_id: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        retries: Optional[int] = None,
        disable_fallback: bool = False,
        **kwargs,
    ) -> StructuredLLMResult:
        """Generate structured JSON response validated against schema with retry loop."""
        p_name, p_version, sys_text, user_text = self._normalize_prompt(prompt, system)
        prompt_msgs = getattr(prompt, "messages", None) if isinstance(prompt, Prompt) else None

        # Build schema instructions
        schema_dict = None
        is_pydantic = isinstance(schema, type) and issubclass(schema, BaseModel)
        if is_pydantic:
            try:
                schema_dict = schema.model_json_schema()
            except Exception:
                try:
                    schema_dict = schema.schema()
                except Exception:
                    pass
        elif isinstance(schema, dict):
            schema_dict = schema

        payload = self._build_request_payload(
            sys_text=sys_text,
            user_text=user_text,
            prompt_messages=prompt_msgs,
            temperature=temperature,
            json_mode=True,
            response_schema=schema_dict,
        )

        max_attempts = (retries if retries is not None else self.max_retries) + 1
        last_err: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                try:
                    resp_json, latency_ms = self._execute_api_call(payload, request_id=request_id)
                except RuntimeError as api_err:
                    # If responseSchema failed due to OpenAPI incompatibilities, retry with pure json_mode
                    if "responseSchema" in str(api_err) or "INVALID_ARGUMENT" in str(api_err):
                        logger.warning("Gemini responseSchema rejected; falling back to prompt-guided JSON mode")
                        payload["generationConfig"].pop("responseSchema", None)
                        if schema_dict:
                            schema_hint = f"\n\nOutput MUST strictly conform to this JSON Schema:\n{json.dumps(schema_dict)}"
                            payload["contents"][-1]["parts"][0]["text"] += schema_hint
                        resp_json, latency_ms = self._execute_api_call(payload, request_id=request_id)
                    else:
                        raise

                raw_text, in_tokens, out_tokens, total_tokens = self._extract_text_and_usage(resp_json)
                cost = self._calculate_cost(in_tokens, out_tokens)

                # Parse JSON
                clean_json = re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip(), flags=re.IGNORECASE)
                clean_json = re.sub(r"\n?```\s*$", "", clean_json.strip())

                parsed = json.loads(clean_json)

                # If Pydantic model is supplied, validate and convert to dict
                if is_pydantic and isinstance(parsed, dict):
                    try:
                        validated = schema.model_validate(parsed)
                        data_dict = validated.model_dump()
                    except Exception:
                        data_dict = parsed
                elif isinstance(parsed, dict):
                    data_dict = parsed
                else:
                    data_dict = {"result": parsed}

                return StructuredLLMResult(
                    data=data_dict,
                    raw_text=raw_text,
                    model=self.model,
                    provider=self.name,
                    prompt_name=p_name,
                    prompt_version=p_version,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=cost,
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
        **kwargs,
    ) -> LLMResult:
        """Generate text from multimodal image + text input (OCR / visual note analysis)."""
        p_name, p_version, sys_text, user_text = self._normalize_prompt(prompt, system)
        image_part = self._resolve_image_base64_and_mime(image)

        payload = self._build_request_payload(
            sys_text=sys_text,
            user_text=user_text,
            image_part=image_part,
            temperature=temperature,
            json_mode=False,
        )

        resp_json, latency_ms = self._execute_api_call(payload, request_id=request_id)
        text, in_tokens, out_tokens, total_tokens = self._extract_text_and_usage(resp_json)
        cost = self._calculate_cost(in_tokens, out_tokens)

        return LLMResult(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_name=p_name,
            prompt_version=p_version,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=cost,
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
        retries: Optional[int] = None,
        **kwargs,
    ) -> StructuredLLMResult:
        """Generate structured JSON from multimodal image + text input with retry loop."""
        p_name, p_version, sys_text, user_text = self._normalize_prompt(prompt, system)
        prompt_msgs = getattr(prompt, "messages", None) if isinstance(prompt, Prompt) else None
        image_part = self._resolve_image_base64_and_mime(image)

        schema_dict = None
        is_pydantic = isinstance(schema, type) and issubclass(schema, BaseModel)
        if is_pydantic:
            try:
                schema_dict = schema.model_json_schema()
            except Exception:
                try:
                    schema_dict = schema.schema()
                except Exception:
                    pass
        elif isinstance(schema, dict):
            schema_dict = schema

        payload = self._build_request_payload(
            sys_text=sys_text,
            user_text=user_text,
            prompt_messages=prompt_msgs,
            image_part=image_part,
            temperature=temperature,
            json_mode=True,
            response_schema=schema_dict,
        )

        max_attempts = (retries if retries is not None else self.max_retries) + 1
        last_err: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                try:
                    resp_json, latency_ms = self._execute_api_call(payload, request_id=request_id)
                except RuntimeError as api_err:
                    if "responseSchema" in str(api_err) or "INVALID_ARGUMENT" in str(api_err):
                        logger.warning("Gemini responseSchema rejected for image call; falling back to JSON mode")
                        payload["generationConfig"].pop("responseSchema", None)
                        if schema_dict:
                            schema_hint = f"\n\nOutput MUST strictly conform to this JSON Schema:\n{json.dumps(schema_dict)}"
                            payload["contents"][-1]["parts"][0]["text"] += schema_hint
                        resp_json, latency_ms = self._execute_api_call(payload, request_id=request_id)
                    else:
                        raise

                raw_text, in_tokens, out_tokens, total_tokens = self._extract_text_and_usage(resp_json)
                cost = self._calculate_cost(in_tokens, out_tokens)

                clean_json = re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip(), flags=re.IGNORECASE)
                clean_json = re.sub(r"\n?```\s*$", "", clean_json.strip())

                parsed = json.loads(clean_json)

                if is_pydantic and isinstance(parsed, dict):
                    try:
                        validated = schema.model_validate(parsed)
                        data_dict = validated.model_dump()
                    except Exception:
                        data_dict = parsed
                elif isinstance(parsed, dict):
                    data_dict = parsed
                else:
                    data_dict = {"result": parsed}

                return StructuredLLMResult(
                    data=data_dict,
                    raw_text=raw_text,
                    model=self.model,
                    provider=self.name,
                    prompt_name=p_name,
                    prompt_version=p_version,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=cost,
                )

            except Exception as exc:
                last_err = exc
                logger.warning(
                    "Multimodal structured generation attempt %d/%d failed (%s): %s",
                    attempt + 1, max_attempts, type(exc).__name__, exc,
                )

        raise RuntimeError(f"Multimodal structured generation failed after {max_attempts} attempts: {last_err}") from last_err

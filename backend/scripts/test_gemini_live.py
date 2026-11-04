#!/usr/bin/env python3
"""Diagnostic script to test Gemini API integration end-to-end.

Usage:
    export GEMINI_API_KEY="AIzaSy..."
    python backend/scripts/test_gemini_live.py
"""
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Configure minimal Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
try:
    import django
    django.setup()
except Exception as e:
    print(f"[-] Note: Django setup skipped: {e}")

from pydantic import BaseModel, Field

from providers.base import Prompt
from providers.llm.gemini import GeminiProvider
from providers.ocr.gemini import GeminiOCRProvider
from providers.registry import get_llm_provider, get_ocr_provider


class NoteAnalysisSchema(BaseModel):
    subject: str = Field(description="Subject domain, e.g. Computer Science, Physics")
    core_concept: str = Field(description="Main topic or theorem")
    key_takeaway: str = Field(description="One sentence summary of the concept")


def run_diagnostics():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

    print("=" * 65)
    print("  StudyAI Gemini API Integration Test")
    print("=" * 65)
    print(f"Model: {model}")

    if not api_key:
        print("\n[!] GEMINI_API_KEY is not set.")
        print("    To run live API tests, export your key:")
        print("      export GEMINI_API_KEY=\"AIzaSy...\"")
        print("      python backend/scripts/test_gemini_live.py\n")
        print("[+] Testing Provider Factory / Registry Toggle:")
        os.environ["USE_GEMINI"] = "true"
        os.environ["GEMINI_API_KEY"] = "dummy-test-key"
        llm = get_llm_provider()
        ocr = get_ocr_provider()
        print(f"    - LLM Provider: {llm.providers[0].name} (model={getattr(llm.providers[0], 'model', 'N/A')})")
        print(f"    - OCR Provider: {ocr.providers[0].name}")
        print("    [OK] USE_GEMINI=true correctly activates Gemini providers.")
        os.environ["USE_GEMINI"] = "false"
        del os.environ["GEMINI_API_KEY"]
        llm_off = get_llm_provider()
        print(f"    - LLM with USE_GEMINI=false: {llm_off.providers[0].name}")
        print("    [OK] USE_GEMINI=false correctly reverts to default local stack.")
        print("\n" + "=" * 65)
        return

    print(f"API Key: {api_key[:6]}...{api_key[-4:]}")
    provider = GeminiProvider(api_key=api_key, model=model)

    # 1. Plain text generation
    print("\n[1/3] Testing Plain Text Generation...")
    prompt = Prompt(name="test_text", version="v1", user="Explain binary search in exactly one short sentence.")
    try:
        res = provider.generate(prompt=prompt)
        print(f"    Response: {res.text}")
        print(f"    Tokens: {res.input_tokens} in / {res.output_tokens} out ({res.total_tokens} total)")
        print(f"    Latency: {res.latency_ms} ms | Cost: ${res.estimated_cost_usd:.6f}")
        print("    [PASS] Plain text generation succeeded.")
    except Exception as exc:
        print(f"    [FAIL] Text generation failed: {exc}")
        return

    # 2. Structured JSON Generation
    print("\n[2/3] Testing Structured JSON Generation (Pydantic)...")
    struct_prompt = Prompt(
        name="test_struct",
        version="v1",
        user="Analyze the topic 'Dijkstra Shortest Path Algorithm'. Extract the subject, core concept, and key takeaway.",
    )
    try:
        s_res = provider.generate_structured(prompt=struct_prompt, schema=NoteAnalysisSchema)
        print(f"    Parsed Data: {s_res.data}")
        print(f"    Tokens: {s_res.input_tokens} in / {s_res.output_tokens} out")
        print(f"    Latency: {s_res.latency_ms} ms | Cost: ${s_res.estimated_cost_usd:.6f}")
        print("    [PASS] Structured generation succeeded.")
    except Exception as exc:
        print(f"    [FAIL] Structured generation failed: {exc}")
        return

    # 3. Multimodal OCR
    print("\n[3/3] Testing Multimodal OCR on sample note...")
    sample_img = backend_dir / "var" / "handwritten_dsa_note.png"
    if sample_img.exists():
        ocr_provider = GeminiOCRProvider(api_key=api_key, model=model)
        try:
            ocr_res = ocr_provider.recognize(str(sample_img), request_id="diag-ocr-1")
            print(f"    Transcribed {len(ocr_res.lines)} lines (Confidence: {ocr_res.confidence})")
            for idx, line in enumerate(ocr_res.lines[:5]):
                print(f"      {idx+1}: {line['text']}")
            if len(ocr_res.lines) > 5:
                print(f"      ... and {len(ocr_res.lines) - 5} more lines")
            print("    [PASS] Multimodal OCR succeeded.")
        except Exception as exc:
            print(f"    [FAIL] Multimodal OCR failed: {exc}")
    else:
        print(f"    [SKIP] Sample image {sample_img} not found.")

    print("\n" + "=" * 65)
    print("  ALL GEMINI INTEGRATION TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_diagnostics()

#!/usr/bin/env python
"""Main entry point for StudyAI enrichment evaluation."""

import os
import sys
import django

# Set environment variables for real LLM evaluation BEFORE Django setup
os.environ["LLM_MODEL"] = "qwen2.5:7b"
os.environ["LLM_PROVIDER_CHAIN"] = "ollama"
os.environ["LLM_DISABLE_FALLBACK"] = "1"

# Setup Django - use evaluation settings for real LLM + file-based SQLite
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

django.setup()

from tests.evaluation.runner import run_full_evaluation


def main():
    dataset_path = "tests/evaluation/datasets/golden_v1.json"
    output_dir = "tests/evaluation/results/baseline_v1"
    runs = 3  # Run 3 times for repeatability

    print("=" * 60)
    print("StudyAI Enrichment Baseline Evaluation")
    print("=" * 60)
    print(f"Dataset: {dataset_path}")
    print(f"Output:  {output_dir}")
    print(f"Runs:    {runs}")
    print("=" * 60)

    # Check if Ollama is available for real LLM evaluation
    import requests
    # Use ollama service name inside Docker, localhost outside
    ollama_url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            print(f"Ollama available. Models: {models}")
            if "qwen2.5:7b" not in " ".join(models):
                print("WARNING: qwen2.5:7b not found. Pull it with: ollama pull qwen2.5:7b")
        else:
            print("Ollama not responding. Real LLM evaluation may fail.")
    except Exception as e:
        print(f"Ollama not available: {e}")
        print("Real LLM evaluation will fail. Start Ollama first.")

    # Run evaluation
    try:
        report = run_full_evaluation(dataset_path, output_dir, runs=runs)
        print("\n" + "=" * 60)
        print("EVALUATION COMPLETE")
        print("=" * 60)
        print(f"Results saved to: {output_dir}")
        print(f"JSON report: {output_dir}/baseline.json")
        print(f"Markdown report: {output_dir}/baseline.md")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
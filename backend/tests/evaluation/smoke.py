#!/usr/bin/env python
"""Fast smoke test for StudyAI enrichment - 5 cases × 1 run."""

import os
import sys
import django
import argparse

# Set environment variables for real LLM evaluation BEFORE Django setup
os.environ["LLM_MODEL"] = "qwen2.5:7b"
os.environ["LLM_PROVIDER_CHAIN"] = "ollama"
os.environ["LLM_DISABLE_FALLBACK"] = "1"

# Setup Django - use evaluation settings for real LLM + PostgreSQL
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

django.setup()

from tests.evaluation.runner import run_full_evaluation
from tests.evaluation.runner import load_golden_dataset


# The 5 representative cases for smoke test
SMOKE_CASE_IDS = [
    "eval_001",  # simple_factual - Dijkstra
    "eval_002",  # multi_concept - Hash tables
    "eval_004",  # missing_info - Newton's 2nd law
    "eval_006",  # long_multi_chunk - BST/AVL/Red-Black
    "eval_008",  # distractor_prone - Derivatives
]


def run_smoke_evaluation(dataset_path: str, output_dir: str, case_ids: list = None):
    """Run smoke evaluation on selected cases."""
    from tests.evaluation.runner import run_full_evaluation
    
    if case_ids is None:
        case_ids = SMOKE_CASE_IDS
    
    # Load and filter cases
    all_cases = load_golden_dataset(dataset_path)
    cases = [c for c in all_cases if c["case_id"] in case_ids]
    
    if len(cases) != len(case_ids):
        missing = set(case_ids) - set(c["case_id"] for c in cases)
        raise ValueError(f"Missing cases: {missing}")
    
    print("=" * 60)
    print("StudyAI Enrichment Smoke Test")
    print("=" * 60)
    print(f"Dataset: {dataset_path}")
    print(f"Output:  {output_dir}")
    print(f"Cases:   {[c['case_id'] for c in cases]}")
    print(f"Runs:    1")
    print("=" * 60)
    
    # Create filtered dataset for the runner
    import json
    with open(dataset_path) as f:
        full_dataset = json.load(f)
    
    filtered_dataset = {
        "dataset_version": full_dataset["dataset_version"],
        "created": full_dataset["created"],
        "description": f"Smoke test subset: {len(cases)} cases",
        "reference_book_mapping": {
            k: v for k, v in full_dataset.get("reference_book_mapping", {}).items()
            if k in case_ids
        },
        "cases": cases
    }
    
    filtered_path = os.path.join(output_dir, "smoke_dataset.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(filtered_path, "w") as f:
        json.dump(filtered_dataset, f, indent=2)
    
    # Run evaluation
    report = run_full_evaluation(filtered_path, output_dir, runs=1)
    
    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE")
    print("=" * 60)
    print(f"Results saved to: {output_dir}")
    return report


def main():
    parser = argparse.ArgumentParser(description="Run smoke test evaluation")
    parser.add_argument("--cases", nargs="+", default=SMOKE_CASE_IDS,
                        help="Case IDs to run (default: 5 smoke cases)")
    parser.add_argument("--output", default="tests/evaluation/results/smoke_real_v1",
                        help="Output directory")
    parser.add_argument("--dataset", default="tests/evaluation/datasets/golden_v1.json",
                        help="Golden dataset path")
    args = parser.parse_args()
    
    # Check Ollama
    import requests
    ollama_url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            print(f"Ollama available. Models: {models}")
            if "qwen2.5:7b" not in " ".join(models):
                print("WARNING: qwen2.5:7b not found")
        else:
            print("Ollama not responding")
            sys.exit(1)
    except Exception as e:
        print(f"Ollama not available: {e}")
        sys.exit(1)
    
    try:
        report = run_smoke_evaluation(args.dataset, args.output, args.cases)
        print(f"\nJSON report: {args.output}/baseline.json")
        print(f"Markdown report: {args.output}/baseline.md")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
"""Variant Evaluation for Best Arm (Arm C: New Extractor + Grounded Prompt).

Evaluates:
1. all_covered_control variant cases on test split (9 cases) -> measures D3 false alarm rate.
2. noisy variant cases on test split (20 cases) -> measures noise robustness.
"""
import os
import sys
import json
import time
from typing import Dict, Any, List

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.evaluation_real")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11435")

sys.path.insert(0, os.path.abspath("."))
import django
django.setup()

import providers.llm.chain
providers.llm.chain.record_provider_call = lambda *args, **kwargs: None

from apps.ai_classroom.gap_candidates_v2 import extract_all_candidates_v2
from apps.ai_classroom.candidate_validation import validate_candidate_grounded
from tests.evaluation.match_eval import match_candidate_to_concept
from providers.registry import get_llm_provider

STATUS_TO_CLASS = {
    "gap": "MISSING",
    "partial": "PARTIALLY_COVERED",
    "covered": "COVERED",
    "off_scope": "IRRELEVANT"
}


def load_data():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    dataset_path = os.path.join(base_dir, "tests/evaluation/datasets/golden_v2.json")
    split_path = os.path.join(base_dir, "tests/evaluation/results/candidate_generation_v2/split.json")
    
    with open(dataset_path) as f:
        data = json.load(f)
    with open(split_path) as f:
        split = json.load(f)
        
    test_ids = set(split["test_cases"])
    control_cases = [c for c in data["cases"] if c["base_id"] in test_ids and c.get("variant") == "all_covered_control"]
    noisy_cases = [c for c in data["cases"] if c["base_id"] in test_ids and c.get("variant") == "noisy"]
    
    return data, control_cases, noisy_cases


def evaluate_cases(cases, corpus, variant_name):
    print(f"\nEvaluating {variant_name} ({len(cases)} cases)...")
    shared_llm = get_llm_provider()
    
    case_results = []
    cases_with_false_alarms = 0
    total_calls = 0
    total_gaps_reported = 0
    
    t0 = time.time()
    for idx, case in enumerate(cases):
        case_id = case.get("case_id", case["base_id"])
        base_id = case["base_id"]
        user_note = case["input_note"]
        gold_concepts = case["concepts"]
        
        # Extract candidates
        chunks = [{"chunk_id": cid, "text": corpus[cid]["text"]} for cid in case["reference_chunk_ids"]]
        cands = extract_all_candidates_v2(chunks, max_per_chunk=1, strict_leakage_check=False)
        total_calls += len(cands)
        
        reported_missing_in_case = 0
        cand_details = []
        
        for cand in cands:
            cand_text = cand.concept
            evidence = corpus.get(cand.source_chunk_id, {}).get("text", "") or cand.evidence_span
            
            # Match
            matched_concept = None
            for gc in gold_concepts:
                is_hit, is_frag = match_candidate_to_concept(cand_text, gc)
                if is_hit:
                    matched_concept = gc
                    break
                    
            val = validate_candidate_grounded(
                user_note=user_note,
                candidate_concept=cand_text,
                reference_evidence=evidence,
                llm_provider=shared_llm
            )
            pred_class = val.get("classification", "MISSING")
            if pred_class == "MISSING":
                reported_missing_in_case += 1
                total_gaps_reported += 1
                
            cand_details.append({
                "candidate": cand_text,
                "matched_concept": matched_concept["topic"] if matched_concept else None,
                "gold_status": matched_concept["status"] if matched_concept else None,
                "predicted_class": pred_class,
                "downgraded": val.get("downgraded", False),
                "quote": val.get("note_quote"),
                "reason": val.get("reason", "")
            })
            
        has_false_alarm = reported_missing_in_case > 0
        if has_false_alarm:
            cases_with_false_alarms += 1
            
        case_results.append({
            "case_id": case_id,
            "base_id": base_id,
            "num_candidates": len(cands),
            "reported_gaps": reported_missing_in_case,
            "has_false_alarm": has_false_alarm,
            "candidates": cand_details
        })
        print(f"  [{idx+1}/{len(cases)}] {case_id}: {len(cands)} cands, {reported_missing_in_case} gaps reported")
        
    elapsed = time.time() - t0
    fa_rate = cases_with_false_alarms / len(cases) if cases else 0.0
    print(f"Finished {variant_name} in {elapsed:.1f}s ({elapsed/max(1, total_calls):.2f}s/call)")
    print(f"  Cases with >= 1 reported gap: {cases_with_false_alarms}/{len(cases)} ({fa_rate*100:.1f}%)")
    print(f"  Total gaps reported: {total_gaps_reported}")
    
    return {
        "variant": variant_name,
        "num_cases": len(cases),
        "total_calls": total_calls,
        "elapsed_sec": elapsed,
        "cases_with_false_alarms": cases_with_false_alarms,
        "false_alarm_rate": fa_rate,
        "total_gaps_reported": total_gaps_reported,
        "cases": case_results
    }


def main():
    data, control_cases, noisy_cases = load_data()
    corpus = data["corpus"]
    
    # 1. Evaluate Control cases (all_covered_control)
    control_metrics = evaluate_cases(control_cases, corpus, "all_covered_control")
    
    # 2. Evaluate Noisy cases
    noisy_metrics = evaluate_cases(noisy_cases, corpus, "noisy")
    
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tests/evaluation/results/candidate_generation_v2/"))
    out_path = os.path.join(output_dir, "phase_d_variants_results.json")
    
    with open(out_path, "w") as f:
        json.dump({
            "control": control_metrics,
            "noisy": noisy_metrics
        }, f, indent=2)
        
    print(f"\nSaved variant results to: {out_path}")


if __name__ == "__main__":
    main()

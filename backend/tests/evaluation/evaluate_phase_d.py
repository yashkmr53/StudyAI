"""Phase D Downstream Qwen Evaluation Runner.

Evaluates the 5 arms on the test split (base variant):
- Arm A: Baseline extractor (capped at 6/case) + Current prompt
- Arm B: New extractor (v2, max 1/chunk) + Current prompt
- Arm C: New extractor (v2, max 1/chunk) + Grounded prompt
- ORACLE-EXTRACTABLE: Gold extractable concepts (92) + Grounded prompt
- ORACLE: All gold concepts (125) + Grounded prompt

Calculates 4-way classification metrics, end-to-end gap recall/precision,
bootstrap 95% confidence intervals by base_id, and error failure taxonomy.
"""
import os
import sys
import json
import time
import random
from typing import Dict, Any, List, Tuple
from collections import defaultdict, Counter

# Ensure Mac OpenMP safety
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.evaluation_real")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11435")

sys.path.insert(0, os.path.abspath("."))
import django
django.setup()

import providers.llm.chain
providers.llm.chain.record_provider_call = lambda *args, **kwargs: None

from unittest.mock import patch
from apps.ai_classroom.gap_candidates import extract_all_candidates as extract_all_candidates_v1
from apps.ai_classroom.gap_candidates_v2 import extract_all_candidates_v2
from apps.ai_classroom.candidate_validation import (
    validate_candidate_with_qwen,
    validate_candidate_grounded
)
from tests.evaluation.match_eval import match_candidate_to_concept

STATUS_TO_CLASS = {
    "gap": "MISSING",
    "partial": "PARTIALLY_COVERED",
    "covered": "COVERED",
    "off_scope": "IRRELEVANT"
}
CLASSES = ["MISSING", "PARTIALLY_COVERED", "COVERED", "IRRELEVANT"]


def load_dataset_and_split():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    dataset_path = os.path.join(base_dir, "tests/evaluation/datasets/golden_v2.json")
    split_path = os.path.join(base_dir, "tests/evaluation/results/candidate_generation_v2/split.json")
    
    with open(dataset_path) as f:
        data = json.load(f)
    with open(split_path) as f:
        split = json.load(f)
        
    test_base_cases = [
        c for c in data["cases"]
        if c["base_id"] in split["test_cases"] and c.get("variant") == "base"
    ]
    return data, split, test_base_cases


def get_arm_a_candidates(test_cases, corpus, cap=6):
    """Arm A: Baseline extractor, deduped, capped at 6 per case."""
    case_candidates = {}
    for case in test_cases:
        chunks = [{"id": cid, "content": corpus[cid]["text"]} for cid in case["reference_chunk_ids"]]
        raw_cands = extract_all_candidates_v1(chunks, max_per_chunk=5)
        raw_cands.sort(key=lambda x: x.confidence, reverse=True)
        seen = set()
        deduped = []
        for c in raw_cands:
            norm = c.concept.lower().strip()
            if norm not in seen:
                seen.add(norm)
                deduped.append(c)
        case_candidates[case["base_id"]] = deduped[:cap]
    return case_candidates


def get_arm_b_c_candidates(test_cases, corpus, max_per_chunk=1):
    """Arm B / C: New reference-structured extractor v2, max 1 per chunk."""
    case_candidates = {}
    for case in test_cases:
        chunks = [{"chunk_id": cid, "text": corpus[cid]["text"]} for cid in case["reference_chunk_ids"]]
        cands = extract_all_candidates_v2(chunks, max_per_chunk=max_per_chunk, strict_leakage_check=False)
        case_candidates[case["base_id"]] = cands
    return case_candidates


def get_oracle_extractable_candidates(test_cases, corpus):
    """ORACLE-EXTRACTABLE: Gold concepts whose topic or alias appears in reference chunks."""
    case_candidates = {}
    for case in test_cases:
        cands = []
        for concept in case["concepts"]:
            topic = concept["topic"]
            aliases = concept.get("aliases", [])
            targets = [topic] + aliases
            
            # Find matching chunk
            matched_chunk = None
            for cid in case["reference_chunk_ids"]:
                chunk_text = corpus[cid]["text"].lower()
                for target in targets:
                    if target.lower() in chunk_text:
                        matched_chunk = (cid, corpus[cid]["text"])
                        break
                if matched_chunk:
                    break
                    
            if matched_chunk:
                cands.append({
                    "concept": topic,
                    "source_chunk_id": matched_chunk[0],
                    "evidence": matched_chunk[1],
                    "gold_concept": concept
                })
        case_candidates[case["base_id"]] = cands
    return case_candidates


def get_oracle_candidates(test_cases, corpus):
    """ORACLE: All gold concepts as candidates."""
    case_candidates = {}
    for case in test_cases:
        cands = []
        primary_chunk_id = case["reference_chunk_ids"][0]
        primary_chunk_text = corpus[primary_chunk_id]["text"]
        for concept in case["concepts"]:
            topic = concept["topic"]
            aliases = concept.get("aliases", [])
            targets = [topic] + aliases
            
            # Try to find chunk where it appears, or default to primary
            evidence = primary_chunk_text
            evidence_cid = primary_chunk_id
            for cid in case["reference_chunk_ids"]:
                chunk_text = corpus[cid]["text"]
                if any(t.lower() in chunk_text.lower() for t in targets):
                    evidence = chunk_text
                    evidence_cid = cid
                    break
                    
            cands.append({
                "concept": topic,
                "source_chunk_id": evidence_cid,
                "evidence": evidence,
                "gold_concept": concept
            })
        case_candidates[case["base_id"]] = cands
    return case_candidates


def run_evaluation_arm(arm_name, test_cases, case_candidates_dict, prompt_type, corpus):
    """Executes evaluation for a single arm."""
    print(f"\n==================== RUNNING {arm_name} ====================")
    total_calls = sum(len(cands) for cands in case_candidates_dict.values())
    print(f"Total candidates/calls to evaluate: {total_calls}")
    
    start_time = time.time()
    results = []
    
    # Patch record_provider_call to avoid SQLite table warnings
    from providers.registry import get_llm_provider
    shared_llm = get_llm_provider()
    with patch("providers.llm.chain.record_provider_call"):
        for case_idx, case in enumerate(test_cases):
            base_id = case["base_id"]
            user_note = case["input_note"]
            cands = case_candidates_dict.get(base_id, [])
            gold_concepts = case["concepts"]
            
            print(f"[{case_idx+1}/{len(test_cases)}] {base_id}: evaluating {len(cands)} candidates...")
            
            for cand in cands:
                # Extract candidate concept text and evidence
                if hasattr(cand, "concept"):
                    cand_text = cand.concept
                    chunk_id = cand.source_chunk_id
                    evidence = getattr(cand, "source_content", None) or corpus.get(chunk_id, {}).get("text", "")
                    gold_obj = None
                elif isinstance(cand, dict) and "gold_concept" in cand:
                    cand_text = cand["concept"]
                    chunk_id = cand["source_chunk_id"]
                    evidence = cand["evidence"]
                    gold_obj = cand["gold_concept"]
                else:
                    cand_text = str(cand)
                    evidence = ""
                    gold_obj = None
                    
                # Match against gold concepts if not already assigned
                matched_concept = gold_obj
                if matched_concept is None:
                    for gc in gold_concepts:
                        is_hit, is_frag = match_candidate_to_concept(cand_text, gc)
                        if is_hit:
                            matched_concept = gc
                            break
                            
                gold_status = matched_concept["status"] if matched_concept else None
                gold_class = STATUS_TO_CLASS.get(gold_status) if gold_status else None
                
                # Execute Qwen call
                call_start = time.time()
                if prompt_type == "v2":
                    val = validate_candidate_with_qwen(
                        user_note=user_note,
                        candidate_concept=cand_text,
                        reference_evidence=evidence,
                        llm_provider=shared_llm,
                        prompt_version="v2"
                    )
                    pred_class = val.get("classification", "MISSING")
                    downgraded = False
                    quote = None
                elif prompt_type == "grounded":
                    val = validate_candidate_grounded(
                        user_note=user_note,
                        candidate_concept=cand_text,
                        reference_evidence=evidence,
                        llm_provider=shared_llm
                    )
                    pred_class = val.get("classification", "MISSING")
                    downgraded = val.get("downgraded", False)
                    quote = val.get("note_quote")
                else:
                    raise ValueError(f"Unknown prompt type: {prompt_type}")
                call_lat = time.time() - call_start
                
                results.append({
                    "arm": arm_name,
                    "base_id": base_id,
                    "candidate": cand_text,
                    "evidence_snippet": evidence[:80],
                    "matched_concept": matched_concept["topic"] if matched_concept else None,
                    "gold_status": gold_status,
                    "gold_class": gold_class,
                    "predicted_class": pred_class,
                    "downgraded": downgraded,
                    "quote": quote,
                    "reason": val.get("reason", ""),
                    "latency": call_lat
                })
                
    elapsed = time.time() - start_time
    print(f"Finished {arm_name} in {elapsed:.1f}s ({elapsed/max(1, total_calls):.2f}s per call)")
    return results, elapsed


def compute_metrics(results, test_cases):
    """Computes all mandatory metrics for an arm."""
    total_calls = len(results)
    latencies = [r["latency"] for r in results]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    
    # 1. Classification Metrics (on matched candidates)
    matched_results = [r for r in results if r["gold_class"] is not None]
    unmatched_results = [r for r in results if r["gold_class"] is None]
    
    correct = sum(1 for r in matched_results if r["predicted_class"] == r["gold_class"])
    accuracy = correct / len(matched_results) if matched_results else 0.0
    
    # Per-class P/R/F1
    class_metrics = {}
    f1_list = []
    for c in CLASSES:
        tp = sum(1 for r in matched_results if r["predicted_class"] == c and r["gold_class"] == c)
        fp = sum(1 for r in matched_results if r["predicted_class"] == c and r["gold_class"] != c)
        fn = sum(1 for r in matched_results if r["predicted_class"] != c and r["gold_class"] == c)
        n_gold = sum(1 for r in matched_results if r["gold_class"] == c)
        
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        
        class_metrics[c] = {
            "n_gold": n_gold,
            "tp": tp, "fp": fp, "fn": fn,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "reliable": n_gold >= 10
        }
        if n_gold > 0:
            f1_list.append(f1)
            
    macro_f1 = sum(f1_list) / len(f1_list) if f1_list else 0.0
    
    # 2. False gaps and Irrelevant gaps
    # A candidate classified as MISSING is a true gap ONLY if it matches a gold concept with status == 'gap'
    reported_gaps = [r for r in results if r["predicted_class"] == "MISSING"]
    true_gaps_found = set()
    false_gap_count = 0
    irrelevant_gap_count = 0
    
    for r in reported_gaps:
        if r["gold_status"] == "gap":
            true_gaps_found.add((r["base_id"], r["matched_concept"]))
        else:
            false_gap_count += 1
            if r["gold_status"] == "off_scope":
                irrelevant_gap_count += 1
                
    # 3. End-to-end Gap Recall & Precision
    all_gold_gaps = set()
    for case in test_cases:
        for cp in case["concepts"]:
            if cp["status"] == "gap":
                all_gold_gaps.add((case["base_id"], cp["topic"]))
                
    total_gold_gaps = len(all_gold_gaps)
    e2e_gap_recall = len(true_gaps_found) / total_gold_gaps if total_gold_gaps > 0 else 0.0
    e2e_gap_precision = len(true_gaps_found) / len(reported_gaps) if reported_gaps else 0.0
    
    # 4. Downgrade count
    downgrade_count = sum(1 for r in results if r.get("downgraded", False))
    
    return {
        "total_calls": total_calls,
        "avg_latency": avg_latency,
        "matched_candidates": len(matched_results),
        "unmatched_candidates": len(unmatched_results),
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "class_metrics": class_metrics,
        "reported_gaps": len(reported_gaps),
        "true_gaps_found": len(true_gaps_found),
        "false_gap_count": false_gap_count,
        "irrelevant_gap_count": irrelevant_gap_count,
        "downgrade_count": downgrade_count,
        "total_gold_gaps": total_gold_gaps,
        "e2e_gap_recall": e2e_gap_recall,
        "e2e_gap_precision": e2e_gap_precision,
    }


def run_bootstrap(results, test_cases, n_iterations=1000, seed=42):
    """Bootstrap 95% confidence intervals resampled by base_id."""
    rng = random.Random(seed)
    base_ids = [c["base_id"] for c in test_cases]
    case_map = {c["base_id"]: c for c in test_cases}
    
    # Pre-group results by base_id
    res_by_case = defaultdict(list)
    for r in results:
        res_by_case[r["base_id"]].append(r)
        
    recalls = []
    precisions = []
    accuracies = []
    
    for _ in range(n_iterations):
        sampled_ids = rng.choices(base_ids, k=len(base_ids))
        
        # Pool sampled results & cases
        sampled_results = []
        sampled_gold_gaps = set()
        
        for idx, bid in enumerate(sampled_ids):
            # Unique identifier for this sample instance to handle replicates
            inst_tag = f"{bid}_{idx}"
            for r in res_by_case[bid]:
                sampled_results.append({**r, "inst_tag": inst_tag})
            case = case_map[bid]
            for cp in case["concepts"]:
                if cp["status"] == "gap":
                    sampled_gold_gaps.add((inst_tag, cp["topic"]))
                    
        # Calculate e2e recall & precision
        reported_gaps = [r for r in sampled_results if r["predicted_class"] == "MISSING"]
        true_gaps = set()
        for r in reported_gaps:
            if r["gold_status"] == "gap":
                true_gaps.add((r["inst_tag"], r["matched_concept"]))
                
        rec = len(true_gaps) / len(sampled_gold_gaps) if sampled_gold_gaps else 0.0
        prec = len(true_gaps) / len(reported_gaps) if reported_gaps else 0.0
        
        # Classification accuracy
        matched = [r for r in sampled_results if r["gold_class"] is not None]
        corr = sum(1 for r in matched if r["predicted_class"] == r["gold_class"])
        acc = corr / len(matched) if matched else 0.0
        
        recalls.append(rec)
        precisions.append(prec)
        accuracies.append(acc)
        
    recalls.sort()
    precisions.sort()
    accuracies.sort()
    
    ci_recall = (recalls[int(0.025 * n_iterations)], recalls[int(0.975 * n_iterations)])
    ci_precision = (precisions[int(0.025 * n_iterations)], precisions[int(0.975 * n_iterations)])
    ci_accuracy = (accuracies[int(0.025 * n_iterations)], accuracies[int(0.975 * n_iterations)])
    
    return {
        "recall_95ci": ci_recall,
        "precision_95ci": ci_precision,
        "accuracy_95ci": ci_accuracy
    }


def main():
    print("Initializing Phase D Evaluation...")
    data, split, test_base_cases = load_dataset_and_split()
    corpus = data["corpus"]
    
    print(f"Loaded {len(test_base_cases)} test base cases.")
    
    # Prepare candidate sets for each arm
    print("\nPreparing candidates across all arms:")
    arm_a_cands = get_arm_a_candidates(test_base_cases, corpus, cap=6)
    arm_b_c_cands = get_arm_b_c_candidates(test_base_cases, corpus, max_per_chunk=1)
    oracle_ext_cands = get_oracle_extractable_candidates(test_base_cases, corpus)
    oracle_cands = get_oracle_candidates(test_base_cases, corpus)
    
    print(f"  Arm A candidates: {sum(len(c) for c in arm_a_cands.values())}")
    print(f"  Arm B/C candidates: {sum(len(c) for c in arm_b_c_cands.values())}")
    print(f"  ORACLE-EXTRACTABLE candidates: {sum(len(c) for c in oracle_ext_cands.values())}")
    print(f"  ORACLE candidates: {sum(len(c) for c in oracle_cands.values())}")
    
    total_planned = (
        sum(len(c) for c in arm_a_cands.values()) +
        sum(len(c) for c in arm_b_c_cands.values()) * 2 +
        sum(len(c) for c in oracle_ext_cands.values()) +
        sum(len(c) for c in oracle_cands.values())
    )
    print(f"\nTOTAL PLANNED QWEN CALLS: {total_planned} (Budget: <= 600)")
    assert total_planned <= 600, f"Planned calls {total_planned} exceeds 600!"
    
    all_arms_results = {}
    all_arms_metrics = {}
    all_arms_ci = {}
    
    # 1. Arm A
    res_a, lat_a = run_evaluation_arm("Arm A", test_base_cases, arm_a_cands, "v2", corpus)
    all_arms_results["Arm A"] = res_a
    all_arms_metrics["Arm A"] = compute_metrics(res_a, test_base_cases)
    all_arms_ci["Arm A"] = run_bootstrap(res_a, test_base_cases)
    
    # 2. Arm B
    res_b, lat_b = run_evaluation_arm("Arm B", test_base_cases, arm_b_cands := arm_b_c_cands, "v2", corpus)
    all_arms_results["Arm B"] = res_b
    all_arms_metrics["Arm B"] = compute_metrics(res_b, test_base_cases)
    all_arms_ci["Arm B"] = run_bootstrap(res_b, test_base_cases)
    
    # 3. Arm C
    res_c, lat_c = run_evaluation_arm("Arm C", test_base_cases, arm_b_c_cands, "grounded", corpus)
    all_arms_results["Arm C"] = res_c
    all_arms_metrics["Arm C"] = compute_metrics(res_c, test_base_cases)
    all_arms_ci["Arm C"] = run_bootstrap(res_c, test_base_cases)
    
    # 4. ORACLE-EXTRACTABLE
    res_oe, lat_oe = run_evaluation_arm("ORACLE-EXTRACTABLE", test_base_cases, oracle_ext_cands, "grounded", corpus)
    all_arms_results["ORACLE-EXTRACTABLE"] = res_oe
    all_arms_metrics["ORACLE-EXTRACTABLE"] = compute_metrics(res_oe, test_base_cases)
    all_arms_ci["ORACLE-EXTRACTABLE"] = run_bootstrap(res_oe, test_base_cases)
    
    # 5. ORACLE
    res_o, lat_o = run_evaluation_arm("ORACLE", test_base_cases, oracle_cands, "grounded", corpus)
    all_arms_results["ORACLE"] = res_o
    all_arms_metrics["ORACLE"] = compute_metrics(res_o, test_base_cases)
    all_arms_ci["ORACLE"] = run_bootstrap(res_o, test_base_cases)
    
    # Save raw outputs
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tests/evaluation/results/candidate_generation_v2/"))
    json_path = os.path.join(output_dir, "phase_d_raw_results.json")
    
    with open(json_path, "w") as f:
        json.dump({
            "metrics": all_arms_metrics,
            "bootstrap_95ci": all_arms_ci,
            "results": all_arms_results
        }, f, indent=2)
        
    print(f"\nSuccessfully saved Phase D raw results to: {json_path}")
    
    # Summary Table
    print("\n" + "="*80)
    print("PHASE D RESULTS SUMMARY (20 Test Base Cases, 125 Gold Concepts, 56 Gold Gaps)")
    print("="*80)
    print(f"{'Arm':<20} | {'Calls':<6} | {'4-way Acc':<10} | {'Macro-F1':<10} | {'Gap Rec':<10} | {'Gap Prec':<10} | {'False Gaps':<10}")
    print("-" * 86)
    for arm in ["Arm A", "Arm B", "Arm C", "ORACLE-EXTRACTABLE", "ORACLE"]:
        m = all_arms_metrics[arm]
        ci = all_arms_ci[arm]
        acc_str = f"{m['accuracy']*100:.1f}%"
        mf1_str = f"{m['macro_f1']:.3f}"
        rec_str = f"{m['e2e_gap_recall']*100:.1f}% [{ci['recall_95ci'][0]*100:.1f}, {ci['recall_95ci'][1]*100:.1f}]"
        prec_str = f"{m['e2e_gap_precision']*100:.1f}% [{ci['precision_95ci'][0]*100:.1f}, {ci['precision_95ci'][1]*100:.1f}]"
        fg_str = f"{m['false_gap_count']}"
        print(f"{arm:<20} | {m['total_calls']:<6} | {acc_str:<10} | {mf1_str:<10} | {rec_str:<22} | {prec_str:<22} | {fg_str:<10}")


if __name__ == "__main__":
    main()

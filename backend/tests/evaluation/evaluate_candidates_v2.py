"""Phase C: Candidate-Only Evaluation for candidate_generation_v2.

Evaluates the reference-structured extractor on dev and test splits.
Produces C1-C4 metrics and generates the 50 seeded random unmatched test candidates
sample to tests/evaluation/results/candidate_generation_v2/unmatched_sample.csv.
"""
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import json
import csv
import random
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict

from apps.ai_classroom.gap_candidates_v2 import (
    extract_all_candidates_v2,
    extract_candidates_from_chunk_v2,
    normalize_canonical_key,
    GapCandidateV2,
)
try:
    from match_eval import match_candidate_to_concept
except ImportError:
    from tests.evaluation.match_eval import match_candidate_to_concept

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
DATASET_PATH = os.path.join(BASE_DIR, "tests/evaluation/datasets/golden_v2.json")
METADATA_PATH = os.path.join(BASE_DIR, "tests/evaluation/datasets/golden_v2_metadata.json")
SPLIT_PATH = os.path.join(BASE_DIR, "tests/evaluation/results/candidate_generation_v2/split.json")
OUTPUT_CSV_PATH = os.path.join(BASE_DIR, "tests/evaluation/results/candidate_generation_v2/unmatched_sample.csv")
OUTPUT_CSV_BACKEND = os.path.join(BASE_DIR, "backend/tests/evaluation/results/candidate_generation_v2/unmatched_sample.csv")


def run_candidate_evaluation(max_per_chunk: int = 1, random_seed: int = 42) -> Dict[str, Any]:
    print("=" * 80)
    print(f"RUNNING CANDIDATE-ONLY EVALUATION (Phase C, max_per_chunk={max_per_chunk})")
    print("=" * 80)

    with open(SPLIT_PATH) as f:
        split = json.load(f)
    dev_case_ids = set(split["dev_cases"])
    test_case_ids = set(split["test_cases"])

    with open(DATASET_PATH) as f:
        v2 = json.load(f)
    corpus = v2["corpus"]
    cases = v2["cases"]

    results = {}

    for split_name, split_case_ids in [("dev", dev_case_ids), ("test", test_case_ids)]:
        split_cases = [c for c in cases if c["case_id"] in split_case_ids]
        
        total_chunks = 0
        total_candidates_emitted = 0
        unique_gold_hits = set()
        total_gold_concepts = 0
        fragments_count = 0
        single_token_count = 0

        status_gold_count = defaultdict(int)
        status_hits_count = defaultdict(int)
        
        # Track unmatched candidates for sample generation
        unmatched_candidates = []

        for case in split_cases:
            cid = case["case_id"]
            case_concepts = case["concepts"]
            
            for cp in case_concepts:
                total_gold_concepts += 1
                status_gold_count[cp["status"]] += 1

            # Prepare authorized reference chunks
            ref_chunks = []
            for r_id in case["reference_chunk_ids"]:
                total_chunks += 1
                chunk_data = corpus.get(r_id, {})
                ref_chunks.append({
                    "chunk_id": r_id,
                    "text": chunk_data.get("text", ""),
                    "metadata": chunk_data.get("metadata", {})
                })

            # Extract candidates with leakage guard
            case_candidates = extract_all_candidates_v2(
                ref_chunks,
                max_per_chunk=max_per_chunk,
                strict_leakage_check=False
            )
            total_candidates_emitted += len(case_candidates)

            # Evaluate matches against gold concepts
            for cand in case_candidates:
                cand_text = cand.concept
                words = cand_text.split()
                if len(words) == 1:
                    single_token_count += 1

                cand_is_hit = False
                cand_is_frag = False

                for cp in case_concepts:
                    hit, is_frag = match_candidate_to_concept(cand_text, cp)
                    if hit:
                        cand_is_hit = True
                        if (cid, cp["topic"]) not in unique_gold_hits:
                            unique_gold_hits.add((cid, cp["topic"]))
                            status_hits_count[cp["status"]] += 1
                    if is_frag:
                        cand_is_frag = True

                if cand_is_frag:
                    fragments_count += 1

                if not cand_is_hit:
                    unmatched_candidates.append({
                        "case_id": cid,
                        "chunk_id": cand.source_chunk_id,
                        "candidate": cand.concept,
                        "canonical_key": cand.canonical_key,
                        "salience_score": round(cand.salience_score, 4),
                        "semantic_similarity": round(cand.semantic_similarity, 4),
                        "extraction_method": cand.extraction_method,
                        "evidence_span": cand.evidence_span[:120],
                    })

        # Calculate metrics
        num_cases = len(split_cases)
        cands_per_case = total_candidates_emitted / num_cases if num_cases else 0.0
        cands_per_chunk = total_candidates_emitted / total_chunks if total_chunks else 0.0
        strict_precision = len(unique_gold_hits) / total_candidates_emitted if total_candidates_emitted else 0.0
        recall = len(unique_gold_hits) / total_gold_concepts if total_gold_concepts else 0.0
        f1 = (2 * strict_precision * recall / (strict_precision + recall)) if (strict_precision + recall) else 0.0
        fragment_rate = fragments_count / total_candidates_emitted if total_candidates_emitted else 0.0
        single_token_rate = single_token_count / total_candidates_emitted if total_candidates_emitted else 0.0

        # Status specific recall
        recall_by_status = {}
        for st in ["gap", "partial", "covered", "off_scope"]:
            g = status_gold_count[st]
            h = status_hits_count[st]
            recall_by_status[st] = {
                "gold": g,
                "hits": h,
                "recall": h / g if g else 0.0
            }

        # Extractive ceiling on this split
        # From Phase A report:
        # Dev lenient ceiling = 91/117 (77.8%)
        # Test lenient ceiling = 92/125 (73.6%)
        lenient_ceiling = 0.778 if split_name == "dev" else 0.736
        fraction_of_ceiling = recall / lenient_ceiling if lenient_ceiling else 0.0

        split_results = {
            "split": split_name,
            "num_cases": num_cases,
            "total_chunks": total_chunks,
            "total_candidates_emitted": total_candidates_emitted,
            "candidates_per_case": cands_per_case,
            "candidates_per_chunk": cands_per_chunk,
            "unique_gold_hits": len(unique_gold_hits),
            "total_gold_concepts": total_gold_concepts,
            "recall": recall,
            "lenient_ceiling": lenient_ceiling,
            "fraction_of_ceiling": fraction_of_ceiling,
            "strict_unique_precision": strict_precision,
            "f1_score": f1,
            "fragment_count": fragments_count,
            "fragment_rate": fragment_rate,
            "single_token_count": single_token_count,
            "single_token_rate": single_token_rate,
            "recall_by_status": recall_by_status,
            "unmatched_count": len(unmatched_candidates),
        }
        results[split_name] = split_results

        print(f"\n--- Results on {split_name.upper()} Split ({num_cases} cases, {total_chunks} chunks) ---")
        print(f"  Candidates Emitted: {total_candidates_emitted} ({cands_per_case:.1f}/case, {cands_per_chunk:.2f}/chunk)")
        print(f"  Unique Gold Hits: {len(unique_gold_hits)} / {total_gold_concepts} ({recall:.1%})")
        print(f"  Lenient Extractive Ceiling: {lenient_ceiling:.1%} -> Fraction of Ceiling: {fraction_of_ceiling:.1%}")
        print(f"  Strict Unique-Concept Precision: {strict_precision:.1%}")
        print(f"  F1 Score: {f1:.3f}")
        print(f"  Fragment Rate: {fragments_count}/{total_candidates_emitted} ({fragment_rate:.1%})")
        print(f"  Single Token Rate: {single_token_count}/{total_candidates_emitted} ({single_token_rate:.1%})")
        print("  Recall by concept status:")
        for st, st_data in recall_by_status.items():
            print(f"    {st:<12}: {st_data['hits']} / {st_data['gold']} ({st_data['recall']:.1%})")

        # Generate seeded sample of 50 unmatched test candidates
        if split_name == "test":
            print(f"\nSampling 50 seeded random unmatched test candidates (seed={random_seed})...")
            random.seed(random_seed)
            sample_size = min(50, len(unmatched_candidates))
            sample = random.sample(unmatched_candidates, sample_size)
            
            for path in [OUTPUT_CSV_PATH, OUTPUT_CSV_BACKEND]:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", newline="") as csvfile:
                    fieldnames = [
                        "sample_id", "case_id", "chunk_id", "candidate",
                        "canonical_key", "salience_score", "extraction_method",
                        "human_label", "evidence_span"
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for idx, item in enumerate(sample, 1):
                        row = {
                            "sample_id": idx,
                            "case_id": item["case_id"],
                            "chunk_id": item["chunk_id"],
                            "candidate": item["candidate"],
                            "canonical_key": item["canonical_key"],
                            "salience_score": item["salience_score"],
                            "extraction_method": item["extraction_method"],
                            "human_label": "",  # To be completed during human review
                            "evidence_span": item["evidence_span"]
                        }
                        writer.writerow(row)
            print(f"  Wrote {sample_size} candidates to {OUTPUT_CSV_PATH}")

    # Check Pre-registered Thresholds on Test Split
    test_res = results["test"]
    c1_overall = test_res["fraction_of_ceiling"] >= 0.85 or test_res["recall"] >= 0.626
    c1_gap = test_res["recall_by_status"]["gap"]["recall"] >= 0.661
    c1_pass = c1_overall and c1_gap
    c2_pass = test_res["strict_unique_precision"] >= 0.40
    c3_pass = test_res["candidates_per_chunk"] <= 1.6
    c4_pass = test_res["fragment_rate"] <= 0.02

    print("\n" + "=" * 80)
    print("PRE-REGISTERED THRESHOLDS CHECK (ON TEST SPLIT):")
    print("=" * 80)
    print(f"C1  Overall Recall >= 62.6% AND Gap Recall >= 66.1%: "
          f"Overall={test_res['recall']:.1%} (Ratio={test_res['fraction_of_ceiling']:.1%}), "
          f"Gap={test_res['recall_by_status']['gap']['recall']:.1%} -> {'PASS' if c1_pass else 'NOT MET'}")
    print(f"C2  Strict Precision >= 40.0%: {test_res['strict_unique_precision']:.1%} -> {'PASS' if c2_pass else 'NOT MET'}")
    print(f"C3  Candidates per Chunk <= 1.6: {test_res['candidates_per_chunk']:.2f} -> {'PASS' if c3_pass else 'NOT MET'}")
    print(f"C4  Fragment Rate <= 2.0%: {test_res['fragment_rate']:.1%} -> {'PASS' if c4_pass else 'NOT MET'}")
    
    # Baseline comparison
    baseline_test_prec = 0.126
    prec_gain = test_res["strict_unique_precision"] - baseline_test_prec
    print(f"\nPrecision Gain vs Baseline (12.6%): +{prec_gain:.1%} absolute")

    return results


if __name__ == "__main__":
    run_candidate_evaluation(max_per_chunk=1)

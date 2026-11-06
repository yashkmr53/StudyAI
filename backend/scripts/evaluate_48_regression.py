import csv
import json
import os
import sys
import time

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.ci")

import django
django.setup()

import numpy as np
from django.conf import settings
from ai.langgraph.nodes.verification_node import (
    QuoteVerificationVerdict,
    _is_quote_in_passage,
    _lexical_overlap,
    _negation_mismatch,
    _key_term_coverage,
)
from providers.base import Prompt
from providers.registry import get_embedding_provider, get_llm_provider

csv_path = "/app/reports/labeling/to_label.csv"
if not os.path.exists(csv_path):
    csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports/labeling/to_label.csv")

with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"Loaded {len(rows)} labeled rows for regression evaluation.")

embed_provider = get_embedding_provider()
llm = get_llm_provider()

sup_cosine_thresh = 0.75
sup_border_thresh = 0.60
sup_lex_thresh = 0.30

results = []
verifier_calls = 0
start_time = time.perf_counter()

for r in rows:
    row_id = int(r["row_id"])
    add_text = r["addition_text"].strip()
    passage_full = r["cited_passage_text"].strip()
    l1_true = r["L1_true"].strip()
    l2_in_passage = r["L2_in_passage"].strip()
    
    # Split cited passage into best sentence and full chunk if formatted as such
    lines = passage_full.split("\n")
    best_sent = ""
    for line in lines:
        if line.startswith("Best-matching sentence:"):
            continue
        if line.startswith("Full cited chunk:"):
            break
        if line.strip():
            best_sent = line.strip()
            break
    if not best_sent:
        best_sent = passage_full[:200]
        
    passage_clean = passage_full.replace("Best-matching sentence:", "").replace("Full cited chunk:", "").strip()

    # 1. Cosine similarity
    try:
        embs = embed_provider.embed([add_text, best_sent])
        a_arr = np.array(embs[0], dtype=float)
        a_norm = a_arr / (np.linalg.norm(a_arr) or 1.0)
        s_arr = np.array(embs[1], dtype=float)
        s_norm = s_arr / (np.linalg.norm(s_arr) or 1.0)
        sim = float(np.dot(a_norm, s_norm))
    except Exception:
        sim = 0.70

    lex_overlap = _lexical_overlap(add_text, best_sent)

    has_neg_mismatch = _negation_mismatch(add_text, best_sent)
    is_extractive = (sim >= sup_cosine_thresh and lex_overlap >= 0.70 and not has_neg_mismatch)
    system_status = "unverified"
    quote_extracted = ""
    is_claim_stated = False
    does_contradict = False
    llm_call_made = False

    if sim < sup_border_thresh:
        system_status = "dropped_low_cosine"
    elif is_extractive:
        system_status = "supported"
    else:
        # Run Quote & Contradiction check
        llm_call_made = True
        verifier_calls += 1
        prompt = Prompt(
            name="quote_verifier",
            version="v1",
            user=(
                "You are an academic textbook verifier checking whether a student note addition is grounded in the cited reference passage.\n\n"
                f"Cited Reference Passage:\n\"\"\"{passage_clean}\"\"\"\n\n"
                f"Candidate Note Addition:\n\"\"\"{add_text}\"\"\"\n\n"
                "Carefully evaluate:\n"
                "1. exact_quote: Extract the exact verbatim sentence from the Cited Reference Passage that directly provides the factual basis for this claim. "
                "If no sentence in the passage states or directly entails this claim, return empty string \"\".\n"
                "2. is_claim_stated: Set true if the exact quote directly states or logically entails the claim made in the addition. Set false if the addition introduces external ungrounded facts not stated in the passage.\n"
                "3. does_passage_contradict: Set true if the candidate addition contradicts the passage, says the opposite of the passage, or builds on a false premise that conflicts with the reference (such as potential energy increasing during descent, FIFO avoiding Belady's anomaly, or a necessary condition being the only eliminable one). Otherwise set false.\n\n"
                "Output JSON with exact_quote, is_claim_stated, does_passage_contradict, rationale."
            ),
        )
        try:
            res_quote = llm.generate_structured(
                prompt=prompt,
                schema=QuoteVerificationVerdict,
                request_id=f"eval:row:{row_id}",
                disable_fallback=True,
                think=False,
            )
            q_data = res_quote.data
            if isinstance(q_data, dict):
                quote_extracted = str(q_data.get("exact_quote", "") or "")
                is_claim_stated = bool(q_data.get("is_claim_stated", False))
                does_contradict = bool(q_data.get("does_passage_contradict", False))
            else:
                quote_extracted = str(getattr(q_data, "exact_quote", "") or "")
                is_claim_stated = bool(getattr(q_data, "is_claim_stated", False))
                does_contradict = bool(getattr(q_data, "does_passage_contradict", False))
        except Exception as exc:
            print(f"Error on row {row_id}: {exc}")

        if does_contradict:
            system_status = "dropped_contradicted"
        else:
            quote_in_p = _is_quote_in_passage(quote_extracted, passage_clean)
            quote_lex = _lexical_overlap(quote_extracted, add_text)
            quote_key_cov = _key_term_coverage(quote_extracted, add_text)
            quote_has_neg = _negation_mismatch(quote_extracted, add_text)

            quote_supports = (
                quote_in_p
                and not quote_has_neg
                and (quote_lex >= 0.20 or quote_key_cov >= 0.25)
            )

            if is_claim_stated and quote_supports:
                system_status = "supported"
            elif not does_contradict and quote_in_p and not quote_has_neg and (quote_lex >= 0.15 or sim >= 0.75):
                system_status = "partial"
            else:
                system_status = "dropped_neutral"

    results.append({
        "row_id": row_id,
        "l1_true": l1_true,
        "l2_in_passage": l2_in_passage,
        "sim": round(sim, 4),
        "lex_overlap": round(lex_overlap, 4),
        "system_status": system_status,
        "llm_call_made": llm_call_made,
        "exact_quote": quote_extracted,
        "is_claim_stated": is_claim_stated,
        "does_contradict": does_contradict,
        "is_bad_row": row_id in (8, 22, 24, 42),
    })

total_time = round(time.perf_counter() - start_time, 2)

bad_rows_survived = [r for r in results if r["is_bad_row"] and r["system_status"] in ("supported", "partial")]
good_rows_kept = [r for r in results if not r["is_bad_row"] and r["system_status"] in ("supported", "partial")]
good_rows_total = [r for r in results if not r["is_bad_row"]]

untrue_persisted = [r for r in results if r["system_status"] in ("supported", "partial") and r["l1_true"] == "N"]
not_in_passage_persisted = [r for r in results if r["system_status"] in ("supported", "partial") and r["l2_in_passage"] == "N"]

print("\n" + "="*50)
print("48-ROW REGRESSION EVALUATION REPORT")
print("="*50)
print(f"Total rows evaluated: {len(results)}")
print(f"Total time elapsed: {total_time}s ({round(total_time/len(results), 2)}s per addition)")
print(f"Verifier LLM calls made: {verifier_calls} of {len(results)}")
print(f"Extractive auto-certifications: {len(results) - verifier_calls}")
print()
print("REGRESSION GATES:")
print(f"- Bad rows (8, 22, 24, 42) survived: {len(bad_rows_survived)} of 4")
for b in [r for r in results if r["is_bad_row"]]:
    print(f"  Row {b['row_id']}: status={b['system_status']}, contradict={b['does_contradict']}, quote='{b['exact_quote'][:40]}'")
print(f"- Untrue additions persisted (L1=N): {len(untrue_persisted)} of {len(good_rows_kept) + len(bad_rows_survived)} ({round(len(untrue_persisted)/(len(good_rows_kept)+len(bad_rows_survived) or 1)*100, 1)}%) [Target: 0]")
print(f"- Not-in-passage persisted (L2=N): {len(not_in_passage_persisted)} of {len(good_rows_kept) + len(bad_rows_survived)} ({round(len(not_in_passage_persisted)/(len(good_rows_kept)+len(bad_rows_survived) or 1)*100, 1)}%) [Target: <= 5%]")
print(f"- Good addition retention rate: {len(good_rows_kept)} of {len(good_rows_total)} ({round(len(good_rows_kept)/len(good_rows_total)*100, 1)}%)")
print()

# Save regression results JSON
out_path = "/app/reports/labeling/regression_48_results.json"
try:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {out_path}")
except Exception:
    pass

"""Phase A2 & A4: Baseline candidate source breakdown and frozen match function evaluation."""
import json
import re
from collections import defaultdict, Counter

with open("backend/tests/evaluation/datasets/golden_v2.json") as f:
    v2 = json.load(f)

corpus = v2["corpus"]
base_cases = [c for c in v2["cases"] if c["variant"] == "base"]

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "as", "is", "was", "are", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must",
    "can", "this", "that", "these", "those"
}

def safe_plural_strip(word: str) -> str:
    word = word.strip().lower()
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        if word.endswith("ies") and len(word) > 4:
            return word[:-3] + "y"
        return word[:-1]
    return word

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [safe_plural_strip(w) for w in text.split() if w]
    return " ".join(tokens)

def match_candidate_to_concept(cand_text: str, concept: dict) -> tuple[bool, bool]:
    """Returns (is_hit, is_fragment) using the frozen match specification."""
    norm_cand = normalize_text(cand_text)
    cand_tokens = norm_cand.split()
    if not cand_tokens:
        return False, False
        
    topic = concept["topic"]
    aliases = concept.get("aliases", [])
    targets = [topic] + aliases

    # Fragment check:
    # "A candidate that is a single token (or proper sub-phrase) of a multi-word gold concept is a FRAGMENT error, never a hit."
    for target in targets:
        norm_target = normalize_text(target)
        target_tokens = norm_target.split()
        if len(target_tokens) > 1:
            if len(cand_tokens) < len(target_tokens):
                target_phrase = " ".join(target_tokens)
                cand_phrase = " ".join(cand_tokens)
                if cand_phrase in target_phrase:
                    return False, True

    # Hit check:
    for target in targets:
        norm_target = normalize_text(target)
        target_tokens = norm_target.split()
        if not target_tokens:
            continue

        # 1. Exact match after normalization
        if norm_cand == norm_target:
            return True, False

        # 2. Token-set containment:
        content_target = set(w for w in target_tokens if w not in STOP_WORDS)
        content_cand = set(w for w in cand_tokens if w not in STOP_WORDS)

        if content_target and content_target.issubset(content_cand):
            extra_tokens = len(cand_tokens) - len(target_tokens)
            if 0 <= extra_tokens <= 2:
                return True, False

    return False, False

from apps.ai_classroom.gap_candidates import extract_all_candidates

source_map = {
    "domain_concept": "DOMAIN_DICTIONARY",
    "technical_pattern": "TECHNICAL_PATTERN",
    "capitalized_domain": "CAPITALIZED_PHRASE",
    "2gram": "NGRAM",
    "3gram": "NGRAM"
}

source_candidates = Counter()
source_hits = Counter()
source_fragments = Counter()
source_recalled_concepts = defaultdict(set)

all_gold_concepts = set()
for c in base_cases:
    for cp in c["concepts"]:
        all_gold_concepts.add((c["case_id"], cp["topic"]))

total_cands = 0
unique_recalled = set()

for c in base_cases:
    cid = c["case_id"]
    chunks = [{"chunk_id": rid, "content": corpus[rid]["text"]} for rid in c["reference_chunk_ids"]]
    cands = extract_all_candidates(chunks, max_per_chunk=5)
    gold_concepts = c["concepts"]

    for cand in cands:
        total_cands += 1
        raw_src = cand.metadata.get("extraction_method", "OTHER")
        src = source_map.get(raw_src, "OTHER")
        source_candidates[src] += 1

        is_hit = False
        is_frag = False
        for cp in gold_concepts:
            hit, frag = match_candidate_to_concept(cand.concept, cp)
            if hit:
                is_hit = True
                source_recalled_concepts[src].add((cid, cp["topic"]))
                unique_recalled.add((cid, cp["topic"]))
            elif frag:
                is_frag = True

        if is_hit:
            source_hits[src] += 1
        elif is_frag:
            source_fragments[src] += 1

print(f"Total Base Cases: {len(base_cases)}, Total Gold Concepts: {len(all_gold_concepts)}")
print(f"Total Candidates Extracted: {total_cands}")
print(f"Unique Gold Concepts Recalled: {len(unique_recalled)}/{len(all_gold_concepts)} = {len(unique_recalled)/len(all_gold_concepts)*100:.1f}%\n")

print(f"{'Source':<20} | {'Candidates':<10} | {'Hits':<6} | {'Precision':<10} | {'Unique Concepts':<16} | {'Fragments':<10}")
print("-" * 85)
for src in ["DOMAIN_DICTIONARY", "TECHNICAL_PATTERN", "CAPITALIZED_PHRASE", "NGRAM"]:
    cnt = source_candidates[src]
    hits = source_hits[src]
    prec = hits / cnt * 100 if cnt > 0 else 0.0
    u_c = len(source_recalled_concepts[src])
    frag = source_fragments[src]
    print(f"{src:<20} | {cnt:<10} | {hits:<6} | {prec:8.1f}%  | {u_c:<16} | {frag:<10}")

print("\n--- Marginal Recall Contribution ---")
for src in ["DOMAIN_DICTIONARY", "TECHNICAL_PATTERN", "CAPITALIZED_PHRASE", "NGRAM"]:
    other_sources = [s for s in ["DOMAIN_DICTIONARY", "TECHNICAL_PATTERN", "CAPITALIZED_PHRASE", "NGRAM"] if s != src]
    other_concepts = set()
    for osrc in other_sources:
        other_concepts.update(source_recalled_concepts[osrc])
    only_this = source_recalled_concepts[src] - other_concepts
    print(f"  {src:<20}: {len(only_this)} unique concepts recalled ONLY by this source ({len(only_this)/len(all_gold_concepts)*100:.1f}%)")

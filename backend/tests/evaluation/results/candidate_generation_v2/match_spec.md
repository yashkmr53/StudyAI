# Frozen Match Specification (Phase A4)

**File:** `tests/evaluation/results/candidate_generation_v2/match_spec.md`  
**Status:** FROZEN (Pre-registered before any extractor tuning)  
**Date:** 2026-09-20  

This document defines the single, immutable matching function `match(candidate, gold_concept)` used to evaluate all Stage 1 candidate extractors on `golden_v2`.

---

## 1. Normalization Pipeline

Both candidate string $C$ and gold target strings $T$ (the gold `topic` and all strings in `aliases`) are normalized as follows:

1. **Casefolding:** Convert to lowercase (`.lower()`).
2. **Punctuation Stripping:** Replace all non-alphanumeric characters (`[^a-z0-9]`) with a single space.
3. **Safe Plural Stripping:**
   - Word length $> 3$ characters.
   - If word ends in `ies` (length $> 4$), replace with `y` (e.g., `properties` $\to$ `property`).
   - If word ends in `s` and does NOT end in `ss`, `us`, or `is`, strip the trailing `s` (e.g., `rotations` $\to$ `rotation`, `heuristics` $\to$ `heuristic`, but `process` stays `process`, `status` stays `status`).
4. **Whitespace Collapsing:** Collapse consecutive whitespace characters into a single space and strip leading/trailing whitespace.

---

## 2. Evaluation Decision Rules

Let $C_{\text{norm}}$ be the normalized candidate string and $C_{\text{tokens}}$ be its token list.  
Let $T = \{G.\text{topic}\} \cup G.\text{aliases}$. For each target $t \in T$, let $t_{\text{norm}}$ be the normalized target string and $t_{\text{tokens}}$ be its token list.

### A. Fragment Rule (Evaluated First)
A candidate that is a single token or a proper sub-phrase of a multi-word gold concept is a **FRAGMENT error**, never a hit:
$$\text{If } |t_{\text{tokens}}| > 1 \text{ and } |C_{\text{tokens}}| < |t_{\text{tokens}}| \text{ and } C_{\text{norm}} \text{ is a substring of } t_{\text{norm}} \implies \text{FRAGMENT (No Hit)}$$
*Examples of fragments:*
- Candidate `"complexity"` against gold target `"time complexity"` $\to$ **FRAGMENT**.
- Candidate `"possibilities frontier"` against gold target `"production possibilities frontier"` $\to$ **FRAGMENT**.
- Candidate `"rotations"` against gold target `"AVL rotations"` $\to$ **FRAGMENT**.

### B. Hit Rules
If not disqualified as a fragment, candidate $C$ is a **HIT** for gold concept $G$ if it satisfies either of the following conditions for any target $t \in T$:

1. **Exact Normalized Match:**
   $$C_{\text{norm}} == t_{\text{norm}}$$
   *Example:* `"time complexity"` matches `"time complexity"`. `"AVL Rotation"` matches `"AVL rotations"`.

2. **Token-Set Containment with Bounded Slack:**
   Let $\text{ContentTokens}(x) = \{w \in x_{\text{tokens}} \mid w \notin \text{STOP\_WORDS}\}$.
   $$\text{ContentTokens}(t) \subseteq \text{ContentTokens}(C) \quad \text{AND} \quad 0 \le |C_{\text{tokens}}| - |t_{\text{tokens}}| \le 2$$
   The candidate contains all content tokens of the gold target and adds at most 2 extra tokens.
   *Example:* `"binary search takes"` against target `"binary search"` (adds 1 token $\le 2$) $\to$ **HIT**.
   *Non-example:* `"binary search algorithm takes about"` against target `"binary search"` (adds 3 tokens $> 2$) $\to$ **NO HIT**.

---

## 3. Ground Truth Extractive Recall Ceiling on `golden_v2` (40 Base Cases, 242 Concepts)

A concept is extractable by an extractive Stage 1 model only if its surface string (or an alias) appears verbatim in its authorized reference chunk text.

| Status | Total Gold Concepts | Strict Ceiling (Topic in Chunk) | Lenient Ceiling (Topic or Alias in Chunk) |
|:---|:---:|:---:|:---:|
| **`gap`** | 114 | 33 (28.9%) | **96 (84.2%)** |
| **`partial`** | 9 | 3 (33.3%) | **8 (88.9%)** |
| **`covered`** | 68 | 18 (26.5%) | **35 (51.5%)** |
| **`off_scope`** | 51 | 41 (80.4%) | **48 (94.1%)** |
| **Overall** | **242** | **95 (39.3%)** | **187 (77.3%)** |

*Note on Covered Concepts:* Only 51.5% of covered concepts appear verbatim in reference chunk text because student notes and reference books frequently describe concepts with descriptive prose rather than introducing the formal topic name.
*Note on Extractive Ceiling:* All candidate generator recall figures must be reported both as absolute recall ($\text{Recall}$) and as a fraction of the theoretical ceiling ($\text{Recall} / \text{Ceiling}_{\text{lenient}}$).

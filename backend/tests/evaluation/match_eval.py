"""Frozen match specification implementation as defined in match_spec.md."""
import re
from typing import Tuple, Dict, Any, List

STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from',
    'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his',
    'her', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs', 'what', 'which', 'who',
    'whom', 'whose', 'where', 'when', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
    'very', 'just', 'now', 'then', 'also', 'even', 'still', 'back', 'well', 'here', 'there', 'again',
    'further', 'once', 'never', 'always', 'sometimes', 'often', 'usually', 'rarely', 'seldom', 'ever',
    'any', 'anyone', 'anything', 'anywhere', 'everyone', 'everything', 'everywhere', 'someone',
    'something', 'somewhere', 'nobody', 'nothing', 'nowhere'
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

def match_candidate_to_concept(cand_text: str, concept: Dict[str, Any]) -> Tuple[bool, bool]:
    """Returns (is_hit, is_fragment) using the frozen match specification."""
    norm_cand = normalize_text(cand_text)
    cand_tokens = norm_cand.split()
    if not cand_tokens:
        return False, False
        
    topic = concept["topic"]
    aliases = concept.get("aliases", [])
    targets = [topic] + aliases

    # Fragment check (evaluated first):
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

        # 2. Token-set containment with bounded slack:
        content_target = set(w for w in target_tokens if w not in STOP_WORDS)
        content_cand = set(w for w in cand_tokens if w not in STOP_WORDS)

        if content_target and content_target.issubset(content_cand):
            extra_tokens = len(cand_tokens) - len(target_tokens)
            if 0 <= extra_tokens <= 2:
                return True, False

    return False, False

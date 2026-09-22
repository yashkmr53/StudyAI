"""Mock LLM provider (development/tests only — §30 leaves models open).

Produces deterministic, schema-valid structured outputs per prompt stage
from the evidence JSON embedded in the prompt user-text. The pipeline
machinery around it (retrieval, schemas, citations, verification,
persistence) is real code.

For the *chat* stage the mock simulates a grounded LLM: it reads the
user's question from the prompt, distinguishes conversational greetings
from material-seeking questions, and generates a grounded answer by
extracting and reformulating the key sentence from the top evidence chunk.
It never returns raw retrieved content verbatim.
"""
import hashlib
import json
import re
import datetime as _dt
from typing import Any, Union

from providers.base import LLMResult, Prompt, StructuredLLMResult


def _evidence_from(prompt: Prompt) -> dict:
    """The pipeline embeds evidence JSON at the end of the user text after
    a sentinel line; the mock parses it deterministically."""
    marker = "EVIDENCE_JSON:"
    if prompt.user and marker in prompt.user:
        text = prompt.user.split(marker, 1)[1].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(text)
                return obj
            except Exception:
                pass
    return {}


def _question_from(prompt: Prompt) -> str:
    """Extract the user's QUESTION from the prompt user text.

    The chat nodes place ``QUESTION: <text>`` before ``EVIDENCE_JSON:``;
    if the question is absent (older call sites) an empty string is
    returned so the mock degrades gracefully.
    """
    marker = "QUESTION:"
    user = prompt.user or ""
    if marker not in user:
        return ""
    before_evidence = user.split("EVIDENCE_JSON:", 1)[0]
    if marker not in before_evidence:
        return ""
    question = before_evidence.split(marker, 1)[1].strip()
    return question.split("\n\n")[0].strip()


def _is_conversational(question: str) -> bool:
    """Heuristic: classify whether a query needs retrieval / evidence
    at all.  Covers greetings, date/time, thanks, personal questions, etc."""
    q = (question or "").lower().strip().rstrip("!?.,;:")
    if not q:
        return True
    _CONV_PATTERNS = [
        r"^h[iy]$", r"^hello$", r"^hey$", r"^hi there$",
        r"^how (are|r) (you|u|doing)$",
        r"^good (morning|afternoon|evening)$",
        r"^what('s| is) up$", r"^sup$", r"^yo$", r"^greetings$",
        r"^thanks+$", r"^thank (you|u)$", r"^bye$", r"^goodbye$",
        r"^what('s| is) today'?s date$", r"^what date is it$",
        r"^what('s| is) the date$", r"^today'?s date$",
        r"^what time is it$", r"^what('s| is) the time$",
        r"^can you hear me$", r"^test$",
        r"^my name is\b",
        r"^i am\b", r"^i'm\b",
        r"^what is my name\b", r"^what's my name\b",
        r"^do you know my name\b", r"^do you remember my name\b",
        r"^what did i (just )?tell you\b",
        r"^what did i (just )?say\b",
        r"^do you remember\b",
        r"^what is my favorite\b", r"^what's my favorite\b",
        r"^who am i\b", r"^tell me about me\b",
    ]
    return any(re.match(p, q) for p in _CONV_PATTERNS)


def _resolve_conversational_response(question: str) -> str:
    """Return a deterministic conversational response for non-material queries."""
    q = (question or "").lower().strip().rstrip("!?.,;:")
    today = _dt.date.today().isoformat()

    if re.match(r"^h[iy]$", q) or re.match(r"^hello$", q) or re.match(r"^hey$", q) or q == "hi there":
        return "Hello! How can I help you with your study materials today?"
    if re.match(r"^how (are|r) (you|u|doing)$", q) or q in ("good morning", "good afternoon", "good evening"):
        return "I'm doing well, thank you for asking! How can I assist with your studies today?"
    if re.match(r"^what('s| is) up$", q) or q == "sup" or q == "yo" or q == "greetings":
        return "Just here and ready to help with your study questions! What would you like to work on?"
    if re.match(r"^thanks", q) or re.match(r"^thank (you|u)$", q):
        return "You're welcome! Happy studying!"
    if re.match(r"^bye$", q) or re.match(r"^goodbye$", q):
        return "Goodbye! Feel free to come back anytime you need help with your studies."
    if re.match(r"^my name is\b", q):
        return f"Nice to meet you! I'll remember your name is {q.split('is', 1)[1].strip().split()[0] if 'is' in q else '...'}."
    if re.match(r"^what is my name\b", q) or re.match(r"^what's my name\b", q):
        return "I don't have access to your name from previous conversations in this mock environment, but a real LLM would answer based on conversation history."
    if re.match(r"^do you know my name\b", q) or re.match(r"^do you remember my name\b", q):
        return "I don't retain memory between sessions, but within a conversation I can reference earlier messages."
    if re.match(r"^what('s| is) today'?s date$", q) or re.match(r"^what date is it$", q) or q == "today's date" or re.match(r"^what('s| is) the date$", q):
        return f"Today's date is {today}."
    if re.match(r"^what time is it$", q) or re.match(r"^what('s| is) the time$", q):
        now = _dt.datetime.now().strftime("%I:%M %p")
        return f"It's currently {now}."
    return "Hello! How can I help you with your study materials today?"


def _extract_key_sentence(content: str) -> str:
    """Pull the first meaningful sentence/line from a chunk, stripping
    bracketed prefixes such as '[Mathematics] ' that are metadata
    rather than prose."""
    if not content:
        return ""
    text = re.sub(r"^\[[^\]]+\]\s*", "", content.strip())

    # Try sentence-based extraction: only accept single-line sentences
    # so that multi-line blobs without punctuation (e.g. OCR "Recognized
    # line 1: …" output) fall through to the line-based extractor below.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for s in sentences:
        s = s.strip()
        if len(s) > 10 and "\n" not in s:
            if not s.endswith((".", "!", "?")):
                s += "."
            return s

    # Fallback: first non-trivial line
    for line in text.split("\n"):
        line = line.strip()
        if len(line) > 10:
            if not line.endswith((".", "!", "?")):
                line += "."
            return line
    return text[:200]


class MockLLMProvider:
    model_name = 'mock-gpt'
    name = "mock"

    def generate(self, *, prompt: Union[Prompt, str], request_id: str = "", **kwargs) -> LLMResult:
        p_name = prompt.name if isinstance(prompt, Prompt) else "direct"
        p_ver = prompt.version if isinstance(prompt, Prompt) else "v1"
        user_text = prompt.user if isinstance(prompt, Prompt) else str(prompt)
        return LLMResult(
            text=f"Mock response for: {user_text[:60]}",
            model=self.model_name,
            provider=self.name,
            prompt_name=p_name,
            prompt_version=p_ver,
            input_tokens=10,
            output_tokens=10,
            total_tokens=20,
        )

    def generate_with_image(self, *, prompt: Union[Prompt, str], image: Any, request_id: str = "", **kwargs) -> LLMResult:
        p_name = prompt.name if isinstance(prompt, Prompt) else "vision"
        p_ver = prompt.version if isinstance(prompt, Prompt) else "v1"
        return LLMResult(
            text="Calculus Differentiation Rules:\nPower rule states that (x^n)' = n * x^(n-1).",
            model=self.model_name,
            provider=self.name,
            prompt_name=p_name,
            prompt_version=p_ver,
            input_tokens=15,
            output_tokens=15,
            total_tokens=30,
        )

    def generate_structured_with_image(self, *, prompt: Union[Prompt, str], image: Any, schema: Union[type, dict] = None, request_id: str = "", **kwargs) -> StructuredLLMResult:
        if isinstance(prompt, str):
            prompt = Prompt(name="vision_structured", version="v1", user=prompt)
        return self.generate_structured(prompt=prompt, schema=schema, request_id=request_id)

    def generate_structured(self, *, prompt: Prompt, schema: Union[type, dict] = None, request_id: str, disable_fallback: bool = False) -> StructuredLLMResult:
        evidence = _evidence_from(prompt)

        if prompt.name == "enrichment_draft":
            data = self._draft(evidence)
        elif prompt.name == "gap_detection":
            data = self._gaps(evidence)
        elif prompt.name == "gap_filling":
            data = self._fill(evidence)
        elif prompt.name == "question_generation":
            data = self._question(evidence)
        elif prompt.name == "chat":
            data = self._chat(evidence, _question_from(prompt))
        elif prompt.name == "gap_candidate_validation":
            data = self._validate_candidate(prompt)
        else:
            # Default handler for unknown prompts (tests, etc.)
            data = {"result": f"Mock response for {prompt.name}", "status": "ok"}

        return StructuredLLMResult(
            data=data,
            model=getattr(self, "model_name", "mock-gpt"),
            provider=self.name,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
        )

    @staticmethod
    def _draft(evidence: dict) -> dict:
        blocks = [{
            "block_type": "overview",
            "title": "Overview",
            "content": f"Structured overview generated from {len(evidence.get('user_chunks', []))} note section(s).",
            "generation_method": "llm",
            "source_chunk_ids": [c["chunk_id"] for c in evidence.get("user_chunks", [])],
        }]
        for i, chunk in enumerate(evidence.get("user_chunks", []), start=1):
            first_line = chunk["content"].split("\n")[0][:180]
            blocks.append({
                "block_type": "key_concept",
                "title": f"Key concept {i}",
                "content": first_line,
                "generation_method": "llm",
                "source_chunk_ids": [chunk["chunk_id"]],
            })
        return {"blocks": blocks}

    @staticmethod
    def _gaps(evidence: dict) -> dict:
        """Topics present in reference chunks but absent from user notes."""
        def tokens(text: str) -> set[str]:
            return {w for w in "".join(c if c.isalnum() else " " for c in text.lower()).split() if len(w) > 4}

        user_tokens: set[str] = set()
        for chunk in evidence.get("user_chunks", []):
            user_tokens |= tokens(chunk["content"])

        gaps = []
        seen = set()
        for chunk in evidence.get("reference_chunks", []):
            for topic in sorted(tokens(chunk["content"]) - user_tokens):
                if topic in seen:
                    continue
                seen.add(topic)
                gaps.append({
                    "topic": topic,
                    "why_missing": f"This concept appears in the reference material but is not covered in the user's note.",
                    "missing_from_note": f"The note does not mention {topic}.",
                    "evidence_in_reference": chunk["content"][:200],
                    "source_chunk_ids": [chunk["chunk_id"]],
                })
                break  # one gap per reference chunk keeps output bounded
        return {"gaps": gaps}

    @staticmethod
    def _fill(evidence: dict) -> dict:
        ref_by_id = {c["chunk_id"]: c for c in evidence.get("reference_chunks", [])}
        blocks = []
        for gap in evidence.get("gaps", []):
            chunk_id = gap["source_chunk_ids"][0] if gap.get("source_chunk_ids") else None
            chunk = ref_by_id.get(chunk_id) if chunk_id else None
            if not chunk:
                continue
            blocks.append({
                "block_type": "gap_fill",
                "title": f"Gap fill: {gap['topic']}",
                "content": f"On '{gap['topic']}', your reference material states: {chunk['content'][:200]}",
                "generation_method": "llm",
                "source_chunk_ids": [chunk["chunk_id"]],
            })
        return {"blocks": blocks}

    @staticmethod
    def _question(evidence: dict) -> dict:
        """Deterministic question from a chunk supporting MCQ, flashcards, short-answer, and explanation."""
        chunk = evidence.get("chunk", {})
        others = evidence.get("distractor_contents", [])
        q_type = evidence.get("question_type", "mcq")
        difficulty = evidence.get("difficulty", "medium")
        key_sentence = (chunk.get("content") or "").split(".")[0].strip() or "the highlighted concept"
        topic = chunk.get("topic") or "this topic"

        if q_type == "flashcard":
            return {
                "prompt": f"Define and explain key concepts behind {topic}:",
                "options": [],
                "answer_index": 0,
                "difficulty": difficulty,
                "question_type": "flashcard",
                "explanation": f"Key concept: {key_sentence}. Grounded in notes.",
            }
        elif q_type == "short_answer":
            return {
                "prompt": f"Briefly explain the role of {topic} in your study notes.",
                "options": [key_sentence],
                "answer_index": 0,
                "difficulty": difficulty,
                "question_type": "short_answer",
                "explanation": f"Model Answer: {key_sentence}. Essential points covered in note chunk.",
            }
        elif q_type == "explanation":
            return {
                "prompt": f"Explain in detail how {topic} functions according to your notes and reference materials.",
                "options": [],
                "answer_index": 0,
                "difficulty": difficulty,
                "question_type": "explanation",
                "explanation": f"Comprehensive rubric: Must identify that {key_sentence}, with supporting rationale.",
            }

        # Default MCQ
        options = [key_sentence]
        for o in others[:3]:
            sentence = (o or "").split(".")[0].strip()
            if sentence and sentence not in options:
                options.append(sentence)
        while len(options) < 4:
            options.append(f"None of the above ({len(options)})")
        import random

        seed = int(hashlib.md5((chunk.get("chunk_id", "") + key_sentence).encode()).hexdigest(), 16)
        order = list(range(len(options)))
        random.Random(seed).shuffle(order)
        shuffled = [options[i] for i in order]
        answer_index = shuffled.index(key_sentence)
        return {
            "prompt": f"Which statement is supported by your notes on '{topic}'?",
            "options": shuffled,
            "answer_index": answer_index,
            "difficulty": difficulty,
            "question_type": "mcq",
            "explanation": f"The correct answer is '{key_sentence}', directly supported by the study notes.",
        }

    @staticmethod
    def _chat(evidence: dict, question: str = "") -> dict:
        """Simulate a grounded chat LLM response.

        Distinguishes conversational queries (no retrieval needed) from
        material-seeking questions.  For material questions with evidence,
        extracts the key sentence from the top chunk and reformulates a
        grounded answer (never echoing a raw chunk verbatim).
        """
        chunks = evidence.get("evidence", [])

        if _is_conversational(question):
            return {
                "answer": _resolve_conversational_response(question),
                "cited_ids": [],
                "cited_chunk_ids": [],
                "confidence": 0.9,
            }

        if not chunks:
            return {
                "answer": "I could not find anything about that in your notes or the reference library.",
                "cited_ids": [],
                "cited_chunk_ids": [],
                "confidence": 0.1,
            }

        top = chunks[0]
        content = top.get("content", "")
        key_point = _extract_key_sentence(content)

        if not key_point:
            key_point = content.strip().split("\n")[0][:200]

        answer = f"Based on your materials, {key_point}"

        # Return citation_ids in both new (cited_ids) and legacy (cited_chunk_ids) formats
        citation_ids = [c.get("citation_id", c.get("chunk_id", "")) for c in chunks]
        return {
            "answer": answer,
            "cited_ids": citation_ids,
            "cited_chunk_ids": citation_ids,
            "confidence": 0.75,
        }

    @staticmethod
    def _validate_candidate(prompt: Prompt) -> dict:
        return {
            "classification": "MISSING",
            "reason": "Mock validation indicates concept is missing from note.",
            "missing_from_note": "Concept is not covered in student note.",
            "evidence_in_reference": "Concept found in reference material."
        }

    # keep backward-compat alias
    @staticmethod
    def _extract_key_sentence(content: str) -> str:
        return MockLLMProvider._extract_key_sentence(content)

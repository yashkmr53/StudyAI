"""Mock LLM provider (development/tests only — §30 leaves models open).

Produces deterministic, schema-valid structured outputs per prompt stage
from the evidence JSON embedded in the prompt user-text. The pipeline
machinery around it (retrieval, schemas, citations, verification,
persistence) is real code.
"""
import hashlib
import json

from providers.base import Prompt, StructuredLLMResult


def _evidence_from(prompt: Prompt) -> dict:
    """The pipeline embeds evidence JSON at the end of the user text after
    a sentinel line; the mock parses it deterministically."""
    marker = "EVIDENCE_JSON:"
    if prompt.user and marker in prompt.user:
        return json.loads(prompt.user.split(marker, 1)[1])
    return {}


class MockLLMProvider:
    model_name = 'mock-gpt'
    name = "mock"

    def generate_structured(self, *, prompt: Prompt, schema: type = None, request_id: str) -> StructuredLLMResult:
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
            data = self._chat(evidence)
        else:
            # Default handler for unknown prompts (tests, etc.)
            data = {"result": f"Mock response for {prompt.name}", "status": "ok"}

        return StructuredLLMResult(
            data=data,
            model=getattr(self, "model_name", "mock-gpt"),
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
                gaps.append({"topic": topic, "reference_chunk_id": chunk["chunk_id"]})
                break  # one gap per reference chunk keeps output bounded
        return {"gaps": gaps}

    @staticmethod
    def _fill(evidence: dict) -> dict:
        ref_by_id = {c["chunk_id"]: c for c in evidence.get("reference_chunks", [])}
        blocks = []
        for gap in evidence.get("gaps", []):
            chunk = ref_by_id.get(gap["reference_chunk_id"])
            if not chunk:
                continue
            blocks.append({
                "block_type": "gap_fill",
                "title": f"Further reading: {gap['topic']}",
                "content": f"On '{gap['topic']}', your reference material states: {chunk['content'][:200]}",
                "generation_method": "llm",
                "source_chunk_ids": [chunk["chunk_id"]],
            })
        return {"blocks": blocks}

    @staticmethod
    def _question(evidence: dict) -> dict:
        """Deterministic MCQ from a chunk: correct option = key sentence,
        distractors = sentences from other chunks."""
        chunk = evidence.get("chunk", {})
        others = evidence.get("distractor_contents", [])
        key_sentence = (chunk.get("content") or "").split(".")[0].strip() or "the highlighted concept"
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
            "prompt": f"Which statement is supported by your notes on '{(chunk.get('topic') or 'this topic')}'?",
            "options": shuffled,
            "answer_index": answer_index,
            "difficulty": "medium",
        }

    @staticmethod
    def _chat(evidence: dict) -> dict:
        chunks = evidence.get("evidence", [])
        if not chunks:
            return {
                "answer": "I could not find anything about that in your notes or the reference library.",
                "cited_chunk_ids": [],
            }
        top = chunks[0]
        answer = f"Based on your materials: {top['content'][:280]}"
        return {
            "answer": answer,
            "cited_chunk_ids": [c["chunk_id"] for c in chunks],
        }

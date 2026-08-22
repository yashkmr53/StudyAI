"""Deterministic idempotency keys (architecture §20)."""


def ocr_key(page_id, content_hash: str, pipeline_version: str) -> str:
    return f"ocr:{page_id}:{content_hash}:{pipeline_version}"


def embedding_key(chunk_id, content_hash: str, embedding_model_version: str) -> str:
    return f"embedding:{chunk_id}:{content_hash}:{embedding_model_version}"


def enrichment_key(revision_id, prompt_version: str, model: str) -> str:
    return f"enrichment:{revision_id}:{prompt_version}:{model}"


def question_generation_key(revision_id, prompt_version: str) -> str:
    return f"question_generation:{revision_id}:{prompt_version}"

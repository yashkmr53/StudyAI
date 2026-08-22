"""Always-failing LLM provider — exercises fallback chains in tests."""
from providers.base import Prompt, StructuredLLMResult


class FailingLLMProvider:
    name = "failing"
    model_name = "failing-model"

    def generate_structured(self, *, prompt: Prompt, schema=None, request_id: str) -> StructuredLLMResult:
        raise RuntimeError(f"{self.name}: simulated provider failure")

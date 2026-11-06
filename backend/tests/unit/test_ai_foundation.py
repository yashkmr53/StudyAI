"""Phase 12 AI foundation tests (langchain adapters, prompt registry, tracing)."""
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from ai.langchain.models import get_chat_model, get_embedding_model, get_provider_chain
from ai.langchain.prompts import PromptRegistry, PromptTemplate, active_prompt, validate_stage_output
from ai.schemas.chat import ChatAnswer
from ai.tracing.config import is_tracing_enabled, get_client


class TestLangChainModels(TestCase):
    def test_get_chat_model_ollama_langchain(self):
        with patch("ai.langchain.models.LangChainChatModelAdapter._init_model"):
            model = get_chat_model("ollama-langchain", base_url="http://test", model="test-model")
            self.assertIsNotNone(model)

    def test_get_chat_model_ollama_fallback(self):
        with patch("ai.langchain.models.LangChainChatModelAdapter._init_model"):
            model = get_chat_model("ollama", base_url="http://test", model="test-model")
            self.assertIsNotNone(model)

    def test_get_chat_model_mock(self):
        model = get_chat_model("mock")
        self.assertIsNotNone(model)

    def test_get_embedding_model_ollama(self):
        get_embedding_model.cache_clear()
        with patch("providers.embeddings.ollama.OllamaEmbeddingProvider.__init__", return_value=None):
            model = get_embedding_model("ollama")
            self.assertIsNotNone(model)

    def test_get_embedding_model_hashing_fallback(self):
        get_embedding_model.cache_clear()
        model = get_embedding_model("hashing")
        self.assertIsNotNone(model)

    def test_get_embedding_model_legacy_raises(self):
        get_embedding_model.cache_clear()
        with self.assertRaises(ValueError):
            get_embedding_model("sentence_transformers_langchain")
        with self.assertRaises(ValueError):
            get_embedding_model("sentence_transformers")

    def test_get_provider_chain_llm(self):
        with patch("ai.langchain.models.LangChainChatModelAdapter._init_model"):
            chain = get_provider_chain("ollama-langchain,mock", provider_type="llm")
            self.assertEqual(len(chain), 2)

    def test_get_provider_chain_embedding(self):
        get_embedding_model.cache_clear()
        with patch("providers.embeddings.ollama.OllamaEmbeddingProvider.__init__", return_value=None):
            chain = get_provider_chain("ollama,hashing", provider_type="embedding")
            self.assertEqual(len(chain), 2)

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            get_chat_model("unknown-provider")


class TestPromptRegistry(TestCase):
    def test_registry_loads_builtin_prompts(self):
        registry = PromptRegistry()
        chat_prompt = registry.get("chat_answer", "v1")
        self.assertIsNotNone(chat_prompt)
        self.assertEqual(chat_prompt.name, "chat_answer")

    def test_get_latest(self):
        registry = PromptRegistry()
        prompt = registry.get("chat_answer", "latest")
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt.version, "v1")

    def test_get_active_raises_when_missing(self):
        registry = PromptRegistry()
        with self.assertRaises(KeyError):
            registry.get_active("nonexistent_prompt")

    def test_to_provider_prompt(self):
        registry = PromptRegistry()
        prompt = registry.to_provider_prompt("chat_answer")
        self.assertEqual(prompt.name, "chat_answer")
        self.assertEqual(prompt.version, "v1")


class TestTracingConfig(TestCase):
    def test_tracing_disabled_by_default(self):
        from ai.tracing import config
        import os
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "false", "LANGSMITH_API_KEY": ""}, clear=False):
            config._tracing_enabled = False
            config._client = None
            self.assertFalse(is_tracing_enabled())

    @override_settings(LANGSMITH_TRACING="true", LANGSMITH_API_KEY="test-key")
    def test_tracing_enabled_via_env(self):
        from ai.tracing import config
        import os
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "test-key"}):
            config._tracing_enabled = False
            config._client = None
            self.assertTrue(is_tracing_enabled())
            config._tracing_enabled = False

    def test_client_returns_none_when_disabled(self):
        from ai.tracing import config
        import os
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "false", "LANGSMITH_API_KEY": ""}, clear=False):
            config._tracing_enabled = False
            config._client = None
            self.assertIsNone(get_client())

    @override_settings(LANGSMITH_REDACT_STUDENT_TEXT=True)
    def test_redact_payload_replaces_student_text_when_enabled(self):
        from ai.tracing.config import _redact_payload

        payload = {
            "topic_id": "topic-123",
            "score": 0.95,
            "text": "Private handwritten student notes about quantum physics",
            "transcript": "student oral transcript",
            "nested": {
                "content": "more sensitive student writing",
                "safe_id": "uuid-abc",
            },
            "list_items": [
                {"prompt": "system prompt with student note: text"},
                {"public_tag": "physics"},
            ],
        }

        redacted = _redact_payload(payload)

        self.assertEqual(redacted["topic_id"], "topic-123")
        self.assertEqual(redacted["score"], 0.95)
        self.assertEqual(redacted["nested"]["safe_id"], "uuid-abc")
        self.assertEqual(redacted["list_items"][1]["public_tag"], "physics")

        self.assertTrue(redacted["text"].startswith("[REDACTED_STUDENT_TEXT: length="))
        self.assertTrue(redacted["transcript"].startswith("[REDACTED_STUDENT_TEXT: length="))
        self.assertTrue(redacted["nested"]["content"].startswith("[REDACTED_STUDENT_TEXT: length="))
        self.assertTrue(redacted["list_items"][0]["prompt"].startswith("[REDACTED_STUDENT_TEXT: length="))

        self.assertNotIn("Private handwritten", str(redacted))
        self.assertNotIn("sensitive student writing", str(redacted))

    @override_settings(LANGSMITH_REDACT_STUDENT_TEXT=False)
    def test_redact_payload_preserves_text_when_redaction_disabled(self):
        from ai.tracing.config import _redact_payload

        payload = {"text": "Original text preserved"}
        result = _redact_payload(payload)
        self.assertEqual(result["text"], "Original text preserved")

    @override_settings(LANGSMITH_REDACT_STUDENT_TEXT=True)
    def test_redact_payload_covers_model_outputs_and_nested_messages(self):
        """Redaction covers model outputs that paraphrase notes, and nested message list structures."""
        from ai.tracing.config import _redact_payload

        payload = {
            "prompt": "Here are student notes: Objects in free fall gain potential energy",
            "messages": [
                {"role": "system", "content": "You are a physics tutor."},
                {"role": "user", "content": "My handwritten notes say: Objects in free fall gain potential energy."},
                {"role": "assistant", "content": "In your notes, you wrote that potential energy increases during descent, but actually gravity does positive work."},
            ],
            "outputs": {
                "generations": [
                    {"text": "Paraphrase of student notes: gravity causes an increase in kinetic energy, not potential energy."},
                    {"message": {"role": "assistant", "content": "Textbook passage excerpt: PE_g = mgh"}},
                ]
            },
            "result": "Final generated model response: In free fall, potential energy decreases.",
        }

        redacted = _redact_payload(payload)

        # Confirm non-sensitive structure and roles are preserved
        self.assertEqual(redacted["messages"][0]["role"], "system")
        self.assertEqual(redacted["messages"][1]["role"], "user")
        self.assertEqual(redacted["messages"][2]["role"], "assistant")
        self.assertEqual(redacted["outputs"]["generations"][1]["message"]["role"], "assistant")

        # Confirm prompt and input texts are redacted
        self.assertTrue(redacted["prompt"].startswith("[REDACTED_STUDENT_TEXT: length="))
        self.assertTrue(redacted["messages"][0]["content"].startswith("[REDACTED_STUDENT_TEXT: length="))
        self.assertTrue(redacted["messages"][1]["content"].startswith("[REDACTED_STUDENT_TEXT: length="))

        # Confirm model outputs (assistant responses and generations) are redacted
        self.assertTrue(redacted["messages"][2]["content"].startswith("[REDACTED_STUDENT_TEXT: length="))
        self.assertTrue(redacted["outputs"]["generations"][0]["text"].startswith("[REDACTED_STUDENT_TEXT: length="))
        self.assertTrue(redacted["outputs"]["generations"][1]["message"]["content"].startswith("[REDACTED_STUDENT_TEXT: length="))
        self.assertTrue(redacted["result"].startswith("[REDACTED_STUDENT_TEXT: length="))

        # Invariant: NO raw student text or textbook paraphrase in the entire redacted payload
        redacted_str = str(redacted)
        self.assertNotIn("Objects in free fall", redacted_str)
        self.assertNotIn("potential energy increases", redacted_str)
        self.assertNotIn("gravity causes an increase", redacted_str)
        self.assertNotIn("PE_g = mgh", redacted_str)

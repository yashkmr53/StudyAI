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

    def test_get_embedding_model_sentence_transformers_langchain(self):
        with patch("ai.langchain.models.LangChainEmbeddingAdapter._init_embeddings"):
            model = get_embedding_model("sentence_transformers_langchain")
            self.assertIsNotNone(model)

    def test_get_embedding_model_hashing_fallback(self):
        model = get_embedding_model("hashing")
        self.assertIsNotNone(model)

    def test_get_provider_chain_llm(self):
        with patch("ai.langchain.models.LangChainChatModelAdapter._init_model"):
            chain = get_provider_chain("ollama-langchain,mock", provider_type="llm")
            self.assertEqual(len(chain), 2)

    def test_get_provider_chain_embedding(self):
        with patch("ai.langchain.models.LangChainEmbeddingAdapter._init_embeddings"):
            chain = get_provider_chain("sentence_transformers_langchain,hashing", provider_type="embedding")
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

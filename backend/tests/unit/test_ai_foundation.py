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

    def test_seed_agent_prompt_versions_succeeds_and_syncs_canonical_prompt(self):
        from apps.agents.models import AgentPromptVersion, seed_agent_prompt_versions
        from apps.ai_classroom.models import PromptVersion

        created = seed_agent_prompt_versions()
        again = seed_agent_prompt_versions()
        self.assertEqual(created, 1)
        self.assertEqual(again, 0)
        self.assertTrue(AgentPromptVersion.objects.filter(name="agent_orchestrator", version="v1").exists())
        self.assertTrue(PromptVersion.objects.filter(prompt_name="agent_orchestrator", version="v1", is_active=True).exists())

    def test_seed_all_prompt_versions_syncs_file_and_classroom_prompts(self):
        from apps.ai_classroom.models import PromptVersion
        from apps.ai_classroom.prompts import seed_all_prompt_versions

        seed_all_prompt_versions()
        for expected in (
            "enrichment_draft",
            "gap_detection",
            "gap_filling",
            "chat_answer",
            "agent_orchestrator",
            "question_generation",
        ):
            self.assertTrue(
                PromptVersion.objects.filter(prompt_name=expected, is_active=True).exists(),
                f"Expected unified PromptVersion for {expected}",
            )

    def test_unified_registry_respects_active_db_override_across_nodes(self):
        from ai.langchain.prompts import resolve_prompt_version, resolve_qualified_version
        from apps.ai_classroom.models import PromptVersion
        from apps.questions.question_generation_nodes import generate_questions_node

        PromptVersion.objects.create(
            prompt_name="question_generation",
            version="v2",
            template="v2 template",
            output_schema_version="v1",
            model="qwen3.5:4b",
            is_active=True,
        )
        PromptVersion.objects.create(
            prompt_name="chat_answer",
            version="v2",
            template="v2 chat template",
            output_schema_version="v1",
            model="qwen3.5:4b",
            is_active=True,
        )

        self.assertEqual(resolve_prompt_version("question_generation"), "v2")
        self.assertEqual(resolve_qualified_version("chat", aliases=("chat_answer",)), "chat:v2")

        captured = {}

        class CapturingLLM:
            model = "mock"
            name = "mock"

            def generate_structured(self, *, prompt, schema=None, request_id="", **kwargs):
                captured["version"] = prompt.version
                return MagicMock(
                    data={
                        "prompt": "Q?",
                        "options": ["A", "B", "C", "D"],
                        "answer_index": 0,
                        "difficulty": "easy",
                        "question_type": "mcq",
                        "explanation": "Explained cleanly.",
                    },
                    model="mock",
                )

        with patch("apps.questions.question_generation_nodes.get_llm_provider", return_value=CapturingLLM()):
            res = generate_questions_node(
                {
                    "chunks": [{"chunk_id": "c-1", "content": "Graph algorithms use priority queues."}],
                    "reference_chunks": [],
                    "question_type": "mcq",
                    "difficulty": "easy",
                }
            )
        self.assertEqual(captured.get("version"), "v2")
        self.assertEqual(len(res["questions"]), 1)


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


class TestT8TracingChokePointAndDecorators(TestCase):
    def setUp(self):
        from ai.tracing import config
        config._tracing_enabled = False
        config._client = None

    def tearDown(self):
        from ai.tracing import config
        config._tracing_enabled = False
        config._client = None

    def test_topic_enrichment_llm_call_emits_redacted_langsmith_trace_when_enabled(self):
        """T8: Topic enrichment calls through LLMChainProvider emit redacted LangSmith traces + PG ProviderCallLog."""
        import os
        import uuid
        from ai.langgraph.nodes.segment_classifier_node import segment_classifier_node
        from apps.audit.models import ProviderCallLog

        mock_client = MagicMock()
        mock_run = MagicMock()
        mock_run.id = "run-enrichment-1"
        mock_client.create_run.return_value = mock_run

        state = {
            "approved_lines": [
                {
                    "id": str(uuid.uuid4()),
                    "lineage_id": "lid-1",
                    "text": "SECRET_STUDENT_NOTE: Maxwell displacement current term",
                    "line_index": 0,
                }
            ],
            "force_include_line_ids": [],
        }

        with override_settings(
            LANGSMITH_TRACING=True,
            LANGSMITH_API_KEY="test-key",
            LANGSMITH_REDACT_STUDENT_TEXT=True,
        ), patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "test-key"}), \
             patch("langsmith.Client", return_value=mock_client):
            segment_classifier_node(state)

        self.assertGreaterEqual(ProviderCallLog.objects.filter(success=True).count(), 1)
        llm_calls = [
            c for c in mock_client.create_run.call_args_list
            if c.kwargs.get("run_type") == "llm"
        ]
        self.assertGreaterEqual(len(llm_calls), 1, f"Expected llm trace from topic enrichment, got: {mock_client.create_run.call_args_list}")
        serialized = str(llm_calls)
        self.assertNotIn("SECRET_STUDENT_NOTE", serialized)

    def test_topic_enrichment_emits_zero_traces_when_disabled(self):
        """T8: With LANGSMITH_TRACING=False, zero LangSmith client calls are sent."""
        import os
        import uuid
        from ai.langgraph.nodes.segment_classifier_node import segment_classifier_node

        mock_client = MagicMock()
        state = {
            "approved_lines": [
                {"id": str(uuid.uuid4()), "lineage_id": "lid-1", "text": "Normal study note text", "line_index": 0}
            ],
            "force_include_line_ids": [],
        }

        with override_settings(LANGSMITH_TRACING=False), \
             patch.dict(os.environ, {"LANGSMITH_TRACING": "false", "LANGSMITH_API_KEY": "test-key"}), \
             patch("langsmith.Client", return_value=mock_client):
            segment_classifier_node(state)

        mock_client.create_run.assert_not_called()

    def test_traced_node_and_graph_redact_payload_pass_parent_run_id_and_end_time(self):
        """T8: @traced_graph and @traced_node redact payloads, pass parent_run_id top-level, and set end_time."""
        import os
        from ai.tracing.decorators import traced_graph, traced_node

        mock_client = MagicMock()
        graph_run = MagicMock()
        graph_run.id = "graph-run-123"
        node_run = MagicMock()
        node_run.id = "node-run-456"
        mock_client.create_run.side_effect = [graph_run, node_run]

        @traced_node("unit_node", feature="test")
        def inner_node(st):
            return {"answer": "SECRET_OUTPUT_ANSWER", "status": "ok"}

        @traced_graph("unit_graph", feature="test")
        def outer_graph(st):
            return inner_node(st)

        with override_settings(
            LANGSMITH_TRACING=True,
            LANGSMITH_API_KEY="test-key",
            LANGSMITH_REDACT_STUDENT_TEXT=True,
        ), patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "test-key"}), \
             patch("langsmith.Client", return_value=mock_client):
            outer_graph({"student_text": "SECRET_INPUT_NOTE", "safe_id": "id-1"})

        self.assertEqual(mock_client.create_run.call_count, 2)
        graph_kwargs = mock_client.create_run.call_args_list[0].kwargs
        node_kwargs = mock_client.create_run.call_args_list[1].kwargs

        self.assertEqual(node_kwargs.get("parent_run_id"), "graph-run-123")
        self.assertNotIn("parent_run_id", node_kwargs.get("extra", {}))
        self.assertNotIn("SECRET_INPUT_NOTE", str(graph_kwargs.get("inputs")))
        self.assertNotIn("SECRET_INPUT_NOTE", str(node_kwargs.get("inputs")))

        for upd in mock_client.update_run.call_args_list:
            self.assertIsNotNone(upd.kwargs.get("end_time"))
            self.assertNotIn("SECRET_OUTPUT_ANSWER", str(upd.kwargs.get("outputs")))

    def test_chat_node_traces_llm_call_exactly_once(self):
        """T8: Chat node calling get_llm_provider() logs exactly 1 llm run (no duplicate node + provider trace)."""
        import os
        from apps.chat.langgraph_nodes import answer_generation_node

        mock_client = MagicMock()
        mock_run = MagicMock()
        mock_run.id = "chat-run-1"
        mock_client.create_run.return_value = mock_run

        state = {
            "user_request": "Explain Dijkstra SECRET_CHAT_QUERY",
            "profile_id": "p1",
            "subject_id": None,
            "session_id": "s1",
            "route": "material",
            "selected_evidence": [
                {"citation_id": "SRC-001", "chunk_id": "c1", "snippet": "Dijkstra finds shortest path", "source_type": "database"}
            ],
            "messages": [],
        }

        with override_settings(
            LANGSMITH_TRACING=True,
            LANGSMITH_API_KEY="test-key",
            LANGSMITH_REDACT_STUDENT_TEXT=True,
        ), patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "test-key"}), \
             patch("langsmith.Client", return_value=mock_client):
            answer_generation_node(state)

        llm_calls = [
            c for c in mock_client.create_run.call_args_list
            if c.kwargs.get("run_type") == "llm"
        ]
        self.assertEqual(len(llm_calls), 1, f"Expected exactly 1 LLM trace, got {len(llm_calls)}")
        self.assertNotIn("SECRET_CHAT_QUERY", str(llm_calls))

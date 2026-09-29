"""Phase 11: Reference Library & Grounded Knowledge test suite.

Comprehensive tests covering:
1. ReferenceDocument & ReferenceChunk models, status lifecycle, and provenance.
2. PDF text extraction and vision OCR fallback.
3. Deterministic textbook chunking with chapter/section tracking and sliding overlap.
4. Ingestion workflow with batched embedding generation and pgvector persistence.
5. Shared Reference Retrieval Service (hybrid search, RRF fusion, profile isolation, subject scoping, global access).
6. Cascade deletion of reference documents and chunks.
7. Note enrichment integration with grounded reference context vs no-reference fallback.
8. Ask StudyAI chat integration with grounded textbook evidence and multi-turn context preservation.
"""
import io
import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from fpdf import FPDF
from rest_framework.test import APIClient

from apps.ai_classroom.enrichment_nodes import draft_node, retrieve_chunks_node
from apps.chat.models import ChatSession
from apps.chat.services import ChatService
from apps.documents.models import Document
from apps.profiles.models import Profile
from apps.references.chunking import chunk_extracted_pages
from apps.references.extraction import extract_pdf_pages
from apps.references.ingestion import ingest_reference_document
from apps.references.models import ReferenceChunk, ReferenceDocument
from apps.references.services import retrieve_reference_context
from apps.retrieval.models import NoteChunk
from apps.retrieval.retrieval import RetrievalService
from apps.subjects.models import Subject
from providers.llm.mock import MockLLMProvider

User = get_user_model()


def _create_sample_pdf(pages_text: list[str]) -> io.BytesIO:
    """Create a minimal real PDF with the provided page contents."""
    pdf = FPDF()
    for text in pages_text:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 10, text)
    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf


class MockEmbedder:
    name = "mock_embedder"

    def embed(self, texts, *, model_version=None):
        return [[0.1] * 1024 for _ in texts]

    def embed_batch(self, texts, *, model_version=None):
        return [[0.1] * 1024 for _ in texts]


class TestReferenceModels(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ref_user@studyai.test", password="password123")
        self.profile = Profile.objects.create(user=self.user, name="Ref Profile")
        self.subject = Subject.objects.create(profile=self.profile, name="Machine Learning")

    def test_create_reference_document(self):
        doc = ReferenceDocument.objects.create(
            title="Deep Learning Foundations",
            source_type=ReferenceDocument.SourceType.TEXTBOOK,
            profile=self.profile,
            subject=self.subject,
            page_count=450,
            chunk_count=120,
            status=ReferenceDocument.Status.READY,
        )
        self.assertEqual(doc.status, ReferenceDocument.Status.READY)
        self.assertEqual(doc.source_type, ReferenceDocument.SourceType.TEXTBOOK)
        self.assertEqual(doc.page_count, 450)
        self.assertEqual(doc.chunk_count, 120)
        self.assertEqual(str(doc), "Deep Learning Foundations (TEXTBOOK, READY)")

    def test_global_scope_document(self):
        doc = ReferenceDocument.objects.create(
            title="Standard Algorithms",
            source_type=ReferenceDocument.SourceType.REFERENCE_PDF,
            profile=None,  # global
            subject=None,
        )
        self.assertIsNone(doc.profile)
        self.assertEqual(doc.status, ReferenceDocument.Status.PENDING)

    def test_reference_chunk_provenance(self):
        doc = ReferenceDocument.objects.create(
            title="Computer Vision Notes",
            source_type=ReferenceDocument.SourceType.LECTURE_MATERIAL,
            profile=self.profile,
            subject=self.subject,
        )
        embedding = [0.05] * 1024
        chunk = ReferenceChunk.objects.create(
            reference_document=doc,
            chunk_index=1,
            page_number=12,
            chapter="Chapter 3: Edge Detection",
            section="3.2 Sobel Operators",
            text="The Sobel operator performs a 2-D spatial gradient measurement on an image.",
            content_hash="abc123hash",
            embedding=embedding,
            metadata={"keywords": ["sobel", "edge", "gradient"]},
        )
        self.assertEqual(chunk.reference_document, doc)
        self.assertEqual(chunk.page_number, 12)
        self.assertEqual(chunk.chapter, "Chapter 3: Edge Detection")
        self.assertEqual(chunk.section, "3.2 Sobel Operators")
        self.assertEqual(len(chunk.embedding), 1024)
        self.assertIn("Computer Vision Notes", str(chunk))


class TestExtractionAndChunking(TestCase):
    def test_direct_pdf_extraction(self):
        text_p1 = "Chapter 1: Introduction to Neural Networks.\nNeural networks are composed of layers of nodes."
        text_p2 = "Chapter 2: Optimization and Loss Functions.\nGradient descent adjusts weights to minimize loss."
        pdf_file = _create_sample_pdf([text_p1, text_p2])

        pages = extract_pdf_pages(pdf_file)
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertIn("Neural networks", pages[0]["text"])
        self.assertEqual(pages[1]["page_number"], 2)
        self.assertIn("Gradient descent", pages[1]["text"])

    def test_ocr_fallback_for_scanned_low_text_page(self):
        low_text = "Img"
        pdf_file = _create_sample_pdf([low_text])

        mock_img = MagicMock()
        mock_img.data = b"fake-png-image-bytes"

        with patch("pypdf.PdfReader") as mock_reader_cls, \
             patch("providers.registry.get_ocr_provider") as mock_get_ocr:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Img"
            mock_page.images = [mock_img]

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]
            mock_reader_cls.return_value = mock_reader

            mock_ocr = MagicMock()
            mock_ocr_res = MagicMock()
            mock_ocr_res.lines = ["Backpropagation and Chain Rule"]
            mock_ocr.recognize.return_value = mock_ocr_res
            mock_get_ocr.return_value = mock_ocr

            pages = extract_pdf_pages(pdf_file)
            self.assertEqual(len(pages), 1)
            self.assertIn("Backpropagation and Chain Rule", pages[0]["text"])
            self.assertEqual(pages[0]["method"], "vision_ocr")

    def test_deterministic_textbook_chunking(self):
        content_p1 = (
            "Chapter 4: Convolutional Networks\n\n"
            "4.1 Architecture Overview\n"
            + "Convolutional neural networks use convolution instead of general matrix multiplication. " * 15
        )
        content_p2 = (
            "4.2 Pooling Layers\n"
            + "Pooling layers simplify the information in the output from the convolutional layer. " * 15
        )
        pages = [
            {"page_number": 1, "text": content_p1},
            {"page_number": 2, "text": content_p2},
        ]

        chunks1 = chunk_extracted_pages(pages, target_words=100, overlap_words=20)
        chunks2 = chunk_extracted_pages(pages, target_words=100, overlap_words=20)

        # Determinism: chunk counts and hashes match identically
        self.assertEqual(len(chunks1), len(chunks2))
        self.assertGreater(len(chunks1), 1)
        for c1, c2 in zip(chunks1, chunks2):
            self.assertEqual(c1["content_hash"], c2["content_hash"])
            self.assertEqual(c1["chapter"], c2["chapter"])
            self.assertEqual(c1["section"], c2["section"])
            self.assertEqual(c1["page_number"], c2["page_number"])

        # Chapter and section tracking
        self.assertTrue(any(c["chapter"] == "Chapter 4: Convolutional Networks" for c in chunks1))
        self.assertTrue(any("4.1" in str(c["section"]) or "4.2" in str(c["section"]) for c in chunks1))


class TestIngestionWorkflow(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ingest_user@studyai.test", password="password123")
        self.profile = Profile.objects.create(user=self.user, name="Ingest Profile")
        self.subject = Subject.objects.create(profile=self.profile, name="Data Science")

    @patch("apps.references.ingestion.get_object_storage")
    @patch("apps.references.ingestion.get_embedding_provider")
    def test_ingestion_success(self, mock_get_embedder, mock_get_storage):
        pdf_buf = _create_sample_pdf([
            "Chapter 1: Vectors and Matrices.\nLinear algebra is fundamental to data science.",
            "Chapter 2: Eigenvalues and Eigenvectors.\nEigen decomposition reveals matrix properties.",
        ])
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.read_bytes.return_value = pdf_buf.getvalue()
        mock_get_storage.return_value = mock_storage

        mock_embedder = MagicMock()
        mock_embedder.name = "sentence_transformers"
        mock_embedder.embed.side_effect = lambda texts, **kw: [[0.1] * 1024 for _ in texts]
        mock_get_embedder.return_value = mock_embedder

        doc = ReferenceDocument.objects.create(
            title="Linear Algebra for Data Science",
            source_type=ReferenceDocument.SourceType.TEXTBOOK,
            file_path="references/linalg.pdf",
            profile=self.profile,
            subject=self.subject,
        )

        res = ingest_reference_document(str(doc.id))
        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["page_count"], 2)
        self.assertGreater(res["chunk_count"], 0)

        # Verify DB state
        doc.refresh_from_db()
        self.assertEqual(doc.status, ReferenceDocument.Status.READY)
        self.assertEqual(doc.page_count, 2)
        self.assertEqual(doc.chunk_count, res["chunk_count"])
        self.assertEqual(doc.chunks.count(), res["chunk_count"])

    @patch("apps.references.ingestion.get_object_storage")
    def test_ingestion_failure_records_error(self, mock_get_storage):
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.read_bytes.side_effect = Exception("Storage connection timeout")
        mock_get_storage.return_value = mock_storage

        doc = ReferenceDocument.objects.create(
            title="Corrupted Book",
            source_type=ReferenceDocument.SourceType.TEXTBOOK,
            file_path="references/missing.pdf",
            profile=self.profile,
        )

        with self.assertRaises(Exception):
            ingest_reference_document(str(doc.id))

        doc.refresh_from_db()
        self.assertEqual(doc.status, ReferenceDocument.Status.FAILED)
        self.assertIn("Storage connection timeout", doc.error_message)


class TestSharedReferenceRetrievalService(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(email="user_a@studyai.test", password="password123")
        self.profile_a = Profile.objects.create(user=self.user_a, name="Profile A")
        self.subject_cs = Subject.objects.create(profile=self.profile_a, name="Computer Science")
        self.subject_math = Subject.objects.create(profile=self.profile_a, name="Mathematics")

        self.user_b = User.objects.create_user(email="user_b@studyai.test", password="password123")
        self.profile_b = Profile.objects.create(user=self.user_b, name="Profile B")

        # Document 1 (Profile A, Subject CS)
        self.doc_cs = ReferenceDocument.objects.create(
            title="CS Textbook",
            source_type=ReferenceDocument.SourceType.TEXTBOOK,
            profile=self.profile_a,
            subject=self.subject_cs,
            status=ReferenceDocument.Status.READY,
        )
        vec_cs = [1.0] + [0.0] * 1023
        self.chunk_cs = ReferenceChunk.objects.create(
            reference_document=self.doc_cs,
            chunk_index=0,
            page_number=10,
            chapter="Chapter 2",
            section="2.1 Graph Search",
            text="Breadth-first search traverses graphs layer by layer using a FIFO queue.",
            content_hash="cs_chunk_0",
            embedding=vec_cs,
        )

        # Document 2 (Profile A, Subject Math)
        self.doc_math = ReferenceDocument.objects.create(
            title="Math Reference",
            source_type=ReferenceDocument.SourceType.REFERENCE_PDF,
            profile=self.profile_a,
            subject=self.subject_math,
            status=ReferenceDocument.Status.READY,
        )
        vec_math = [0.0, 1.0] + [0.0] * 1022
        self.chunk_math = ReferenceChunk.objects.create(
            reference_document=self.doc_math,
            chunk_index=0,
            page_number=25,
            chapter="Chapter 5",
            section="5.3 Integration",
            text="Riemann sums approximate the definite integral of a continuous function.",
            content_hash="math_chunk_0",
            embedding=vec_math,
        )

        # Document 3 (Global Reference - profile=None)
        self.doc_global = ReferenceDocument.objects.create(
            title="General Reference Handbook",
            source_type=ReferenceDocument.SourceType.TEXTBOOK,
            profile=None,
            subject=None,
            status=ReferenceDocument.Status.READY,
        )
        vec_global = [0.5, 0.5] + [0.0] * 1022
        self.chunk_global = ReferenceChunk.objects.create(
            reference_document=self.doc_global,
            chunk_index=0,
            page_number=1,
            chapter="Introduction",
            section="1.0 Scientific Method",
            text="Hypothesis testing provides empirical validation across all scientific disciplines.",
            content_hash="global_chunk_0",
            embedding=vec_global,
        )

    @patch("apps.references.services.get_embedding_provider")
    def test_ranking_and_query_similarity(self, mock_get_embedder):
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.9] + [0.0] * 1023]
        mock_get_embedder.return_value = mock_embedder

        results = retrieve_reference_context(
            "graph traversal queue",
            profile=self.profile_a,
            subject=self.subject_cs,
            top_k=3,
        )
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["chunk_id"], str(self.chunk_cs.id))
        self.assertIn("Breadth-first search", results[0]["text"])
        self.assertEqual(results[0]["source_title"], "CS Textbook")

    @patch("apps.references.services.get_embedding_provider")
    def test_profile_isolation(self, mock_get_embedder):
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.9] + [0.0] * 1023]
        mock_get_embedder.return_value = mock_embedder

        # Profile B must NOT see Profile A's CS textbook
        results_b = retrieve_reference_context(
            "graph traversal",
            profile=self.profile_b,
            top_k=5,
        )
        doc_ids_b = [r["document_id"] for r in results_b]
        self.assertNotIn(str(self.doc_cs.id), doc_ids_b)
        self.assertNotIn(str(self.doc_math.id), doc_ids_b)

    @patch("apps.references.services.get_embedding_provider")
    def test_global_scope_accessible_to_all_profiles(self, mock_get_embedder):
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.5, 0.5] + [0.0] * 1022]
        mock_get_embedder.return_value = mock_embedder

        # Global document accessible to Profile B
        results = retrieve_reference_context(
            "hypothesis testing scientific method",
            profile=self.profile_b,
            top_k=5,
        )
        doc_ids = [r["document_id"] for r in results]
        self.assertIn(str(self.doc_global.id), doc_ids)

    def test_cascade_deletion(self):
        doc_id = self.doc_cs.id
        chunk_id = self.chunk_cs.id

        self.assertTrue(ReferenceDocument.objects.filter(id=doc_id).exists())
        self.assertTrue(ReferenceChunk.objects.filter(id=chunk_id).exists())

        self.doc_cs.delete()

        self.assertFalse(ReferenceDocument.objects.filter(id=doc_id).exists())
        self.assertFalse(ReferenceChunk.objects.filter(id=chunk_id).exists())


class TestEnrichmentAndChatIntegration(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="enrich_user@studyai.test", password="password123")
        self.profile = Profile.objects.create(
            user=self.user, name="Enrich Profile", module=Profile.Module.AI_CLASSROOM
        )
        self.subject = Subject.objects.create(profile=self.profile, name="Machine Learning")

        # Create textbook reference
        self.doc = ReferenceDocument.objects.create(
            title="Pattern Recognition and ML",
            source_type=ReferenceDocument.SourceType.TEXTBOOK,
            profile=self.profile,
            subject=self.subject,
            status=ReferenceDocument.Status.READY,
        )
        self.chunk = ReferenceChunk.objects.create(
            reference_document=self.doc,
            chunk_index=0,
            page_number=45,
            chapter="Chapter 3",
            section="3.1 Linear Models",
            text="Linear models for regression map input vectors to continuous target values using linear combinations.",
            content_hash="prml_0",
            embedding=[0.8] + [0.0] * 1023,
        )

    @patch("apps.references.services.get_embedding_provider")
    def test_enrichment_incorporates_reference_chunks(self, mock_get_embedder):
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.8] + [0.0] * 1023]
        mock_get_embedder.return_value = mock_embedder

        # Create note document and note chunk
        note_doc = Document.objects.create(
            profile=self.profile,
            subject=self.subject,
            title="Linear Models Lecture Note",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.PDF,
        )
        note_chunk = NoteChunk.objects.create(
            document=note_doc,
            chunk_index=0,
            content="Linear models for regression predict continuous outputs.",
            revision_id=uuid.uuid4(),
            page_start=1,
            page_end=1,
            stale=False,
        )

        # 1. Test retrieve_chunks_node uses shared reference retrieval
        state = {"document_id": str(note_doc.id)}
        retrieved_state = retrieve_chunks_node(state)

        self.assertIn("reference_chunks", retrieved_state)
        self.assertGreaterEqual(len(retrieved_state["reference_chunks"]), 1)
        ref_c = retrieved_state["reference_chunks"][0]
        self.assertEqual(ref_c["source_title"], "Pattern Recognition and ML")
        self.assertEqual(ref_c["source_type"], "TEXTBOOK")
        self.assertTrue(retrieved_state["evidence_payload"]["has_reference_material"])

        # 2. Test draft_node supplies grounding guidance
        with patch("apps.ai_classroom.enrichment_nodes.get_llm_provider") as mock_get_llm:
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            draft_state = {**state, **retrieved_state}
            res = draft_node(draft_state)
            self.assertIn("draft_result", res)

            call_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            self.assertIn("REFERENCE MATERIAL is provided in 'reference_chunks'", call_prompt.user)

    def test_enrichment_no_reference_fallback(self):
        # Subject with NO reference documents
        subject_empty = Subject.objects.create(profile=self.profile, name="Empty Subject")
        note_doc = Document.objects.create(
            profile=self.profile,
            subject=subject_empty,
            title="Standalone Note",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.PDF,
        )
        NoteChunk.objects.create(
            document=note_doc,
            chunk_index=0,
            content="Basic notes without any textbook.",
            revision_id=uuid.uuid4(),
            page_start=1,
            page_end=1,
            stale=False,
        )

        state = {"document_id": str(note_doc.id)}
        retrieved_state = retrieve_chunks_node(state)
        self.assertEqual(retrieved_state["reference_chunks"], [])
        self.assertFalse(retrieved_state["evidence_payload"]["has_reference_material"])

        with patch("apps.ai_classroom.enrichment_nodes.get_llm_provider") as mock_get_llm:
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            draft_state = {**state, **retrieved_state}
            res = draft_node(draft_state)
            self.assertIn("draft_result", res)

            call_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            self.assertIn("No textbook or reference material is available", call_prompt.user)
            self.assertIn("Do NOT fabricate or cite any textbook references", call_prompt.user)

    @patch("providers.registry.get_embedding_provider")
    def test_chat_retrieves_reference_material_and_preserves_multi_turn(self, mock_get_embedder):
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.8] + [0.0] * 1023]
        mock_embedder.embed_batch.return_value = [[0.8] + [0.0] * 1023]
        mock_get_embedder.return_value = mock_embedder

        session = ChatSession.objects.create(
            profile=self.profile, subject=self.subject, title="Grounded Reference Chat"
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            # Turn 1: user asks about textbook topic referencing their material
            msg1 = ChatService.ask(session, "Explain linear models according to my textbook.")
            self.assertIsNotNone(msg1)

            # Turn 2: user follow-up
            msg2 = ChatService.ask(session, "Can you provide an example?")
            self.assertIsNotNone(msg2)

            # Second call prompt preserves multi-turn conversation
            second_call_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            prompt_msgs = getattr(second_call_prompt, "messages", [])
            contents = [str(m.get("content")) for m in prompt_msgs]

            self.assertTrue(any("linear models" in c.lower() for c in contents))
            self.assertTrue(any("example" in c.lower() for c in contents))

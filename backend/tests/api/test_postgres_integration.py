"""Real PostgreSQL integration suite (T11).

Covers PostgreSQL-specific capabilities skipped on SQLite:
1. Row-Level Security (RLS) isolation between two profiles under non-superuser `studyai_app`
2. Hybrid retrieval (pgvector dense + tsvector keyword) with and without `tag_ids`
3. ReferenceChunk HNSW cosine index verification in pg_indexes and EXPLAIN
"""
import hashlib

import pytest
from django.db import connection, transaction
from django.test import TestCase

from apps.accounts.models import User
from apps.ai_classroom.models import DocumentTag, Tag
from apps.documents.models import Document, DocumentLine, DocumentPage, DocumentPageRevision
from apps.profiles.models import Profile
from apps.references.models import ReferenceChunk
from apps.retrieval.models import NoteChunk
from apps.retrieval.retrieval import RetrievalService
from apps.retrieval.services import index_document
from apps.subjects.models import Subject
from shared.database.rls import profile_scoped_transaction


@pytest.mark.postgres
class PostgresIntegrationSuiteTests(TestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL + pgvector + RLS required")

        self.user_a = User.objects.create_user(email="pg_a@example.com", password="SecretPass123!")
        self.user_b = User.objects.create_user(email="pg_b@example.com", password="SecretPass123!")
        self.profile_a = Profile.objects.create(user=self.user_a, name="PG Profile A")
        self.profile_b = Profile.objects.create(user=self.user_b, name="PG Profile B")

    def _create_indexed_note(self, profile: Profile, subject: Subject | None, text: str, title: str) -> Document:
        with profile_scoped_transaction(profile.id):
            doc = Document.objects.create(
                profile=profile,
                subject=subject,
                title=title,
                source=Document.Source.UPLOAD,
                source_type=Document.SourceType.IMAGE,
            )
            page = DocumentPage.objects.create(
                document=doc,
                page_number=1,
                image_ref="uploads/pg_test_page.png",
                ocr_status=DocumentPage.OcrStatus.COMPLETED,
                review_status=DocumentPage.ReviewStatus.APPROVED,
                is_approved=True,
            )
            rev = DocumentPageRevision.objects.create(
                page=page,
                revision_number=1,
                revision_type=DocumentPageRevision.RevisionType.USER_EDIT,
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
                ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
            )
            page.current_revision_id = rev.pk
            page.save(update_fields=["current_revision_id"])
            DocumentLine.objects.create(
                page_revision=rev,
                line_index=1,
                text=text,
                confidence_score=0.99,
            )
            index_document(doc)
        return doc

    def test_rls_isolation_between_two_profiles(self):
        doc_a = self._create_indexed_note(
            self.profile_a,
            None,
            "Alice private eigenvalues linear algebra matrix decomposition notes.",
            "Alice Notes",
        )
        doc_b = self._create_indexed_note(
            self.profile_b,
            None,
            "Bob private organic chemistry nucleophilic substitution mechanisms.",
            "Bob Notes",
        )

        with connection.cursor() as cursor:
            cursor.execute("SET ROLE studyai_app;")

        try:
            with profile_scoped_transaction(self.profile_a.id):
                self.assertEqual(set(Document.objects.values_list("id", flat=True)), {doc_a.id})
                self.assertEqual(set(NoteChunk.objects.values_list("document_id", flat=True)), {doc_a.id})

            with profile_scoped_transaction(self.profile_b.id):
                self.assertEqual(set(Document.objects.values_list("id", flat=True)), {doc_b.id})
                self.assertEqual(set(NoteChunk.objects.values_list("document_id", flat=True)), {doc_b.id})

            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.current_profile_id', '', true)")
            self.assertEqual(Document.objects.filter(pk__in=[doc_a.id, doc_b.id]).count(), 0)
            self.assertEqual(NoteChunk.objects.filter(document_id__in=[doc_a.id, doc_b.id]).count(), 0)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE;")

    def test_retrieval_search_with_and_without_tags(self):
        subject = Subject.objects.create(profile=self.profile_a, name="Algorithms PG")
        tag_graphs = Tag.objects.create(subject=subject, stable_key="pg_graphs", display_name="PG Graphs")
        tag_dp = Tag.objects.create(subject=subject, stable_key="pg_dp", display_name="PG DP")

        doc_graphs = self._create_indexed_note(
            self.profile_a,
            subject,
            "Algorithms study note: Dijkstra computes shortest paths in weighted directed graphs.",
            "Graphs Doc",
        )
        doc_dp = self._create_indexed_note(
            self.profile_a,
            subject,
            "Algorithms study note: Dynamic programming caches overlapping subproblems via memoization.",
            "DP Doc",
        )
        with profile_scoped_transaction(self.profile_a.id):
            DocumentTag.objects.create(document=doc_graphs, tag=tag_graphs)
            DocumentTag.objects.create(document=doc_dp, tag=tag_dp)

            # Without tag_ids: returns both documents with real dense (pgvector) & keyword (tsvector) ranks
            all_results = RetrievalService.search(
                self.user_a,
                "algorithms study note shortest paths subproblems",
                profile=self.profile_a,
                include_reference=False,
            )
            self.assertEqual({r.document_id for r in all_results}, {str(doc_graphs.id), str(doc_dp.id)})
            self.assertTrue(all(r.dense_rank is not None for r in all_results))
            self.assertTrue(all(r.keyword_rank is not None for r in all_results))

            # With tag_ids=[tag_graphs.id]: excludes doc_dp on both dense and keyword channels
            tagged_results = RetrievalService.search(
                self.user_a,
                "algorithms study note shortest paths subproblems",
                profile=self.profile_a,
                tag_ids=[tag_graphs.id],
                include_reference=False,
            )
            self.assertEqual({r.document_id for r in tagged_results}, {str(doc_graphs.id)})
            self.assertIsNotNone(tagged_results[0].dense_rank)
            self.assertIsNotNone(tagged_results[0].keyword_rank)

    def test_reference_chunk_hnsw_index(self):
        from pgvector.django import CosineDistance

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'references_referencechunk'
                  AND indexname = 'idx_refchunk_hnsw_embedding'
                """
            )
            row = cursor.fetchone()
        self.assertIsNotNone(row, "idx_refchunk_hnsw_embedding not found")
        self.assertIn("USING hnsw", row[1])
        self.assertIn("vector_cosine_ops", row[1])

        qvec = [0.01] * 1024
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL enable_seqscan = off;")
                qs = (
                    ReferenceChunk.objects.exclude(embedding__isnull=True)
                    .annotate(distance=CosineDistance("embedding", qvec))
                    .order_by("distance")[:5]
                )
                sql, params = qs.query.sql_with_params()
                cursor.execute(f"EXPLAIN {sql}", params)
                plan_lines = "\n".join(r[0] for r in cursor.fetchall())
        self.assertIn("idx_refchunk_hnsw_embedding", plan_lines)

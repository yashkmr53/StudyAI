"""Tests for PR 3 Reference-Coverage Guidance, Honest Labels & Telemetry.

Covers:
3.1 Topic coverage in serialization (evidence_status_by_topic, subject_id, subject_name).
3.2 ENRICHMENT_SHOW_PARTIAL setting toggling partial additions in get_blocks().
3.3 Reference library change detection:
    - reference_library_hash deterministic generation.
    - reference_snapshot_hash stored on EnrichedNote.
    - settings_version includes library hash and forces real regeneration on textbook change.
    - reference_library_changed read-time computation (true on gap, false on all sufficient).
3.4 Job progress reporting (current_stage, stages_done derived from checkpoints).
3.5 Privacy-safe telemetry in diagnostics and report_enrichment_coverage management command.
"""
import uuid
from io import StringIO
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock
from apps.ai_classroom.services import dispatch_enrichment_job
from apps.ai_classroom.views_serializers import EnrichedNoteSerializer
from apps.documents.models import Document, DocumentPage, DocumentPageRevision, DocumentLine
from apps.documents.views import _enrichment_job_payload
from apps.jobs.models import Job, JobExecutionState
from apps.profiles.models import Profile
from apps.references.models import ReferenceDocument
from apps.references.services import reference_library_hash
from apps.subjects.models import Subject
from django.contrib.auth import get_user_model
User = get_user_model()


class ReferenceCoverageTests(TestCase):
    def setUp(self):
        from shared.database.rls import profile_scoped_transaction

        self.user = User.objects.create(email="coverage_test@studyai.internal")
        self.profile = Profile.objects.create(user=self.user, name="Coverage Tester")
        with profile_scoped_transaction(self.profile.id):
            self.subject = Subject.objects.create(name="Computer Science", profile=self.profile)

            # Document with subject
            self.doc = Document.objects.create(
                profile=self.profile,
                subject=self.subject,
                title="OS Virtual Memory",
                source=Document.Source.UPLOAD,
                source_type=Document.SourceType.PDF,
            )
            self.page = DocumentPage.objects.create(
                document=self.doc,
                page_number=1,
                is_approved=True,
                is_ignored=False,
                approved_by=self.user,
                approved_at=timezone.now(),
            )
            self.rev = DocumentPageRevision.objects.create(
                page=self.page,
                revision_number=1,
                created_by=self.user,
                text_hash="hash_coverage_123",
            )
            self.page.current_revision_id = self.rev.id
            self.page.save()

            self.line = DocumentLine.objects.create(
                page_revision=self.rev,
                line_index=0,
                lineage_id=uuid.uuid4(),
                text="Virtual memory maps virtual addresses to physical frames.",
            )

    def test_reference_library_hash_deterministic(self):
        """Hash changes when documents are added or updated, and returns 'empty' when none exist."""
        from shared.database.rls import profile_scoped_transaction

        # When no books exist
        h0 = reference_library_hash(self.subject)
        self.assertEqual(h0, "empty")

        # When subject is None and no books exist
        self.assertEqual(reference_library_hash(None), "empty")

        # Add a READY reference document
        with profile_scoped_transaction(self.profile.id):
            ref_doc = ReferenceDocument.objects.create(
                title="OS Concepts",
                subject=self.subject,
                profile=self.profile,
                status=ReferenceDocument.Status.READY,
                chunk_count=10,
            )
        h1 = reference_library_hash(self.subject, profile=self.profile)
        self.assertNotEqual(h1, "empty")
        self.assertEqual(len(h1), 16)
        # When subject is None, it covers all READY documents
        self.assertEqual(reference_library_hash(None, profile=self.profile), h1)

        # Updating chunk count changes the hash
        with profile_scoped_transaction(self.profile.id):
            ref_doc.chunk_count = 15
            ref_doc.save(update_fields=("chunk_count", "updated_at"))
        h2 = reference_library_hash(self.subject, profile=self.profile)
        self.assertNotEqual(h1, h2)

        # Unscoped reference document (subject is None) affects subject hash
        with profile_scoped_transaction(self.profile.id):
            unscoped_doc = ReferenceDocument.objects.create(
                title="Global Handbook",
                subject=None,
                profile=self.profile,
                status=ReferenceDocument.Status.READY,
                chunk_count=5,
            )
        h3 = reference_library_hash(self.subject, profile=self.profile)
        self.assertNotEqual(h2, h3)

        # Another profile's document does not affect self.profile's hash
        user2 = User.objects.create(email="user2@example.com")
        profile2 = Profile.objects.create(user=user2, name="User Two")
        with profile_scoped_transaction(profile2.id):
            ReferenceDocument.objects.create(
                title="Other Profile Book",
                subject=None,
                profile=profile2,
                status=ReferenceDocument.Status.READY,
                chunk_count=20,
            )
        h4 = reference_library_hash(self.subject, profile=self.profile)
        self.assertEqual(h3, h4)

    def test_settings_version_incorporates_library_hash(self):
        """dispatch_enrichment_job embeds reference library hash in settings_version."""
        from shared.database.rls import profile_scoped_transaction

        with profile_scoped_transaction(self.profile.id):
            ReferenceDocument.objects.create(
                title="Computer Systems",
                subject=self.subject,
                status=ReferenceDocument.Status.READY,
                chunk_count=25,
            )
            expected_ref_hash = reference_library_hash(self.subject)

            job = dispatch_enrichment_job(self.doc, self.user)
        self.assertIn(expected_ref_hash, job.metadata["settings_version"])
        self.assertEqual(job.metadata["reference_snapshot_hash"], expected_ref_hash)

    def test_reference_library_changed_read_time_behavior(self):
        """Serializer computes reference_library_changed=True only when library hash changed AND note has none/partial."""
        from shared.database.rls import profile_scoped_transaction

        with profile_scoped_transaction(self.profile.id):
            ref_doc = ReferenceDocument.objects.create(
                title="Algorithms Book",
                subject=self.subject,
                status=ReferenceDocument.Status.READY,
                chunk_count=50,
            )
            initial_hash = reference_library_hash(self.subject)

            # 1. Note with 'partial' topic and matching initial_hash -> changed is False
            note = EnrichedNote.objects.create(
                document=self.doc,
                content_hash="desc_1",
                settings_version=f"v1:{initial_hash}",
                reference_snapshot_hash=initial_hash,
                evidence_status_by_topic={"t1": "partial", "t2": "sufficient"},
            )
            serializer = EnrichedNoteSerializer(note)
            self.assertFalse(serializer.data["reference_library_changed"])
            self.assertEqual(serializer.data["subject_id"], str(self.subject.id))
            self.assertEqual(serializer.data["subject_name"], "Computer Science")

            # 2. Upload/update reference document -> current hash changes -> note with partial has changed=True
            ref_doc.chunk_count = 60
            ref_doc.save(update_fields=("chunk_count", "updated_at"))
            self.assertNotEqual(reference_library_hash(self.subject), initial_hash)

            serializer_after = EnrichedNoteSerializer(note)
            self.assertTrue(serializer_after.data["reference_library_changed"])

            # 3. Note whose topics are ALL 'sufficient' never flags library_changed
            perfect_note = EnrichedNote.objects.create(
                document=self.doc,
                content_hash="desc_perfect",
                settings_version=f"v1:{initial_hash}",
                reference_snapshot_hash=initial_hash,
                evidence_status_by_topic={"t1": "sufficient", "t2": "sufficient"},
            )
            perf_serializer = EnrichedNoteSerializer(perfect_note)
            self.assertFalse(perf_serializer.data["reference_library_changed"])

    @override_settings(ENRICHMENT_SHOW_PARTIAL=True)
    def test_enrichment_show_partial_true(self):
        """When ENRICHMENT_SHOW_PARTIAL=True, both supported and partial additions are serialized."""
        from shared.database.rls import profile_scoped_transaction

        with profile_scoped_transaction(self.profile.id):
            note = EnrichedNote.objects.create(
                document=self.doc,
                content_hash="desc_partial_1",
            )
            EnrichedNoteBlock.objects.create(
                enriched_note=note,
                block_index=1,
                block_kind=EnrichedNoteBlock.BlockKind.ADDITION,
                support_status="supported",
                content="Fully supported addition",
                generation_method=EnrichedNoteBlock.GenerationMethod.LLM,
            )
            EnrichedNoteBlock.objects.create(
                enriched_note=note,
                block_index=2,
                block_kind=EnrichedNoteBlock.BlockKind.ADDITION,
                support_status="partial",
                content="Partial addition extending textbook",
                generation_method=EnrichedNoteBlock.GenerationMethod.LLM,
            )

            serializer = EnrichedNoteSerializer(note)
            blocks = serializer.data["blocks"]
            self.assertEqual(len(blocks), 2)
            contents = [b["content"] for b in blocks]
            self.assertIn("Fully supported addition", contents)
            self.assertIn("Partial addition extending textbook", contents)

    @override_settings(ENRICHMENT_SHOW_PARTIAL=False)
    def test_enrichment_show_partial_false(self):
        """When ENRICHMENT_SHOW_PARTIAL=False, partial additions are omitted while supported remain."""
        from shared.database.rls import profile_scoped_transaction

        with profile_scoped_transaction(self.profile.id):
            note = EnrichedNote.objects.create(
                document=self.doc,
                content_hash="desc_partial_2",
            )
            EnrichedNoteBlock.objects.create(
                enriched_note=note,
                block_index=1,
                block_kind=EnrichedNoteBlock.BlockKind.ADDITION,
                support_status="supported",
                content="Fully supported addition",
                generation_method=EnrichedNoteBlock.GenerationMethod.LLM,
            )
            EnrichedNoteBlock.objects.create(
                enriched_note=note,
                block_index=2,
                block_kind=EnrichedNoteBlock.BlockKind.ADDITION,
                support_status="partial",
                content="Partial addition extending textbook",
                generation_method=EnrichedNoteBlock.GenerationMethod.LLM,
            )

            serializer = EnrichedNoteSerializer(note)
            blocks = serializer.data["blocks"]
            self.assertEqual(len(blocks), 1)
            self.assertEqual(blocks[0]["content"], "Fully supported addition")

    def test_job_progress_current_stage_and_stages_done(self):
        """_enrichment_job_payload derives current_stage and stages_done from checkpoints."""
        job = Job.objects.create(
            job_type="enrich",
            resource_type="document",
            resource_id=str(self.doc.pk),
            status=Job.Status.RUNNING,
        )

        # Add checkpoints for classify and plan
        JobExecutionState.objects.create(job=job, completed_node="load_and_gate", state_json={})
        JobExecutionState.objects.create(job=job, completed_node="classify", state_json={})
        JobExecutionState.objects.create(
            job=job,
            completed_node="plan",
            state_json={"topic_plan": {"topics": [{"topic_id": "t1"}, {"topic_id": "t2"}]}},
        )

        payload1 = _enrichment_job_payload(job)
        prog1 = payload1["progress"]
        self.assertEqual(prog1["stages_done"], ["classify", "plan"])
        self.assertEqual(prog1["current_stage"], "research 1 of 2")

        # Complete research for t1
        JobExecutionState.objects.create(job=job, completed_node="research", topic_id="t1", state_json={})
        payload2 = _enrichment_job_payload(job)
        prog2 = payload2["progress"]
        self.assertEqual(prog2["current_stage"], "research 2 of 2")
        self.assertIn("research 1 of 2", prog2["stages_done"])

        # Complete research for t2
        JobExecutionState.objects.create(job=job, completed_node="research", topic_id="t2", state_json={})
        payload3 = _enrichment_job_payload(job)
        prog3 = payload3["progress"]
        self.assertEqual(prog3["current_stage"], "write 1 of 2")

    def test_privacy_safe_telemetry_in_diagnostics_and_report_command(self):
        """EnrichedNote diagnostics contain counts only (zero note text) and report command runs cleanly."""
        telemetry = {
            "topics_total": 2,
            "topics_by_evidence": {"sufficient": 1, "partial": 1, "none": 0},
            "additions_by_support": {"supported": 3, "partial": 1},
            "drops_by_reason": {
                "unanchored": 0,
                "low_similarity": 1,
                "unsupported": 0,
                "contradicted": 0,
                "duplicate": 0,
            },
            "llm_calls": 7,
            "seconds": 54.2,
            "planner_fallback": False,
        }

        from shared.database.rls import profile_scoped_transaction

        with profile_scoped_transaction(self.profile.id):
            note = EnrichedNote.objects.create(
                document=self.doc,
                content_hash="desc_telemetry",
                evidence_status_by_topic={"t1": "sufficient", "t2": "partial"},
                diagnostics=telemetry,
            )

            # Assert zero string leaks in diagnostics
            diag = note.diagnostics
            self.assertIsInstance(diag["topics_total"], int)
            self.assertIsInstance(diag["seconds"], float)
            self.assertNotIn("text", diag)
            self.assertNotIn("content", diag)
            self.assertNotIn("title", diag)

            # Run report_enrichment_coverage command
            out = StringIO()
            call_command("report_enrichment_coverage", "--days", "1", stdout=out)
            output_str = out.getvalue()

        self.assertIn("Topic Reference-Coverage", output_str)
        self.assertIn("Sufficient (Reference found)", output_str)
        self.assertIn("Addition Support Status", output_str)
        self.assertIn("From your reference", output_str)
        self.assertIn("Extends reference", output_str)

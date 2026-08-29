"""Seed realistic test data for local development and testing."""
import hashlib
import logging
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.ai_classroom.models import CitationBlock, DocumentTag, EnrichedNote, EnrichedNoteBlock, Tag
from apps.chat.models import ChatMessage, ChatSession
from apps.documents.models import Document, DocumentLine, DocumentPage, DocumentPageRevision
from apps.profiles.models import Profile
from apps.questions.models import Question, QuestionTagLink
from apps.retrieval.models import NoteChunk
from apps.subjects.models import Subject
from apps.tests.models import MasteryScore, TestAttempt, TestInstance, TestQuestion

logger = logging.getLogger(__name__)

SUBJECTS = ["Mathematics", "Physics", "Computer Science"]
TEST_USER_EMAIL = "test@studyai.local"
TEST_USER_PASSWORD = "testpass123"
PROFILE_NAME = "Test Profile"

PAGE_CONTENT = [
    "The fundamental theorem of calculus links differentiation and integration.",
    "Newton's second law states that force equals mass times acceleration.",
    "A binary search tree is a data structure that maintains sorted order.",
    "Photosynthesis converts light energy into chemical energy in plants.",
    "The time complexity of quicksort is O(n log n) on average.",
    "Ohm's law describes the relationship between voltage, current, and resistance.",
    "Recursion is a method where a function calls itself to solve smaller instances.",
    "The mitochondria is the powerhouse of the cell.",
    "Graph traversal algorithms include breadth-first search and depth-first search.",
    "Acceleration due to gravity on Earth is approximately 9.8 m/s^2.",
]

ENRICHMENT_BLOCKS = [
    ("overview", "This section introduces the core concept and its real-world applications."),
    ("key_concept", "The main idea here is that small changes accumulate to produce large effects over time."),
    ("gap_fill", "Remember to review the prerequisite definitions before attempting advanced problems."),
    ("practice_tip", "Try solving 3-5 practice problems after studying this section to reinforce understanding."),
]

TAG_HIERARCHIES = {
    "Mathematics": [
        ("algebra", ["equations", "polynomials", "functions"]),
        ("calculus", ["derivatives", "integrals", "limits"]),
    ],
    "Physics": [
        ("mechanics", ["motion", "forces", "energy"]),
        ("thermodynamics", ["heat", "entropy", "gas-laws"]),
    ],
    "Computer Science": [
        ("data-structures", ["arrays", "trees", "graphs"]),
        ("algorithms", ["sorting", "searching", "dynamic-programming"]),
    ],
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Command(BaseCommand):
    help = "Seed realistic test data for local development and testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing seed data before creating new data",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Resetting existing seed data...")
            self._reset_data()

        self.stdout.write("Seeding test data...")
        user, profile = self._seed_user_profile()
        subjects = self._seed_subjects(profile)
        docs = self._seed_documents(profile, subjects)
        chunks = self._seed_chunks(docs)
        self._seed_enrichments(docs, chunks)
        self._seed_tags(subjects)
        self._seed_document_tags(docs)
        self._seed_questions(subjects, chunks)
        self._seed_tests(subjects)
        self._seed_chat_sessions(profile, subjects)

        self.stdout.write(self.style.SUCCESS("Successfully seeded test data."))

    def _reset_data(self):
        ChatMessage.objects.all().delete()
        ChatSession.objects.all().delete()
        MasteryScore.objects.all().delete()
        TestAttempt.objects.all().delete()
        TestQuestion.objects.all().delete()
        TestInstance.objects.all().delete()
        QuestionTagLink.objects.all().delete()
        Question.objects.all().delete()
        DocumentTag.objects.all().delete()
        Tag.objects.all().delete()
        CitationBlock.objects.all().delete()
        EnrichedNoteBlock.objects.all().delete()
        EnrichedNote.objects.all().delete()
        NoteChunk.objects.all().delete()
        DocumentLine.objects.all().delete()
        DocumentPageRevision.objects.all().delete()
        DocumentPage.objects.all().delete()
        Document.objects.all().delete()
        Subject.objects.all().delete()
        Profile.objects.all().delete()
        User.objects.filter(email=TEST_USER_EMAIL).delete()

    def _seed_user_profile(self):
        user, _ = User.objects.get_or_create(
            email=TEST_USER_EMAIL,
            defaults={"is_active": True},
        )
        user.set_password(TEST_USER_PASSWORD)
        user.save()
        profile, _ = Profile.objects.get_or_create(
            user=user,
            name=PROFILE_NAME,
        )
        return user, profile

    def _seed_subjects(self, profile):
        subjects = []
        for name in SUBJECTS:
            subject, _ = Subject.objects.get_or_create(
                profile=profile,
                name=name,
            )
            subjects.append(subject)
        return subjects

    def _seed_documents(self, profile, subjects):
        docs = []
        for subject in subjects:
            for i in range(2):
                doc_name = f"{subject.name} - Document {i + 1}"
                doc, _ = Document.objects.get_or_create(
                    profile=profile,
                    subject=subject,
                    source=Document.Source.UPLOAD,
                    source_type=Document.SourceType.IMAGE,
                    defaults={"schema_version": "1"},
                )
                page, _ = DocumentPage.objects.get_or_create(
                    document=doc,
                    page_number=1,
                    defaults={"ocr_status": DocumentPage.OcrStatus.COMPLETED},
                )
                revision, _ = DocumentPageRevision.objects.get_or_create(
                    page=page,
                    revision_number=1,
                    defaults={
                        "content_hash": sha256(doc_name),
                        "content_snapshot": {"lines": []},
                        "ocr_status": DocumentPageRevision.OcrStatus.COMPLETED,
                        "ocr_provider": "mock",
                    },
                )
                lines = []
                for j, text in enumerate(PAGE_CONTENT[:20]):
                    line_text = f"[{subject.name}] {text}"
                    line, _ = DocumentLine.objects.get_or_create(
                        page_revision=revision,
                        line_index=j,
                        defaults={
                            "text": line_text,
                            "is_heading": j == 0,
                        },
                    )
                    lines.append(line)
                doc.pages.add(page)
                docs.append(doc)
        return docs

    def _seed_chunks(self, docs):
        chunks = []
        for doc in docs:
            for page in doc.pages.all():
                revision = page.revisions.order_by("-revision_number").first()
                if not revision:
                    continue
                lines = list(revision.lines.order_by("line_index"))
                for chunk_idx, i in enumerate(range(0, max(len(lines) - 2, 1), 3)):
                    content = "\n".join(l.text for l in lines[i : i + 3])
                    content_hash = sha256(content)
                    chunk, _ = NoteChunk.objects.get_or_create(
                        revision_id=str(revision.id),
                        content_hash=content_hash,
                        chunk_index=chunk_idx,
                        defaults={
                            "document": doc,
                            "profile": doc.profile,
                            "subject": doc.subject,
                            "revision_ids": [str(revision.id)],
                            "page_start": 1,
                            "page_end": 1,
                            "content": content,
                            "source_type": "note",
                        },
                    )
                    chunks.append(chunk)
        return chunks

    def _seed_enrichments(self, docs, chunks):
        for doc in docs[:3]:
            content_hash = sha256(f"enrich:{doc.id}")
            note, _ = EnrichedNote.objects.get_or_create(
                document=doc,
                content_hash=content_hash,
                defaults={
                    "revision_ids": [],
                    "provider": "mock",
                    "model": "mock-gpt",
                    "prompt_version": "enrichment_draft:v1",
                    "schema_version": "v1",
                },
            )
            for idx, (block_type, text) in enumerate(ENRICHMENT_BLOCKS):
                block, _ = EnrichedNoteBlock.objects.get_or_create(
                    enriched_note=note,
                    block_index=idx,
                    block_type=block_type,
                    defaults={
                        "title": f"{block_type.replace('_', ' ').title()} block",
                        "content": text,
                        "generation_method": EnrichedNoteBlock.GenerationMethod.LLM,
                        "source_chunk_ids": [str(c.id) for c in chunks[:2]],
                    },
                )
                CitationBlock.objects.get_or_create(
                    enriched_note_block=block,
                    defaults={
                        "source_refs": [],
                        "verification_status": CitationBlock.VerificationStatus.SUPPORTED,
                        "verification_score": 0.85,
                        "verifier_version": "verifier:v1",
                    },
                )

    def _seed_tags(self, subjects):
        for subject in subjects:
            hierarchies = TAG_HIERARCHIES.get(subject.name, [])
            for unit_key, topics in hierarchies:
                unit_tag, _ = Tag.objects.get_or_create(
                    subject=subject,
                    stable_key=unit_key,
                    defaults={"display_name": unit_key.replace("-", " ").title()},
                )
                for topic in topics:
                    Tag.objects.get_or_create(
                        subject=subject,
                        stable_key=f"{unit_key}:{topic}",
                        defaults={
                            "display_name": topic.replace("-", " ").title(),
                            "parent": unit_tag,
                        },
                     )

    def _seed_document_tags(self, docs):
        for doc in docs:
            tags = list(Tag.objects.filter(subject=doc.subject))
            if not tags:
                continue
            for tag in random.sample(tags, min(2, len(tags))):
                DocumentTag.objects.get_or_create(document=doc, tag=tag)

    def _seed_questions(self, subjects, chunks):
        difficulties = list(Question.Difficulty.choices)
        for subject in subjects:
            subject_chunks = [c for c in chunks if c.subject_id == subject.id]
            tags = list(Tag.objects.filter(subject=subject))
            for i in range(5):
                chunk = random.choice(subject_chunks)
                question, _ = Question.objects.get_or_create(
                    document=chunk.document,
                    source_revision_id=chunk.revision_id,
                    source_chunk_id=chunk.id,
                    content_hash=sha256(f"q:{subject.name}:{i}"),
                    question_key=f"q{i}",
                    defaults={
                        "difficulty": random.choice(difficulties)[0],
                        "prompt": f"Sample question {i + 1} for {subject.name}?",
                        "options": ["Option A", "Option B", "Option C", "Option D"],
                        "answer_index": 0,
                        "generation_model": "mock-gpt",
                        "prompt_version": "question_generation:v1",
                        "stale": False,
                    },
                )
                if tags:
                    tag = random.choice(tags)
                    QuestionTagLink.objects.get_or_create(question=question, tag=tag)

    def _seed_tests(self, subjects):
        for subject in subjects:
            test, _ = TestInstance.objects.get_or_create(
                profile=subject.profile,
                subject=subject,
                title=f"{subject.name} Practice Test",
                type=TestInstance.Type.PRACTICE,
            )
            questions = list(Question.objects.filter(document__subject=subject)[:5])
            for idx, question in enumerate(questions):
                TestQuestion.objects.get_or_create(
                    test=test,
                    question=question,
                    defaults={"order": idx},
                )
            for idx, question in enumerate(questions):
                TestAttempt.objects.get_or_create(
                    test=test,
                    question=question,
                    defaults={
                        "selected_index": 0,
                        "correct": True,
                        "confidence": 0.8,
                    },
                )
            for tag in Tag.objects.filter(subject=subject)[:2]:
                MasteryScore.objects.get_or_create(
                    profile=subject.profile,
                    subject=subject,
                    tag=tag,
                    defaults={"mastery": 0.75, "attempt_count": 3, "correct_count": 2},
                )

    def _seed_chat_sessions(self, profile, subjects):
        for subject in subjects:
            session, _ = ChatSession.objects.get_or_create(
                profile=profile,
                subject=subject,
                title=f"{subject.name} chat",
            )
            ChatMessage.objects.get_or_create(
                session=session,
                role=ChatMessage.Role.USER,
                content=f"What is {subject.name} about?",
                defaults={"model": "mock-gpt", "prompt_version": "chat:v1"},
            )
            ChatMessage.objects.get_or_create(
                session=session,
                role=ChatMessage.Role.ASSISTANT,
                content=f"{subject.name} is a fascinating subject with many core concepts.",
                defaults={
                    "citations": [],
                    "model": "mock-gpt",
                    "prompt_version": "chat:v1",
                },
            )
        module_session, _ = ChatSession.objects.get_or_create(
            profile=profile,
            subject=None,
            title="AI Classroom chat",
        )
        ChatMessage.objects.get_or_create(
            session=module_session,
            role=ChatMessage.Role.USER,
            content="Summarize my study material across all subjects.",
            defaults={"model": "mock-gpt", "prompt_version": "chat:v1"},
        )
        ChatMessage.objects.get_or_create(
            session=module_session,
            role=ChatMessage.Role.ASSISTANT,
            content="You have notes across Mathematics, Physics, and Computer Science.",
            defaults={
                "citations": [],
                "model": "mock-gpt",
                "prompt_version": "chat:v1",
            },
        )

"""Adaptive test graph nodes."""
import logging
from django.db import transaction

from ai.langgraph.state.adaptive_test_state import AdaptiveTestState
from ai.tracing.decorators import traced_node
from apps.profiles.models import Profile
from apps.revision.services import RevisionPlanningService
from apps.retrieval.retrieval import RetrievalService
from apps.questions.services import QuestionGenerationService
from apps.tests.services import TestGenerationService
from apps.tests.models import TestInstance, TestQuestion
from apps.documents.models import Document

logger = logging.getLogger(__name__)


@traced_node("studyai.adaptive_test.mastery", feature="adaptive_test")
def get_mastery_node(state: AdaptiveTestState, config=None) -> dict:
    profile = Profile.objects.get(pk=state["profile_id"])
    overview = RevisionPlanningService.overview(profile)
    return {"mastery_overview": overview}


@traced_node("studyai.adaptive_test.identify_weak", feature="adaptive_test")
def identify_weak_topics_node(state: AdaptiveTestState, config=None) -> dict:
    overview = state.get("mastery_overview", {})
    all_tags = overview.get("tags", [])
    subject_id = state.get("subject_id")
    focus_weak_only = state.get("focus_weak_only", True)

    weak_tags = [
        tag for tag in all_tags
        if tag["status"] in ("weak", "not_assessed")
        and (not subject_id or tag.get("subject_id") == subject_id or not tag.get("subject_id"))
    ]

    if not weak_tags and focus_weak_only:
        weak_tags = [tag for tag in all_tags if tag["status"] != "not_assessed"]

    if not weak_tags:
        raise ValueError("No topics available for test generation. Please add some notes first.")

    return {
        "weak_tags": weak_tags,
        "all_tags": all_tags,
    }


@traced_node("studyai.adaptive_test.retrieve", feature="adaptive_test")
def retrieve_notes_node(state: AdaptiveTestState, config=None) -> dict:
    from django.conf import settings
    from apps.accounts.models import User

    weak_tags = state.get("weak_tags", [])
    profile = Profile.objects.get(pk=state["profile_id"])
    user = profile.user

    all_document_ids = set()
    for tag in weak_tags:
        evidence = RetrievalService.search(
            user=user,
            query=tag["stable_key"],
            subject_id=state.get("subject_id"),
            top_k=5,
            include_reference=False,
        )
        for e in evidence:
            all_document_ids.add(str(e.document_id))

    if not all_document_ids:
        raise ValueError("No relevant notes found for weak topics.")

    return {"retrieved_document_ids": list(all_document_ids)[:5]}


@traced_node("studyai.adaptive_test.generate", feature="adaptive_test")
def generate_questions_node(state: AdaptiveTestState, config=None) -> dict:
    profile = Profile.objects.get(pk=state["profile_id"])
    doc_ids = state.get("retrieved_document_ids", [])
    num_questions = state.get("num_questions", 10)
    all_questions = []

    per_doc = max(1, num_questions // len(doc_ids) + 1) if doc_ids else num_questions

    for doc_id in doc_ids:
        try:
            document = Document.objects.get(pk=doc_id, profile=profile)
            questions = QuestionGenerationService.generate_for_document(document, max_questions=per_doc)
            for q in questions:
                all_questions.append({
                    "id": str(q.pk),
                    "prompt": q.prompt,
                    "options": q.options,
                    "answer_index": q.answer_index,
                    "difficulty": q.difficulty,
                    "source_chunk_id": str(q.source_chunk_id),
                })
        except Document.DoesNotExist:
            continue

    if not all_questions:
        raise ValueError("Could not generate questions from available notes.")

    return {"generated_questions": all_questions}


@traced_node("studyai.adaptive_test.select", feature="adaptive_test")
def select_questions_node(state: AdaptiveTestState, config=None) -> dict:
    difficulty = state.get("difficulty")
    questions = state.get("generated_questions", [])
    num_questions = state.get("num_questions", 10)

    filtered = questions
    if difficulty:
        filtered = [q for q in questions if q["difficulty"] == difficulty]

    if len(filtered) < num_questions:
        filtered = questions

    selected = filtered[:num_questions]
    return {"selected_questions": selected}


@traced_node("studyai.adaptive_test.create_test", feature="adaptive_test")
def create_test_node(state: AdaptiveTestState, config=None) -> dict:
    profile = Profile.objects.get(pk=state["profile_id"])
    subject = None
    if state.get("subject_id"):
        from apps.subjects.models import Subject
        try:
            subject = Subject.objects.get(pk=state["subject_id"], profile=profile)
        except (Subject.DoesNotExist, ValueError, TypeError):
            subject = None

    selected = state.get("selected_questions", [])

    with transaction.atomic():
        test = TestInstance.objects.create(
            profile=profile,
            subject=subject,
            type=TestInstance.Type.PRACTICE,
        )
        for order, q in enumerate(selected, start=1):
            TestQuestion.objects.create(test=test, question_id=q["id"], order=order)

    return {"test_id": str(test.pk)}


@traced_node("studyai.adaptive_test.format", feature="adaptive_test")
def format_output_node(state: AdaptiveTestState, config=None) -> dict:
    selected = state.get("selected_questions", [])
    weak_topic_names = [tag["display_name"] for tag in state.get("weak_tags", [])]

    return {
        "test_id": state.get("test_id"),
        "selected_questions": selected,
        "weak_topics_used": weak_topic_names,
        "total_questions_generated": len(selected),
    }

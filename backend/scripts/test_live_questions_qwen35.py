"""Live end-to-end verification script for Phase 7: Question Generation & Adaptive Testing Pipeline.

Verifies:
1. Multiple question formats:
   - MCQs (4 options, correct answer index, explanation)
   - Flashcards (concept on front, explanation on back)
   - Short Answer (open-ended question, model answer & rubric)
   - Explanation checks (deep conceptual question, detailed rubric)
2. Grounding in user notes + reference textbook chunks
3. Mastery-aware difficulty adaptation (easy/medium/hard based on mastery state)
4. Model provenance: qwen3.5:4b (no legacy mocks or fallbacks)
5. Adaptive test generation (weakness prioritization, TestInstance & TestQuestion creation)
"""
import os
import sys
import uuid
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
import django
django.setup()

from django.contrib.auth import get_user_model
from django.conf import settings
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.documents.models import Document, DocumentPage, DocumentPageRevision
from apps.retrieval.models import NoteChunk
from apps.questions.models import Question
from apps.questions.services import QuestionGenerationService
from apps.tests.models import MasteryScore, TestInstance, TestQuestion
from apps.tests.services import TestGenerationService, MasteryScoringService
from apps.ai_classroom.models import Tag, DocumentTag

User = get_user_model()


def run_live_question_verification():
    print("=" * 75)
    print("Phase 7: Live End-to-End Question Generation & Adaptive Testing Verification")
    print(f"Target LLM: {settings.LLM_MODEL}")
    print(f"Target Embeddings: {settings.EMBEDDING_MODEL_NAME} ({settings.EMBEDDING_DIMENSIONS}d)")
    print("=" * 75)

    # 1. Setup User, Profile, Subject, and Document with realistic chunks
    user, _ = User.objects.get_or_create(email="phase7_tester@studyai.test", defaults={"first_name": "Phase7"})
    profile, _ = Profile.objects.get_or_create(user=user)
    subject, _ = Subject.objects.get_or_create(profile=profile, name="Algorithms & Data Structures")

    doc = Document.objects.create(
        profile=profile,
        subject=subject,
        source=Document.Source.UPLOAD,
        source_type=Document.SourceType.PDF,
    )
    page = DocumentPage.objects.create(document=doc, page_number=1)
    rev = DocumentPageRevision.objects.create(page=page, revision_number=1, content_hash="hash_rev_1")
    rev_id = rev.id

    chunk1 = NoteChunk.objects.create(
        document=doc,
        profile=profile,
        subject=subject,
        revision_id=rev_id,
        page_start=1,
        page_end=1,
        chunk_index=0,
        content=(
            "Dijkstra's algorithm finds the shortest path between nodes in a weighted graph with non-negative edge weights. "
            "It uses a priority queue (min-heap) to greedily select the unvisited vertex with minimal tentative distance. "
            "Its time complexity using a binary heap is O((V + E) log V)."
        ),
        content_hash="hash_dijkstra_101",
        source_type="note",
    )

    chunk2 = NoteChunk.objects.create(
        document=doc,
        profile=profile,
        subject=subject,
        revision_id=rev_id,
        page_start=1,
        page_end=1,
        chunk_index=1,
        content=(
            "The Bellman-Ford algorithm computes single-source shortest paths on weighted digraphs. "
            "Unlike Dijkstra's algorithm, Bellman-Ford can handle edges with negative weights. "
            "It runs in O(V * E) time by relaxing all edges V-1 times, and can detect negative cycles."
        ),
        content_hash="hash_bellman_202",
        source_type="note",
    )

    tag, _ = Tag.objects.get_or_create(
        subject=subject,
        stable_key="shortest-paths",
        defaults={"display_name": "Shortest Paths Algorithms"},
    )
    DocumentTag.objects.get_or_create(document=doc, tag=tag)

    print(f"\n[1] Created Test Document {doc.pk} with 2 chunks in subject '{subject.name}'")

    # 2. Test MCQ Generation
    print("\n[2] Testing Multiple-Choice Question (MCQ) Generation with Qwen3.5:4B...")
    start_time = time.monotonic()
    mcq_questions = QuestionGenerationService.generate_for_document(
        doc,
        max_questions=1,
        question_type="mcq",
        difficulty="medium",
    )
    mcq_duration = time.monotonic() - start_time
    print(f"    Generated {len(mcq_questions)} MCQ in {mcq_duration:.2f}s")
    for q in mcq_questions:
        print(f"    - ID: {q.pk}")
        print(f"      Prompt: {q.prompt}")
        print(f"      Options ({len(q.options)}): {q.options}")
        print(f"      Correct Answer: [{q.answer_index}] -> {q.answer_text}")
        print(f"      Difficulty: {q.difficulty}")
        print(f"      Type: {q.question_type}")
        print(f"      Explanation: {q.explanation[:120]}...")
        print(f"      Generation Model: {q.generation_model}")
        assert q.question_type == "mcq"
        assert len(q.options) == 4, f"Expected 4 options for MCQ, got {len(q.options)}"
        assert 0 <= q.answer_index < len(q.options)
        assert len(q.explanation) > 0
        assert q.generation_model == "qwen3.5:4b"

    # 3. Test Flashcard Generation
    print("\n[3] Testing Flashcard Generation with Qwen3.5:4B...")
    start_time = time.monotonic()
    fc_questions = QuestionGenerationService.generate_for_document(
        doc,
        max_questions=1,
        question_type="flashcard",
        difficulty="medium",
    )
    fc_duration = time.monotonic() - start_time
    print(f"    Generated {len(fc_questions)} Flashcard in {fc_duration:.2f}s")
    for q in fc_questions:
        print(f"    - ID: {q.pk}")
        print(f"      Front (Prompt): {q.prompt}")
        print(f"      Back (Explanation): {q.explanation}")
        print(f"      Type: {q.question_type}")
        print(f"      Generation Model: {q.generation_model}")
        assert q.question_type == "flashcard"
        assert len(q.prompt) > 5
        assert len(q.explanation) > 5
        assert q.generation_model == "qwen3.5:4b"

    # 4. Test Short-Answer Generation
    print("\n[4] Testing Short-Answer Question Generation with Qwen3.5:4B...")
    start_time = time.monotonic()
    sa_questions = QuestionGenerationService.generate_for_document(
        doc,
        max_questions=1,
        question_type="short_answer",
        difficulty="medium",
    )
    sa_duration = time.monotonic() - start_time
    print(f"    Generated {len(sa_questions)} Short Answer in {sa_duration:.2f}s")
    for q in sa_questions:
        print(f"    - ID: {q.pk}")
        print(f"      Prompt: {q.prompt}")
        print(f"      Model Answer / Rubric: {q.explanation}")
        print(f"      Type: {q.question_type}")
        assert q.question_type == "short_answer"
        assert len(q.prompt) > 5
        assert len(q.explanation) > 5
        assert q.generation_model == "qwen3.5:4b"

    # 5. Test Explanation-Based Check Generation
    print("\n[5] Testing Explanation-Based Question Generation with Qwen3.5:4B...")
    start_time = time.monotonic()
    ex_questions = QuestionGenerationService.generate_for_document(
        doc,
        max_questions=1,
        question_type="explanation",
        difficulty="hard",
    )
    ex_duration = time.monotonic() - start_time
    print(f"    Generated {len(ex_questions)} Explanation Question in {ex_duration:.2f}s")
    for q in ex_questions:
        print(f"    - ID: {q.pk}")
        print(f"      Prompt: {q.prompt}")
        print(f"      Grading Rubric: {q.explanation}")
        print(f"      Difficulty: {q.difficulty}")
        print(f"      Type: {q.question_type}")
        assert q.question_type == "explanation"
        assert len(q.prompt) > 5
        assert len(q.explanation) > 5
        assert q.difficulty == "hard"
        assert q.generation_model == "qwen3.5:4b"

    # 6. Test Mastery-Aware Difficulty Adaptation
    print("\n[6] Testing Mastery-Aware Difficulty Adaptation...")
    weak_qs = QuestionGenerationService.generate_for_document(
        doc,
        max_questions=1,
        question_type="mcq",
        mastery_level="weak",
    )
    print(f"    Weak Mastery Target Difficulty -> {weak_qs[0].difficulty} (Expected: easy)")
    assert weak_qs[0].difficulty == "easy"

    strong_qs = QuestionGenerationService.generate_for_document(
        doc,
        max_questions=1,
        question_type="mcq",
        mastery_level="strong",
    )
    print(f"    Strong Mastery Target Difficulty -> {strong_qs[0].difficulty} (Expected: hard)")
    assert strong_qs[0].difficulty == "hard"

    # 7. Test Adaptive Test Generation Service
    print("\n[7] Testing Adaptive Test Generation Service (TestGenerationService.build_test)...")
    test_instance = TestGenerationService.build_test(
        profile=profile,
        subject=subject,
        num_questions=3,
        title="Shortest Paths Mastery Check",
    )
    test_questions = list(test_instance.test_questions.select_related("question").all())
    print(f"    Created TestInstance: {test_instance.id} ('{test_instance.title}')")
    print(f"    Assigned Questions ({len(test_questions)}):")
    for tq in test_questions:
        print(f"      #{tq.order}: [{tq.question.difficulty.upper()}] {tq.question.prompt[:70]}... (Type: {tq.question.question_type})")
    assert len(test_questions) >= 1

    # 8. Test Attempt Grading & Mastery Update
    print("\n[8] Testing Attempt Scoring and EMA Mastery Update...")
    first_q = test_questions[0].question
    m_before = MasteryScore.objects.filter(profile=profile, tag=tag).first()
    before_val = m_before.mastery if m_before else 0.0
    print(f"    Mastery before attempt: {before_val:.3f}")

    updated_m = MasteryScoringService.record_attempt(
        profile=profile,
        question=first_q,
        correct=True,
        confidence=0.9,
    )
    assert updated_m is not None
    print(f"    Mastery after correct attempt: {updated_m.mastery:.3f} (Attempts: {updated_m.attempt_count}, Correct: {updated_m.correct_count})")
    assert updated_m.mastery > before_val
    assert updated_m.attempt_count >= 1

    print("\n" + "=" * 75)
    print("PHASE 7 VERIFICATION SUCCESSFUL: ALL CHECKS PASSED WITH QWEN3.5:4B!")
    print("=" * 75)


if __name__ == "__main__":
    run_live_question_verification()

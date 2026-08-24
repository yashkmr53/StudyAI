"""Learning Tools (Phase 1 & 2).

Wraps existing mastery, revision, and question services for agent use.
"""
from typing import Optional
from pydantic import Field

from django.db import transaction
from django.conf import settings

from apps.agents.tools.base import ToolInput, ToolOutput, ToolMetadata, BaseTool
from shared.exceptions import ValidationError


class MasteryTag(ToolOutput):
    tag_id: str
    stable_key: str
    display_name: str
    status: str
    mastery: Optional[float] = None
    attempt_count: int = 0
    last_assessed_at: Optional[str] = None


class GetMasteryInput(ToolInput):
    subject_id: Optional[str] = Field(None, description="Optional subject UUID to filter tags")


class GetMasteryOutput(ToolOutput):
    tags: list[MasteryTag]
    assessed_count: int
    not_assessed_count: int


class GetMasteryTool(BaseTool):
    metadata = ToolMetadata(
        name="get_mastery",
        description="Get mastery overview for the user's learning tags. Returns per-tag mastery scores (0-1), status (weak/fair/strong/not_assessed), and attempt counts. Use to identify weak topics for targeted practice.",
        input_schema=GetMasteryInput,
        output_schema=GetMasteryOutput,
        requires_auth=True,
        timeout_seconds=10,
        category="learning",
    )

    def _execute(self, input: GetMasteryInput, *, user, request_id: str) -> GetMasteryOutput:
        from apps.profiles.models import Profile
        from apps.revision.services import RevisionPlanningService

        profile = Profile.objects.get(user=user)

        if input.subject_id:
            from apps.subjects.models import Subject
            try:
                subject = Subject.objects.get(pk=input.subject_id, profile=profile)
            except (Subject.DoesNotExist, ValueError, TypeError):
                subject = None
        else:
            subject = None

        overview = RevisionPlanningService.overview(profile)

        tags = [
            MasteryTag(
                tag_id=tag["tag_id"],
                stable_key=tag["stable_key"],
                display_name=tag["display_name"],
                status=tag["status"],
                mastery=tag["mastery"],
                attempt_count=tag["attempt_count"],
                last_assessed_at=tag["last_assessed_at"].isoformat() if tag["last_assessed_at"] else None,
            )
            for tag in overview["tags"]
        ]

        return GetMasteryOutput(
            tags=tags,
            assessed_count=overview["assessed_count"],
            not_assessed_count=overview["not_assessed_count"],
        )


class RevisionPlanInput(ToolInput):
    subject_id: Optional[str] = Field(None, description="Optional subject UUID")
    target_date: str = Field(..., description="Target date (ISO format: YYYY-MM-DD)")


class PriorityTag(ToolOutput):
    tag_id: str
    display_name: str
    status: str
    priority: float


class DailySchedule(ToolOutput):
    date: str
    focus: list[str]


class RevisionPlanOutput(ToolOutput):
    target_date: str
    days_left: int
    priorities: list[PriorityTag]
    schedule: list[DailySchedule]


class GetRevisionPlanTool(BaseTool):
    metadata = ToolMetadata(
        name="get_revision_plan",
        description="Generate a deterministic daily revision plan until a target date. Prioritizes weak topics, upcoming assessments, and recent failures. Returns prioritized tags and a day-by-day schedule.",
        input_schema=RevisionPlanInput,
        output_schema=RevisionPlanOutput,
        requires_auth=True,
        timeout_seconds=10,
        category="learning",
    )

    def _execute(self, input: RevisionPlanInput, *, user, request_id: str) -> RevisionPlanOutput:
        from apps.profiles.models import Profile
        from apps.revision.services import RevisionPlanningService
        from datetime import date

        profile = Profile.objects.get(user=user)

        subject = None
        if input.subject_id:
            from apps.subjects.models import Subject
            try:
                subject = Subject.objects.get(pk=input.subject_id, profile=profile)
            except (Subject.DoesNotExist, ValueError, TypeError):
                subject = None

        target_date = date.fromisoformat(input.target_date)
        plan = RevisionPlanningService.build_plan(profile, subject, target_date)

        priorities = [
            PriorityTag(
                tag_id=p["tag_id"],
                display_name=p["display_name"],
                status=p["status"],
                priority=p["priority"],
            )
            for p in plan["priorities"]
        ]

        schedule = [
            DailySchedule(date=s["date"], focus=s["focus"])
            for s in plan["schedule"]
        ]

        return RevisionPlanOutput(
            target_date=plan["target_date"],
            days_left=plan["days_left"],
            priorities=priorities,
            schedule=schedule,
        )


class PreviousQuestion(ToolOutput):
    question_id: str
    prompt: str
    options: list[str]
    answer_index: int
    difficulty: str
    tags: list[str]
    source_chunk_id: str


class GetPreviousQuestionsInput(ToolInput):
    subject_id: Optional[str] = Field(None, description="Optional subject UUID")
    tag_id: Optional[str] = Field(None, description="Optional tag UUID to filter by concept")
    limit: int = Field(20, ge=1, le=50, description="Maximum questions to return")


class GetPreviousQuestionsOutput(ToolOutput):
    questions: list[PreviousQuestion]


class GetPreviousQuestionsTool(BaseTool):
    metadata = ToolMetadata(
        name="get_previous_questions",
        description="Retrieve previously generated questions for the user's documents. Can filter by subject or concept tag. Use to avoid duplicates or review past questions.",
        input_schema=GetPreviousQuestionsInput,
        output_schema=GetPreviousQuestionsOutput,
        requires_auth=True,
        timeout_seconds=10,
        category="learning",
    )

    def _execute(self, input: GetPreviousQuestionsInput, *, user, request_id: str) -> GetPreviousQuestionsOutput:
        from apps.profiles.models import Profile
        from apps.questions.models import Question, QuestionTagLink
        from apps.ai_classroom.models import Tag

        profile = Profile.objects.get(user=user)

        qs = Question.objects.filter(
            document__profile=profile,
            stale=False
        ).select_related("document", "document__subject")

        if input.subject_id:
            qs = qs.filter(document__subject_id=input.subject_id)

        if input.tag_id:
            qs = qs.filter(tag_link__tag_id=input.tag_id)

        questions = qs.order_by("-created_at")[:input.limit]

        result = []
        for q in questions:
            tags = []
            if hasattr(q, "tag_link") and q.tag_link and q.tag_link.tag:
                tags.append(q.tag_link.tag.stable_key)

            result.append(PreviousQuestion(
                question_id=str(q.pk),
                prompt=q.prompt,
                options=q.options,
                answer_index=q.answer_index,
                difficulty=q.difficulty,
                tags=tags,
                source_chunk_id=str(q.source_chunk_id),
            ))

        return GetPreviousQuestionsOutput(questions=result)


class GeneratedQuestion(ToolOutput):
    question_id: str
    prompt: str
    options: list[str]
    answer_index: int
    difficulty: str
    source_chunk_id: str


class GenerateQuestionsInput(ToolInput):
    document_id: str = Field(..., description="Document UUID to generate questions from")
    count: int = Field(5, ge=1, le=20, description="Number of questions to generate")
    difficulty: Optional[str] = Field(None, description="Target difficulty: easy, medium, hard")
    focus_weak_topics: bool = Field(False, description="If true, prioritize chunks related to weak mastery tags")


class GenerateQuestionsOutput(ToolOutput):
    questions: list[GeneratedQuestion]
    test_id: Optional[str] = None


class GenerateQuestionsTool(BaseTool):
    metadata = ToolMetadata(
        name="generate_questions",
        description="Generate new MCQs from a specific document. Questions are grounded in document chunks, bound to source revision, and persisted. Optionally create a test instance.",
        input_schema=GenerateQuestionsInput,
        output_schema=GenerateQuestionsOutput,
        requires_auth=True,
        timeout_seconds=60,
        category="learning",
    )

    def _execute(self, input: GenerateQuestionsInput, *, user, request_id: str) -> GenerateQuestionsOutput:
        from apps.profiles.models import Profile
        from apps.documents.models import Document
        from apps.questions.services import QuestionGenerationService
        from apps.tests.services import TestGenerationService
        from apps.tests.models import TestInstance

        profile = Profile.objects.get(user=user)

        try:
            document = Document.objects.get(pk=input.document_id, profile=profile)
        except (Document.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Document not found or access denied")

        questions = QuestionGenerationService.generate_for_document(document, max_questions=input.count)

        result = []
        for q in questions:
            result.append(GeneratedQuestion(
                question_id=str(q.pk),
                prompt=q.prompt,
                options=q.options,
                answer_index=q.answer_index,
                difficulty=q.difficulty,
                source_chunk_id=str(q.source_chunk_id),
            ))

        return GenerateQuestionsOutput(questions=result, test_id=None)


class TestQuestionRef(ToolOutput):
    question_id: str
    order: int


class CreateTestInput(ToolInput):
    subject_id: Optional[str] = Field(None, description="Optional subject UUID")
    num_questions: int = Field(10, ge=1, le=50, description="Number of questions in test")
    test_type: str = Field("practice", description="Test type: practice or mock")


class CreateTestOutput(ToolOutput):
    test_id: str
    questions: list[TestQuestionRef]


class CreateTestTool(BaseTool):
    metadata = ToolMetadata(
        name="create_test",
        description="Create an adaptive test instance for the user. Questions are selected based on mastery (weak topics first), recency, and difficulty matching. Returns test ID and question list.",
        input_schema=CreateTestInput,
        output_schema=CreateTestOutput,
        requires_auth=True,
        timeout_seconds=30,
        category="learning",
    )

    def _execute(self, input: CreateTestInput, *, user, request_id: str) -> CreateTestOutput:
        from apps.profiles.models import Profile
        from apps.tests.services import TestGenerationService
        from apps.tests.models import TestInstance, TestQuestion

        profile = Profile.objects.get(user=user)

        subject = None
        if input.subject_id:
            from apps.subjects.models import Subject
            try:
                subject = Subject.objects.get(pk=input.subject_id, profile=profile)
            except (Subject.DoesNotExist, ValueError, TypeError):
                subject = None

        test = TestGenerationService.build_test(
            profile,
            subject=subject,
            num_questions=input.num_questions,
            type_=TestInstance.Type.PRACTICE if input.test_type == "practice" else TestInstance.Type.MOCK,
        )

        test_questions = TestQuestion.objects.filter(test=test).select_related("question").order_by("order")

        questions = [
            TestQuestionRef(question_id=str(tq.question_id), order=tq.order)
            for tq in test_questions
        ]

        return CreateTestOutput(test_id=str(test.pk), questions=questions)


class MasteryAwareTestInput(ToolInput):
    subject_id: Optional[str] = Field(None, description="Optional subject UUID to scope the test")
    num_questions: int = Field(10, ge=1, le=50, description="Number of questions to generate")
    difficulty: Optional[str] = Field("hard", description="Target difficulty: easy, medium, hard")
    focus_weak_only: bool = Field(True, description="If true, only generate questions for weak mastery topics")


class MasteryAwareTestOutput(ToolOutput):
    test_id: str
    questions: list[TestQuestionRef]
    weak_topics_used: list[str]
    total_questions_generated: int


class MasteryAwareTestGenerationTool(BaseTool):
    """
    Mastery-aware test generation workflow.
    
    This tool encapsulates the full workflow:
    1. Get mastery overview to identify weak topics
    2. Search notes for content related to weak topics
    3. Generate questions from that content
    4. Create a test instance with those questions
    
    Use this when user asks for "create test on my weak topics" or similar.
    """
    metadata = ToolMetadata(
        name="mastery_aware_test_generation",
        description="Generate a practice test focused on the user's weak mastery topics. Automatically identifies weak areas, retrieves relevant notes, generates targeted questions, and creates a test instance. Use for requests like 'create 10 hard questions from my weak topics'.",
        input_schema=MasteryAwareTestInput,
        output_schema=MasteryAwareTestOutput,
        requires_auth=True,
        timeout_seconds=120,
        category="learning",
    )

    def _execute(self, input: MasteryAwareTestInput, *, user, request_id: str) -> MasteryAwareTestOutput:
        from apps.profiles.models import Profile
        from ai.langgraph.graphs.adaptive_test_graph import invoke_adaptive_test_graph
        from ai.langgraph.state.adaptive_test_state import AdaptiveTestState

        profile = Profile.objects.get(user=user)

        initial_state = AdaptiveTestState(
            profile_id=str(profile.pk),
            subject_id=input.subject_id,
            num_questions=input.num_questions,
            difficulty=input.difficulty,
            focus_weak_only=input.focus_weak_only,
            mastery_overview={},
            weak_tags=[],
            all_tags=[],
            retrieved_document_ids=[],
            generated_questions=[],
            selected_questions=[],
            test_id=None,
            errors=[],
            execution_metadata={},
        )

        final_state = invoke_adaptive_test_graph(initial_state)

        selected = final_state.get("selected_questions", [])
        question_refs = [
            TestQuestionRef(question_id=q["id"], order=i + 1)
            for i, q in enumerate(selected)
        ]

        return MasteryAwareTestOutput(
            test_id=final_state.get("test_id", ""),
            questions=question_refs,
            weak_topics_used=final_state.get("weak_topics_used", []),
            total_questions_generated=len(selected),
        )


# Auto-register tools on module import
from apps.agents.tools import get_tool_registry
get_tool_registry().register(GetMasteryTool())
get_tool_registry().register(GetRevisionPlanTool())
get_tool_registry().register(GetPreviousQuestionsTool())
get_tool_registry().register(GenerateQuestionsTool())
get_tool_registry().register(CreateTestTool())
get_tool_registry().register(MasteryAwareTestGenerationTool())
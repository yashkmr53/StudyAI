"""Question and Tag evaluation harnesses for StudyAI enrichment pipeline."""

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.questions.models import Question, QuestionTagLink
from apps.ai_classroom.models import Tag, DocumentTag
from apps.documents.models import Document

User = get_user_model()


@dataclass
class QuestionQualityResult:
    case_id: str
    question_id: str
    prompt: str
    options: List[str]
    answer_index: int
    difficulty: str
    source_chunk_id: str
    relevance: float  # 0-1
    connection: float  # 0-1
    non_trivial: float  # 0-1
    appropriate_difficulty: float  # 0-1
    answerable: float  # 0-1
    good_distractors: float  # 0-1
    overall_score: float
    notes: str


@dataclass
class QuestionAggregateMetrics:
    total_questions: int
    avg_relevance: float
    avg_connection: float
    avg_non_trivial: float
    avg_appropriate_difficulty: float
    avg_answerable: float
    avg_good_distractors: float
    avg_overall: float
    by_difficulty: Dict[str, Dict[str, float]]
    duplicate_questions: int
    trivial_questions: int


class QuestionEvaluator:
    def __init__(self):
        pass

    def evaluate_questions(self, case: Dict[str, Any], document: Document) -> tuple[List[QuestionQualityResult], QuestionAggregateMetrics]:
        questions = Question.objects.filter(document=document).order_by("created_at")
        expected = case.get("expected_question_characteristics", {})
        expected_topics = expected.get("topics", [])
        min_questions = expected.get("min_questions", 1)
        difficulty_range = expected.get("difficulty_range", ["easy", "medium"])

        results = []
        seen_prompts = set()
        duplicate_count = 0
        trivial_count = 0

        for q in questions:
            # Heuristic evaluation (manual labels would be better)
            relevance = self._score_relevance(q, expected_topics, document)
            connection = self._score_connection(q, document)
            non_trivial = self._score_non_trivial(q)
            appropriate_difficulty = self._score_difficulty(q, difficulty_range)
            answerable = self._score_answerable(q)
            good_distractors = self._score_distractors(q)

            overall = (relevance + connection + non_trivial + appropriate_difficulty + answerable + good_distractors) / 6

            # Check duplicates
            prompt_key = q.prompt.lower().strip()
            if prompt_key in seen_prompts:
                duplicate_count += 1
            seen_prompts.add(prompt_key)

            # Check trivial
            if non_trivial < 0.3:
                trivial_count += 1

            results.append(QuestionQualityResult(
                case_id=case["case_id"],
                question_id=str(q.pk),
                prompt=q.prompt,
                options=q.options,
                answer_index=q.answer_index,
                difficulty=q.difficulty,
                source_chunk_id=str(q.source_chunk_id) if q.source_chunk_id else "",
                relevance=round(relevance, 2),
                connection=round(connection, 2),
                non_trivial=round(non_trivial, 2),
                appropriate_difficulty=round(appropriate_difficulty, 2),
                answerable=round(answerable, 2),
                good_distractors=round(good_distractors, 2),
                overall_score=round(overall, 2),
                notes="",
            ))

        # Aggregate
        n = len(results)
        if n > 0:
            aggregate = QuestionAggregateMetrics(
                total_questions=n,
                avg_relevance=round(sum(r.relevance for r in results) / n, 4),
                avg_connection=round(sum(r.connection for r in results) / n, 4),
                avg_non_trivial=round(sum(r.non_trivial for r in results) / n, 4),
                avg_appropriate_difficulty=round(sum(r.appropriate_difficulty for r in results) / n, 4),
                avg_answerable=round(sum(r.answerable for r in results) / n, 4),
                avg_good_distractors=round(sum(r.good_distractors for r in results) / n, 4),
                avg_overall=round(sum(r.overall_score for r in results) / n, 4),
                by_difficulty=self._by_difficulty(results),
                duplicate_questions=duplicate_count,
                trivial_questions=trivial_count,
            )
        else:
            aggregate = QuestionAggregateMetrics(
                total_questions=0,
                avg_relevance=0.0, avg_connection=0.0, avg_non_trivial=0.0,
                avg_appropriate_difficulty=0.0, avg_answerable=0.0,
                avg_good_distractors=0.0, avg_overall=0.0,
                by_difficulty={}, duplicate_questions=0, trivial_questions=0,
            )

        return results, aggregate

    def _score_relevance(self, question: Question, expected_topics: List[str], document: Document) -> float:
        prompt_lower = question.prompt.lower()
        if not expected_topics:
            return 0.5  # No ground truth, neutral score
        
        matches = sum(1 for topic in expected_topics if topic.lower() in prompt_lower)
        return matches / max(1, len(expected_topics))

    def _score_connection(self, question: Question, document: Document) -> float:
        if not question.source_chunk_id:
            return 0.0
        try:
            chunk = document.chunks.get(pk=question.source_chunk_id)
            # Check if question keywords appear in chunk
            q_words = set(question.prompt.lower().split())
            c_words = set(chunk.content.lower().split())
            overlap = len(q_words & c_words) / max(1, len(q_words))
            return overlap
        except Exception:
            return 0.0

    def _score_non_trivial(self, question: Question) -> float:
        prompt = question.prompt.lower()
        # Penalize definition-only questions
        trivial_patterns = ["what is", "define", "definition of", "meaning of"]
        if any(p in prompt for p in trivial_patterns):
            if len(prompt.split()) < 10:
                return 0.2
            return 0.5
        # Reward questions asking for explanation, comparison, application
        deep_patterns = ["why", "how", "compare", "difference", "explain", "apply", "example"]
        if any(p in prompt for p in deep_patterns):
            return 1.0
        return 0.5

    def _score_difficulty(self, question: Question, expected_range: List[str]) -> float:
        if question.difficulty in expected_range:
            return 1.0
        # Partial credit for adjacent difficulties
        diff_order = ["easy", "medium", "hard"]
        try:
            exp_idx = [diff_order.index(d) for d in expected_range]
            q_idx = diff_order.index(question.difficulty)
            if q_idx in exp_idx:
                return 1.0
            return 0.5 if min(abs(q_idx - e) for e in exp_idx) == 1 else 0.0
        except ValueError:
            return 0.5

    def _score_answerable(self, question: Question) -> float:
        if not question.source_chunk_id:
            return 0.0
        # Check if answer is in options and makes sense
        try:
            answer = question.options[question.answer_index] if question.answer_index < len(question.options) else ""
            return 1.0 if answer and len(answer) > 2 else 0.0
        except Exception:
            return 0.0

    def _score_distractors(self, question: Question) -> float:
        opts = question.options
        if len(opts) < 3:
            return 0.0
        # Check if distractors are distinct
        unique = len(set(opts)) == len(opts)
        # Check if not obviously wrong (too short, etc.)
        reasonable = all(len(o) > 2 for o in opts)
        return 1.0 if (unique and reasonable) else 0.5

    def _by_difficulty(self, results: List[QuestionQualityResult]) -> Dict[str, Dict[str, float]]:
        by_diff = {}
        for r in results:
            if r.difficulty not in by_diff:
                by_diff[r.difficulty] = {"count": 0, "avg_overall": 0.0}
            by_diff[r.difficulty]["count"] += 1
            by_diff[r.difficulty]["avg_overall"] += r.overall_score
        for d in by_diff:
            by_diff[d]["avg_overall"] = round(by_diff[d]["avg_overall"] / by_diff[d]["count"], 4)
        return by_diff


@dataclass
class TagQualityResult:
    case_id: str
    tag_id: str
    stable_key: str
    display_name: str
    relevance: float
    coverage: float
    non_redundant: float
    non_generic: float
    supported: float
    overall_score: float
    notes: str


@dataclass
class TagAggregateMetrics:
    total_tags: int
    avg_relevance: float
    avg_coverage: float
    avg_non_redundant: float
    avg_non_generic: float
    avg_supported: float
    avg_overall: float
    redundant_pairs: int
    generic_tags: int
    unsupported_tags: int


class TagEvaluator:
    GENERIC_TAGS = {"chapter", "section", "example", "introduction", "overview", "summary", "conclusion", "notes", "topic", "concept", "idea", "point"}

    def __init__(self):
        pass

    def evaluate_tags(self, case: Dict[str, Any], document: Document) -> tuple[List[TagQualityResult], TagAggregateMetrics]:
        doc_tags = DocumentTag.objects.filter(document=document).select_related("tag")
        expected_concepts = case.get("expected_key_concepts", [])

        results = []
        redundant_pairs = 0
        generic_count = 0
        unsupported_count = 0

        tag_list = list(doc_tags)
        for i, dt in enumerate(tag_list):
            tag = dt.tag
            stable_key = tag.stable_key
            display = tag.display_name

            relevance = self._score_relevance(tag, expected_concepts, document)
            coverage = self._score_coverage(tag, expected_concepts)
            non_redundant = self._score_non_redundant(tag, tag_list, i)
            non_generic = self._score_non_generic(tag)
            supported = self._score_supported(tag, document)

            if non_redundant < 0.5:
                redundant_pairs += 1
            if non_generic < 0.5:
                generic_count += 1
            if supported < 0.5:
                unsupported_count += 1

            overall = (relevance + coverage + non_redundant + non_generic + supported) / 5

            results.append(TagQualityResult(
                case_id=case["case_id"],
                tag_id=str(tag.pk),
                stable_key=stable_key,
                display_name=display,
                relevance=round(relevance, 2),
                coverage=round(coverage, 2),
                non_redundant=round(non_redundant, 2),
                non_generic=round(non_generic, 2),
                supported=round(supported, 2),
                overall_score=round(overall, 2),
                notes="",
            ))

        n = len(results)
        if n > 0:
            aggregate = TagAggregateMetrics(
                total_tags=n,
                avg_relevance=round(sum(r.relevance for r in results) / n, 4),
                avg_coverage=round(sum(r.coverage for r in results) / n, 4),
                avg_non_redundant=round(sum(r.non_redundant for r in results) / n, 4),
                avg_non_generic=round(sum(r.non_generic for r in results) / n, 4),
                avg_supported=round(sum(r.supported for r in results) / n, 4),
                avg_overall=round(sum(r.overall_score for r in results) / n, 4),
                redundant_pairs=redundant_pairs,
                generic_tags=generic_count,
                unsupported_tags=unsupported_count,
            )
        else:
            aggregate = TagAggregateMetrics(
                total_tags=0, avg_relevance=0.0, avg_coverage=0.0,
                avg_non_redundant=0.0, avg_non_generic=0.0, avg_supported=0.0,
                avg_overall=0.0, redundant_pairs=0, generic_tags=0, unsupported_tags=0,
            )

        return results, aggregate

    def _score_relevance(self, tag: Tag, expected_concepts: List[str], document: Document) -> float:
        if not expected_concepts:
            return 0.5  # No ground truth, neutral
        tag_lower = tag.stable_key.lower()
        matches = sum(1 for c in expected_concepts if c.lower() in tag_lower or tag_lower in c.lower())
        return matches / max(1, len(expected_concepts))

    def _score_coverage(self, tag: Tag, expected_concepts: List[str]) -> float:
        """Coverage: how much of the expected concept space this tag represents.
        Distinct from relevance - coverage is about whether the tag is a major concept."""
        if not expected_concepts:
            return 0.5
        tag_lower = tag.stable_key.lower()
        # Coverage = is this tag one of the main expected concepts (exact or near match)
        for c in expected_concepts:
            c_lower = c.lower()
            if c_lower == tag_lower or c_lower in tag_lower or tag_lower in c_lower:
                return 1.0
        return 0.0

    def _score_non_redundant(self, tag: Tag, all_tags: List[DocumentTag], index: int) -> float:
        tag_key = tag.stable_key.lower()
        for j, other_dt in enumerate(all_tags):
            if j == index:
                continue
            other_key = other_dt.tag.stable_key.lower()
            if tag_key in other_key or other_key in tag_key:
                return 0.0
            # Check similarity
            if self._similar(tag_key, other_key) > 0.8:
                return 0.0
        return 1.0

    def _similar(self, a: str, b: str) -> float:
        # Simple Jaccard on character bigrams
        def bigrams(s):
            return set(s[i:i+2] for i in range(len(s)-1))
        A, B = bigrams(a), bigrams(b)
        return len(A & B) / max(1, len(A | B))

    def _score_non_generic(self, tag: Tag) -> float:
        if tag.stable_key.lower() in self.GENERIC_TAGS:
            return 0.0
        if tag.display_name.lower() in self.GENERIC_TAGS:
            return 0.0
        return 1.0

    def _score_supported(self, tag: Tag, document: Document) -> float:
        # Check if tag token appears in document chunks
        chunks = document.chunks.filter(stale=False)
        token = tag.stable_key.replace("-", " ").lower()
        for chunk in chunks:
            if token in chunk.content.lower():
                return 1.0
        return 0.0

    def _score_non_generic(self, tag: Tag) -> float:
        if tag.stable_key.lower() in self.GENERIC_TAGS:
            return 0.0
        if tag.display_name.lower() in self.GENERIC_TAGS:
            return 0.0
        return 1.0

    def _score_supported(self, tag: Tag, document: Document) -> float:
        # Check if tag token appears in document chunks
        chunks = document.chunks.filter(stale=False)
        token = tag.stable_key.replace("-", " ").lower()
        for chunk in chunks:
            if token in chunk.content.lower():
                return 1.0
        return 0.0


def run_question_tag_evaluation(cases: List[Dict[str, Any]], document_ids: List[str], output_dir: str = None) -> Dict[str, Any]:
    from apps.documents.models import Document

    q_evaluator = QuestionEvaluator()
    t_evaluator = TagEvaluator()

    all_q_results = []
    all_t_results = []
    q_aggregates = []
    t_aggregates = []

    for case, doc_id in zip(cases, document_ids):
        document = Document.objects.get(pk=doc_id)
        q_results, q_agg = q_evaluator.evaluate_questions(case, document)
        t_results, t_agg = t_evaluator.evaluate_tags(case, document)
        all_q_results.extend(q_results)
        all_t_results.extend(t_results)
        q_aggregates.append(q_agg)
        t_aggregates.append(t_agg)

    # Combine aggregates
    total_q = sum(a.total_questions for a in q_aggregates)
    total_t = sum(a.total_tags for a in t_aggregates)

    q_combined = QuestionAggregateMetrics(
        total_questions=total_q,
        avg_relevance=round(sum(a.avg_relevance * a.total_questions for a in q_aggregates) / max(1, total_q), 4),
        avg_connection=round(sum(a.avg_connection * a.total_questions for a in q_aggregates) / max(1, total_q), 4),
        avg_non_trivial=round(sum(a.avg_non_trivial * a.total_questions for a in q_aggregates) / max(1, total_q), 4),
        avg_appropriate_difficulty=round(sum(a.avg_appropriate_difficulty * a.total_questions for a in q_aggregates) / max(1, total_q), 4),
        avg_answerable=round(sum(a.avg_answerable * a.total_questions for a in q_aggregates) / max(1, total_q), 4),
        avg_good_distractors=round(sum(a.avg_good_distractors * a.total_questions for a in q_aggregates) / max(1, total_q), 4),
        avg_overall=round(sum(a.avg_overall * a.total_questions for a in q_aggregates) / max(1, total_q), 4),
        by_difficulty={},
        duplicate_questions=sum(a.duplicate_questions for a in q_aggregates),
        trivial_questions=sum(a.trivial_questions for a in q_aggregates),
    )

    t_combined = TagAggregateMetrics(
        total_tags=total_t,
        avg_relevance=round(sum(a.avg_relevance * a.total_tags for a in t_aggregates) / max(1, total_t), 4),
        avg_coverage=round(sum(a.avg_coverage * a.total_tags for a in t_aggregates) / max(1, total_t), 4),
        avg_non_redundant=round(sum(a.avg_non_redundant * a.total_tags for a in t_aggregates) / max(1, total_t), 4),
        avg_non_generic=round(sum(a.avg_non_generic * a.total_tags for a in t_aggregates) / max(1, total_t), 4),
        avg_supported=round(sum(a.avg_supported * a.total_tags for a in t_aggregates) / max(1, total_t), 4),
        avg_overall=round(sum(a.avg_overall * a.total_tags for a in t_aggregates) / max(1, total_t), 4),
        redundant_pairs=sum(a.redundant_pairs for a in t_aggregates),
        generic_tags=sum(a.generic_tags for a in t_aggregates),
        unsupported_tags=sum(a.unsupported_tags for a in t_aggregates),
    )

    output = {
        "question_metrics": asdict(q_combined),
        "tag_metrics": asdict(t_combined),
        "question_results": [asdict(r) for r in all_q_results],
        "tag_results": [asdict(r) for r in all_t_results],
    }

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(Path(output_dir) / "question_tag_results.json", "w") as f:
            json.dump(output, f, indent=2, default=str)

    return output
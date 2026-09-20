"""Latency evaluation harness for StudyAI enrichment pipeline."""

import time
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path
from contextlib import contextmanager

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.ai_classroom.services import EnrichmentService, run_enrichment_job
from apps.jobs.models import Job

User = get_user_model()


@dataclass
class StageTiming:
    stage: str
    duration_ms: int
    success: bool
    error: Optional[str] = None


@dataclass
class LatencyCaseResult:
    case_id: str
    document_id: str
    stages: List[StageTiming]
    total_ms: int
    success: bool


@dataclass
class LatencyAggregateMetrics:
    total_cases: int
    successful_cases: int
    avg_total_ms: float
    median_total_ms: float
    p95_total_ms: float
    stage_averages: Dict[str, float]
    stage_medians: Dict[str, float]
    stage_p95s: Dict[str, float]


class LatencyEvaluator:
    def __init__(self, user):
        self.user = user

    @contextmanager
    def _time_stage(self, stage_name: str):
        start = time.monotonic()
        error = None
        success = True
        try:
            yield
        except Exception as e:
            error = str(e)
            success = False
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            self._current_stages.append(StageTiming(
                stage=stage_name,
                duration_ms=duration_ms,
                success=success,
                error=error,
            ))

    def evaluate_case(self, case: Dict[str, Any], document: Any) -> LatencyCaseResult:
        self._current_stages = []

        # Run full enrichment pipeline with timing using synchronous execution
        try:
            from apps.ai_classroom.services import run_enrichment_job
            from apps.jobs.models import Job
            from apps.ai_classroom.models import EnrichedNote
            
            # Create a job and run enrichment directly
            with self._time_stage("job_creation"):
                job = Job.objects.create(
                    job_type='enrich',
                    resource_type='document',
                    resource_id=str(document.pk),
                    profile_id=document.profile_id,
                    idempotency_key=f'latency_eval:{document.pk}',
                )

            # Run enrichment synchronously and measure total time
            with self._time_stage("total_enrichment"):
                run_enrichment_job(job)

            # Verify enrichment completed (check if EnrichedNote was created)
            with self._time_stage("job_status_check"):
                note = EnrichedNote.objects.filter(document=document, superseded=False).first()
                if not note:
                    raise Exception("Enrichment completed but no EnrichedNote created")

        except Exception as e:
            # Record the error
            pass

        total_ms = sum(s.duration_ms for s in self._current_stages)
        success = all(s.success for s in self._current_stages)

        return LatencyCaseResult(
            case_id=case["case_id"],
            document_id=str(document.pk),
            stages=self._current_stages,
            total_ms=total_ms,
            success=success,
        )

    def evaluate_dataset(self, cases: List[Dict[str, Any]], documents: List[Any]) -> tuple[List[LatencyCaseResult], LatencyAggregateMetrics]:
        results = []
        for case, doc in zip(cases, documents):
            result = self.evaluate_case(case, doc)
            results.append(result)

        successful = [r for r in results if r.success]
        total_ms_list = [r.total_ms for r in successful]
        total_ms_list.sort()

        n = len(total_ms_list)
        if n > 0:
            avg_total = sum(total_ms_list) / n
            median_total = total_ms_list[n // 2]
            p95_total = total_ms_list[int(n * 0.95)]
        else:
            avg_total = median_total = p95_total = 0

        # Stage aggregates
        stage_averages = {}
        stage_medians = {}
        stage_p95s = {}

        all_stages = set()
        for r in successful:
            for s in r.stages:
                all_stages.add(s.stage)

        for stage in all_stages:
            durations = [s.duration_ms for r in successful for s in r.stages if s.stage == stage]
            durations.sort()
            m = len(durations)
            if m > 0:
                stage_averages[stage] = round(sum(durations) / m, 2)
                stage_medians[stage] = durations[m // 2]
                stage_p95s[stage] = durations[int(m * 0.95)]
            else:
                stage_averages[stage] = stage_medians[stage] = stage_p95s[stage] = 0

        aggregate = LatencyAggregateMetrics(
            total_cases=len(results),
            successful_cases=len(successful),
            avg_total_ms=round(avg_total, 2),
            median_total_ms=median_total,
            p95_total_ms=p95_total,
            stage_averages=stage_averages,
            stage_medians=stage_medians,
            stage_p95s=stage_p95s,
        )

        return results, aggregate


def run_latency_evaluation(cases: List[Dict[str, Any]], documents: List[Any], user, output_dir: str = None) -> Dict[str, Any]:
    evaluator = LatencyEvaluator(user)
    results, aggregate = evaluator.evaluate_dataset(cases, documents)

    output = {
        "aggregate_metrics": asdict(aggregate),
        "case_results": [asdict(r) for r in results],
    }

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(Path(output_dir) / "latency_results.json", "w") as f:
            json.dump(output, f, indent=2, default=str)

    return output
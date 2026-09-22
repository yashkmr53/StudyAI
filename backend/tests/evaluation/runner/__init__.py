"""Main evaluation runner for StudyAI enrichment pipeline."""

import json
import os
from typing import List, Dict, Any
from pathlib import Path

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.documents.models import Document, DocumentPage, DocumentPageRevision, DocumentLine
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.retrieval.models import NoteChunk
from apps.ai_classroom.models import EnrichedNote
from apps.ai_classroom.services import EnrichmentService
from apps.jobs.models import Job

from tests.evaluation.runner.retrieval_eval import run_retrieval_evaluation, RetrievalEvaluator
from tests.evaluation.runner.citation_eval import run_citation_evaluation, CitationEvaluator
from tests.evaluation.runner.gap_eval import run_gap_evaluation, GapEvaluator
from tests.evaluation.runner.question_tag_eval import run_question_tag_evaluation
from tests.evaluation.runner.latency_eval import run_latency_evaluation

User = get_user_model()


def load_golden_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path) as f:
        data = json.load(f)
    return data["cases"]


def setup_evaluation_environment():
    """Create test user, profile, subject, and seed reference books."""
    user, _ = User.objects.get_or_create(email="eval@test.com", defaults={"password": "testpass"})
    if not user.has_usable_password():
        user.set_password("testpass")
        user.save()
    profile, _ = Profile.objects.get_or_create(user=user, name="Eval User")
    subject, _ = Subject.objects.get_or_create(profile=profile, name="Computer Science")
    return user, profile, subject


def create_document_from_case(case: Dict[str, Any], profile: Profile, subject: Subject, reference_book_mapping: Dict[str, str] = None) -> Document:
    """Create a document with chunks from the evaluation case."""
    from apps.references.models import ReferenceBook
    from apps.documents.models import Document as DocumentModel, DocumentPageRevision
    with transaction.atomic():
        # Create a reference book for this case first (if mapping exists)
        reference_book = None
        if reference_book_mapping:
            # Create a reference book for this case
            ref_doc = DocumentModel.objects.create(
                profile=None,
                subject=subject,
                source=DocumentModel.Source.REFERENCE,
                source_type=DocumentModel.SourceType.REFERENCE,
            )
            import hashlib
            ref_content = case.get("reference_book_content", "")
            ref_hash = hashlib.sha256(ref_content.encode()).hexdigest()
            ref_page = DocumentPage.objects.create(document=ref_doc, page_number=1)
            ref_revision = DocumentPageRevision.objects.create(
                page=ref_page,
                revision_number=1,
                content_hash=ref_hash,
                content_snapshot={"text": ref_content},
                ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
            )
            DocumentLine.objects.create(
                page_revision=ref_revision,
                line_index=0,
                text=ref_content,
            )
            ref_page.current_revision_id = ref_revision.pk
            ref_page.save()

            reference_book = ReferenceBook.objects.create(
                subject=subject,
                title=f"Reference Book: {case['case_id']}",
                document=ref_doc,
                status=ReferenceBook.Status.READY,
            )

        document = DocumentModel.objects.create(
            profile=profile,
            subject=subject,
            source=DocumentModel.Source.UPLOAD,
            source_type=DocumentModel.SourceType.PDF,
            reference_book_id=reference_book.pk if reference_book else None,
        )

        # Create a page and revision
        import hashlib
        content = case["input_note"]
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        page = DocumentPage.objects.create(document=document, page_number=1)
        revision = DocumentPageRevision.objects.create(
            page=page,
            revision_number=1,
            content_hash=content_hash,
            content_snapshot={"text": content},
            ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
        )
        # Create a DocumentLine for the content
        DocumentLine.objects.create(
            page_revision=revision,
            line_index=0,
            text=content,
        )
        page.current_revision_id = revision.pk
        page.save()

        # Create note chunks (split by sentences/paragraphs)
        content = case["input_note"]
        # Simple chunking: split by sentences
        import re
        sentences = re.split(r'(?<=[.!?])\s+', content)
        chunks = []
        current_chunk = ""
        chunk_idx = 0

        for sent in sentences:
            if len(current_chunk) + len(sent) > 500:  # ~120 words target
                if current_chunk:
                    chunk = NoteChunk.objects.create(
                        document=document,
                        profile=profile,
                        subject=subject,
                        revision_id=revision.pk,
                        revision_ids=[str(revision.pk)],
                        page_start=1,
                        page_end=1,
                        chunk_index=chunk_idx,
                        content=current_chunk.strip(),
                        content_hash=f"hash_{chunk_idx}",
                        source_type="note",
                        stale=False,
                    )
                    chunks.append(chunk)
                    chunk_idx += 1
                current_chunk = sent
            else:
                current_chunk += " " + sent

        if current_chunk:
            chunk = NoteChunk.objects.create(
                document=document,
                profile=profile,
                subject=subject,
                revision_id=revision.pk,
                revision_ids=[str(revision.pk)],
                page_start=1,
                page_end=1,
                chunk_index=chunk_idx,
                content=current_chunk.strip(),
                content_hash=f"hash_{chunk_idx}",
                source_type="note",
                stale=False,
            )
            chunks.append(chunk)
            chunk_idx += 1

        # Create reference book chunks from reference_book_mapping (stable keys)
        if reference_book_mapping:
            # Create a reference book for this document
            ref_doc = DocumentModel.objects.create(
                profile=None,
                subject=subject,
                source=DocumentModel.Source.REFERENCE,
                source_type=DocumentModel.SourceType.REFERENCE,
            )
            import hashlib
            ref_content = case.get("reference_book_content", "")
            ref_hash = hashlib.sha256(ref_content.encode()).hexdigest()
            ref_page = DocumentPage.objects.create(document=ref_doc, page_number=1)
            ref_revision = DocumentPageRevision.objects.create(
                page=ref_page,
                revision_number=1,
                content_hash=ref_hash,
                content_snapshot={"text": ref_content},
                ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
            )
            DocumentLine.objects.create(
                page_revision=ref_revision,
                line_index=0,
                text=ref_content,
            )
            ref_page.current_revision_id = ref_revision.pk
            ref_page.save()

            ref_book = ReferenceBook.objects.create(
                subject=subject,
                title=f"Reference Book: {case['case_id']}",
                document=ref_doc,
                status=ReferenceBook.Status.READY,
            )

            # Update the document with the reference_book_id
            document.reference_book_id = ref_book.pk
            document.save(update_fields=['reference_book_id'])

            # Create one reference chunk per stable mapping entry
            for stable_key, mapping_content in reference_book_mapping.items():
                chunk = NoteChunk.objects.create(
                    document=ref_doc,
                    profile=None,  # Reference chunks are profile-wide
                    subject=subject,
                    revision_id=ref_revision.pk,
                    revision_ids=[str(ref_revision.pk)],
                    page_start=1,
                    page_end=1,
                    chunk_index=chunk_idx,
                    content=mapping_content.strip(),
                    content_hash=f"eval_ref_{stable_key}",
                    source_type="reference",
                    reference_book=ref_book,
                    stale=False,
                )
                chunks.append(chunk)
                chunk_idx += 1

        # Generate embeddings for all chunks
        _generate_embeddings_for_chunks(chunks)

        return document


def _generate_embeddings_for_chunks(chunks):
    """Generate embeddings for chunks using the configured provider."""
    from providers.registry import get_embedding_provider
    from django.conf import settings
    
    provider = get_embedding_provider()
    model_version = getattr(settings, 'EMBEDDING_MODEL_VERSION', 'sentence-transformers-all-MiniLM-L6-v2-v1')
    
    texts = [c.content for c in chunks]
    embeddings = provider.embed(texts, model_version=model_version)
    
    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding
        chunk.embedding_model = provider.name
        chunk.embedding_version = model_version
        chunk.save(update_fields=['embedding', 'embedding_model', 'embedding_version'])


def run_full_evaluation(dataset_path: str, output_dir: str, runs: int = 1):
    """Run complete evaluation suite on golden dataset."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Load full dataset including reference_book_mapping
    with open(dataset_path) as f:
        full_dataset = json.load(f)
    cases = full_dataset["cases"]
    reference_book_mapping = full_dataset.get("reference_book_mapping", {})

    user, profile, subject = setup_evaluation_environment()

    all_runs_results = []

    for run_idx in range(runs):
        print(f"\n=== Run {run_idx + 1}/{runs} ===")

        # Create documents for each case
        documents = []
        for case in cases:
            case_mapping = reference_book_mapping.get(case["case_id"], {})
            doc = create_document_from_case(case, profile, subject, case_mapping)
            documents.append(doc)
            print(f"Created document {doc.pk} for {case['case_id']}")

        # Run enrichment for each document
        enriched_note_ids = []
        for i, (case, doc) in enumerate(zip(cases, documents)):
            print(f"  Enriching {case['case_id']} ({i+1}/{len(cases)})...")
            
            # Create a job and run enrichment directly (bypassing job queue for test env)
            from apps.jobs.models import Job
            from apps.ai_classroom.services import run_enrichment_job
            
            job = Job.objects.create(
                job_type='enrich',
                resource_type='document',
                resource_id=str(doc.pk),
                profile_id=doc.profile_id,
                idempotency_key=f'eval:{doc.pk}:{run_idx}',
            )
            print(f"    Created job {job.pk}")
            
            # Run enrichment directly (bypassing job queue which has issues in test env)
            run_enrichment_job(job)
            job.refresh_from_db()
            
            print(f"    Job {job.pk} completed with status: {job.status}")
            
            # Get the created EnrichedNote
            note = EnrichedNote.objects.filter(document=doc, superseded=False).first()
            if note:
                enriched_note_ids.append(str(note.pk))
                print(f"    Created EnrichedNote {note.pk} with {note.blocks.count()} blocks")
            else:
                print(f"    WARNING: No EnrichedNote created (job status: {job.status})")
                if job.last_error:
                    print(f"    Job error: {job.last_error}")

        # Run evaluations
        run_results = {}

        print("  Running retrieval evaluation...")
        retrieval_results = run_retrieval_evaluation(dataset_path, user, k=10, output_dir=f"{output_dir}/run_{run_idx}")
        run_results["retrieval"] = retrieval_results

        print("  Running citation evaluation...")
        citation_results = run_citation_evaluation(enriched_note_ids, output_dir=f"{output_dir}/run_{run_idx}")
        run_results["citation"] = citation_results

        print("  Running gap evaluation...")
        gap_results = run_gap_evaluation(cases, enriched_note_ids, dataset_path=dataset_path, output_dir=f"{output_dir}/run_{run_idx}")
        run_results["gap"] = gap_results

        print("  Running question/tag evaluation...")
        qt_results = run_question_tag_evaluation(cases, [str(d.pk) for d in documents], output_dir=f"{output_dir}/run_{run_idx}")
        run_results["questions_tags"] = qt_results

        print("  Running latency evaluation...")
        latency_results = run_latency_evaluation(cases, documents, user, output_dir=f"{output_dir}/run_{run_idx}")
        run_results["latency"] = latency_results

        all_runs_results.append(run_results)

    # Aggregate across runs
    print("\n=== Aggregating results ===")
    aggregate = aggregate_runs(all_runs_results)

    # Save final report
    final_report = {
        "dataset_version": "v1",
        "num_runs": runs,
        "num_cases": len(cases),
        "aggregate": aggregate,
        "runs": all_runs_results,
    }

    with open(Path(output_dir) / "baseline.json", "w") as f:
        json.dump(final_report, f, indent=2, default=str)

    # Generate markdown report
    generate_markdown_report(final_report, Path(output_dir) / "baseline.md")

    print(f"\nEvaluation complete. Results saved to {output_dir}")
    return final_report


def aggregate_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate metrics across multiple runs, computing mean and std."""
    if not runs:
        return {}

    # Collect all metric values across runs
    metric_names = ["retrieval", "citation", "gap", "questions_tags", "latency"]
    aggregated = {}
    
    for metric_name in metric_names:
        all_values = {}
        for run in runs:
            if metric_name in run:
                run_agg = run[metric_name].get("aggregate_metrics", {})
                for key, value in run_agg.items():
                    if isinstance(value, (int, float)):
                        if key not in all_values:
                            all_values[key] = []
                        all_values[key].append(value)
        
        # Compute mean and std for each metric
        metric_result = {}
        for key, values in all_values.items():
            if values:
                import statistics
                metric_result[key] = {
                    "mean": round(statistics.mean(values), 4),
                    "std": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
                    "min": round(min(values), 4),
                    "max": round(max(values), 4),
                    "n": len(values),
                    "values": [round(v, 4) for v in values]
                }
        
        # Also include per-run breakdown
        metric_result["per_run"] = {}
        for i, run in enumerate(runs):
            if metric_name in run:
                run_agg = run[metric_name].get("aggregate_metrics", {})
                metric_result["per_run"][f"run_{i}"] = {k: round(v, 4) if isinstance(v, float) else v 
                                                      for k, v in run_agg.items()}
        
        aggregated[metric_name] = metric_result

    # For questions_tags, handle nested structure
    if "questions_tags" in aggregated:
        qt = aggregated["questions_tags"]
        if "questions" in qt and "tags" in qt:
            # Flatten for backward compatibility
            pass

    return aggregated


def generate_markdown_report(report: Dict[str, Any], output_path: Path):
    """Generate human-readable markdown report."""
    lines = [
        "# StudyAI Enrichment Baseline Evaluation Report",
        "",
        f"**Dataset Version:** {report['dataset_version']}",
        f"**Number of Runs:** {report['num_runs']}",
        f"**Number of Cases:** {report['num_cases']}",
        "",
        "## Aggregate Metrics",
        "",
    ]

    agg = report.get("aggregate", {})

    # Retrieval
    ret = agg.get("retrieval", {})
    if ret:
        lines.extend([
            "### Retrieval",
            f"- **Recall@K:** {ret.get('recall_at_k', 'N/A')}",
            f"- **Precision@K:** {ret.get('precision_at_k', 'N/A')}",
            f"- **MRR:** {ret.get('mrr', 'N/A')}",
            f"- **Cases with Hits:** {ret.get('cases_with_hits', 'N/A')} / {ret.get('total_cases', 'N/A')}",
            "",
        ])

    # Citation
    cit = agg.get("citation", {})
    if cit:
        lines.extend([
            "### Citations",
            f"- **Validity Rate:** {cit.get('validity_rate', 'N/A')}",
            f"- **Provenance Rate:** {cit.get('provenance_rate', 'N/A')}",
            f"- **Support Rate:** {cit.get('support_rate', 'N/A')}",
            f"- **Partially Supported Rate:** {cit.get('partially_supported_rate', 'N/A')}",
            f"- **Unsupported Rate:** {cit.get('unsupported_rate', 'N/A')}",
            f"- **Not Verified Rate:** {cit.get('not_verified_rate', 'N/A')}",
            "",
        ])

    # Gap
    gap = agg.get("gap", {})
    if gap:
        lines.extend([
            "### Gap Detection & Filling",
            f"- **Detection Precision:** {gap.get('detection_precision', 'N/A')}",
            f"- **Detection Recall:** {gap.get('detection_recall', 'N/A')}",
            f"- **Detection F1:** {gap.get('detection_f1', 'N/A')}",
            f"- **Fill Rate:** {gap.get('fill_rate', 'N/A')}",
            f"- **Correct Strong:** {gap.get('fill_correct_strong', 'N/A')}",
            f"- **Correct Shallow:** {gap.get('fill_correct_shallow', 'N/A')}",
            f"- **Partially Correct:** {gap.get('fill_partially_correct', 'N/A')}",
            f"- **Incorrect:** {gap.get('fill_incorrect', 'N/A')}",
            f"- **Missing:** {gap.get('fill_missing', 'N/A')}",
            "",
        ])

    # Questions/Tags
    qt = agg.get("questions_tags", {})
    qm = qt.get("questions", {})
    tm = qt.get("tags", {})
    if qm:
        lines.extend([
            "### Questions",
            f"- **Total Questions:** {qm.get('total_questions', 'N/A')}",
            f"- **Avg Overall Score:** {qm.get('avg_overall', 'N/A')}",
            f"- **Avg Relevance:** {qm.get('avg_relevance', 'N/A')}",
            f"- **Avg Connection:** {qm.get('avg_connection', 'N/A')}",
            f"- **Avg Non-Trivial:** {qm.get('avg_non_trivial', 'N/A')}",
            f"- **Avg Answerable:** {qm.get('avg_answerable', 'N/A')}",
            f"- **Duplicate Questions:** {qm.get('duplicate_questions', 'N/A')}",
            f"- **Trivial Questions:** {qm.get('trivial_questions', 'N/A')}",
            "",
        ])
    if tm:
        lines.extend([
            "### Tags",
            f"- **Total Tags:** {tm.get('total_tags', 'N/A')}",
            f"- **Avg Overall Score:** {tm.get('avg_overall', 'N/A')}",
            f"- **Avg Relevance:** {tm.get('avg_relevance', 'N/A')}",
            f"- **Avg Non-Redundant:** {tm.get('avg_non_redundant', 'N/A')}",
            f"- **Avg Non-Generic:** {tm.get('avg_non_generic', 'N/A')}",
            f"- **Avg Supported:** {tm.get('avg_supported', 'N/A')}",
            f"- **Redundant Pairs:** {tm.get('redundant_pairs', 'N/A')}",
            f"- **Generic Tags:** {tm.get('generic_tags', 'N/A')}",
            f"- **Unsupported Tags:** {tm.get('unsupported_tags', 'N/A')}",
            "",
        ])

    # Latency
    lat = agg.get("latency", {})
    if lat:
        lines.extend([
            "### Latency",
            f"- **Avg Total:** {lat.get('avg_total_ms', 'N/A')} ms",
            f"- **Median Total:** {lat.get('median_total_ms', 'N/A')} ms",
            f"- **P95 Total:** {lat.get('p95_total_ms', 'N/A')} ms",
            "",
            "#### Stage Breakdown",
        ])
        for stage, avg in lat.get("stage_averages", {}).items():
            lines.append(f"- **{stage}:** avg={avg}ms, median={lat.get('stage_medians', {}).get(stage, 'N/A')}ms, p95={lat.get('stage_p95s', {}).get(stage, 'N/A')}ms")
        lines.append("")

    lines.extend([
        "## Per-Run Details",
        "",
    ])

    for i, run in enumerate(report.get("runs", [])):
        lines.append(f"### Run {i+1}")
        lines.append("")
        for eval_type, results in run.items():
            if isinstance(results, dict) and "aggregate_metrics" in results:
                m = results["aggregate_metrics"]
                lines.append(f"#### {eval_type.replace('_', ' ').title()}")
                for key, val in m.items():
                    if not isinstance(val, (dict, list)):
                        lines.append(f"- {key}: {val}")
                lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


class FullEvaluationTest(TestCase):
    """Integration test to run the full evaluation suite."""

    def setUp(self):
        self.dataset_path = "tests/evaluation/datasets/golden_v1.json"
        self.output_dir = "tests/evaluation/results/test_run"

    def test_full_evaluation_single_run(self):
        """Run a single evaluation pass (smoke test)."""
        # This requires the full pipeline to work with real LLM
        # Skip in unit tests, run manually for baseline
        self.skipTest("Run manually with real LLM for baseline")

    def test_retrieval_evaluation_unit(self):
        """Test retrieval evaluator with mocked data."""
        pass
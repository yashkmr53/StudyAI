"""Run AI evaluation datasets (architecture §26).

Usage:
    manage.py run_ai_evaluation --file eval/citation_cases.json
    manage.py run_ai_evaluation --file eval/retrieval_cases.json --user someone@example.com

Case file shapes:
  {"kind": "citation", "cases": [
     {"block_content": "...", "cited_chunk_contents": ["...", "..."],
      "expected_status": "supported"|"partially_supported"|"unsupported"}
  ]}
  {"kind": "retrieval", "cases": [
     {"query": "...", "expected_chunk_ids": ["<uuid>", ...]}
  ]}   # retrieval requires --user and indexed chunks
"""
import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Evaluate AI quality metrics over a JSON case dataset (§26)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--user", help="Email for retrieval cases (scoped to their profiles).")
        parser.add_argument("--k", type=int, default=5)
        parser.add_argument(
            "--assert-gte", action="append", default=[],
            metavar="METRIC=VALUE",
            help="Exit non-zero when metric < VALUE (regression gate). Repeatable.",
        )

    def handle(self, *args, **options):
        from apps.accounts.models import User
        from apps.evaluation.runner import record_run, run_citation_cases, run_retrieval_cases

        with open(options["file"]) as fh:
            dataset = json.load(fh)

        kind = dataset.get("kind")
        cases = dataset.get("cases", [])
        if not cases:
            self.stdout.write(self.style.WARNING("Dataset has no cases."))
            return

        if kind == "citation":
            metrics = run_citation_cases(cases)
        elif kind == "retrieval":
            email = options.get("user")
            if not email:
                self.stdout.write(self.style.ERROR("--user is required for retrieval evaluation."))
                return
            user = User.objects.get(email=email)
            metrics = run_retrieval_cases(cases, user, k=options["k"])
        else:
            self.stdout.write(self.style.ERROR(f"Unknown kind: {kind}"))
            return

        run = record_run(kind=kind, dataset_name=options["file"], cases_count=len(cases), metrics=metrics)
        self.stdout.write(self.style.SUCCESS(f"EvalRun {run.pk} — {json.dumps(metrics)}"))

        failures = []
        for assertion in options["assert_gte"]:
            key, _, raw = assertion.partition("=")
            threshold = float(raw)
            actual = metrics.get(key)
            if actual is None or actual < threshold:
                failures.append(f"{key}={actual} < {threshold}")
        if failures:
            self.stdout.write(self.style.ERROR("REGRESSION: " + "; ".join(failures)))
            raise SystemExit(2)
        self.stdout.write(self.style.SUCCESS("Regression gate passed."))

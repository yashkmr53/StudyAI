"""Management command to report enrichment reference-coverage guidance & telemetry (PR 3 §3.5).

Aggregates privacy-safe metrics across recent enriched notes:
- Total notes enriched
- Topics total and breakdown by evidence status (sufficient, partial, none) with %
- Additions total and breakdown by support status (supported, partial)
- Notes with none/partial whose subject reference library changed afterwards
- Dropped additions count by reason

Usage:
    python manage.py report_enrichment_coverage --days 30 [--subject "Computer Science"]
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock
from apps.references.services import reference_library_hash
from apps.subjects.models import Subject


class Command(BaseCommand):
    help = "Generate privacy-safe enrichment reference coverage and telemetry report"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to look back (default: 30)",
        )
        parser.add_argument(
            "--subject",
            type=str,
            default=None,
            help="Optional subject name or ID to filter by",
        )

    def handle(self, *args, **options):
        days = options["days"]
        subject_filter = options.get("subject")

        since = timezone.now() - timedelta(days=days)
        qs = EnrichedNote.objects.filter(superseded=False, created_at__gte=since)

        if subject_filter:
            qs = qs.filter(document__subject__name__iexact=subject_filter) | qs.filter(document__subject__id__iexact=subject_filter)

        notes = list(qs.select_related("document__subject"))
        total_notes = len(notes)

        self.stdout.write("=================================================================")
        self.stdout.write(f"StudyAI Enrichment Reference-Coverage Report (Past {days} days)")
        if subject_filter:
            self.stdout.write(f"Subject Filter: {subject_filter}")
        self.stdout.write("=================================================================")
        self.stdout.write(f"Total Notes Enriched: {total_notes}\n")

        if total_notes == 0:
            self.stdout.write("No enriched notes found in the specified window.")
            return

        # 1. Topics by evidence status
        topics_sufficient = 0
        topics_partial = 0
        topics_none = 0

        # 2. Additions by support status
        additions_supported = 0
        additions_partial = 0

        # 3. Drops by reason
        drops_by_reason = {
            "unanchored": 0,
            "low_similarity": 0,
            "unsupported": 0,
            "contradicted": 0,
            "duplicate": 0,
        }

        # 4. Notes whose library changed afterwards
        library_changed_notes = 0

        for note in notes:
            # Topic counts from evidence_status_by_topic
            ev_map = note.evidence_status_by_topic or {}
            for status in ev_map.values():
                if status == "sufficient":
                    topics_sufficient += 1
                elif status == "partial":
                    topics_partial += 1
                elif status == "none":
                    topics_none += 1

            # Telemetry diagnostics
            diag = note.diagnostics or {}
            add_diag = diag.get("additions_by_support", {})
            additions_supported += add_diag.get("supported", 0)
            additions_partial += add_diag.get("partial", 0)

            drops_diag = diag.get("drops_by_reason", {})
            for r, cnt in drops_diag.items():
                if r in drops_by_reason:
                    drops_by_reason[r] += cnt

            # Check if reference library changed
            doc = note.document
            if doc and doc.subject:
                cur_hash = reference_library_hash(doc.subject)
                has_gap = any(s in ("none", "partial") for s in ev_map.values())
                if has_gap and (note.reference_snapshot_hash != cur_hash):
                    library_changed_notes += 1

        # Fallback to direct block counting if diagnostics were empty (e.g. legacy notes)
        if additions_supported == 0 and additions_partial == 0:
            note_ids = [n.id for n in notes]
            additions_supported = EnrichedNoteBlock.objects.filter(
                enriched_note_id__in=note_ids,
                block_kind=EnrichedNoteBlock.BlockKind.ADDITION,
                support_status="supported",
            ).count()
            additions_partial = EnrichedNoteBlock.objects.filter(
                enriched_note_id__in=note_ids,
                block_kind=EnrichedNoteBlock.BlockKind.ADDITION,
                support_status="partial",
            ).count()

        topics_total = topics_sufficient + topics_partial + topics_none
        additions_total = additions_supported + additions_partial

        self.stdout.write("--- Topic Reference-Coverage ---")
        self.stdout.write(f"Total Topics: {topics_total}")
        if topics_total > 0:
            pct_suf = (topics_sufficient / topics_total) * 100
            pct_par = (topics_partial / topics_total) * 100
            pct_non = (topics_none / topics_total) * 100
            self.stdout.write(f"  • Sufficient (Reference found):   {topics_sufficient:4d} ({pct_suf:5.1f}%)")
            self.stdout.write(f"  • Partial    (Limited reference): {topics_partial:4d} ({pct_par:5.1f}%)")
            self.stdout.write(f"  • None       (No reference found): {topics_none:4d} ({pct_non:5.1f}%)")
        else:
            self.stdout.write("  (No topic data available)")

        self.stdout.write("\n--- Addition Support Status ---")
        self.stdout.write(f"Total Additions: {additions_total}")
        if additions_total > 0:
            pct_asuf = (additions_supported / additions_total) * 100
            pct_apar = (additions_partial / additions_total) * 100
            self.stdout.write(f"  • Supported  (From your reference):  {additions_supported:4d} ({pct_asuf:5.1f}%)")
            self.stdout.write(f"  • Partial    (Extends reference):    {additions_partial:4d} ({pct_apar:5.1f}%)")
        else:
            self.stdout.write("  (No additions generated)")

        self.stdout.write("\n--- Reference Library Invalidation ---")
        self.stdout.write(f"Notes with None/Partial Coverage: {sum(1 for n in notes if any(s in ('none', 'partial') for s in (n.evidence_status_by_topic or {}).values()))}")
        self.stdout.write(f"Notes whose Library Changed:     {library_changed_notes}")

        self.stdout.write("\n--- Filtered / Dropped Additions by Reason ---")
        total_dropped = sum(drops_by_reason.values())
        self.stdout.write(f"Total Dropped: {total_dropped}")
        for r, cnt in drops_by_reason.items():
            pct = (cnt / total_dropped * 100) if total_dropped > 0 else 0.0
            self.stdout.write(f"  • {r:16s}: {cnt:4d} ({pct:5.1f}%)")
        self.stdout.write("=================================================================\n")

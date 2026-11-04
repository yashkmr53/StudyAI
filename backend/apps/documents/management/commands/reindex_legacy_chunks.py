"""Management command to throttled re-index legacy documents and retire cross-page chunks safely (architecture §8, §10).

Usage:
    python manage.py reindex_legacy_chunks --throttle=1.0 --batch-size=50
"""
import time
import logging
from django.core.management.base import BaseCommand
from django.db.models import F

from apps.documents.models import Document
from apps.retrieval.models import NoteChunk
from apps.retrieval.services import index_document

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Throttled re-indexing of documents with legacy cross-page chunks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--throttle",
            type=float,
            default=0.5,
            help="Sleep duration in seconds between documents to throttle DB and embedding load.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Max documents to process in one execution.",
        )

    def handle(self, *args, **options):
        throttle = options["throttle"]
        batch_size = options["batch_size"]

        # Find document IDs with legacy cross-page chunks (page_start != page_end)
        legacy_doc_ids = list(
            NoteChunk.objects.exclude(page_start=F("page_end"))
            .values_list("document_id", flat=True)
            .distinct()[:batch_size]
        )

        if not legacy_doc_ids:
            self.stdout.write(self.style.SUCCESS("No documents with legacy cross-page chunks found."))
            return

        self.stdout.write(
            f"Found {len(legacy_doc_ids)} documents to re-index (throttle={throttle}s)..."
        )

        success = 0
        for doc_id in legacy_doc_ids:
            try:
                doc = Document.objects.get(pk=doc_id)
                stats = index_document(doc)
                self.stdout.write(
                    f"Re-indexed document {doc_id}: kept={stats['kept']}, deleted={stats['deleted']}, created={stats['created']}, embedded={stats['embedded']}"
                )
                success += 1
            except Exception as exc:
                self.stderr.write(f"Failed to re-index document {doc_id}: {exc}")

            if throttle > 0:
                time.sleep(throttle)

        self.stdout.write(self.style.SUCCESS(f"Successfully re-indexed {success}/{len(legacy_doc_ids)} documents."))

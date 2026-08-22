"""Reference-book ingestion (architecture §15).

Ingests a platform-curated book from a JSON file through the canonical
ingestion layer:

    [
      {
        "title": "Algorithms Unlocked",
        "author": "...", "edition": "1st", "isbn": "...",
        "subject_name": "Algorithms",
        "chapters": [
          {"number": 1, "title": "What's the problem?", "text": "...paragraphs..."}
        ]
      }
    ]

Each chapter becomes a document page (one line per paragraph) on a
reference Document; the book is then chunked+embedded and marked READY.
Only READY books participate in retrieval. Users cannot modify these —
there is no public write API by design.
"""
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.documents.models import Document, DocumentLine, DocumentPage, DocumentPageRevision
from apps.references.models import ReferenceBook, ReferenceBookChapter
from apps.retrieval.services import enqueue_index_job


class Command(BaseCommand):
    help = "Ingest a reference book JSON file into the canonical layer and index it."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the reference book JSON file.")

    def handle(self, *args, **options):
        with open(options["file"]) as fh:
            payload = json.load(fh)

        created_books = 0
        for entry in payload:
            with transaction.atomic():
                subject = None
                subject_name = entry.get("subject_name")
                if subject_name:
                    from apps.subjects.models import Subject

                    subject = Subject.objects.filter(name=subject_name).first()

                if ReferenceBook.objects.filter(title=entry["title"], author=entry.get("author", "")).exists():
                    self.stdout.write(f"Skip existing book: {entry['title']}")
                    continue

                document = Document.objects.create(
                    profile=None,
                    subject=subject,
                    source=Document.Source.REFERENCE,
                    source_type=Document.SourceType.REFERENCE,
                )

                book = ReferenceBook.objects.create(
                    subject=subject,
                    title=entry["title"],
                    author=entry.get("author", ""),
                    edition=entry.get("edition", ""),
                    isbn=entry.get("isbn", ""),
                    status=ReferenceBook.Status.PROCESSING,
                )
                book.document = document
                book.save(update_fields=("document",))

                page_number = 0
                current_page_start = 0
                for chapter in entry.get("chapters", []):
                    page_number += 1
                    paragraphs = [p.strip() for p in chapter["text"].split("\n\n") if p.strip()]
                    page = DocumentPage.objects.create(document=document, page_number=page_number)
                    revision = DocumentPageRevision.objects.create(
                        page=page,
                        revision_number=1,
                        content_hash=__import__("hashlib").sha256(
                            "\n".join(paragraphs).encode()
                        ).hexdigest(),
                        content_snapshot={"lines": paragraphs, "origin": "reference"},
                        ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
                    )
                    DocumentLine.objects.bulk_create(
                        [
                            DocumentLine(page_revision=revision, line_index=i, text=p)
                            for i, p in enumerate(paragraphs)
                        ]
                    )
                    page.current_revision_id = revision.pk
                    page.ocr_status = DocumentPageRevision.OcrStatus.COMPLETED
                    page.save(update_fields=("current_revision_id", "ocr_status"))

                    ReferenceBookChapter.objects.create(
                        book=book,
                        chapter_number=int(chapter.get("number", page_number)),
                        title=chapter.get("title", f"Chapter {page_number}"),
                        page_range_start=current_page_start or page_number,
                        page_range_end=page_number,
                    )
                    current_page_start = current_page_start or page_number

                job, _ = enqueue_index_job(document)
                from apps.jobs.models import Job
                from django.conf import settings

                if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False) and job.status == Job.Status.SUCCEEDED:
                    book.status = ReferenceBook.Status.READY
                book.save(update_fields=("status",))
                created_books += 1
                self.stdout.write(f"Ingested '{book.title}' ({page_number} chapters/pages), index job {job.status}")

        self.stdout.write(self.style.SUCCESS(f"Done. {created_books} book(s) ingested."))

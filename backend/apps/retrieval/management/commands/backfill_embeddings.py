"""Management command to backfill embeddings with canonical Qwen3-Embedding-0.6B.

StudyAI Phased AI Stack Migration (Phase 3):
Embeds any chunks with NULL embeddings or outdated embedding versions.
Runs natively using the canonical Qwen3EmbeddingProvider with GPU/MPS acceleration.
"""
import logging
import time
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.retrieval.models import NoteChunk
from providers.registry import get_embedding_provider, embedding_model_version

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill embeddings for NoteChunks using canonical Qwen3-Embedding-0.6B (1024-d)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=32,
            help="Number of chunks to embed per batch (default: 32).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of chunks to process (0 = all).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Include stale chunks in re-embedding and mark them active.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be embedded without modifying the database.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        limit = options["limit"]
        include_stale = options["all"]
        dry_run = options["dry_run"]

        provider = get_embedding_provider()
        model_version = embedding_model_version()

        self.stdout.write(
            f"Provider: {provider.name} | Dimension: {provider.dimension} | Target Version: {model_version}"
        )

        query = NoteChunk.objects.filter(embedding__isnull=True)
        if not include_stale:
            query = query.filter(stale=False)

        total_count = query.count()
        if limit > 0:
            query = query[:limit]
            total_count = min(total_count, limit)

        self.stdout.write(f"Found {total_count} chunks requiring embeddings.")

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("All target chunks already have up-to-date embeddings."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f"[DRY RUN] Would embed {total_count} chunks."))
            return

        chunks_list = list(query)
        processed = 0
        start_time = time.time()

        for i in range(0, len(chunks_list), batch_size):
            batch = chunks_list[i : i + batch_size]
            texts = [c.content for c in batch]

            t0 = time.time()
            try:
                vectors = provider.embed(texts, model_version=model_version)
            except Exception as exc:
                self.stderr.write(f"Batch embedding failed: {exc}")
                continue

            with transaction.atomic():
                for chunk, vector in zip(batch, vectors):
                    chunk.embedding = vector
                    chunk.embedding_model = provider.name
                    chunk.embedding_version = model_version
                    if include_stale:
                        chunk.stale = False
                    chunk.save(update_fields=("embedding", "embedding_model", "embedding_version", "stale"))

            processed += len(batch)
            elapsed_batch = time.time() - t0
            self.stdout.write(
                f"Embedded {processed}/{len(chunks_list)} chunks ({elapsed_batch:.2f}s for batch of {len(batch)})"
            )

        total_time = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully embedded {processed} chunks in {total_time:.2f}s "
                f"({processed / total_time:.1f} chunks/sec)."
            )
        )

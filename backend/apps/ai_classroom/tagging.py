"""Tag extraction + change log (architecture §18, §53).

Extraction is rule-based (frequent significant tokens → find-or-create
stable tags) until the LLM swap; identity rules are already final:
- same (subject, stable_key) ⇒ same Tag regardless of display name
- renames log a RENAMED entry; linking a document logs LINKED
"""
import logging

from django.db import transaction
from django.utils.text import slugify

from apps.ai_classroom.models import DocumentTag, Tag, TagChangeLog

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your",
    "have", "will", "each", "which", "their", "when", "then", "than",
}


def _significant_tokens(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for word in text.lower().split():
        word = "".join(c for c in word if c.isalnum())
        if len(word) < 5 or word in _STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    return counts


class TaggingService:
    @staticmethod
    @transaction.atomic
    def extract_for_document(document, generation_job=None, max_tags: int = 5) -> list[Tag]:
        """Find-or-create stable tags from document chunk contents and link
        them to the document. Idempotent. Documents without a subject are
        skipped — §18 anchors tags to a subject."""
        if document.subject_id is None:
            return []

        token_counts: dict[str, int] = {}
        for chunk in document.chunks.filter(stale=False):
            for token, n in _significant_tokens(chunk.content).items():
                token_counts[token] = token_counts.get(token, 0) + n

        ordered = sorted(token_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:max_tags]

        linked: list[Tag] = []
        for token, _count in ordered:
            stable_key = slugify(token)
            if not stable_key:
                continue
            tag, tag_created = Tag.objects.get_or_create(
                subject=document.subject,
                stable_key=stable_key,
                defaults={"display_name": token.capitalize()},
            )
            if tag_created:
                TagChangeLog.objects.create(
                    tag=tag,
                    stable_key_snapshot=stable_key,
                    change_type=TagChangeLog.ChangeType.ADDED,
                    new_value=tag.display_name,
                    generation_job=generation_job,
                )
            _, link_created = DocumentTag.objects.get_or_create(
                document=document,
                tag=tag,
                defaults={"generation_job": generation_job},
            )
            if link_created:
                TagChangeLog.objects.create(
                    tag=tag,
                    stable_key_snapshot=stable_key,
                    change_type=TagChangeLog.ChangeType.LINKED,
                    new_value=str(document.pk),
                    generation_job=generation_job,
                )
            linked.append(tag)

        logger.info("Tagged document %s with %s tag(s)", document.pk, len(linked))
        return linked

    @staticmethod
    @transaction.atomic
    def rename_tag(tag: Tag, new_display_name: str, *, actor_job=None) -> None:
        """Renames never change identity (§18): same row, same stable_key."""
        old = tag.display_name
        if old == new_display_name:
            return
        tag.display_name = new_display_name
        tag.save(update_fields=("display_name",))
        TagChangeLog.objects.create(
            tag=tag,
            stable_key_snapshot=tag.stable_key,
            change_type=TagChangeLog.ChangeType.RENAMED,
            old_value=old,
            new_value=new_display_name,
            generation_job=actor_job,
        )

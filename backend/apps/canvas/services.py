"""Canvas session and sync services (architecture §4, §5, §65, §67).

Locking model (§5):
- single writer per session
- every write carries device_id + lock_generation; accepted only when the
  holder matches, the generation matches, and the lock is unexpired
- heartbeat refreshes expiry; takeover force-transfers ownership and
  increments the generation so stale writers receive 409 SESSION_LOCK_LOST

Finalize (§67) runs in one transaction: lock validation + page
finalization. Document revision creation + OCR job enqueue extend this
same transaction in Phase 3.
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.canvas.models import CanvasPage, CanvasSession, CanvasStroke
from apps.documents.models import Document, DocumentPage, DocumentPageRevision
from providers.registry import get_object_storage
from shared.exceptions import ResourceNotFound, RevisionConflict, SessionLockLost, ValidationError

LOCK_TTL_SECONDS = getattr(settings, "CANVAS_LOCK_TTL_SECONDS", 90)


def _expiry() -> object:
    return timezone.now() + timedelta(seconds=LOCK_TTL_SECONDS)


class CanvasSessionService:
    @staticmethod
    def create_session(user, profile, device_id: str, subject=None) -> CanvasSession:
        return CanvasSession.objects.create(
            profile=profile,
            subject=subject,
            device_id=device_id,
            lock_holder=device_id,
            lock_generation=1,
            lock_expires_at=_expiry(),
        )

    @staticmethod
    def get_owned_session(user, session_id, *, for_update: bool = False) -> CanvasSession:
        qs = CanvasSession.objects.filter(profile__user=user)
        if for_update:
            qs = qs.select_for_update()
        try:
            return qs.get(pk=session_id)
        except (CanvasSession.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Canvas session not found.")

    @staticmethod
    def ensure_lock(session: CanvasSession, device_id: str, lock_generation) -> None:
        """Fencing check: holder + generation + unexpired, else 409 SESSION_LOCK_LOST."""
        expired = session.lock_expires_at is None or session.lock_expires_at <= timezone.now()
        if (
            session.lock_holder != device_id
            or str(lock_generation) != str(session.lock_generation)
            or expired
        ):
            raise SessionLockLost()

    @classmethod
    def heartbeat(cls, user, session_id, device_id: str, lock_generation) -> CanvasSession:
        with transaction.atomic():
            session = cls.get_owned_session(user, session_id, for_update=True)
            cls.ensure_lock(session, device_id, lock_generation)
            session.lock_expires_at = _expiry()
            session.save(update_fields=("lock_expires_at", "updated_at"))
            return session

    @classmethod
    def takeover(cls, user, session_id, device_id: str) -> CanvasSession:
        """Force-transfer ownership; increments generation to fence stale writers."""
        if not device_id:
            raise ValidationError("device_id is required.")
        with transaction.atomic():
            session = cls.get_owned_session(user, session_id, for_update=True)
            session.lock_generation += 1
            session.lock_holder = device_id
            session.lock_expires_at = _expiry()
            session.save(update_fields=("lock_generation", "lock_holder", "lock_expires_at", "updated_at"))
            return session


class CanvasSyncService:
    @staticmethod
    def _locked_page_for_user(user, page_id) -> tuple[CanvasPage, CanvasSession]:
        try:
            page = CanvasPage.objects.select_related("session").get(
                pk=page_id, session__profile__user=user
            )
        except (CanvasPage.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Canvas page not found.")
        # Lock the session row: it owns the fencing state for all page writes.
        session = CanvasSession.objects.select_for_update().get(pk=page.session_id)
        return page, session

    @classmethod
    def create_page(cls, user, session_id, page_number, device_id: str, lock_generation) -> CanvasPage:
        with transaction.atomic():
            session = CanvasSessionService.get_owned_session(user, session_id, for_update=True)
            CanvasSessionService.ensure_lock(session, device_id, lock_generation)
            try:
                return CanvasPage.objects.create(session=session, page_number=page_number)
            except Exception as exc:
                from django.db import IntegrityError

                if isinstance(exc, IntegrityError):
                    raise ValidationError("Page number already exists for this session.")
                raise

    @classmethod
    def append_strokes(cls, user, page_id, device_id: str, lock_generation, strokes: list[dict]) -> dict:
        """Idempotent batch append. Replays of a client_idempotency_key are duplicates."""
        import uuid as uuidlib

        from django.db import IntegrityError

        with transaction.atomic():
            page, session = cls._locked_page_for_user(user, page_id)
            CanvasSessionService.ensure_lock(session, device_id, lock_generation)
            if page.is_finalized:
                raise RevisionConflict("Page is finalized and can no longer be modified.")

            created: list[CanvasStroke] = []
            duplicate_keys: list[str] = []
            for data in strokes:
                key = data.get("client_idempotency_key")
                if not key:
                    raise ValidationError("Each stroke requires client_idempotency_key.")
                points = data.get("points")
                if not isinstance(points, list) or len(points) < 2:
                    raise ValidationError("Stroke points must be a list with at least 2 values.")
                stroke_id = data.get("id") or uuidlib.uuid4()
                try:
                    # Nested atomic = savepoint: a duplicate key must not poison
                    # the surrounding transaction for the remaining strokes.
                    with transaction.atomic():
                        stroke = CanvasStroke.objects.create(
                            id=stroke_id,
                            page=page,
                            sequence_order=int(data.get("sequence_order") or 0),
                            points=points,
                            client_idempotency_key=key,
                        )
                    created.append(stroke)
                except IntegrityError:
                    duplicate_keys.append(key)

            return {
                "created": [str(s.id) for s in created],
                "duplicate_keys": duplicate_keys,
            }

    @classmethod
    def finalize_page(cls, user, page_id, device_id: str, lock_generation) -> dict:
        """One transaction: lock validation + finalization + ingestion (§67).

        Creates (once per session) the canonical Document, a DocumentPage
        per finalized canvas page, an initial DocumentPageRevision hashed
        from the rendered page image, and the logical OCR job. The storage
        write of the rendered PNG happens before commit; a rollback would
        leave an orphaned object, which is harmless and cleaned by policy.
        """
        with transaction.atomic():
            page, session = cls._locked_page_for_user(user, page_id)
            CanvasSessionService.ensure_lock(session, device_id, lock_generation)
            already = page.is_finalized
            document = None
            revision = None
            job = None
            if not already:
                from apps.documents.services import IngestionService, compute_content_hash
                from apps.canvas.raster import render_strokes_png

                page.is_finalized = True
                page.finalized_at = timezone.now()
                page.save(update_fields=("is_finalized", "finalized_at"))

                strokes = list(page.strokes.order_by("sequence_order").values_list("points", flat=True))
                png = render_strokes_png(strokes)

                document = (
                    Document.objects.filter(source="canvas", source_type="canvas_page", profile=session.profile)
                    .order_by("created_at")
                    .first()
                )
                if document is None:
                    document, doc_page = IngestionService.create_document(
                        user,
                        profile=session.profile,
                        source=Document.Source.CANVAS,
                        source_type=Document.SourceType.CANVAS_PAGE,
                        subject=session.subject,
                    )
                    CanvasSession.objects.filter(pk=session.pk).update(document=document)
                else:
                    doc_page_number = (
                        DocumentPage.objects.filter(document=document).count() + 1
                    )
                    doc_page = DocumentPage.objects.create(
                        document=document, page_number=doc_page_number
                    )

                key = f"{session.profile_id}/{doc_page.id}.png"
                get_object_storage().store_bytes(key, png)
                doc_page.image_ref = key
                doc_page.save(update_fields=("image_ref",))

                content_hash = compute_content_hash(png)
                revision = IngestionService._create_revision_locked(
                    doc_page,
                    content_hash=content_hash,
                    ocr_status=DocumentPageRevision.OcrStatus.PENDING,
                )
                job, _created = IngestionService.enqueue_ocr_job(doc_page, revision)

            return {
                "page_id": str(page.pk),
                "is_finalized": True,
                "already_finalized": already,
                "document_id": str(document.pk) if document else None,
                "revision_id": str(revision.pk) if revision else None,
                "job_id": str(job.pk) if job else None,
            }

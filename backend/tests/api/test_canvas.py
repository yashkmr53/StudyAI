"""Canvas API tests: sessions, pages, strokes, fencing, idempotency, finalize.

Fencing semantics (§5) and idempotent replay (§4) are exercised through the
real API. Concurrency is limited by SQLite in unit settings (select_for_update
is a no-op there); fencing logic itself is row-state based and fully covered.
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.canvas.models import CanvasPage, CanvasSession, CanvasStroke
from apps.profiles.models import Profile
from tests.api.utils import authenticated_client

LOCK_TTL = 90


def lock_payload(device_id: str, generation: int) -> dict:
    return {"device_id": device_id, "lock_generation": generation}


class CanvasBaseTestCase(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.alice_profile = Profile.objects.get(user__email="alice@example.com")
        self.device_a = "device-aaaa"
        self.device_b = "device-bbbb"

    def create_session(self, client=None, device_id=None):
        client = client or self.alice
        response = client.post(
            "/api/v1/canvas/sessions",
            {"profile": str(self.alice_profile.id), "device_id": device_id or self.device_a},
            content_type="application/json",
        )
        assert response.status_code == 201, response.content
        return response.json()

    def create_page(self, session, page_number=1, device_id=None, generation=1):
        response = self.alice.post(
            "/api/v1/canvas/pages",
            {
                "session": session["id"],
                "page_number": page_number,
                "device_id": device_id or self.device_a,
                "lock_generation": generation,
            },
            content_type="application/json",
        )
        return response

    def push_strokes(self, page_id, device_id=None, generation=1, keys=("k1",)):
        strokes = [
            {"sequence_order": i, "points": [1.0, 2.0, 3.0, 4.0], "client_idempotency_key": k}
            for i, k in enumerate(keys)
        ]
        return self.alice.post(
            f"/api/v1/canvas/pages/{page_id}/strokes",
            {**lock_payload(device_id or self.device_a, generation), "strokes": strokes},
            content_type="application/json",
        )


class SessionTests(CanvasBaseTestCase):
    def test_create_session_holds_initial_lock(self):
        data = self.create_session()
        self.assertEqual(data["lock_holder"], self.device_a)
        self.assertEqual(data["lock_generation"], 1)
        self.assertIsNotNone(data["lock_expires_at"])

    def test_create_session_in_foreign_profile_forbidden(self):
        response = self.bob.post(
            "/api/v1/canvas/sessions",
            {"profile": str(self.alice_profile.id), "device_id": self.device_b},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_get_session_returns_pages(self):
        session = self.create_session()
        self.create_page(session)
        data = self.alice.get(f"/api/v1/canvas/sessions/{session['id']}").json()
        self.assertEqual(len(data["pages"]), 1)
        self.assertEqual(data["pages"][0]["page_number"], 1)

    def test_sessions_listing_is_user_scoped(self):
        self.create_session()
        listing = self.bob.get("/api/v1/canvas/sessions").json()
        self.assertEqual(listing["count"], 0)


class PageTests(CanvasBaseTestCase):
    def test_create_page_requires_valid_lock(self):
        session = self.create_session()
        response = self.create_page(session, generation=99)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "SESSION_LOCK_LOST")

    def test_create_duplicate_page_number_rejected(self):
        session = self.create_session()
        self.assertEqual(self.create_page(session).status_code, 201)
        response = self.create_page(session)
        self.assertEqual(response.status_code, 422)

    def test_foreign_user_page_access_404(self):
        session = self.create_session()
        page_response = self.create_page(session)
        page_id = page_response.json()["id"]
        response = self.bob.get(f"/api/v1/canvas/pages/{page_id}")
        self.assertEqual(response.status_code, 404)


class StrokeFencingTests(CanvasBaseTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.create_session()
        self.page = self.create_page(self.session).json()

    def test_append_strokes_with_valid_lock(self):
        response = self.push_strokes(self.page["id"], keys=("k1", "k2"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["created"]), 2)
        self.assertEqual(body["duplicate_keys"], [])
        self.assertEqual(CanvasStroke.objects.filter(page_id=self.page["id"]).count(), 2)

    def test_replayed_idempotency_keys_are_duplicates_not_new_rows(self):
        self.push_strokes(self.page["id"], keys=("k1",))
        response = self.push_strokes(self.page["id"], keys=("k1", "k2"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["created"]), 1)          # only k2 new
        self.assertEqual(body["duplicate_keys"], ["k1"])
        self.assertEqual(CanvasStroke.objects.filter(page_id=self.page["id"]).count(), 2)

    def test_stale_generation_rejected_with_session_lock_lost(self):
        response = self.push_strokes(self.page["id"], generation=42)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "SESSION_LOCK_LOST")
        self.assertEqual(CanvasStroke.objects.count(), 0)

    def test_wrong_device_rejected_even_with_matching_generation(self):
        response = self.push_strokes(self.page["id"], device_id=self.device_b)
        self.assertEqual(response.status_code, 409)

    def test_expired_lock_rejected(self):
        CanvasSession.objects.update(lock_expires_at=timezone.now() - timezone.timedelta(seconds=1))
        response = self.push_strokes(self.page["id"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "SESSION_LOCK_LOST")

    def test_missing_client_key_validation_error(self):
        response = self.alice.post(
            f"/api/v1/canvas/pages/{self.page['id']}/strokes",
            {
                **lock_payload(self.device_a, 1),
                "strokes": [{"points": [1.0, 2.0], "sequence_order": 0}],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)


class HeartbeatTakeoverTests(CanvasBaseTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.create_session()
        self.page = self.create_page(self.session).json()

    def test_heartbeat_refreshes_expiry(self):
        old_expiry = CanvasSession.objects.get(pk=self.session["id"]).lock_expires_at
        response = self.alice.post(
            f"/api/v1/canvas/sessions/{self.session['id']}/heartbeat",
            lock_payload(self.device_a, 1),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        new_expiry = CanvasSession.objects.get(pk=self.session["id"]).lock_expires_at
        self.assertGreater(new_expiry, old_expiry)

    def test_heartbeat_with_stale_generation_fails(self):
        response = self.alice.post(
            f"/api/v1/canvas/sessions/{self.session['id']}/heartbeat",
            lock_payload(self.device_a, 7),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_takeover_increments_generation_and_fences_old_device(self):
        response = self.alice.post(
            f"/api/v1/canvas/sessions/{self.session['id']}/takeover",
            {"device_id": self.device_b},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["lock_generation"], 2)
        self.assertEqual(data["lock_holder"], self.device_b)

        stale = self.push_strokes(self.page["id"], device_id=self.device_a, generation=1)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "SESSION_LOCK_LOST")

        fresh = self.push_strokes(self.page["id"], device_id=self.device_b, generation=2)
        self.assertEqual(fresh.status_code, 200)


class FinalizeTests(CanvasBaseTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.create_session()
        self.page = self.create_page(self.session).json()

    def finalize(self, device_id=None, generation=1):
        return self.alice.post(
            f"/api/v1/canvas/pages/{self.page['id']}/finalize",
            lock_payload(device_id or self.device_a, generation),
            content_type="application/json",
        )

    def test_finalize_marks_page_immutably(self):
        response = self.finalize()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_finalized"])
        page = CanvasPage.objects.get(pk=self.page["id"])
        self.assertTrue(page.is_finalized)
        self.assertIsNotNone(page.finalized_at)

    def test_finalize_is_idempotent(self):
        first = self.finalize()
        second = self.finalize()
        self.assertEqual(first.status_code, second.status_code == 200 and first.status_code)
        self.assertTrue(second.json()["already_finalized"])

    def test_writes_after_finalize_conflict(self):
        self.finalize()
        response = self.push_strokes(self.page["id"], keys=("k9",))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "REVISION_CONFLICT")

    def test_finalize_requires_lock(self):
        response = self.finalize(generation=5)
        self.assertEqual(response.status_code, 409)

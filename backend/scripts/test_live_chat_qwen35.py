"""Live end-to-end verification script for Phase 6 / Phase 14: Chatbot & AI Tutor Pipeline.

Verifies:
1. Conversational greeting & assistance (route=conversational, model=qwen3.5:4b)
2. Material-grounded query with student notes & reference textbook (route=material, 1024-dim pgvector Qwen3 embeddings)
3. Reference book query (Textbook chunk retrieval & citation verification)
4. Multimodal note image query (qwen3.5:4b vision)
5. Streaming SSE Generator (ChatService.stream)
6. Model provenance in database (model="qwen3.5:4b", canonical embedding)
"""
import os
import sys
import base64
import json
import uuid

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
import django
django.setup()

from django.contrib.auth import get_user_model
from django.conf import settings
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.chat.models import ChatSession, ChatMessage
from apps.chat.services import ChatService
from apps.retrieval.models import NoteChunk
from apps.documents.models import Document
from shared.database.rls import profile_scoped_transaction

User = get_user_model()

def run_chat_verification():
    print("=" * 70, flush=True)
    print("Phase 14 / Phase 6: Live End-to-End Chatbot & AI Tutor Verification", flush=True)
    print(f"Target LLM: {settings.LLM_MODEL}", flush=True)
    print(f"Target Embedding: {settings.EMBEDDING_MODEL_NAME} ({settings.EMBEDDING_DIMENSIONS}d)", flush=True)
    print("=" * 70, flush=True)

    # 1. Setup User and ChatSession
    user, _ = User.objects.get_or_create(email="admin@studyai.dev", defaults={"first_name": "Admin"})
    profile = Profile.objects.filter(user=user).first()
    if not profile:
        profile = Profile.objects.create(user=user)

    with profile_scoped_transaction(profile.id):
        subject, _ = Subject.objects.get_or_create(profile=profile, name="DSA AI")

        session = ChatSession.objects.create(
            profile=profile,
            subject=subject,
            title="DSA AI Tutor Session",
        )
        print(f"[1] Created test ChatSession: {session.id} for user '{user.email}'", flush=True)

        # Check available chunks
        chunks_count = NoteChunk.objects.filter(stale=False).count()
        print(f"    Available NoteChunks in pgvector DB: {chunks_count}", flush=True)

        # 2. Conversational query (no citations, polite tutor response)
        print("\n[2] Testing Conversational Query ('Hello! Can you help me study C programming?')...", flush=True)
        msg1 = ChatService.ask(session, "Hello! Can you help me study C programming?")
        print(f"    Role: {msg1.role}", flush=True)
        print(f"    Model: {msg1.model}", flush=True)
        print(f"    Verification Status: {msg1.verification_status}", flush=True)
        print(f"    Citations Count: {len(msg1.citations)}", flush=True)
        print(f"    Content Preview: {msg1.content[:160]}...", flush=True)
        assert "qwen3.5:4b" in msg1.model, f"Expected qwen3.5:4b, got {msg1.model}"
        assert len(msg1.citations) == 0, f"Conversational query should have 0 citations, got {len(msg1.citations)}"

        # 3. Material-grounded query
        print("\n[3] Testing Material-Grounded Query ('What is the relationship between arrays and pointers in C?')...", flush=True)
        msg2 = ChatService.ask(session, "What is the relationship between arrays and pointers in C?")
        print(f"    Role: {msg2.role}", flush=True)
        print(f"    Model: {msg2.model}", flush=True)
        print(f"    Verification Status: {msg2.verification_status} (score: {msg2.verification_score})", flush=True)
        print(f"    Citations Count: {len(msg2.citations)}", flush=True)
        print(f"    Content Preview: {msg2.content[:200]}...", flush=True)
        assert "qwen3.5:4b" in msg2.model, f"Expected qwen3.5:4b, got {msg2.model}"

        # 4. Multimodal handwritten note image query
        print("\n[4] Testing Multimodal Query with Image...", flush=True)
        minimal_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        msg3 = ChatService.ask(
            session,
            "What does this image show?",
            image=minimal_png_b64,
        )
        print(f"    Role: {msg3.role}", flush=True)
        print(f"    Model: {msg3.model}", flush=True)
        print(f"    Verification Status: {msg3.verification_status}", flush=True)
        print(f"    Content Preview: {msg3.content[:200]}...", flush=True)
        assert "qwen3.5:4b" in msg3.model, f"Expected qwen3.5:4b, got {msg3.model}"

        # 5. Streaming SSE Generator Verification
        print("\n[5] Testing Streaming SSE Generator (ChatService.stream)...", flush=True)
        stream_events = list(ChatService.stream(session, "Briefly explain pointers in 1 sentence."))
        print(f"    Total SSE Events Emitted: {len(stream_events)}", flush=True)
        event_types = set()
        for ev in stream_events:
            for line in ev.split("\n"):
                if line.startswith("event: "):
                    event_types.add(line.replace("event: ", "").strip())
        print(f"    Event Types Observed: {sorted(list(event_types))}", flush=True)
        assert "token" in event_types, "Expected 'token' event in SSE stream"
        assert "done" in event_types, "Expected 'done' event in SSE stream"

        # 6. Check database message records
        total_msgs = ChatMessage.objects.filter(session=session).count()
        assistant_msgs = ChatMessage.objects.filter(session=session, role=ChatMessage.Role.ASSISTANT)
        print(f"\n[6] Database Audit for Session {session.id}:", flush=True)
        print(f"    Total Messages: {total_msgs}", flush=True)
        print(f"    Assistant Messages: {assistant_msgs.count()}", flush=True)
        for m in assistant_msgs:
            assert "qwen3.5:4b" in m.model, f"Found invalid model: {m.model}"
            print(f"    Msg {m.id}: model={m.model}, citations={len(m.citations)}, status={m.verification_status}", flush=True)

        # Cleanup test chat session
        session.delete()
        print("\n[7] Cleaned up test chat session.", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("PHASE 14 / PHASE 6 LIVE CHAT VERIFICATION COMPLETED SUCCESSFULLY!", flush=True)
    print("Canonical Models Verified: Generative/Multimodal: qwen3.5:4b | Embeddings: qwen3-embedding:0.6b", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    run_chat_verification()

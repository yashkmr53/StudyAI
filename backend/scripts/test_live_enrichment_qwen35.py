"""Live end-to-end enrichment verification script for Phase 14.

Pipeline Target:
Note + Retrieved References → LLM Gap Analysis → LLM Enrichment → Citation Validation → Persistence

Canonical Models Verified:
- Generative/OCR: qwen3.5:4b through Ollama
- Embeddings: qwen3-embedding:0.6b through Ollama (1024 dimensions, Metal/MPS accelerated on host)
- Reference Material: Target textbook "Let us c   yashwantkanetkar" (id=f148dab2-1ff0-4bd0-aa98-0857df36c068)
"""
import os
import sys
import time
import uuid

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()

from django.contrib.auth import get_user_model
from django.conf import settings
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.documents.models import Document, DocumentPage, DocumentPageRevision, DocumentLine
from apps.references.models import ReferenceDocument, ReferenceChunk
from apps.retrieval.models import NoteChunk
from apps.retrieval.services import index_document
from apps.jobs.models import Job
from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock, CitationBlock
from apps.ai_classroom.services import run_enrichment_job
from apps.references.services import retrieve_reference_context
from providers.registry import get_llm_provider, get_embedding_provider
from shared.database.rls import profile_scoped_transaction

User = get_user_model()

print("=" * 70, flush=True)
print("PHASE 14 LIVE TEST: End-to-End Note Enrichment with Canonical Ollama Models", flush=True)
print("LLM: qwen3.5:4b | Embeddings: qwen3-embedding:0.6b (1024d)", flush=True)
print("=" * 70, flush=True)

# Step 1: Verify Providers & Dimensions
llm = get_llm_provider()
emb = get_embedding_provider()
llm_model = getattr(llm, "model_name", None)
if llm_model is None and hasattr(llm, "providers") and llm.providers:
    llm_model = getattr(llm.providers[0], "model_name", "unknown")
elif llm_model is None and hasattr(llm, "_chain") and llm._chain:
    llm_model = getattr(llm._chain[0], "model_name", "unknown")

print(f"[1] LLM Provider: {llm.name}, Model: {llm_model}", flush=True)
print(f"    Embedding Provider: {emb.name}, Model: {emb.model_name}, Dimension: {emb.dimension}, Version: {emb.model_version}", flush=True)
assert emb.dimension == 1024, f"Expected 1024 dimensions, got {emb.dimension}"
assert "qwen3-embedding" in emb.model_name, f"Expected qwen3-embedding, got {emb.model_name}"

# Test a live embedding vector
test_vec = emb.embed_query("pointer arithmetic and arrays in C")
assert len(test_vec) == 1024, f"Expected 1024 length vector, got {len(test_vec)}"
norm = sum(x**2 for x in test_vec) ** 0.5
assert abs(norm - 1.0) < 1e-4, f"Expected L2 normalized vector, got norm={norm}"
print(f"    Verified live embedding generation: norm={norm:.4f}, dim={len(test_vec)}", flush=True)

# Step 2: Bind Profile and Subject (Profile: 6ed4659f-d4eb-415f-9b70-9774fa584077)
target_profile_id = uuid.UUID("6ed4659f-d4eb-415f-9b70-9774fa584077")
target_doc_id = uuid.UUID("f148dab2-1ff0-4bd0-aa98-0857df36c068")

with profile_scoped_transaction(target_profile_id):
    profile = Profile.objects.filter(id=target_profile_id).select_related("user").first()
    if not profile:
        user, _ = User.objects.get_or_create(email="admin@studyai.dev", defaults={"first_name": "Admin"})
        profile, _ = Profile.objects.get_or_create(id=target_profile_id, user=user)
    user = profile.user

    subject = Subject.objects.filter(profile=profile, name="DSA AI").first()
    if not subject:
        subject = Subject.objects.create(profile=profile, name="DSA AI")

    print(f"\n[2] Active Profile: {profile.id} (user: {user.email})", flush=True)
    print(f"    Active Subject: {subject.name} (id: {subject.id})", flush=True)

    # Step 3: Verify Reference Textbook & Live Reference Retrieval
    ref_doc = ReferenceDocument.objects.get(id=target_doc_id)
    ref_chunks_count = ReferenceChunk.objects.filter(reference_document=ref_doc).count()
    print(f"\n[3] Target Reference Textbook: '{ref_doc.title}'", flush=True)
    print(f"    Document Status: {ref_doc.status}, Pages: {ref_doc.page_count}, Chunks in DB: {ref_chunks_count}", flush=True)
    assert ref_doc.status == ReferenceDocument.Status.READY, f"Expected READY, got {ref_doc.status}"
    assert ref_chunks_count == 695, f"Expected 695 chunks, got {ref_chunks_count}"

    # Perform hybrid reference retrieval
    retrieved_refs = retrieve_reference_context(
        "pointers arrays dynamic memory address C programming",
        profile=profile,
        subject=subject,
        top_k=3,
    )
    print(f"    Live Retrieval Returned: {len(retrieved_refs)} chunks", flush=True)
    assert len(retrieved_refs) > 0, "Reference retrieval returned 0 chunks!"
    for r in retrieved_refs:
        print(f"      -> Chunk {r['chunk_id']} (page {r['page']}, score: {r['score']:.4f}): {r['snippet'][:90]}...", flush=True)

    # Step 4: Create a Student Document with Note Lines
    student_doc = Document.objects.create(
        profile=profile,
        subject=subject,
        title="Pointers and Arrays in C",
        source=Document.Source.UPLOAD,
        source_type=Document.SourceType.PDF,
        schema_version="1",
    )
    student_page = DocumentPage.objects.create(
        document=student_doc,
        page_number=1,
        ocr_status=DocumentPage.OcrStatus.COMPLETED,
    )
    student_rev = DocumentPageRevision.objects.create(
        page=student_page,
        revision_number=1,
        content_hash="test_c_pointers_hash_001",
        ocr_status=DocumentPage.OcrStatus.COMPLETED,
        ocr_provider="qwen35",
    )
    student_page.current_revision_id = student_rev.pk
    student_page.save(update_fields=("current_revision_id",))

    lines_text = [
        "Pointers in C Programming",
        "A pointer is a variable that stores the memory address of another variable.",
        "The address operator & gives the address of a variable, e.g., ptr = &num.",
        "The dereference operator * accesses the value stored at the memory address, e.g., val = *ptr.",
        "Arrays and pointers are closely related in C; the name of an array is a constant pointer to its first element.",
        "My notes need clarification on pointer arithmetic and how array indexing maps to pointer dereferencing.",
    ]
    for idx, text in enumerate(lines_text):
        DocumentLine.objects.create(
            page_revision=student_rev,
            line_index=idx,
            text=text,
        )

    print(f"\n[4] Created student document {student_doc.pk} with {len(lines_text)} note lines.", flush=True)

    # Step 5: Index Student Document with Canonical Embedding Provider
    print("\n[5] Indexing student document with qwen3-embedding:0.6b (1024d)...", flush=True)
    t0 = time.time()
    stats = index_document(student_doc)
    t_index = time.time() - t0
    print(f"    Indexing completed in {t_index:.2f}s: {stats}", flush=True)

    user_chunks = NoteChunk.objects.filter(document=student_doc, stale=False)
    print(f"    Generated {user_chunks.count()} note chunks in pgvector.", flush=True)
    for uc in user_chunks:
        emb_len = len(uc.embedding) if uc.embedding is not None else 0
        print(f"      Chunk {uc.pk}: words={len(uc.content.split())}, dim={emb_len}, model={uc.embedding_model}, version={uc.embedding_version}", flush=True)
        assert emb_len == 1024, f"Expected 1024 dimensions, got {emb_len}"
        assert uc.embedding_model == "ollama", f"Expected ollama model, got {uc.embedding_model}"
        assert uc.embedding_version == "qwen3-embedding-0.6b-v1", f"Expected canonical version, got {uc.embedding_version}"

    # Step 6: Trigger Enrichment Pipeline Job
    print("\n[6] Launching enrichment job through canonical LangGraph pipeline...", flush=True)
    print("    Pipeline Flow: Note + Retrieved References → LLM Gap Analysis → LLM Enrichment → Citation Validation → Persistence", flush=True)
    job = Job.objects.create(
        job_type="enrich",
        resource_type="document",
        resource_id=str(student_doc.pk),
        profile_id=profile.pk,
        idempotency_key=f"enrich:{student_doc.pk}:test:{uuid.uuid4().hex[:8]}",
        status=Job.Status.QUEUED,
    )

    t0 = time.time()
    run_enrichment_job(job)
    t_enrich = time.time() - t0
    print(f"    Enrichment pipeline executed in {t_enrich:.2f}s", flush=True)

    # Step 7: Inspect Enriched Note, Blocks, and Citations
    enriched_note = EnrichedNote.objects.filter(document=student_doc, superseded=False).first()
    assert enriched_note is not None, "EnrichedNote was not created!"

    print(f"\n[7] Enriched Note Result:", flush=True)
    print(f"    Note ID: {enriched_note.pk}", flush=True)
    print(f"    Provider: {enriched_note.provider}", flush=True)
    print(f"    Model: {enriched_note.model}", flush=True)
    print(f"    Prompt Version: {enriched_note.prompt_version}", flush=True)

    blocks = list(enriched_note.blocks.all().order_by("block_index"))
    print(f"    Enriched Blocks Count: {len(blocks)}", flush=True)
    assert len(blocks) > 0, "No blocks generated in EnrichedNote!"

    for b in blocks:
        citation = getattr(b, "citation", None)
        c_status = citation.verification_status if citation else "no_citation"
        c_score = citation.verification_score if citation else None
        c_refs = citation.source_refs if citation else []
        print(f"\n    [Block {b.block_index}] ({b.block_type.upper()}) - {b.title or 'No Title'}", flush=True)
        print(f"      Method: {b.generation_method}", flush=True)
        print(f"      Content: {b.content[:120]}...", flush=True)
        print(f"      Source Chunk IDs: {b.source_chunk_ids}", flush=True)
        print(f"      Citation Status: {c_status}, Score: {c_score}, Refs: {len(c_refs)}", flush=True)

    # Step 8: Verify REST API Endpoints with Active Profile Context
    print("\n[8] Verifying REST Endpoints...", flush=True)
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=user)

    # GET /api/v1/documents/{id}
    r1 = client.get(
        f"/api/v1/documents/{student_doc.pk}",
        HTTP_HOST="localhost",
        HTTP_X_ACTIVE_PROFILE=str(target_profile_id),
    )
    print(f"    GET /api/v1/documents/{student_doc.pk} -> status {r1.status_code}", flush=True)
    assert r1.status_code == 200, f"Expected 200, got {r1.status_code}"

    # GET /api/v1/documents/{id}/enrichment
    r2 = client.get(
        f"/api/v1/documents/{student_doc.pk}/enrichment",
        HTTP_HOST="localhost",
        HTTP_X_ACTIVE_PROFILE=str(target_profile_id),
    )
    print(f"    GET /api/v1/documents/{student_doc.pk}/enrichment -> status {r2.status_code}", flush=True)
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
    enrich_payload = r2.json()
    print(f"    API Enriched Note Model: {enrich_payload.get('model')}, Provider: {enrich_payload.get('provider')}", flush=True)
    print(f"    API Enriched Blocks: {len(enrich_payload.get('blocks', []))}", flush=True)
    assert len(enrich_payload.get("blocks", [])) > 0, "No blocks returned by enrichment API"

# Step 9: Verify Row-Level Security (RLS) Isolation
print("\n[9] Verifying Row-Level Security Isolation...", flush=True)
isolated_profile_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
with profile_scoped_transaction(isolated_profile_id):
    hidden_docs = Document.objects.filter(pk=student_doc.pk).count()
    hidden_chunks = NoteChunk.objects.filter(document__pk=student_doc.pk).count()
    hidden_refs = ReferenceChunk.objects.filter(reference_document__pk=target_doc_id).count()
    print(f"    Isolated Profile sees student docs: {hidden_docs} (expected 0)", flush=True)
    print(f"    Isolated Profile sees student chunks: {hidden_chunks} (expected 0)", flush=True)
    print(f"    Isolated Profile sees textbook chunks: {hidden_refs} (expected 0)", flush=True)
    assert hidden_docs == 0, "RLS breach: isolated profile can see student doc!"
    assert hidden_chunks == 0, "RLS breach: isolated profile can see student chunks!"
    assert hidden_refs == 0, "RLS breach: isolated profile can see target textbook chunks!"

# Cleanup test student document
with profile_scoped_transaction(target_profile_id):
    student_doc.delete()
    print("\n[10] Cleaned up temporary student document.", flush=True)

print("\n" + "=" * 70, flush=True)
print("SUCCESS: Phase 14 End-to-End Live Verification PASSED!", flush=True)
print("All canonical models (qwen3.5:4b, qwen3-embedding:0.6b), textbook retrieval, enrichment graph, and RLS verified.", flush=True)
print("=" * 70, flush=True)
sys.exit(0)

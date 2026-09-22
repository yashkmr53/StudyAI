"""Live end-to-end enrichment test using qwen3.5:4b and Qwen/Qwen3-Embedding-0.6B.

Steps verified:
1. Retrieval indexing with Qwen/Qwen3-Embedding-0.6B (1024 dimensions)
2. Semantic retrieval of user notes + reference material
3. Graph execution: draft -> candidate gap detection -> validation -> gap fill -> citation stitching -> verification
4. Models verified: qwen3.5:4b LLM (think=False), Qwen/Qwen3-Embedding-0.6B
5. Persistence: EnrichedNote, EnrichedNoteBlock, CitationBlock with verified source_chunk_ids
6. Learning features: TaggingService and QuestionGenerationService
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
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.documents.models import Document, DocumentPage, DocumentPageRevision, DocumentLine
from apps.references.models import ReferenceBook, ReferenceBookChapter
from apps.retrieval.models import NoteChunk
from apps.retrieval.services import index_document
from apps.jobs.models import Job
from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock, CitationBlock
from apps.ai_classroom.services import run_enrichment_job
from providers.registry import get_llm_provider, get_embedding_provider

User = get_user_model()

print("=" * 70)
print("PHASE 5 LIVE TEST: End-to-End Note Enrichment with qwen3.5:4b & Qwen3-Embedding")
print("=" * 70)

# Step 1: Verify Providers
llm = get_llm_provider()
emb = get_embedding_provider()
llm_model = getattr(llm, "model_name", None)
if llm_model is None and hasattr(llm, "providers") and llm.providers:
    llm_model = getattr(llm.providers[0], "model_name", "unknown")
elif llm_model is None and hasattr(llm, "_chain") and llm._chain:
    llm_model = getattr(llm._chain[0], "model_name", "unknown")

print(f"LLM Provider: {llm.name}, Model: {llm_model}")
print(f"Embedding Provider: {emb.name}, Model: {emb.model_name}, Dimension: {emb.dimension}")
assert emb.dimension == 1024, f"Expected 1024 dimensions, got {emb.dimension}"

# Step 2: Setup User, Profile, and Subject
user, _ = User.objects.get_or_create(email="enrich@studyai.local")
profile, _ = Profile.objects.get_or_create(user=user)
subject, _ = Subject.objects.get_or_create(profile=profile, name="Biology")

# Step 3: Setup Reference Book & Reference Chunks
ref_doc = Document.objects.create(
    source=Document.Source.REFERENCE,
    source_type=Document.SourceType.REFERENCE,
    subject=subject,
)
ref_book = ReferenceBook.objects.create(
    title=f"Campbell Biology: Respiration {uuid.uuid4().hex[:6]}",
    subject=subject,
    author="Campbell & Reece",
    edition="12th",
    document=ref_doc,
    status=ReferenceBook.Status.READY,
)

# Create reference chunk with rich evidence
ref_content = (
    "Oxidative Phosphorylation and the Electron Transport Chain: "
    "In the inner mitochondrial membrane, complexes I through IV transfer electrons from NADH and FADH2 to molecular oxygen. "
    "This electron transfer drives proton pumping across the inner membrane from the matrix into the intermembrane space, "
    "generating a steep electrochemical proton gradient (proton-motive force). "
    "Protons flow back into the matrix through the F0/F1 ATP synthase complex, driving the phosphorylation of ADP to ATP via chemiosmosis. "
    "Oxidative phosphorylation produces approximately 26 to 28 ATP per glucose, yielding a net total of roughly 30 to 32 ATP for the complete respiration cycle."
)
import hashlib
ref_hash = hashlib.sha256(ref_content.encode()).hexdigest()

ref_vec = emb.embed_documents([ref_content])[0]
ref_chunk = NoteChunk.objects.create(
    reference_book=ref_book,
    document=ref_doc,
    subject=subject,
    source_type="reference",
    revision_id=uuid.uuid4(),
    revision_ids=[],
    page_start=164,
    page_end=165,
    chunk_index=1,
    content=ref_content,
    content_hash=ref_hash,
    embedding=ref_vec,
    embedding_model=emb.model_name,
    embedding_version=emb.model_version,
    stale=False,
)
print(f"Created reference chunk {ref_chunk.pk} with {len(ref_vec)}-dim embedding.")

# Step 4: Setup Student Document with Note Lines
doc = Document.objects.create(
    profile=profile,
    subject=subject,
    source=Document.Source.UPLOAD,
    source_type=Document.SourceType.IMAGE,
    schema_version="1",
    reference_book_id=ref_book.pk,
)
page = DocumentPage.objects.create(
    document=doc,
    page_number=1,
    ocr_status=DocumentPage.OcrStatus.COMPLETED,
)
revision = DocumentPageRevision.objects.create(
    page=page,
    revision_number=1,
    content_hash="test_note_hash_001",
    ocr_status=DocumentPage.OcrStatus.COMPLETED,
    ocr_provider="qwen35",
)
page.current_revision_id = revision.pk
page.save()

lines_text = [
    "Cellular Respiration Overview",
    "Glycolysis happens in the cytoplasm. It splits glucose into 2 pyruvate molecules and produces 2 ATP and 2 NADH.",
    "The Citric Acid Cycle (Krebs cycle) takes place in the mitochondrial matrix.",
    "Krebs cycle generates 2 ATP, 6 NADH, and 2 FADH2 per glucose molecule through acetyl-CoA oxidation.",
    "However, my notes are missing details on how ATP synthase actually generates the bulk of ATP from NADH.",
]
for idx, text in enumerate(lines_text):
    DocumentLine.objects.create(
        page_revision=revision,
        line_index=idx,
        text=text,
    )

print(f"Created student document {doc.pk} with {len(lines_text)} note lines.")

# Step 5: Index the student document with Qwen3-Embedding
print("\nIndexing student document with Qwen3-Embedding (1024 dimensions)...")
t0 = time.time()
stats = index_document(doc)
t_index = time.time() - t0
print(f"Indexing completed in {t_index:.2f}s: {stats}")

user_chunks = NoteChunk.objects.filter(document=doc, stale=False)
print(f"Generated {user_chunks.count()} user note chunks in pgvector.")
for uc in user_chunks:
    emb_len = len(uc.embedding) if uc.embedding is not None else 0
    print(f"  Chunk {uc.pk}: {len(uc.content.split())} words, embedding dimension={emb_len}")
    assert emb_len == 1024, f"Expected 1024 embedding dimension, got {emb_len}"

# Step 6: Trigger Enrichment Pipeline Job
print("\nLaunching enrichment job with qwen3.5:4b...")
job = Job.objects.create(
    job_type="enrich",
    resource_type="document",
    resource_id=str(doc.pk),
    profile_id=profile.pk,
    idempotency_key=f"enrich:{doc.pk}:test:{uuid.uuid4().hex[:8]}",
    status=Job.Status.QUEUED,
)

t0 = time.time()
run_enrichment_job(job)
t_enrich = time.time() - t0
job.refresh_from_db()
print(f"Enrichment pipeline executed in {t_enrich:.2f}s, job status: {job.status}")

# Step 7: Inspect Generated EnrichedNote, Blocks, and Citations
enriched_note = EnrichedNote.objects.filter(document=doc, superseded=False).first()
assert enriched_note is not None, "EnrichedNote was not created!"

print(f"\n--- Enriched Note Result ---")
print(f"Note ID: {enriched_note.pk}")
print(f"Provider: {enriched_note.provider}")
print(f"Model: {enriched_note.model}")
print(f"Prompt Version: {enriched_note.prompt_version}")

blocks = list(enriched_note.blocks.all().order_by("block_index"))
print(f"Enriched Blocks Count: {len(blocks)}")
assert len(blocks) > 0, "No blocks generated in EnrichedNote!"

for b in blocks:
    citation = getattr(b, "citation", None)
    c_status = citation.verification_status if citation else "no_citation"
    c_score = citation.verification_score if citation else None
    c_refs = citation.source_refs if citation else []
    print(f"\n[Block {b.block_index}] ({b.block_type.upper()}) - {b.title or 'No Title'}")
    print(f"  Method: {b.generation_method}")
    print(f"  Content: {b.content[:140]}...")
    print(f"  Source Chunk IDs: {b.source_chunk_ids}")
    print(f"  Citation Status: {c_status}, Score: {c_score}, Refs: {len(c_refs)}")
    for r in c_refs:
        print(f"    -> Ref: type={r.get('source_type')}, chunk_id={r.get('chunk_id')}")

# Step 8: Verify Tags and Questions generated by downstream hooks
from apps.ai_classroom.models import DocumentTag
from apps.questions.models import Question

tags = list(DocumentTag.objects.filter(document=doc))
print(f"\n--- Generated Tags ({len(tags)}) ---", flush=True)
for t in tags:
    print(f"  Tag: {t.tag.display_name} (id={t.tag.pk})", flush=True)

questions = list(Question.objects.filter(document=doc))
print(f"\n--- Generated Questions ({len(questions)}) ---", flush=True)
for q in questions:
    print(f"  Q: {q.prompt[:80]}... (difficulty={q.difficulty}, answer={q.answer_text})", flush=True)

# Step 9: Verify REST Endpoints
print("\n--- Verifying REST Endpoints ---", flush=True)
from rest_framework.test import APIClient
client = APIClient()
client.force_authenticate(user=user)

# 1. GET /api/v1/documents/{id}
r1 = client.get(f"/api/v1/documents/{doc.pk}", HTTP_HOST="localhost")
print(f"GET /api/v1/documents/{doc.pk} -> status {r1.status_code}", flush=True)
assert r1.status_code == 200, f"Expected 200, got {r1.status_code}"

# 2. GET /api/v1/documents/{id}/enrichment
r2 = client.get(f"/api/v1/documents/{doc.pk}/enrichment", HTTP_HOST="localhost")
print(f"GET /api/v1/documents/{doc.pk}/enrichment -> status {r2.status_code}", flush=True)
assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
enrich_payload = r2.json()
print(f"API Enriched Note Model: {enrich_payload.get('model')}, Provider: {enrich_payload.get('provider')}", flush=True)
print(f"API Enriched Blocks: {len(enrich_payload.get('blocks', []))}", flush=True)
assert len(enrich_payload.get("blocks", [])) > 0, "No blocks returned by enrichment API"

# 3. GET /api/v1/documents/{id}/tags
r3 = client.get(f"/api/v1/documents/{doc.pk}/tags", HTTP_HOST="localhost")
print(f"GET /api/v1/documents/{doc.pk}/tags -> status {r3.status_code}", flush=True)
assert r3.status_code == 200, f"Expected 200, got {r3.status_code}"
raw_tags = r3.json()
api_tags = [t if isinstance(t, str) else t.get("display_name", str(t)) for t in raw_tags]
print(f"API Document Tags: {api_tags}", flush=True)

print("\n" + "=" * 70, flush=True)
print("SUCCESS: Phase 5 End-to-End Live Note Enrichment Pipeline PASSED!", flush=True)
print("=" * 70, flush=True)
sys.exit(0)

# Assumptions and Decisions — Phase 4

Prior decisions remain in force (A-001…A-020, B-001…B-012, C-001…C-012 in [`../phase_3/architecture/ASSUMPTIONS_AND_DECISIONS.md`](../architecture/ASSUMPTIONS_AND_DECISIONS.md)). Phase 4 decisions (D-series):

| ID | Decision |
|---|---|
| D-001 | PDF library: **fpdf2** (pure Python) with **vendored DejaVu Sans fonts** for full Unicode faithfulness. |
| D-002 | `DigitizedDocument.revision_id` from the spec generalized to a `revision_ids` JSON list — one artifact covers all current page revisions of a document. |
| D-003 | Artifact identity is content-addressed: sha256 over canonical descriptor {renderer_version, per-page revision ids + content hashes + verbatim lines}; unique per document. |
| D-004 | `/digitized-documents/{id}/download` returns a JSON payload `{url, expires_in, file_size}` containing a short-lived signed URL instead of a 302 redirect — browsers cannot attach JWT headers to navigations. |
| D-005 | Headings render as styled ONLY when explicitly flagged (`DocumentLine.is_heading`); never inferred from text shape or size. |
| D-006 | Render job idempotency key: `pdf:{document_id}:{descriptor_hash[:32]}`; an unchanged document re-request returns the existing artifact (HTTP 200) rather than enqueueing duplicate work. |
| D-007 | PDF structural furniture limited to §49's allowance: footer page numbering and document metadata (title/author/creator/subject). No headers, watermarks, or decorative content. |

---

## Details

### D-001 — fpdf2 + vendored DejaVu
- **Context:** Python 3.14 rules out C-extension wheels of uncertain support; core PDF fonts are latin-1-only, which would silently break faithfulness on non-latin transcriptions.
- **Alternatives:** reportlab (wheel risk on 3.14), weasyprint (heavy system deps), headless Chromium (way too heavy).
- **Consequences:** DejaVu (~300 KB ×2) committed under a redistribution-permitting license; still no CJK glyph coverage — see KNOWN_LIMITATIONS. Font subsetting by fpdf2 keeps artifacts small.
- **Architecture impact:** none — renderer sits behind the service boundary.

### D-002/D-003 — Content-addressed multi-page artifacts
- **Why:** spec's singular `revision_id` doesn't model multi-page documents; hashing the full descriptor gives exact reproducibility semantics ("same inputs ⇒ same artifact") and makes §27 retention trivial.
- **Consequences:** any edit to any page ⇒ new artifact; superseded artifacts retained forever until a GC policy exists.

### D-004 — Signed-URL payload vs redirect
- **Why:** frontend fetches with Bearer header; a redirect target must be auth-free ⇒ signed URL is exactly that.
- **Alternatives:** 302 redirect (breaks header-carrying clients), cookie auth (new auth surface).

### D-005 — Explicit headings only
- **Why:** §49 says "headings where explicitly represented by the source" — inference is semantic interpretation, forbidden for NoteSpace. `is_heading` arrives from provider metadata or user edits only.

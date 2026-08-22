import { useCallback, useEffect, useRef, useState } from "react";
import { documentsApi, type DigitizedInfo, type DocumentInfo, type JobInfo, type LinePayload, type PageStatus, type RevisionInfo } from "../../services/api/documents";
import { useAuthStore } from "../auth/authStore";

type Detail = {
  document: DocumentInfo;
  pages: PageStatus[];
  revisionsByPage: Record<string, RevisionInfo>;
  digitized: DigitizedInfo | null;
};

export function NotespacePage() {
  const profileId = useAuthStore((s) => s.profile?.id ?? null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshList = useCallback(async () => {
    try {
      setDocuments((await documentsApi.list()).results);
    } catch {
      setError("Could not load documents");
    }
  }, []);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  async function onUpload(file: File) {
    if (!profileId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await documentsApi.create(profileId, file.name);
      await documentsApi.uploadToSignedUrl(created.upload.url, file, file.type || "image/png");
      await documentsApi.finalizeUpload(created.document.id, created.page.id);
      await openDocument(created.document.id);
      await refreshList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function openDocument(id: string) {
    setBusy(true);
    setError(null);
    try {
      const document = await documentsApi.get(id);
      const pages = await documentsApi.pages(id);
      const revisionsByPage: Record<string, RevisionInfo> = {};
      for (const p of pages) {
        if (!p.current_revision_id) continue;
        const revs = await documentsApi.revisions(id, p.id);
        revs.sort((a, b) => b.revision_number - a.revision_number);
        if (revs[0]) revisionsByPage[p.id] = revs[0];
      }
      const digitizedList = (await documentsApi.listDigitized(id)).results;
      const digitized: Detail["digitized"] = digitizedList.length ? digitizedList[digitizedList.length - 1] : null;
      setDetail({ document, pages, revisionsByPage, digitized });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load document");
    } finally {
      setBusy(false);
    }
  }

  if (!detail) {
    return (
      <div className="placeholder">
        <h1>NoteSpace</h1>
        <p>Faithful transcription of handwritten pages into typed PDFs.</p>
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          disabled={busy || !profileId}
          onChange={(e) => e.target.files?.[0] && void onUpload(e.target.files[0])}
        />
        {busy && <p>Working…</p>}
        {error && <p className="error-text">{error}</p>}
        <h3 style={{ marginTop: "2rem" }}>Your documents</h3>
        {documents.length === 0 && <p style={{ color: "#6b7280" }}>Nothing yet.</p>}
        <ul style={{ listStyle: "none", padding: 0 }}>
          {documents.map((d) => (
            <li key={d.id} style={{ margin: "0.25rem 0" }}>
              <button onClick={() => void openDocument(d.id)}>
                {new Date(d.created_at).toLocaleString()} · {d.source}/{d.source_type}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <DocumentDetail
      detail={detail}
      onBack={() => {
        setDetail(null);
        void refreshList();
      }}
      onError={setError}
      setDetail={setDetail}
    />
  );
}

function DocumentDetail({
  detail,
  onBack,
  onError,
  setDetail,
}: {
  detail: Detail;
  onBack: () => void;
  onError: (msg: string | null) => void;
  setDetail: React.Dispatch<React.SetStateAction<Detail | null>>;
}) {
  const docId = detail.document.id;
  const [edits, setEdits] = useState<Record<string, { text: string; is_heading: boolean }[]>>({});
  const [renderJob, setRenderJob] = useState<JobInfo | null>(null);
  const [digitized, setDigitized] = useState<Detail["digitized"]>(detail.digitized);
  const [downloading, setDownloading] = useState(false);
  const [busy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => () => { if (pollRef.current) window.clearInterval(pollRef.current); }, []);

  async function saveEdit(pageId: string) {
    const lines = edits[pageId];
    if (!lines) return;
    try {
      await documentsApi.submitEdit(
        docId,
        pageId,
        lines.map((l, i) => ({ line_index: i, text: l.text, is_heading: l.is_heading })),
      );
      onError(null);
      window.location.reload(); // simplest correct state refresh for v1
    } catch (e) {
      onError(e instanceof Error ? e.message : "Save failed");
    }
  }

  function startEdit(pageId: string, lines: LinePayload[]) {
    setEdits((prev) => ({
      ...prev,
      [pageId]: lines.map((l) => ({ text: l.text, is_heading: !!l.is_heading })),
    }));
  }

  async function generatePdf() {
    setError(null);
    try {
      const res = await documentsApi.requestPdf(docId);
      if (res.digitized_document) {
        setDigitized(res.digitized_document);
        return;
      }
      if (!res.job) return;
      setRenderJob(res.job);
      pollRef.current = window.setInterval(async () => {
        const listing = await documentsApi.listDigitized(docId).catch(() => null);
        if (listing && listing.count > 0) {
          if (pollRef.current) window.clearInterval(pollRef.current);
          setRenderJob(null);
          setDigitized(listing.results[listing.results.length - 1]);
          // refresh pages (ocr_status may have changed)
          const document = await documentsApi.get(docId);
          const pages = await documentsApi.pages(docId);
          setDetail((d: Detail | null) => (d ? { ...d, document, pages } : d));
        }
      }, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "PDF request failed");
    }
  }

  async function downloadPdf() {
    if (!digitized) return;
    setDownloading(true);
    try {
      const payload = await documentsApi.getDownloadUrl(digitized.id);
      window.open(payload.url, "_blank");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="placeholder">
      <button onClick={onBack} style={{ marginBottom: "1rem" }}>← All documents</button>
      <h1>Document</h1>
      <p style={{ color: "#6b7280" }}>
        Created {new Date(detail.document.created_at).toLocaleString()} · source:{" "}
        {detail.document.source}/{detail.document.source_type}
      </p>

      {detail.pages.map((page) => {
        const rev = detail.revisionsByPage[page.id];
        const editing = edits[page.id];
        return (
          <div key={page.id} style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}>
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
              <strong>Page {page.page_number}</strong>
              <StatusChip status={page.ocr_status} />
              <span style={{ flex: 1 }} />
              {!editing && rev && (
                <button onClick={() => startEdit(page.id, rev.lines)}>Edit transcription</button>
              )}
            </div>
            {!rev && <p style={{ color: "#6b7280" }}>No revision yet.</p>}
            {rev && !editing && (
              <ol style={{ marginTop: "0.5rem" }}>
                {rev.lines.map((l) => (
                  <li key={l.line_index} style={{ fontWeight: l.is_heading ? 700 : 400 }}>
                    {l.text}
                    {l.confidence_score != null && (
                      <span style={{ color: "#9ca3af", fontSize: "0.8em" }}> ({Math.round(l.confidence_score * 100)}%)</span>
                    )}
                  </li>
                ))}
              </ol>
            )}
            {editing && (
              <div>
                {editing.map((l, i) => (
                  <div key={i} style={{ display: "flex", gap: "0.5rem", margin: "0.35rem 0" }}>
                    <input
                      style={{ flex: 1 }}
                      value={l.text}
                      onChange={(e) =>
                        setEdits((prev) => ({
                          ...prev,
                          [page.id]: prev[page.id].map((x, j) => (j === i ? { ...x, text: e.target.value } : x)),
                        }))
                      }
                    />
                    <label style={{ fontSize: "0.85rem", whiteSpace: "nowrap" }}>
                      <input
                        type="checkbox"
                        checked={l.is_heading}
                        onChange={(e) =>
                          setEdits((prev) => ({
                            ...prev,
                            [page.id]: prev[page.id].map((x, j) => (j === i ? { ...x, is_heading: e.target.checked } : x)),
                          }))
                        }
                      />{" "}
                      heading
                    </label>
                  </div>
                ))}
                <button onClick={() => void saveEdit(page.id)}>Save new revision</button>{" "}
                <button onClick={() => setEdits((prev) => ({ ...prev, [page.id]: undefined as never }))}>Cancel</button>
              </div>
            )}
          </div>
        );
      })}

      <h3>Typed PDF</h3>
      {digitized ? (
        <p>
          Ready — rendered by {digitized.renderer_version} ·{" "}
          {digitized.file_size != null && `${(digitized.file_size / 1024).toFixed(0)} KB · `}
          <button onClick={() => void downloadPdf()} disabled={downloading}>
            Download PDF
          </button>
        </p>
      ) : renderJob ? (
        <p>Rendering… ({renderJob.status})</p>
      ) : (
        <button onClick={() => void generatePdf()} disabled={busy}>
          Generate PDF
        </button>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: "#dcfce7",
    needs_review: "#fef3c7",
    failed: "#fee2e2",
    processing: "#dbeafe",
    pending: "#f3f4f6",
  };
  return (
    <span style={{ background: colors[status] ?? "#f3f4f6", padding: "0.15rem 0.5rem", borderRadius: 999, fontSize: "0.8rem" }}>
      {status}
    </span>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { Dialog, EmptyState, SkeletonRows } from "../ui/primitives";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { AlertIcon, BookIcon, PlusIcon, TrashIcon, UploadIcon } from "../ui/icons";
import { useToast } from "../ui/Toast";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { referencesApi, type ReferenceDocumentItem } from "../../services/api/references";

export function ReferenceLibraryPage() {
  const { subjectId } = useParams<{ subjectId?: string }>();
  const subjects = useWorkspaceStore((s) => s.subjects);
  const subject = subjects.find((s) => s.id === subjectId);
  const subjectName = subject?.name ?? "";
  const toast = useToast();

  const [documents, setDocuments] = useState<ReferenceDocumentItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [documentToDelete, setDocumentToDelete] = useState<ReferenceDocumentItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Poll timer ref
  const pollTimerRef = useRef<number | null>(null);

  async function fetchDocuments() {
    try {
      const data = await referencesApi.list(subjectId ? { subject: subjectId } : undefined);
      setDocuments(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reference documents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    void fetchDocuments();
  }, [subjectId]);

  // Set up polling if any document is in PENDING or PROCESSING state
  useEffect(() => {
    const hasInProgress = documents?.some((d) => d.status === "PENDING" || d.status === "PROCESSING");

    if (hasInProgress) {
      pollTimerRef.current = window.setInterval(async () => {
        try {
          const data = await referencesApi.list(subjectId ? { subject: subjectId } : undefined);
          setDocuments(data);
        } catch {
          // Keep polling silently
        }
      }, 3000);
    } else {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [documents, subjectId]);

  async function handleDelete() {
    if (!documentToDelete) return;
    setDeleting(true);
    try {
      await referencesApi.remove(documentToDelete.id);
      setDocuments((prev) => (prev ? prev.filter((d) => d.id !== documentToDelete.id) : []));
      toast.success("Reference document removed");
      setDocumentToDelete(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to remove reference document");
    } finally {
      setDeleting(false);
    }
  }

  const breadcrumbs = useMemo(() => {
    if (subjectId && subjectName) {
      return [
        { label: "Subjects", to: "/subjects" },
        { label: subjectName, to: `/subjects/${subjectId}` },
        { label: "Reference Library" },
      ];
    }
    return [
      { label: "Subjects", to: "/subjects" },
      { label: "Reference Library" },
    ];
  }, [subjectId, subjectName]);

  return (
    <div className="content__inner content__inner--wide">
      <Breadcrumbs crumbs={breadcrumbs} />

      <div className="page-heading page-heading__row" style={{ marginTop: 14 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: "var(--accent-subtle, #eef0fc)",
                color: "var(--accent, #4f5bd5)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <BookIcon size={18} />
            </div>
            <h1>Reference Library</h1>
          </div>
          <p className="subtitle" style={{ marginTop: 6 }}>
            {subjectId && subjectName
              ? `Textbooks and reference material indexed for ${subjectName} note enrichment & grounded chat.`
              : "Textbooks, papers, and reference PDFs indexed across your workspace."}
          </p>
        </div>

        <div className="page-heading__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => setUploadDialogOpen(true)}
          >
            <PlusIcon size={14} />
            Upload Reference
          </button>
        </div>
      </div>

      {error && (
        <div className="form-error" role="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {loading && !documents && <SkeletonRows count={4} />}

      {!loading && documents && documents.length === 0 && (
        <EmptyState
          icon={<BookIcon size={32} />}
          title="No reference material indexed yet"
          description="Upload textbooks or reference PDFs so StudyAI can ground your note enrichment and Ask StudyAI with verified source citations."
          action={
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setUploadDialogOpen(true)}
            >
              <UploadIcon size={14} />
              Upload Your First Textbook
            </button>
          }
        />
      )}

      {documents && documents.length > 0 && (
        <div className="card-grid" style={{ marginTop: 16 }}>
          {documents.map((doc) => {
            const isReady = doc.status === "READY";
            const isProcessing = doc.status === "PROCESSING";
            const isPending = doc.status === "PENDING";
            const isFailed = doc.status === "FAILED";

            return (
              <div
                key={doc.id}
                className="card"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  padding: "16px 20px",
                  borderRadius: 10,
                  border: "1px solid var(--border)",
                  background: "var(--surface)",
                  position: "relative",
                }}
              >
                <div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      justifyContent: "space-between",
                      gap: 12,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: 6,
                          background: "var(--accent-subtle, #eef0fc)",
                          color: "var(--accent, #4f5bd5)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexShrink: 0,
                        }}
                      >
                        <BookIcon size={15} />
                      </div>
                      <h3
                        style={{
                          margin: 0,
                          fontSize: "1.05rem",
                          fontWeight: 600,
                          color: "var(--text)",
                          wordBreak: "break-word",
                        }}
                      >
                        {doc.title}
                      </h3>
                    </div>

                    <button
                      type="button"
                      className="icon-btn"
                      title="Delete Reference"
                      style={{ color: "var(--danger, #c93a3a)" }}
                      onClick={() => setDocumentToDelete(doc)}
                    >
                      <TrashIcon size={14} />
                    </button>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 6,
                      marginTop: 12,
                      alignItems: "center",
                    }}
                  >
                    {isReady && <span className="chip chip--green">✓ Ready</span>}
                    {isProcessing && (
                      <span className="chip chip--amber" style={{ animation: "pulse 1.5s infinite" }}>
                        ⏳ Processing...
                      </span>
                    )}
                    {isPending && <span className="chip chip--blue">Queued</span>}
                    {isFailed && <span className="chip chip--red">Failed</span>}

                    <span className="chip chip--gray">
                      {doc.source_type === "TEXTBOOK"
                        ? "Textbook"
                        : doc.source_type === "REFERENCE_PDF"
                        ? "Reference PDF"
                        : "Lecture Material"}
                    </span>

                    <span className="chip chip--gray">
                      {doc.scope === "global" ? "Global" : "Private"}
                    </span>

                    {doc.subject_name && (
                      <span className="chip chip--blue">{doc.subject_name}</span>
                    )}
                  </div>

                  {isFailed && doc.error_message && (
                    <div
                      style={{
                        marginTop: 10,
                        padding: "6px 10px",
                        borderRadius: 6,
                        background: "var(--danger-subtle, #fbeaea)",
                        color: "var(--danger, #c93a3a)",
                        fontSize: "0.85rem",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <AlertIcon size={14} />
                      <span>{doc.error_message}</span>
                    </div>
                  )}
                </div>

                <div
                  style={{
                    marginTop: 16,
                    paddingTop: 12,
                    borderTop: "1px solid var(--border-subtle, rgba(0,0,0,0.06))",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    fontSize: "0.82rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  <span>
                    {doc.page_count > 0 ? `${doc.page_count} pages` : "Pages pending"} ·{" "}
                    {doc.chunk_count > 0 ? `${doc.chunk_count} chunks indexed` : "0 chunks"}
                  </span>
                  <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <UploadReferenceDialog
        open={uploadDialogOpen}
        onClose={() => setUploadDialogOpen(false)}
        defaultSubjectId={subjectId ?? null}
        subjects={subjects}
        onUploaded={(created) => {
          setDocuments((prev) => [created, ...(prev ?? [])]);
          toast.success("Textbook uploaded. Ingestion and indexing started.");
        }}
      />

      {documentToDelete && (
        <ConfirmDialog
          open={!!documentToDelete}
          title="Delete Reference Document"
          message={
            <div>
              <p style={{ fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
                Are you sure you want to delete "{documentToDelete.title}"?
              </p>
              <p>
                This will permanently delete the document, stored file, and all associated indexed
                textbook chunks from vector search.
              </p>
            </div>
          }
          confirmLabel="Delete Document"
          busy={deleting}
          onConfirm={() => void handleDelete()}
          onClose={() => setDocumentToDelete(null)}
        />
      )}
    </div>
  );
}

interface UploadDialogProps {
  open: boolean;
  onClose: () => void;
  defaultSubjectId: string | null;
  subjects: Array<{ id: string; name: string }>;
  onUploaded: (doc: ReferenceDocumentItem) => void;
}

function UploadReferenceDialog({
  open,
  onClose,
  defaultSubjectId,
  subjects,
  onUploaded,
}: UploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState<"TEXTBOOK" | "REFERENCE_PDF" | "LECTURE_MATERIAL">("TEXTBOOK");
  const [subjectId, setSubjectId] = useState<string>(defaultSubjectId ?? "");
  const [scope, setScope] = useState<"profile" | "global">("profile");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (defaultSubjectId) {
      setSubjectId(defaultSubjectId);
    }
  }, [defaultSubjectId]);

  function reset() {
    setFile(null);
    setTitle("");
    setSourceType("TEXTBOOK");
    setSubjectId(defaultSubjectId ?? "");
    setScope("profile");
    setError(null);
    onClose();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      if (!title.trim()) {
        const cleanName = selected.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
        setTitle(cleanName.charAt(0).toUpperCase() + cleanName.slice(1));
      }
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Please select a PDF file to upload.");
      return;
    }
    const cleanTitle = title.trim() || file.name;
    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", cleanTitle);
      formData.append("source_type", sourceType);
      formData.append("scope", scope);
      if (subjectId) {
        formData.append("subject", subjectId);
        formData.append("subject_id", subjectId);
      }

      const created = await referencesApi.upload(formData);
      reset();
      onUploaded(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Upload Reference Document"
      description="Upload textbooks or reference PDFs for AI note enrichment and grounded Q&A."
      onClose={reset}
      actions={
        <>
          <button type="button" className="btn btn--ghost" onClick={reset} disabled={uploading}>
            Cancel
          </button>
          <button
            type="submit"
            form="upload-reference-form"
            className="btn btn--primary"
            disabled={uploading || !file}
          >
            {uploading ? "Uploading & Indexing..." : "Upload & Index"}
          </button>
        </>
      }
    >
      <form id="upload-reference-form" onSubmit={(e) => void handleSubmit(e)}>
        <button type="submit" style={{ display: "none" }} aria-hidden="true" tabIndex={-1}>
          Submit
        </button>
        <div className="field">
          <label htmlFor="ref-file">PDF Document *</label>
          <input
            id="ref-file"
            type="file"
            accept=".pdf,application/pdf"
            className="input"
            onChange={handleFileChange}
            disabled={uploading}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="ref-title">Title</label>
          <input
            id="ref-title"
            type="text"
            className="input"
            placeholder="e.g. Introduction to Algorithms 4th Ed"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={uploading}
          />
        </div>

        <div className="field">
          <label htmlFor="ref-type">Source Type</label>
          <select
            id="ref-type"
            className="input"
            value={sourceType}
            onChange={(e) =>
              setSourceType(e.target.value as "TEXTBOOK" | "REFERENCE_PDF" | "LECTURE_MATERIAL")
            }
            disabled={uploading}
          >
            <option value="TEXTBOOK">Textbook</option>
            <option value="REFERENCE_PDF">Reference PDF</option>
            <option value="LECTURE_MATERIAL">Lecture Material</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="ref-subject">Subject Scope</label>
          <select
            id="ref-subject"
            className="input"
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
            disabled={uploading}
          >
            <option value="">(All Subjects / General Workspace)</option>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="ref-scope">Access Scope</label>
          <select
            id="ref-scope"
            className="input"
            value={scope}
            onChange={(e) => setScope(e.target.value as "profile" | "global")}
            disabled={uploading}
          >
            <option value="profile">Current Profile Only (Private)</option>
            <option value="global">Global (Available across all profiles)</option>
          </select>
        </div>

        {error && <p className="form-error">{error}</p>}
      </form>
    </Dialog>
  );
}

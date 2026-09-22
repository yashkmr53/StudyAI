import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { enrichmentApi, parseEnrichment } from "../../services/api/enrichment";
import { tagsApi } from "../../services/api/tags";
import type { EnrichmentSnapshot, NoteMeta } from "../../types/domain";
import { EmptyState, ErrorState } from "../ui/primitives";
import { AlertIcon, RefreshIcon, SparkleIcon } from "../ui/icons";

/**
 * Enriched tab (§17). Rendered only when EnrichmentService is enabled —
 * NoteSpace never mounts this component (Rule 5).
 *
 * Explicit states per §19: generating, ready, out-of-date, failure.
 * Never a blank page while generation runs.
 */

const POLL_MS = 2500;
const MAX_POLLS = 120;

interface Props {
  note: NoteMeta;
  /** Called when a citation chip is clicked (§18). */
  onCitation: (page: number) => void;
}

export function EnrichedView({ note, onCitation }: Props) {
  const { t } = useTranslation();
  const [snapshot, setSnapshot] = useState<EnrichmentSnapshot | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [tags, setTags] = useState<{ stable_key: string; display_name: string }[]>([]);
  const [jobId, setJobId] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(`studyai.enrichment.job.${note.refId}`);
    } catch {
      return null;
    }
  });
  const [isGenerating, setIsGenerating] = useState<boolean>(() => {
    try {
      return !!sessionStorage.getItem(`studyai.enrichment.job.${note.refId}`);
    } catch {
      return false;
    }
  });
  const [activeCitation, setActiveCitation] = useState<any | null>(null);
  const pollsLeft = useRef(MAX_POLLS);
  const pollTimer = useRef<number | null>(null);
  const jobIdRef = useRef<string | null>(jobId);
  jobIdRef.current = jobId;

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const activeJobId = jobIdRef.current;
      if (activeJobId) {
        const jobInfo = await enrichmentApi.getJob(activeJobId);
        if (jobInfo) {
          if (
            jobInfo.status === "failed_retryable" ||
            jobInfo.status === "failed_dead_letter" ||
            jobInfo.status === "cancelled"
          ) {
            setIsGenerating(false);
            setJobId(null);
            try {
              sessionStorage.removeItem(`studyai.enrichment.job.${note.refId}`);
            } catch {}
            const failSnap: EnrichmentSnapshot = { state: "failed", blocks: [], generatedAt: null };
            setSnapshot(failSnap);
            setLoadError(false);
            return failSnap;
          }
        }
      }

      const snap = await enrichmentApi.get(note.refId);
      if ((isGenerating || jobIdRef.current) && snap.state === "not_enriched") {
        setSnapshot((prev) =>
          prev ? { ...prev, state: "enriching" } : { state: "enriching", blocks: [], generatedAt: null },
        );
        setLoadError(false);
        return { state: "enriching" as const, blocks: [], generatedAt: null };
      }

      if (snap.state === "enriched" || snap.state === "out_of_date" || snap.state === "failed") {
        setIsGenerating(false);
        setJobId(null);
        try {
          sessionStorage.removeItem(`studyai.enrichment.job.${note.refId}`);
        } catch {}
      }

      setSnapshot(snap);
      setLoadError(false);
      return snap;
    } catch {
      if (isGenerating || jobIdRef.current) {
        return null;
      }
      setLoadError(true);
      return null;
    }
  }, [note.refId, isGenerating]);

  useEffect(() => {
    let savedJob: string | null = null;
    try {
      savedJob = sessionStorage.getItem(`studyai.enrichment.job.${note.refId}`);
    } catch {}

    setJobId(savedJob);
    setIsGenerating(!!savedJob);
    setSnapshot(savedJob ? { state: "enriching", blocks: [], generatedAt: null } : null);
    setLoadError(false);
    setTags([]);
    setActiveCitation(null);
    stopPolling();
    void refresh();
    void tagsApi
      .listForDocument(note.refId)
      .then((t) =>
        setTags(
          t.map((x) => ({ stable_key: x.stable_key, display_name: x.display_name })),
        ),
      )
      .catch(() => {});
    return stopPolling;
  }, [note.refId, refresh, stopPolling]);

  // Poll while generation job is running or state is enriching
  useEffect(() => {
    const shouldPoll = isGenerating || jobId !== null || snapshot?.state === "enriching";
    if (!shouldPoll) {
      stopPolling();
      return;
    }
    pollsLeft.current = MAX_POLLS;
    pollTimer.current = window.setInterval(async () => {
      if (pollsLeft.current-- <= 0) {
        stopPolling();
        setIsGenerating(false);
        setJobId(null);
        try {
          sessionStorage.removeItem(`studyai.enrichment.job.${note.refId}`);
        } catch {}
        setSnapshot((prev) =>
          prev ? { ...prev, state: "failed" } : { state: "failed", blocks: [], generatedAt: null },
        );
        return;
      }
      const snap = await refresh();
      if (
        snap &&
        (snap.state === "enriched" || snap.state === "failed" || snap.state === "out_of_date")
      ) {
        stopPolling();
        setIsGenerating(false);
        setJobId(null);
        try {
          sessionStorage.removeItem(`studyai.enrichment.job.${note.refId}`);
        } catch {}
      }
    }, POLL_MS);
    return stopPolling;
  }, [isGenerating, jobId, snapshot?.state, refresh, stopPolling, note.refId]);

  async function generate() {
    setActionError(null);
    setIsGenerating(true);
    setSnapshot((prev) => ({
      state: "enriching",
      blocks: prev?.blocks ?? [],
      generatedAt: prev?.generatedAt ?? null,
    }));
    try {
      const res = await enrichmentApi.generate(note.refId);
      if (res.jobId) {
        setJobId(res.jobId);
        try {
          sessionStorage.setItem(`studyai.enrichment.job.${note.refId}`, res.jobId);
        } catch {}
      }
      if (res.enrichedNote) {
        const snap = await parseEnrichment({ enriched_note: res.enrichedNote });
        setSnapshot(snap);
        setIsGenerating(false);
        setJobId(null);
        try {
          sessionStorage.removeItem(`studyai.enrichment.job.${note.refId}`);
        } catch {}
      }
    } catch {
      setIsGenerating(false);
      setJobId(null);
      try {
        sessionStorage.removeItem(`studyai.enrichment.job.${note.refId}`);
      } catch {}
      setActionError(t("notes.enriched.startFailed"));
    }
  }

  if (loadError && !snapshot) {
    return (
      <ErrorState
        title={t("notes.detail.loadFailed")}
        message={t("errors.genericTryAgain")}
        onRetry={() => void refresh()}
      />
    );
  }

  if (!snapshot) {
    return (
      <div
        className="skeleton"
        style={{ height: 320, borderRadius: 14 }}
        aria-label={t("notes.enriched.thinkingAria")}
      />
    );
  }

  if (snapshot.state === "enriching") {
    return (
      <div className="enrichment-progress" role="status">
        <h3>{t("notes.enriched.generatingTitle")}</h3>
        <p>{t("notes.enriched.generatingBody")}</p>
        <div className="pulse" aria-hidden />
      </div>
    );
  }

  if (snapshot.state === "not_enriched") {
    return (
      <EmptyState
        icon={<SparkleIcon size={20} />}
        title={t("notes.enriched.emptyTitle")}
        description={t("notes.enriched.emptyDescription")}
        action={
          <button type="button" className="btn btn--primary" onClick={() => void generate()}>
            <SparkleIcon size={14} />
            {t("notes.enriched.generate")}
          </button>
        }
      />
    );
  }

  return (
    <div>
      {snapshot.state === "out_of_date" && (
        <div className="stale-note" role="alert">
          <AlertIcon size={18} />
          <div className="grow">
            <h4>{t("notes.enriched.staleTitle")}</h4>
            <p>{t("notes.enriched.staleBody")}</p>
          </div>
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => void generate()}>
            <RefreshIcon size={13} />
            {t("notes.enriched.regenerate")}
          </button>
        </div>
      )}

      {snapshot.state === "failed" && (
        <ErrorState
          title={t("notes.enriched.failedTitle")}
          message={t("notes.enriched.failedMessage")}
          retryLabel={t("notes.enriched.tryAgain")}
          onRetry={() => void generate()}
        />
      )}

      {actionError && (
        <p className="form-error" role="alert" style={{ marginBottom: 16 }}>
          {actionError}
        </p>
      )}

      <article className="enriched-body">
        <header style={{ marginBottom: 22 }}>
          <h2 style={{ fontSize: 20, letterSpacing: "-0.02em" }}>{note.title}</h2>
          {snapshot.generatedAt && (
            <p className="faint small" style={{ marginTop: 4 }}>
              {t("notes.enriched.generatedAt", {
                date: new Date(snapshot.generatedAt).toLocaleString(),
              })}
            </p>
          )}
        </header>

        {snapshot.blocks.length === 0 ? (
          <p className="muted">{t("notes.enriched.nothingYet")}</p>
        ) : (
          snapshot.blocks.map((block) => (
            <section key={`${block.index}-${block.title}`} className="enriched-block">
              {block.title && (
                <h3 className="enriched-block__title">
                  <span className="faint">{block.index + 1}.</span> {block.title}
                </h3>
              )}
              <div className="enriched-block__content">
                {block.content.split(/\n{2,}/).map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
              {block.citations.length > 0 && (
                <div className="citations-container" style={{ marginTop: 12 }}>
                  <div className="citations-row" aria-label={t("notes.enriched.sourcesAria")}>
                    {block.citations.map((citation, i) => {
                      const isRef = citation.sourceType === "reference";
                      const isSelected = activeCitation === citation;
                      if (isRef) {
                        return (
                          <button
                            key={`ref-${citation.page}-${i}`}
                            type="button"
                            className={`citation-chip ${isSelected ? "citation-chip--active" : ""}`}
                            style={{
                              background: isSelected ? "#eef0fc" : "#f4f5f7",
                              borderColor: isSelected ? "#4f5bd5" : "#d1d5db",
                              color: isSelected ? "#4f5bd5" : "#374151",
                            }}
                            onClick={() => setActiveCitation(isSelected ? null : citation)}
                            title={`Reference textbook citation (page ${citation.page})`}
                          >
                            <span>📖 Ref: p. {citation.page}</span>
                          </button>
                        );
                      }
                      return (
                        <button
                          key={`note-${citation.page}-${i}`}
                          type="button"
                          className="citation-chip"
                          onClick={() => onCitation(citation.page)}
                          title={t("notes.enriched.citationTooltip", { page: citation.page })}
                        >
                          <span>📝 {t("notes.enriched.citation", { page: citation.page })}</span>
                        </button>
                      );
                    })}
                  </div>

                  {activeCitation && block.citations.includes(activeCitation) && activeCitation.sourceType === "reference" && (
                    <div
                      className="citation-detail-card"
                      style={{
                        marginTop: 8,
                        padding: "10px 14px",
                        borderRadius: 8,
                        background: "#f8f9fc",
                        border: "1px solid #e2e6fa",
                        fontSize: "12.5px",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontWeight: 600, color: "#1f2937" }}>
                          📖 Reference Textbook {activeCitation.page ? `· Page ${activeCitation.page}` : ""}
                        </span>
                        {activeCitation.verificationStatus && (
                          <span
                            className="chip chip--ghost"
                            style={{
                              fontSize: "11px",
                              padding: "1px 6px",
                              color: activeCitation.verificationStatus === "supported" ? "#188554" : "#9a6700",
                            }}
                          >
                            {activeCitation.verificationStatus.replace("_", " ")}
                          </span>
                        )}
                      </div>
                      {activeCitation.content && (
                        <blockquote
                          style={{
                            margin: 0,
                            padding: "6px 10px",
                            borderLeft: "3px solid #4f5bd5",
                            background: "#ffffff",
                            fontStyle: "italic",
                            color: "#4b5563",
                            lineHeight: 1.45,
                          }}
                        >
                          "{activeCitation.content}"
                        </blockquote>
                      )}
                    </div>
                  )}
                </div>
              )}
            </section>
          ))
        )}
      </article>
      {tags.length > 0 && (
        <div className="tags-row" style={{ marginTop: 18 }}>
          {tags.map((tag) => (
            <span key={tag.stable_key} className="chip chip--ghost">
              {tag.display_name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

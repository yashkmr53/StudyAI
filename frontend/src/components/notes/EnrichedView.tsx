import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { enrichmentApi } from "../../services/api/enrichment";
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
  const pollsLeft = useRef(MAX_POLLS);
  const pollTimer = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const snap = await enrichmentApi.get(note.refId);
      setSnapshot(snap);
      setLoadError(false);
      return snap;
    } catch {
      setLoadError(true);
      return null;
    }
  }, [note.refId]);

  useEffect(() => {
    setSnapshot(null);
    setLoadError(false);
    stopPolling();
    void refresh();
    return stopPolling;
  }, [note.refId, refresh, stopPolling]);

  // Poll only while a generation job is running.
  useEffect(() => {
    if (!snapshot || snapshot.state !== "enriching") {
      stopPolling();
      return;
    }
    pollsLeft.current = MAX_POLLS;
    pollTimer.current = window.setInterval(async () => {
      if (pollsLeft.current-- <= 0) {
        stopPolling();
        return;
      }
      const snap = await refresh();
      if (snap && snap.state !== "enriching") stopPolling();
    }, POLL_MS);
    return stopPolling;
  }, [snapshot?.state, refresh, stopPolling]);

  async function generate() {
    setActionError(null);
    try {
      await enrichmentApi.generate(note.refId);
      await refresh();
    } catch {
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
                <div className="citations-row" aria-label={t("notes.enriched.sourcesAria")}>
                  {block.citations.map((citation, i) => (
                    <button
                      key={`${citation.page}-${i}`}
                      type="button"
                      className="citation-chip"
                      onClick={() => onCitation(citation.page)}
                      title={t("notes.enriched.citationTooltip", { page: citation.page })}
                    >
                      {t("notes.enriched.citation", { page: citation.page })}
                    </button>
                  ))}
                </div>
              )}
            </section>
          ))
        )}
      </article>
    </div>
  );
}

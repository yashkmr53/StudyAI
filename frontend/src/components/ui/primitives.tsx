import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import { AlertIcon } from "./icons";

/* ---- Modal dialog ---- */

interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children?: ReactNode;
  actions?: ReactNode;
  wide?: boolean;
}

export function Dialog({ open, title, description, onClose, children, actions, wide }: DialogProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    // move focus into the dialog for keyboard users
    const first = ref.current?.querySelector<HTMLElement>(
      "input, textarea, button",
    );
    first?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="dialog-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        className={wide ? "dialog dialog--wide" : "dialog"}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <h2 className="dialog__title">{title}</h2>
        {description && <p className="dialog__desc">{description}</p>}
        {children}
        {actions && <div className="dialog__actions">{actions}</div>}
      </div>
    </div>
  );
}

/* ---- Empty state ---- */

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  plain?: boolean;
}

export function EmptyState({ icon, title, description, action, plain }: EmptyStateProps) {
  return (
    <div className={plain ? "empty-state empty-state--plain" : "empty-state"}>
      {icon && <div className="empty-state__icon">{icon}</div>}
      <div className="empty-state__title">{title}</div>
      {description && <div className="empty-state__desc">{description}</div>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}

/* ---- Error state ---- */

interface ErrorStateProps {
  /** Defaults to common.states.error when omitted. */
  title?: string;
  /** Defaults to errors.genericTryAgain when omitted. */
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
}

export function ErrorState({ title, message, onRetry, retryLabel }: ErrorStateProps) {
  const { t } = useTranslation();
  return (
    <div className="state-block" role="alert">
      <div className="empty-state__icon">
        <AlertIcon size={20} />
      </div>
      <div className="empty-state__title">{title ?? t("common.states.error")}</div>
      <div className="empty-state__desc">{message ?? t("errors.genericTryAgain")}</div>
      {onRetry && (
        <button type="button" className="btn btn--secondary" onClick={onRetry}>
          {retryLabel ?? t("common.actions.retry")}
        </button>
      )}
    </div>
  );
}

/* ---- Skeletons ---- */

export function SkeletonCardGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="card-grid" aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="card" style={{ padding: 18 }}>
          <div className="skeleton" style={{ width: 36, height: 36, borderRadius: 10, marginBottom: 12 }} />
          <div className="skeleton" style={{ width: "62%", height: 14, marginBottom: 8 }} />
          <div className="skeleton" style={{ width: "40%", height: 11 }} />
          <div className="skeleton" style={{ width: "100%", height: 1, marginTop: 16 }} />
          <div className="skeleton" style={{ width: "48%", height: 10, marginTop: 12 }} />
        </div>
      ))}
    </div>
  );
}

export function SkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <div aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="note-row" style={{ cursor: "default" }}>
          <div style={{ flex: 1 }}>
            <div className="skeleton" style={{ width: `${45 + ((i * 13) % 30)}%`, height: 13, marginBottom: 7 }} />
            <div className="skeleton" style={{ width: `${25 + ((i * 9) % 20)}%`, height: 10 }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---- Status chips ---- */

export function TranscriptionChip({ status }: { status: string }) {
  const { t } = useTranslation();
  if (status === "completed" || status === "transcribed") {
    return <span className="chip chip--green">{t("notes.status.transcribed")}</span>;
  }
  if (status === "processing") {
    return (
      <span className="chip chip--blue">
        <span className="spinner spinner--inline" aria-hidden /> {t("notes.status.processing")}
      </span>
    );
  }
  if (status === "failed") {
    return <span className="chip chip--red">{t("notes.status.transcriptionFailed")}</span>;
  }
  return <span className="chip chip--gray">{t("notes.status.pending")}</span>;
}

export function EnrichmentChip({ state }: { state: string }) {
  const { t } = useTranslation();
  switch (state) {
    case "enriched":
      return <span className="chip chip--green">{t("notes.status.enriched")}</span>;
    case "enriching":
      return (
        <span className="chip chip--blue">
          <span className="spinner spinner--inline" aria-hidden /> {t("notes.status.enriching")}
        </span>
      );
    case "out_of_date":
      return <span className="chip chip--amber">{t("notes.status.outOfDate")}</span>;
    case "failed":
      return <span className="chip chip--red">{t("notes.status.enrichmentFailed")}</span>;
    default:
      return <span className="chip chip--gray">{t("notes.status.notEnriched")}</span>;
  }
}

/* ---- Relative time ---- */

/**
 * Localized relative time. Strings live under common.time.* so future
 * language files translate them like everything else.
 */
export function timeAgo(iso: string | null | undefined): string | null {
  const { t } = useTranslation();
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 60) return t("common.time.justNow");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t("common.time.minutesAgo", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("common.time.hoursAgo", { count: hours });
  const days = Math.floor(hours / 24);
  if (days === 1) return t("common.time.yesterday");
  if (days < 7) return t("common.time.daysAgo", { count: days });
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

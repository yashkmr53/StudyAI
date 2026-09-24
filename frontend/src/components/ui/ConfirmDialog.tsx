import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "./primitives";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string | ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: "danger" | "primary";
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  confirmVariant = "danger",
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog
      open={open}
      title={title}
      onClose={busy ? () => undefined : onClose}
      actions={
        <>
          <button
            type="button"
            className="btn btn--secondary"
            onClick={onClose}
            disabled={busy}
          >
            {cancelLabel ?? t("common.actions.cancel")}
          </button>
          <button
            type="button"
            className={`btn btn--${confirmVariant}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? t("common.states.working") : (confirmLabel ?? t("common.actions.delete"))}
          </button>
        </>
      }
    >
      <div style={{ marginTop: 8, fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.5 }}>
        {message}
      </div>
    </Dialog>
  );
}

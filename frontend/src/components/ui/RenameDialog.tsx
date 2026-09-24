import { useState, useEffect, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "./primitives";

interface RenameDialogProps {
  open: boolean;
  title: string;
  initialValue: string;
  label?: string;
  onSave: (newName: string) => Promise<void>;
  onClose: () => void;
}

export function RenameDialog({
  open,
  title,
  initialValue,
  label,
  onSave,
  onClose,
}: RenameDialogProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState(initialValue);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setValue(initialValue);
      setError(null);
      setBusy(false);
    }
  }, [open, initialValue]);

  async function handleSubmit(e?: FormEvent) {
    e?.preventDefault();
    const clean = value.trim();
    if (!clean) {
      setError(t("crud.errors.emptyName", "Name cannot be empty"));
      return;
    }
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await onSave(clean);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.states.error"));
    } finally {
      setBusy(false);
    }
  }

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
            {t("common.actions.cancel")}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void handleSubmit()}
            disabled={busy || !value.trim()}
          >
            {busy ? t("common.states.working") : t("common.actions.save")}
          </button>
        </>
      }
    >
      <form onSubmit={(e) => void handleSubmit(e)} style={{ marginTop: 12 }}>
        {label && (
          <label className="label" style={{ display: "block", marginBottom: 6, fontSize: 13, fontWeight: 500 }}>
            {label}
          </label>
        )}
        <input
          type="text"
          className="input"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (error) setError(null);
          }}
          disabled={busy}
          autoFocus
          style={{ width: "100%" }}
        />
        {error && (
          <div className="form-error" role="alert" style={{ marginTop: 8, fontSize: 12.5 }}>
            {error}
          </div>
        )}
      </form>
    </Dialog>
  );
}

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../features/auth/authStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { Dialog } from "../ui/primitives";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Navigate to the new subject after creation. */
  openAfterCreate?: boolean;
}

export function NewSubjectDialog({ open, onClose, openAfterCreate }: Props) {
  const profileId = useAuthStore((s) => s.profile?.id ?? null);
  const createSubject = useWorkspaceStore((s) => s.createSubject);
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  function close() {
    setName("");
    setError(null);
    onClose();
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || !profileId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createSubject(profileId, trimmed);
      close();
      if (openAfterCreate) navigate(`/subjects/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("newSubjectDialog.fallbackError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title={t("newSubjectDialog.title")}
      description={t("newSubjectDialog.description")}
      onClose={close}
      actions={
        <>
          <button type="button" className="btn btn--ghost" onClick={close}>
            {t("common.actions.cancel")}
          </button>
          <button
            type="submit"
            form="new-subject-form"
            className="btn btn--primary"
            disabled={busy || !name.trim()}
          >
            {busy ? t("newSubjectDialog.creating") : t("newSubjectDialog.create")}
          </button>
        </>
      }
    >
      <form id="new-subject-form" onSubmit={(e) => void submit(e)}>
        <div className="field">
          <label htmlFor="new-subject-name">{t("newSubjectDialog.nameLabel")}</label>
          <input
            id="new-subject-name"
            className="input"
            placeholder={t("newSubjectDialog.namePlaceholder")}
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        {error && <p className="form-error">{error}</p>}
      </form>
    </Dialog>
  );
}

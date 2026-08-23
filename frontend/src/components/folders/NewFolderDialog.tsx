import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../features/auth/authStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import type { FolderNode } from "../../types/domain";
import { Dialog } from "../ui/primitives";
import { childrenOf } from "../../utils/folderTree";

interface Props {
  open: boolean;
  onClose: () => void;
  subjectId: string;
  /** Preselected parent (e.g. creating from inside a folder). */
  defaultParentId?: string | null;
  /** Navigate into the new folder when created. */
  onCreated?: (folderId: string) => void;
}

interface TreeOption {
  id: string | null;
  label: string;
  depth: number;
}

function flattenOptions(
  folders: FolderNode[],
  parentId: string | null,
  depth: number,
  out: TreeOption[],
): void {
  for (const folder of childrenOf(folders, parentId)) {
    out.push({ id: folder.id, label: folder.name, depth });
    flattenOptions(folders, folder.id, depth + 1, out);
  }
}

export function NewFolderDialog({ open, onClose, subjectId, defaultParentId = null, onCreated }: Props) {
  const profileId = useAuthStore((s) => s.profile?.id ?? null);
  const folders = useWorkspaceStore((s) => s.folders);
  const createFolder = useWorkspaceStore((s) => s.createFolder);

  const [name, setName] = useState("");
  const [parentId, setParentId] = useState<string | null>(defaultParentId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  const options = useMemo(() => {
    const subjectFolders = folders.filter((f) => f.subjectId === subjectId);
    const out: TreeOption[] = [{ id: null, label: t("folders.dialog.topLevel"), depth: 0 }];
    flattenOptions(subjectFolders, null, 0, out);
    return out;
  }, [folders, subjectId]);

  function close() {
    setName("");
    setError(null);
    setParentId(defaultParentId);
    onClose();
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || !profileId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createFolder(profileId, subjectId, trimmed, parentId);
      close();
      onCreated?.(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("folders.dialog.fallbackError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title={t("folders.dialog.title")}
      description={t("folders.dialog.description")}
      onClose={close}
      actions={
        <>
          <button type="button" className="btn btn--ghost" onClick={close}>
            {t("common.actions.cancel")}
          </button>
          <button
            type="submit"
            form="new-folder-form"
            className="btn btn--primary"
            disabled={busy || !name.trim()}
          >
            {busy ? t("folders.dialog.creating") : t("folders.dialog.create")}
          </button>
        </>
      }
    >
      <form id="new-folder-form" onSubmit={(e) => void submit(e)}>
        <div className="field">
          <label htmlFor="new-folder-name">{t("folders.dialog.nameLabel")}</label>
          <input
            id="new-folder-name"
            className="input"
            placeholder={t("folders.dialog.namePlaceholder")}
            value={name}
            maxLength={255}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="new-folder-parent">{t("folders.dialog.locationLabel")}</label>
          <select
            id="new-folder-parent"
            className="input"
            value={parentId ?? ""}
            onChange={(e) => setParentId(e.target.value || null)}
          >
            {options.map((opt) => (
              <option key={opt.id ?? "__root__"} value={opt.id ?? ""}>
                {"\u00A0".repeat(opt.depth * 4)}
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        {error && <p className="form-error">{error}</p>}
      </form>
    </Dialog>
  );
}

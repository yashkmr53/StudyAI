import { useState, useMemo, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { Dialog } from "../ui/primitives";
import { FolderIcon } from "../ui/icons";
import { UNFILED_FOLDER_ID, type FolderNode } from "../../types/domain";
import { childrenOf } from "../../utils/folderTree";

interface MoveNoteDialogProps {
  open: boolean;
  noteId: string;
  noteTitle: string;
  currentFolderId: string | null;
  subjectId: string;
  onMoved?: (targetFolderId: string) => void;
  onClose: () => void;
}

interface TreeOption {
  id: string;
  label: string;
  depth: number;
}

function flattenTree(
  folders: FolderNode[],
  parentId: string | null,
  depth: number,
  out: TreeOption[],
) {
  for (const folder of childrenOf(folders, parentId)) {
    out.push({ id: folder.id, label: folder.name, depth });
    flattenTree(folders, folder.id, depth + 1, out);
  }
}

export function MoveNoteDialog({
  open,
  noteId,
  noteTitle,
  currentFolderId,
  subjectId,
  onMoved,
  onClose,
}: MoveNoteDialogProps) {
  const { t } = useTranslation();
  const notes = useWorkspaceStore((s) => s.notes);
  const folders = useWorkspaceStore((s) => s.folders);
  const moveNote = useWorkspaceStore((s) => s.moveNote);

  const initialSelected = currentFolderId || UNFILED_FOLDER_ID;
  const [selectedFolderId, setSelectedFolderId] = useState<string>(initialSelected);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = useMemo(() => {
    const subjectFolders = folders.filter((f) => f.subjectId === subjectId);
    const list: TreeOption[] = [
      { id: UNFILED_FOLDER_ID, label: t("workspace.unfiled", "Unfiled"), depth: 0 },
    ];
    flattenTree(subjectFolders, null, 0, list);
    return list;
  }, [folders, subjectId, t]);

  async function handleMove(e?: FormEvent) {
    e?.preventDefault();
    if (busy) return;
    if (selectedFolderId === (currentFolderId || UNFILED_FOLDER_ID)) {
      onClose();
      return;
    }
    const isDuplicate = notes.some(
      (n) =>
        n.id !== noteId &&
        n.subjectId === subjectId &&
        (n.folderId || UNFILED_FOLDER_ID) === selectedFolderId &&
        n.title.trim().toLowerCase() === noteTitle.trim().toLowerCase()
    );
    if (isDuplicate) {
      setError(
        selectedFolderId === UNFILED_FOLDER_ID
          ? t("crud.errors.duplicateNoteInSubject", "A note with this name already exists in this subject")
          : t("crud.errors.duplicateNoteInFolder", "A note with this name already exists in this folder")
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await moveNote(noteId, selectedFolderId);
      onMoved?.(selectedFolderId);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("crud.errors.moveNote", "Failed to move note"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title={t("crud.moveNote", "Move Note")}
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
            onClick={() => void handleMove()}
            disabled={busy}
          >
            {busy ? t("common.states.working") : t("common.actions.save", "Move")}
          </button>
        </>
      }
    >
      <form onSubmit={(e) => void handleMove(e)} style={{ marginTop: 8 }}>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", marginBottom: 12 }}>
          {t("crud.moveNotePrompt", {
            defaultValue: "Choose a folder for \"{{title}}\":",
            title: noteTitle,
          })}
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 240, overflowY: "auto" }}>
          {options.map((opt) => {
            const isSelected = selectedFolderId === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                className={`popover__item ${isSelected ? "selected" : ""}`}
                style={{
                  paddingLeft: 10 + opt.depth * 16,
                  background: isSelected ? "var(--accent-subtle)" : undefined,
                  color: isSelected ? "var(--accent)" : undefined,
                  fontWeight: isSelected ? 600 : 400,
                }}
                onClick={() => {
                  setSelectedFolderId(opt.id);
                  if (error) setError(null);
                }}
              >
                <FolderIcon size={15} />
                <span className="grow nowrap">{opt.label}</span>
                {isSelected && (
                  <span className="check" style={{ visibility: "visible" }}>✓</span>
                )}
              </button>
            );
          })}
        </div>

        {error && (
          <div className="form-error" role="alert" style={{ marginTop: 10, fontSize: 12.5 }}>
            {error}
          </div>
        )}
      </form>
    </Dialog>
  );
}

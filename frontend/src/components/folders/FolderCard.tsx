import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { FolderNode } from "../../types/domain";
import { FolderIcon } from "../ui/icons";

interface Props {
  folder: Pick<FolderNode, "id" | "name">;
  subjectId: string;
  noteCount: number;
  /** Unfiled renders with a neutral icon but otherwise identical styling (§14). */
  variant?: "folder" | "unfiled";
}

export function FolderCard({ folder, subjectId, noteCount, variant = "folder" }: Props) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  return (
    <button
      type="button"
      className="card folder-card"
      onClick={() => navigate(`/subjects/${subjectId}/folders/${folder.id}`)}
      aria-label={t("folders.detail.openAria", { name: folder.name })}
    >
      <span className="folder-card__top">
        <span className="folder-card__icon">
          {variant === "unfiled" ? <InboxGlyph /> : <FolderIcon size={16} />}
        </span>
        <span className="folder-card__name">{folder.name}</span>
      </span>
      <span className="folder-card__meta">
        {t("folders.card.notes", { count: noteCount })}
      </span>
    </button>
  );
}

function InboxGlyph() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  );
}

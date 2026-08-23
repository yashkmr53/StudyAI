import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { SubjectSummary } from "../../types/domain";
import { timeAgo } from "../ui/primitives";
import { subjectGlyph } from "../layout/Sidebar";

export function SubjectCard({ subject }: { subject: SubjectSummary }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const glyph = subjectGlyph(subject.name);

  return (
    <button
      type="button"
      className="card subject-card"
      onClick={() => navigate(`/subjects/${subject.id}`)}
      aria-label={t("subjectCard.openAria", { name: subject.name })}
    >
      <span className="subject-card__glyph" style={{ background: glyph.background, color: glyph.color }}>
        {glyph.label}
      </span>
      <span className="subject-card__name">{subject.name}</span>
      <span className="subject-card__stats">
        <span>{t("subjectCard.notes", { count: subject.noteCount })}</span>
        <span>{t("subjectCard.folders", { count: subject.folderCount })}</span>
      </span>
      <span className="subject-card__last">
        {timeAgo(subject.lastOpenedAt)
          ? t("subjectCard.lastOpened", { time: timeAgo(subject.lastOpenedAt) })
          : ""}
      </span>
    </button>
  );
}

import { useTranslation } from "react-i18next";
import type { ModuleId } from "../../types/modules";

interface Props {
  value: ModuleId;
  onChange: (moduleId: ModuleId) => void;
}

const MODULE_IDS: ModuleId[] = ["NOTE_SPACE", "AI_CLASSROOM"];

/**
 * In-page module toggle (§8). Purely presentational: switching is handled
 * by the parent as local client state — no route change, no fetch, no
 * reload, no loading screen. Labels are i18n keys per module.
 */
export function ModuleToggle({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="segmented" role="tablist" aria-label={t("modules.toggleLabel")}>
      {MODULE_IDS.map((id) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={value === id}
          className={value === id ? "segmented__option active" : "segmented__option"}
          onClick={() => onChange(id)}
        >
          <span className="dot" aria-hidden />
          {t(`onboarding.module.${id === "NOTE_SPACE" ? "noteSpaceName" : "aiClassroomName"}`)}
        </button>
      ))}
    </div>
  );
}

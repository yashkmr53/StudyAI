import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../auth/authStore";
import { MODULE_SERVICE_MATRIX, type ModuleId } from "../../types/modules";
import { useModuleConfigStore } from "../../state/moduleConfigStore";
import { saveProgress } from "./onboardingState";
import { OnboardingLayout } from "./OnboardingLayout";

const OPTION_IDS: ModuleId[] = ["NOTE_SPACE", "AI_CLASSROOM"];

/** Ordered service ids for the capability summary line. */
const SERVICE_ORDER = [
  "transcription",
  "write",
  "enrichment",
  "tests",
  "qa",
  "chat",
] as const;

function useOption(t: TFunction): { id: ModuleId; name: string; description: string; services: string[] }[] {
  return OPTION_IDS.map((id) => {
    const cfg = MODULE_SERVICE_MATRIX[id];
    const services = SERVICE_ORDER.filter((s) => cfg[s]).map((s) =>
      t(`onboarding.module.services.${s}`),
    );
    const name = t(
      id === "NOTE_SPACE" ? "onboarding.module.noteSpaceName" : "onboarding.module.aiClassroomName",
    );
    const description = t(
      id === "NOTE_SPACE"
        ? "onboarding.module.noteSpaceDescription"
        : "onboarding.module.aiClassroomDescription",
    );
    return { id, name, description, services };
  });
}

/**
 * Step 3 — Pick Module (§6). Establishes the profile's default module only;
 * users can still switch modules later inside any subject workspace.
 */
export function ModuleStep() {
  const navigate = useNavigate();
  const profileId = useAuthStore((s) => s.profile?.id ?? null);
  const hydrateFor = useModuleConfigStore((s) => s.hydrateFor);
  const setDefaultModule = useModuleConfigStore((s) => s.setDefaultModule);
  const [choice, setChoice] = useState<ModuleId | null>(null);
  const { t } = useTranslation();
  const options = useOption(t);

  function next() {
    if (!choice) return;
    // Seed the once-per-session config cache with the onboarding choice.
    hydrateFor(profileId ?? "", choice);
    if (profileId) setDefaultModule(profileId, choice);
    saveProgress({ lastStep: "subjects", moduleChoice: choice });
    navigate("/onboarding/subjects");
  }

  return (
    <OnboardingLayout
      step={1}
      title={t("onboarding.module.title")}
      subtitle={t("onboarding.module.subtitle")}
    >
      <div role="radiogroup" aria-label={t("onboarding.module.radioGroupLabel")}>
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={choice === option.id}
            className={choice === option.id ? "module-option selected" : "module-option"}
            onClick={() => setChoice(option.id)}
          >
            <span className="module-option__head">
              <span className="module-option__name">{option.name}</span>
              <span className="module-option__radio" aria-hidden />
            </span>
            <span className="module-option__desc">{option.description}</span>
            <span className="module-option__desc small faint">{option.services.join(" · ")}</span>
          </button>
        ))}
      </div>

      <button
        type="button"
        className="btn btn--primary btn--lg btn--block"
        style={{ marginTop: 18 }}
        disabled={!choice}
        onClick={next}
      >
        {t("onboarding.module.continue")}
      </button>
    </OnboardingLayout>
  );
}

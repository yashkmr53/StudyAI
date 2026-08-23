import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../auth/authStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { markOnboarded, saveProgress } from "./onboardingState";
import { OnboardingLayout } from "./OnboardingLayout";

const MAX_SUBJECTS = 12;

/**
 * Step 4 — Enter Courses (§6). Creates *only* Subject records — no folders,
 * notebooks, starter notes or templates (Rule 16).
 */
export function SubjectsStep() {
  const navigate = useNavigate();
  const profileId = useAuthStore((s) => s.profile?.id ?? null);
  const createSubject = useWorkspaceStore((s) => s.createSubject);
  const { t } = useTranslation();

  const [count, setCount] = useState(1);
  const [names, setNames] = useState<string[]>([""]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Names already created server-side; retries skip these. */
  const createdNames = useRef<Set<string>>(new Set());

  const validNames = useMemo(
    () => names.slice(0, count).map((n) => n.trim()).filter(Boolean),
    [names, count],
  );

  // Renaming/removing a subject invalidates its "already created" marker.
  useEffect(() => {
    for (const name of [...createdNames.current]) {
      if (!validNames.includes(name)) createdNames.current.delete(name);
    }
  }, [validNames]);

  function onCountChange(raw: string) {
    const parsed = Math.max(1, Math.min(MAX_SUBJECTS, Number(raw) || 1));
    setCount(parsed);
    setNames((prev) => {
      const next = [...prev];
      while (next.length < parsed) next.push("");
      return next.slice(0, parsed);
    });
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!profileId || busy || validNames.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      let failure: { name: string; reason: string } | null = null;
      for (const name of validNames) {
        if (createdNames.current.has(name)) continue;
        try {
          await createSubject(profileId, name);
          createdNames.current.add(name);
        } catch (err) {
          // Stop at the failing subject so numbering stays intact;
          // retrying resumes where it left off.
          failure = {
            name,
            reason: err instanceof Error ? err.message : "Please try again.",
          };
          break;
        }
      }
      if (failure) {
        setError(t("onboarding.subjects.resumeError", failure));
      } else if (validNames.every((n) => createdNames.current.has(n))) {
        markOnboarded(profileId);
        saveProgress({ lastStep: "subjects" });
        navigate("/subjects");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <OnboardingLayout
      step={2}
      title={t("onboarding.subjects.title")}
      subtitle={t("onboarding.subjects.subtitle")}
    >
      <form onSubmit={(e) => void submit(e)}>
        <div className="field" style={{ maxWidth: 140 }}>
          <label htmlFor="subject-count">{t("onboarding.subjects.countLabel")}</label>
          <input
            id="subject-count"
            className="input"
            type="number"
            min={1}
            max={MAX_SUBJECTS}
            value={count}
            onChange={(e) => onCountChange(e.target.value)}
          />
        </div>

        <div style={{ margin: "18px 0 6px" }}>
          {names.slice(0, count).map((name, i) => (
            <div key={i} className="subject-input-row">
              <span className="idx">{i + 1}</span>
              <input
                className="input"
                placeholder={t("onboarding.subjects.placeholder", {
                  index: i + 1,
                  example: t(
                    `onboarding.subjects.example${(i % 4) + 1}`,
                  ) as string,
                })}
                value={name}
                maxLength={200}
                aria-label={t("onboarding.subjects.nameAria", { index: i + 1 })}
                onChange={(e) =>
                  setNames((prev) => prev.map((v, j) => (j === i ? e.target.value : v)))
                }
              />
            </div>
          ))}
        </div>

        {error && <p className="form-error" style={{ margin: "10px 0" }}>{error}</p>}

        <button
          type="submit"
          className="btn btn--primary btn--lg btn--block"
          style={{ marginTop: 16 }}
          disabled={busy || validNames.length === 0}
        >
          {busy ? t("onboarding.subjects.finishing") : t("onboarding.subjects.finish")}
        </button>
      </form>
    </OnboardingLayout>
  );
}

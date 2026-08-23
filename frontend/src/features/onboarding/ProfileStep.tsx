import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../auth/authStore";
import { saveProgress } from "./onboardingState";

/** Step 2 — Create Profile (§6): the profile is the study context. */
export function ProfileStep() {
  const navigate = useNavigate();
  const profiles = useAuthStore((s) => s.profiles);
  const profile = useAuthStore((s) => s.profile);
  const addProfile = useAuthStore((s) => s.addProfile);
  const { t } = useTranslation();

  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      await addProfile(trimmed);
      saveProgress({ lastStep: "module" });
      navigate("/onboarding/module");
    } catch {
      setError(t("onboarding.profile.error"));
    } finally {
      setBusy(false);
    }
  }

  function keepExisting() {
    saveProgress({ lastStep: "module" });
    navigate("/onboarding/module");
  }

  return (
    <div className="onboarding">
      <div className="auth-brand">
        <span className="mark">S</span>
        <span className="name">{t("app.name")}</span>
      </div>
      <div className="onboarding__progress" aria-hidden>
        <span className="progress-segment done" />
        <span className="progress-segment" />
        <span className="progress-segment" />
      </div>
      <main className="onboarding-card onboarding-card--narrow">
        <h1 className="auth-title">{t("onboarding.profile.title")}</h1>
        <p className="auth-subtitle">{t("onboarding.profile.subtitle")}</p>

        <form onSubmit={(e) => void submit(e)}>
          <div className="field">
            <label htmlFor="profile-name">{t("onboarding.profile.nameLabel")}</label>
            <input
              id="profile-name"
              className="input"
              placeholder={t("onboarding.profile.namePlaceholder")}
              value={name}
              autoFocus
              maxLength={80}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          {error && <p className="form-error" style={{ marginBottom: 12 }}>{error}</p>}
          <button
            type="submit"
            className="btn btn--primary btn--lg btn--block"
            disabled={busy || !name.trim()}
          >
            {busy ? t("onboarding.profile.creating") : t("onboarding.profile.submit")}
          </button>
        </form>

        {(profile || profiles.length > 0) && (
          <>
            <div className="divider-row">or</div>
            <button type="button" className="btn btn--secondary btn--block" onClick={keepExisting}>
              {t("onboarding.profile.keepUsing", { name: profile?.name ?? profiles[0]?.name ?? "" })}
            </button>
          </>
        )}
      </main>
    </div>
  );
}

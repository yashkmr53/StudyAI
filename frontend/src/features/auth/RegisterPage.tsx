import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "./authStore";
import { ApiError } from "../../types/api";

export function RegisterPage() {
  const register = useAuthStore((s) => s.register);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (password.length < 10) {
      setError(t("auth.register.shortPassword"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await register(email, password);
      navigate("/onboarding/profile");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("auth.register.failedFallback"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="auth-brand">
          <span className="mark">S</span>
          <span className="name">{t("app.name")}</span>
        </div>

        <h1 className="auth-title">{t("auth.register.title")}</h1>
        <p className="auth-subtitle">{t("auth.register.subtitle")}</p>

        {error && (
          <p className="form-error" style={{ marginBottom: 14 }} role="alert">
            {error}
          </p>
        )}

        <div className="field">
          <label htmlFor="register-email">{t("auth.register.emailLabel")}</label>
          <input
            id="register-email"
            className="input"
            type="email"
            placeholder={t("auth.register.emailPlaceholder")}
            value={email}
            autoComplete="email"
            required
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="register-password">{t("auth.register.passwordLabel")}</label>
          <input
            id="register-password"
            className="input"
            type="password"
            placeholder={t("auth.register.passwordPlaceholder")}
            value={password}
            autoComplete="new-password"
            minLength={10}
            required
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="hint-text">{t("auth.register.passwordHint")}</span>
        </div>

        <button type="submit" className="btn btn--primary btn--lg btn--block" disabled={busy}>
          {busy ? t("auth.register.submitting") : t("auth.register.submit")}
        </button>

        <p className="small faint" style={{ textAlign: "center", marginTop: 16 }}>
          {t("auth.register.haveAccount")} <Link to="/login">{t("auth.register.signInLink")}</Link>
        </p>
      </form>
    </div>
  );
}

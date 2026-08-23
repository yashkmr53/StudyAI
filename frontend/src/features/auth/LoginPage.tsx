import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "./authStore";
import { ApiError } from "../../types/api";

/** Step 1 — Login (§6). Clean, minimal; Google button is a placeholder. */
export function LoginPage() {
  const login = useAuthStore((s) => s.login);
  const email0 = useAuthStore((s) => s.email);
  const initialized = useAuthStore((s) => s.initialized);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in? Move on.
  useEffect(() => {
    if (initialized && email0) navigate("/", { replace: true });
  }, [initialized, email0, navigate]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : t("auth.login.failedFallback"),
      );
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

        <h1 className="auth-title">{t("auth.login.title")}</h1>
        <p className="auth-subtitle">{t("auth.login.subtitle")}</p>

        {error && (
          <p className="form-error" style={{ marginBottom: 14 }} role="alert">
            {error}
          </p>
        )}

        <div className="field">
          <label htmlFor="login-email">{t("auth.login.emailLabel")}</label>
          <input
            id="login-email"
            className="input"
            type="email"
            placeholder={t("auth.login.emailPlaceholder")}
            value={email}
            autoComplete="email"
            required
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="login-password">{t("auth.login.passwordLabel")}</label>
          <input
            id="login-password"
            className="input"
            type="password"
            placeholder={t("auth.login.passwordPlaceholder")}
            value={password}
            autoComplete="current-password"
            required
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button type="submit" className="btn btn--primary btn--lg btn--block" disabled={busy}>
          {busy ? t("auth.login.submitting") : t("auth.login.submit")}
        </button>

        <button
          type="button"
          className="btn btn--secondary btn--lg btn--block"
          disabled
          title={t("auth.login.comingSoon")}
        >
          {t("auth.login.google")}
        </button>

        <p className="small faint" style={{ textAlign: "center", marginTop: 16 }}>
          {t("auth.login.noAccount")} <Link to="/register">{t("auth.login.createAccountLink")}</Link>
        </p>
      </form>
    </div>
  );
}

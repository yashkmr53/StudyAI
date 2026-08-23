import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

/** Shared chrome for the four-step onboarding flow (§6). */
export function OnboardingLayout({
  step,
  title,
  subtitle,
  children,
}: {
  /** Zero-based index into the visible progress segments (login excluded). */
  step: number;
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="onboarding">
      <div className="auth-brand">
        <span className="mark">S</span>
        <span className="name">{t("app.name")}</span>
      </div>

      <div className="onboarding__progress" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className={i <= step ? "progress-segment done" : "progress-segment"} />
        ))}
      </div>

      <main className="onboarding-card" style={{ width: "100%" }}>
        <h1 className="auth-title">{title}</h1>
        {subtitle && <p className="auth-subtitle">{subtitle}</p>}
        {children}
      </main>
    </div>
  );
}

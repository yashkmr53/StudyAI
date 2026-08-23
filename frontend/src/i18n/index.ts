import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";

/**
 * Central i18n runtime (Phase 12).
 *
 * - Resources live in `src/i18n/<lang>.json` — one file per language.
 *   Adding a language = create `hi.json` / `bn.json` and register it here.
 * - Components use `useTranslation()`; non-React modules import `appI18n`
 *   and call `appI18n.t(key, options)` directly.
 */

export const LANG_STORAGE_KEY = "studyai.lang";

export const appI18n = i18n.createInstance();

/** Switch the active language at runtime (future language switcher hook-up). */
export async function setAppLanguage(language: string): Promise<void> {
  await appI18n.changeLanguage(language);
  safeStorageSet(LANG_STORAGE_KEY, language);
}

/* localStorage is unavailable in non-browser environments (unit tests). */
function storedLanguage(): string | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage.getItem(LANG_STORAGE_KEY);
  } catch {
    return null;
  }
}

function safeStorageSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — session-only language */
  }
}

void appI18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
  },
  lng: storedLanguage() || "en",
  fallbackLng: "en",
  // React already escapes rendered text; double-escaping would show entities.
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default appI18n;

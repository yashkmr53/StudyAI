import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import { App } from "./app/App";
import "./i18n";
import "./app/styles.css";

const disablePwa = import.meta.env.VITE_DISABLE_PWA === "1";

if ("serviceWorker" in navigator) {
  if (disablePwa) {
    // Compose/local builds must drop leftover workers so a new image is visible
    // without "Clear site data". Unregister, then reload once if a worker was controlling this page.
    void navigator.serviceWorker.getRegistrations().then(async (regs) => {
      if (regs.length === 0) return;
      await Promise.all(regs.map((r) => r.unregister()));
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
      window.location.reload();
    });
  } else {
    registerSW({ immediate: true });
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "../routes";
import { OfflineBanner } from "../components/OfflineBanner";
import { ToastProvider } from "../components/ui/Toast";

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <OfflineBanner />
        <AppRoutes />
      </ToastProvider>
    </BrowserRouter>
  );
}

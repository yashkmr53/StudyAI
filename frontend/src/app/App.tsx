import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "../routes";
import { OfflineBanner } from "../components/OfflineBanner";
import { ToastProvider } from "../components/ui/Toast";
import { TooltipProvider } from "../components/ui/Tooltip";

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <TooltipProvider>
          <OfflineBanner />
          <AppRoutes />
        </TooltipProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}

import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "../routes";
import { OfflineBanner } from "../components/OfflineBanner";

export function App() {
  return (
    <BrowserRouter>
      <OfflineBanner />
      <AppRoutes />
    </BrowserRouter>
  );
}

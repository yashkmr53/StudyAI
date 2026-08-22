import { useOnlineStatus } from "../../hooks/useOnlineStatus";

/**
 * Offline banner component (G5).
 * Shows a banner when the app is offline.
 */
export function OfflineBanner(): JSX.Element | null {
  const { isOnline, wasOffline } = useOnlineStatus();

  if (isOnline && !wasOffline) {
    return null;
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        backgroundColor: isOnline ? "#10B981" : "#EF4444",
        color: "white",
        padding: "8px 16px",
        textAlign: "center",
        fontSize: "14px",
        fontWeight: 500,
        zIndex: 9999,
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
        transition: "opacity 0.3s ease",
      }}
      role="status"
      aria-live="polite"
    >
      {isOnline
        ? "Connection restored. Syncing changes..."
        : "You are offline. Changes will sync when reconnected."}
    </div>
  );
}
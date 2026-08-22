import { create } from "zustand";
import { persist } from "zustand/middleware";
import { getOperationsByStatus, type SyncOperation } from "../db/indexeddb/db";
import { flushOutbox, retryFailedOperations } from "../services/sync/outbox";

interface OutboxState {
  operations: SyncOperation[];
  pendingCount: number;
  sendingCount: number;
  failedCount: number;
  acknowledgedCount: number;
  retryingCount: number;
  isFlushing: boolean;
  lastFlushError: string | null;
  refresh: () => Promise<void>;
  flush: () => Promise<{ acked: number; lockLost: boolean }>;
  retry: () => Promise<void>;
}

export const useOutboxStore = create<OutboxState>()(
  persist(
    (set, get) => ({
      operations: [],
      pendingCount: 0,
      sendingCount: 0,
      failedCount: 0,
      acknowledgedCount: 0,
      retryingCount: 0,
      isFlushing: false,
      lastFlushError: null,

      refresh: async () => {
        const [pending, sending, failed, acknowledged, retrying] = await Promise.all([
          getOperationsByStatus("pending"),
          getOperationsByStatus("sending"),
          getOperationsByStatus("failed"),
          getOperationsByStatus("acknowledged"),
          getOperationsByStatus("retrying"),
        ]);

        const allOps = [...pending, ...sending, ...failed, ...acknowledged, ...retrying];

        set({
          operations: allOps,
          pendingCount: pending.length,
          sendingCount: sending.length,
          failedCount: failed.length,
          acknowledgedCount: acknowledged.length,
          retryingCount: retrying.length,
        });
      },

      flush: async () => {
        set({ isFlushing: true, lastFlushError: null });
        try {
          const result = await flushOutbox();
          await get().refresh();
          return result;
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : "Flush failed";
          set({ lastFlushError: errorMessage });
          throw error;
        } finally {
          set({ isFlushing: false });
        }
      },

      retry: async () => {
        set({ lastFlushError: null });
        try {
          await retryFailedOperations();
          await get().refresh();
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : "Retry failed";
          set({ lastFlushError: errorMessage });
          throw error;
        }
      },
    }),
    {
      name: "outbox-store",
      partialize: (state) => ({
        // Only persist counts, not the full operations
        pendingCount: state.pendingCount,
        sendingCount: state.sendingCount,
        failedCount: state.failedCount,
        acknowledgedCount: state.acknowledgedCount,
        retryingCount: state.retryingCount,
      }),
    }
  )
);

/**
 * Hook to subscribe to outbox status changes and persist to IndexedDB
 */
export function useOutboxSync() {
  const refresh = useOutboxStore((state) => state.refresh);
  return { refresh };
}
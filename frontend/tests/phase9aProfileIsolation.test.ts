import "fake-indexeddb/auto";

// In-memory localStorage mock for node environment
const store: Record<string, string> = {};
const localStorageMock = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => {
    store[key] = String(value);
  },
  removeItem: (key: string) => {
    delete store[key];
  },
  clear: () => {
    for (const key of Object.keys(store)) delete store[key];
  },
  key: (i: number) => Object.keys(store)[i] ?? null,
  get length() {
    return Object.keys(store).length;
  },
};
Object.defineProperty(globalThis, "localStorage", {
  value: localStorageMock,
  writable: true,
  configurable: true,
});

import { describe, expect, it, vi, beforeEach } from "vitest";
import { useAuthStore } from "../src/features/auth/authStore";
import { useWorkspaceStore } from "../src/state/workspaceStore";
import { profilesApi } from "../src/services/api/profiles";
import { subjectsApi } from "../src/services/api/subjects";
import { getActiveModule } from "../src/services/api/client";
import { MODULE_SERVICE_MATRIX } from "../src/types/modules";
import type { Profile } from "../src/types/api";

describe("Phase 9A — Profile / Module / Subject Isolation", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    useWorkspaceStore.getState().resetWorkspace();
  });

  it("profilesApi.list() without module argument suppresses X-Active-Module header", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          count: 1,
          results: [
            {
              id: "p-ai-1",
              name: "Yash",
              module: "AI_CLASSROOM",
              created_at: "2026-09-22T00:00:00Z",
              updated_at: "2026-09-22T00:00:00Z",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const profiles = await profilesApi.list();
    expect(profiles).toHaveLength(1);
    expect(profiles[0].module).toBe("AI_CLASSROOM");

    const callHeaders = fetchSpy.mock.calls[0][1]?.headers as Record<string, string>;
    expect(callHeaders["X-Active-Module"]).toBeUndefined();
  });

  it("profilesApi.list('AI_CLASSROOM') passes X-Active-Module header", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ count: 1, results: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await profilesApi.list("AI_CLASSROOM");
    const callHeaders = fetchSpy.mock.calls[0][1]?.headers as Record<string, string>;
    expect(callHeaders["X-Active-Module"]).toBe("AI_CLASSROOM");
  });

  it("authStore.init() restores AI_CLASSROOM profile and sets module to AI_CLASSROOM", async () => {
    localStorage.setItem("studyai.access", "dummy-access-token");
    localStorage.setItem("studyai.email", "admin@studyai.dev");
    // Even if studyai.module was not saved or was NOTE_SPACE:
    localStorage.removeItem("studyai.module");

    const aiProfile: Profile = {
      id: "00950271-e8d4-449c-83fd-79ab0e88a842",
      name: "Yash",
      module: "AI_CLASSROOM",
      created_at: "2026-09-22T05:38:48Z",
      updated_at: "2026-09-22T05:38:54Z",
    };

    vi.spyOn(profilesApi, "list").mockResolvedValueOnce([aiProfile]);

    await useAuthStore.getState().init();

    const state = useAuthStore.getState();
    expect(state.profile).not.toBeNull();
    expect(state.profile?.id).toBe("00950271-e8d4-449c-83fd-79ab0e88a842");
    expect(state.profile?.name).toBe("Yash");
    expect(state.profile?.module).toBe("AI_CLASSROOM");
    expect(state.module).toBe("AI_CLASSROOM");
    expect(getActiveModule()).toBe("AI_CLASSROOM");
    expect(localStorage.getItem("studyai.module")).toBe("AI_CLASSROOM");
    expect(localStorage.getItem("studyai.profile")).toBe("00950271-e8d4-449c-83fd-79ab0e88a842");
  });

  it("authStore.switchToProfile switches module and resets workspace to prevent cross-profile bleed", async () => {
    const aiProfile: Profile = {
      id: "prof-ai-1",
      name: "AI Student",
      module: "AI_CLASSROOM",
      created_at: "2026-09-22T00:00:00Z",
      updated_at: "2026-09-22T00:00:00Z",
    };

    const nsProfile: Profile = {
      id: "prof-ns-2",
      name: "Notes Student",
      module: "NOTE_SPACE",
      created_at: "2026-09-22T00:00:00Z",
      updated_at: "2026-09-22T00:00:00Z",
    };

    // Start with AI Classroom profile
    useAuthStore.getState().switchToProfile(aiProfile);
    expect(useAuthStore.getState().module).toBe("AI_CLASSROOM");
    expect(useAuthStore.getState().profile?.id).toBe("prof-ai-1");

    // Populate workspace state
    useWorkspaceStore.setState({
      profileId: "prof-ai-1",
      loaded: true,
      subjects: [
        {
          id: "subj-dsa",
          name: "DSA",
          noteCount: 1,
          folderCount: 0,
          lastOpenedAt: null,
        },
        {
          id: "subj-ml",
          name: "ML",
          noteCount: 0,
          folderCount: 0,
          lastOpenedAt: null,
        },
      ],
    });

    expect(useWorkspaceStore.getState().subjects).toHaveLength(2);

    // Switch to NoteSpace profile
    useAuthStore.getState().switchToProfile(nsProfile);

    // Verify workspace was reset immediately
    const ws = useWorkspaceStore.getState();
    expect(ws.loaded).toBe(false);
    expect(ws.subjects).toHaveLength(0);
    expect(ws.profileId).toBeNull();

    // Verify auth state updated
    const authState = useAuthStore.getState();
    expect(authState.module).toBe("NOTE_SPACE");
    expect(authState.profile?.id).toBe("prof-ns-2");
    expect(getActiveModule()).toBe("NOTE_SPACE");
  });

  it("workspaceStore.loadWorkspace isolates subjects strictly by profileId", async () => {
    const profA = "prof-a-id";
    const profB = "prof-b-id";

    vi.spyOn(subjectsApi, "list").mockImplementation(async (profileId?: string) => {
      if (profileId === profA) {
        return [
          { id: "s-dsa", name: "DSA", profile: profA, created_at: "2026-09-22T00:00:00Z" },
          { id: "s-ml", name: "ML", profile: profA, created_at: "2026-09-22T00:00:00Z" },
        ];
      }
      if (profileId === profB) {
        return [
          { id: "s-history", name: "History", profile: profB, created_at: "2026-09-22T00:00:00Z" },
        ];
      }
      return [];
    });

    // Load Profile A
    await useWorkspaceStore.getState().loadWorkspace(profA);
    let state = useWorkspaceStore.getState();
    expect(state.profileId).toBe(profA);
    expect(state.subjects.map((s) => s.name)).toEqual(["DSA", "ML"]);

    // Reset and load Profile B
    useWorkspaceStore.getState().resetWorkspace();
    await useWorkspaceStore.getState().loadWorkspace(profB);
    state = useWorkspaceStore.getState();
    expect(state.profileId).toBe(profB);
    expect(state.subjects.map((s) => s.name)).toEqual(["History"]);
    expect(state.subjects.map((s) => s.name)).not.toContain("DSA");
    expect(state.subjects.map((s) => s.name)).not.toContain("ML");
  });

  it("MODULE_SERVICE_MATRIX correctly provisions AI_CLASSROOM vs NOTE_SPACE services", () => {
    const aiServices = MODULE_SERVICE_MATRIX.AI_CLASSROOM;
    expect(aiServices.chat).toBe(true);
    expect(aiServices.tests).toBe(true);
    expect(aiServices.qa).toBe(true);
    expect(aiServices.enrichment).toBe(true);
    expect(aiServices.write).toBe(true);
    expect(aiServices.transcription).toBe(true);

    const nsServices = MODULE_SERVICE_MATRIX.NOTE_SPACE;
    expect(nsServices.chat).toBe(false);
    expect(nsServices.tests).toBe(false);
    expect(nsServices.qa).toBe(false);
    expect(nsServices.enrichment).toBe(true);
  });
});

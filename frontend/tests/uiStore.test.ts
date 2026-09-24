import { describe, expect, it, beforeEach } from "vitest";
import { useUiStore } from "../src/state/uiStore";

// Mock localStorage
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
};
Object.defineProperty(globalThis, "localStorage", {
  value: localStorageMock,
  writable: true,
  configurable: true,
});

describe("Dynamic Sidebar (useUiStore)", () => {
  beforeEach(() => {
    localStorage.clear();
    useUiStore.setState({
      sidebarCollapsed: false,
      mobileSidebarOpen: false,
    });
  });

  it("initializes with sidebar expanded by default", () => {
    expect(useUiStore.getState().sidebarCollapsed).toBe(false);
  });

  it("toggles sidebar to collapsed and persists to localStorage", () => {
    useUiStore.getState().toggleSidebar();
    expect(useUiStore.getState().sidebarCollapsed).toBe(true);
    expect(localStorage.getItem("studyai.sidebar_collapsed")).toBe("true");

    // Toggle back to expanded
    useUiStore.getState().toggleSidebar();
    expect(useUiStore.getState().sidebarCollapsed).toBe(false);
    expect(localStorage.getItem("studyai.sidebar_collapsed")).toBe("false");
  });

  it("explicitly sets sidebar collapsed state", () => {
    useUiStore.getState().setSidebarCollapsed(true);
    expect(useUiStore.getState().sidebarCollapsed).toBe(true);
    expect(localStorage.getItem("studyai.sidebar_collapsed")).toBe("true");

    useUiStore.getState().setSidebarCollapsed(false);
    expect(useUiStore.getState().sidebarCollapsed).toBe(false);
    expect(localStorage.getItem("studyai.sidebar_collapsed")).toBe("false");
  });

  it("manages mobile sidebar open and close state", () => {
    expect(useUiStore.getState().mobileSidebarOpen).toBe(false);

    useUiStore.getState().setMobileSidebarOpen(true);
    expect(useUiStore.getState().mobileSidebarOpen).toBe(true);

    useUiStore.getState().closeMobileSidebar();
    expect(useUiStore.getState().mobileSidebarOpen).toBe(false);
  });
});

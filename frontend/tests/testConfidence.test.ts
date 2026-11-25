import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";

const mockApiRequest = vi.fn().mockResolvedValue({ attempt: { correct: true }, mastery: null });
vi.mock("../src/services/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/services/api/client")>();
  return {
    ...actual,
    apiRequest: mockApiRequest,
  };
});

describe("Tests confidence selector & API forwarding (R5)", () => {
  beforeEach(() => {
    mockApiRequest.mockClear();
  });

  it("forwards caller-selected confidence instead of hardcoding 0.8", async () => {
    const { testsApi } = await import("../src/services/api/tests");
    await testsApi.submitAttempt("test-1", "q-1", 2, 0.4);
    expect(mockApiRequest).toHaveBeenCalledWith(
      "/tests/test-1/attempts",
      expect.objectContaining({
        method: "POST",
        body: { question_id: "q-1", selected_index: 2, confidence: 0.4 },
      }),
    );

    await testsApi.submitAttempt("test-1", "q-1", 1, 1.0);
    expect(mockApiRequest).toHaveBeenLastCalledWith(
      "/tests/test-1/attempts",
      expect.objectContaining({
        body: { question_id: "q-1", selected_index: 1, confidence: 1.0 },
      }),
    );
  });

  it("exposes selectable confidence options in TestsPage", async () => {
    const mod = await import("../src/components/tests/TestsPage");
    expect((mod as any).CONFIDENCE_OPTIONS).toEqual([
      { value: 0.4, label: "Guess" },
      { value: 0.75, label: "Unsure" },
      { value: 1.0, label: "Confident" },
    ]);
    const html = renderToStaticMarkup(
      createElement((mod as any).ConfidenceSelector, {
        questionId: "q-1",
        value: 0.4,
        disabled: false,
        onChange: () => {},
      }),
    );
    expect(html).toContain("Guess");
    expect(html).toContain("Unsure");
    expect(html).toContain("Confident");
  });
});

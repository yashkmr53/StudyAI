/**
 * TestsService client (§23). Backend test contracts are still loose, so the
 * client normalizes aggressively and the UI renders honest empty/error
 * states when the API cannot serve a test yet.
 */
import { apiRequest } from "./client";
import type { TestAttemptQuestion, TestSummary } from "../../types/domain";
import { listAll } from "./pagination";
import { appI18n } from "../../i18n";

interface WireTest {
  id?: string;
  title?: string;
  subject?: string | null;
  question_count?: number;
  status?: string;
  mastery?: unknown;
  created_at?: string;
  questions?: WireQuestion[];
}

interface WireQuestion {
  id?: string;
  prompt?: string;
  options?: unknown;
  answer_index?: number;
}

function normalizeOptions(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((o) => String(o));
  if (raw && typeof raw === "object") return Object.values(raw).map((v) => String(v));
  return [];
}

function normalizeTest(wire: WireTest): TestSummary | null {
  if (!wire.id) return null;
  const status =
    wire.status === "completed" || wire.status === "draft" ? wire.status : "ready";
  return {
    id: wire.id,
    title: wire.title || "Untitled test",
    subjectId: wire.subject ?? null,
    questionCount: wire.question_count ?? wire.questions?.length ?? 0,
    status,
    mastery:
      typeof wire.mastery === "number"
        ? wire.mastery
        : Number.isFinite(Number(wire.mastery))
          ? Number(wire.mastery)
          : null,
    createdAt: wire.created_at,
  };
}

export const testsApi = {
  async list(): Promise<TestSummary[]> {
    const wire = await listAll<WireTest>("/tests");
    return wire.map(normalizeTest).filter((t): t is TestSummary => t !== null);
  },

  create(subjectId: string | null, title: string): Promise<TestSummary> {
    return apiRequest<WireTest>("/tests", {
      method: "POST",
      body: { subject: subjectId, title },
    }).then((wire) => {
      const t = normalizeTest(wire);
      if (!t) throw new Error(appI18n.t("errors.testCreateFailed"));
      return t;
    });
  },

  /** Questions for an attempt; answers may be withheld until submission. */
  async getQuestions(testId: string): Promise<TestAttemptQuestion[]> {
    const payload = await apiRequest<WireTest>(`/tests/${testId}`);
    return (payload.questions ?? [])
      .filter((q) => q.id && q.prompt)
      .map((q) => ({
        id: q.id as string,
        prompt: q.prompt as string,
        options: normalizeOptions(q.options),
        answerIndex:
          typeof q.answer_index === "number" ? q.answer_index : null,
      }));
  },

  submitAttempt(
    testId: string,
    answers: Record<string, number>,
  ): Promise<{ score: number }> {
    return apiRequest<{ score?: number }>(`/tests/${testId}/attempts`, {
      method: "POST",
      body: { answers },
    }).then((r) => ({ score: r.score ?? 0 }));
  },
};

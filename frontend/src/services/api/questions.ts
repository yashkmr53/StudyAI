/**
 * QAService client — practice questions generated per document (§24).
 * Parsed defensively; the UI consumes normalized PracticeQuestion values.
 */
import type { PracticeQuestion } from "../../types/domain";
import { listAll } from "./pagination";

interface WireQuestion {
  id?: string;
  document?: string;
  prompt?: string;
  options?: unknown;
  answer_index?: number;
  answer_text?: string;
  difficulty?: string;
  stale?: boolean;
}

function normalizeOptions(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((o) => String(o));
  if (raw && typeof raw === "object") {
    const rec = raw as Record<string, unknown>;
    const values = Object.values(rec);
    if (values.every((v) => typeof v === "string")) {
      return values.map((v) => String(v));
    }
  }
  return [];
}

function normalize(q: WireQuestion): PracticeQuestion | null {
  const options = normalizeOptions(q.options);
  if (!q.id || !q.prompt || options.length === 0) return null;
  return {
    id: q.id,
    documentId: q.document ?? "",
    prompt: q.prompt,
    options,
    answerIndex: Math.max(0, q.answer_index ?? 0),
    answerText: q.answer_text ?? "",
    difficulty:
      q.difficulty === "easy" || q.difficulty === "hard" ? q.difficulty : "medium",
    stale: Boolean(q.stale),
  };
}

export const questionsApi = {
  /** All practice questions belonging to one document. */
  async listForDocument(documentId: string): Promise<PracticeQuestion[]> {
    const wire = await listAll<WireQuestion>(`/documents/${documentId}/questions`);
    return wire
      .map(normalize)
      .filter((q): q is PracticeQuestion => q !== null);
  },
};

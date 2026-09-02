/**
 * ChatService client (§25). Subject-scoped sessions; messages posted to
 * `/chat/sessions/{id}/messages`. Wire shapes parsed defensively.
 */
import { apiRequest } from "./client";
import type { ChatCitation, ChatThreadSummary, ChatMessageItem } from "../../types/domain";
import { listAll } from "./pagination";

interface WireSession {
  id?: string;
  subject?: string | null;
  title?: string;
  created_at?: string;
}

interface WireMessage {
  id?: string;
  role?: string;
  content?: string;
  citations?: unknown;
}

function normalizeCitations(raw: unknown): ChatCitation[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((r): ChatCitation | null => {
      if (r && typeof r === "object") {
        const obj = r as Record<string, unknown>;
        return {
          source_id: typeof obj.source_id === "string" ? obj.source_id : undefined,
          source_type: typeof obj.source_type === "string" ? obj.source_type : "database",
          chunk_id: typeof obj.chunk_id === "string" ? obj.chunk_id : undefined,
          document_id: typeof obj.document_id === "string" ? obj.document_id : undefined,
          document_title: typeof obj.document_title === "string" ? obj.document_title : obj.document_title ?? null,
          subject_name: typeof obj.subject_name === "string" ? obj.subject_name : obj.subject_name ?? null,
          page_start: typeof obj.page_start === "number" ? obj.page_start : undefined,
          page_end: typeof obj.page_end === "number" ? obj.page_end : undefined,
          snippet: typeof obj.snippet === "string" ? obj.snippet : undefined,
          rrf_score: typeof obj.rrf_score === "number" ? obj.rrf_score : undefined,
          url: typeof obj.url === "string" ? obj.url : obj.url ?? null,
        } as ChatCitation;
      }
      if (typeof r === "number") return { page_start: r } as ChatCitation;
      return null;
    })
    .filter((c): c is ChatCitation => c !== null);
}

export const chatApi = {
  async listSessions(): Promise<ChatThreadSummary[]> {
    const wire = await listAll<WireSession>("/chat/sessions");
    return wire
      .filter((s): s is WireSession & { id: string } => Boolean(s.id))
      .map((s) => ({
        id: s.id,
        title: s.title || "New chat",
        subjectId: s.subject ?? null,
        createdAt: s.created_at,
      }));
  },

  createSession(subjectId: string, title: string): Promise<ChatThreadSummary> {
    return apiRequest<WireSession>("/chat/sessions", {
      method: "POST",
      body: { subject: subjectId || null, title },
    }).then((s) => ({
      id: s.id as string,
      title: s.title || title || "New chat",
      subjectId: s.subject ?? null,
      createdAt: s.created_at,
    }));
  },

  async listMessages(sessionId: string): Promise<ChatMessageItem[]> {
    const payload = await apiRequest<unknown>(`/chat/sessions/${sessionId}/messages`);
    const wire: WireMessage[] = Array.isArray(payload)
      ? (payload as WireMessage[])
      : ((payload as { results?: WireMessage[] })?.results ?? []);
    return wire
      .filter((m) => m.content != null)
      .map((m) => ({
        id: m.id ?? crypto.randomUUID(),
        role: m.role === "user" ? "user" : "assistant",
        content: String(m.content),
        citations: normalizeCitations(m.citations),
      }));
  },

  /** Send a user message; resolves with the assistant reply when ready. */
  sendMessage(
    sessionId: string,
    content: string,
  ): Promise<{ user: ChatMessageItem; assistant: ChatMessageItem }> {
    return apiRequest<WireMessage>(`/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      body: { content },
    }).then((reply) => {
      const assistantContent = reply.content ?? "";
      const citations = normalizeCitations(reply.citations);
      const now = () => crypto.randomUUID();
      return {
        user: { id: `u-${now()}`, role: "user", content, citations: [] },
        assistant: {
          id: `a-${now()}`,
          role: "assistant" as const,
          content: assistantContent,
          citations,
        },
      };
    });
  },
};

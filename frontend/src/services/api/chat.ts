/**
 * ChatService client (§25). Subject-scoped sessions; messages posted to
 * `/chat/sessions/{id}/messages`. Wire shapes parsed defensively.
 */
import { apiRequest } from "./client";
import type { ChatMessageItem, ChatThreadSummary, CitationRef } from "../../types/domain";
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

function normalizeCitations(raw: unknown): CitationRef[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((r) => {
      if (typeof r === "number") return { page: r };
      if (r && typeof r === "object" && typeof (r as WireSourceRef).page_number === "number") {
        return { page: (r as WireSourceRef).page_number as number };
      }
      return null;
    })
    .filter((c): c is CitationRef => c !== null);
}

interface WireSourceRef {
  page_number?: number;
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
      title: s.title || title,
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
    return apiRequest<unknown>(`/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      body: { role: "user", content },
    }).then((payload) => {
      // The backend may reply with the full exchange or just the answer text.
      let assistantContent = "";
      let citations: CitationRef[] = [];
      if (typeof payload === "string") {
        assistantContent = payload;
      } else if (payload && typeof payload === "object") {
        const rec = payload as Record<string, unknown>;
        const reply = (rec.assistant ?? rec.reply ?? rec.message) as
          | WireMessage
          | string
          | undefined;
        if (typeof reply === "string") assistantContent = reply;
        else if (reply?.content) {
          assistantContent = reply.content;
          citations = normalizeCitations(reply.citations);
        }
      }
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

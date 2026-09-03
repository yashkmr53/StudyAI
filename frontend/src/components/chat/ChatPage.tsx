import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { ModuleProvider, useSubjectModule } from "../modules/ModuleContext";
import { EmptyState, ErrorState } from "../ui/primitives";
import { ChatIcon, PlusIcon, SparkleIcon } from "../ui/icons";
import { chatApi } from "../../services/api/chat";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { useAgentChat } from "../../hooks/useAgentChat";
import { ToolStatusIndicator } from "./ToolStatusIndicator";
import { AgentMessageBubble } from "./AgentMessageBubble";
import type { ChatMessageItem, ChatThreadSummary } from "../../types/domain";
import type { AgentMessage } from "../../types/agent";

/** Ask StudyAI (§25) — module-scoped chat with optional agent mode (Phase 2). */
export function ChatPage() {
  const { subjectId } = useParams<{ subjectId?: string }>();
  const subjects = useWorkspaceStore((s) => s.subjects);
  const subjectName = subjects.find((s) => s.id === subjectId)?.name ?? "";
  const { moduleId, services } = useSubjectModule(subjectId);
  const { t } = useTranslation();

  const [threads, setThreads] = useState<ChatThreadSummary[] | null>(null);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [agentMode, setAgentMode] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sendingRef = useRef(false);
  const streamAbortRef = useRef<AbortController | null>(null);

  const {
    sendMessage: sendAgentMessage,
    sending: agentSending,
    toolCalls,
  } = useAgentChat({
    sessionId: activeThreadId || "",
    onMessageSent: (userMsg, assistantMsg) => {
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
    },
    onError: (err) => {
      setError(err.message);
      setMessages((prev) => prev.filter((m) => !m.id.startsWith("pending-")));
    },
  });

  useEffect(() => {
    let cancelled = false;
    chatApi
      .listSessions()
      .then((all) => {
        if (cancelled) return;
        const mine = all.filter((t) => !subjectId ? t.subjectId === null : t.subjectId === null || t.subjectId === subjectId);
        setThreads(mine);
        setActiveThreadId(mine[0]?.id ?? null);
      })
      .catch(() => !cancelled && setError(t("chat.loadSessionsFailed")));
    return () => {
      cancelled = true;
    };
  }, [subjectId]);

  useEffect(() => {
    if (!activeThreadId) return;
    let cancelled = false;
    if (!sendingRef.current) {
      setMessages([]);
    }
    chatApi
      .listMessages(activeThreadId)
      .then((m) => !cancelled && setMessages(m))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [activeThreadId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  // Auto-scroll while streaming so users see tokens arrive live.
  useEffect(() => {
    if (!streaming) return;
    const id = window.setInterval(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    }, 80);
    return () => window.clearInterval(id);
  }, [streaming]);

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
    };
  }, []);

  async function newThread() {
    setError(null);
    try {
      const thread = await chatApi.createSession(
        subjectId ?? "",
        "",
      );
      setThreads((prev) => [thread, ...(prev ?? [])]);
      setActiveThreadId(thread.id);
      setMessages([]);
    } catch {
      setError(t("chat.createSessionFailed"));
    }
  }

  async function send() {
    const content = draft.trim();
    if (!content || !activeThreadId || sendingRef.current) return;
    setDraft("");
    sendingRef.current = true;

    const pendingId = `pending-${crypto.randomUUID()}`;
    const userMsg: ChatMessageItem = { id: `u-${pendingId}`, role: "user", content, citations: [] };
    const pendingAssistantMsg: ChatMessageItem = {
      id: pendingId,
      role: "assistant",
      content: "",
      citations: [],
      pending: true,
    };

    setMessages((prev) => [...prev, userMsg, pendingAssistantMsg]);
    setError(null);

    if (agentMode) {
      try {
        const reply = await sendAgentMessage(content);
        if (!reply) {
          setMessages((prev) => prev.filter((m) => m.id !== pendingId && m.id !== userMsg.id));
        }
      } catch {
        setMessages((prev) => prev.filter((m) => m.id !== pendingId && m.id !== userMsg.id));
        setMessages((prev) => [
          ...prev,
          {
            id: pendingId,
            role: "assistant",
            content: t("chat.sendFailedBubble"),
            citations: [],
          },
        ]);
      } finally {
        sendingRef.current = false;
      }
      return;
    }

    // Streaming classic RAG chat
    const abort = new AbortController();
    streamAbortRef.current = abort;
    setStreaming(true);

    const appendToken = (delta: string) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingId ? { ...m, content: m.content + delta, pending: false } : m,
        ),
      );
    };

    const setCitations = (citations: ChatMessageItem["citations"]) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === pendingId ? { ...m, citations } : m)),
      );
    };

    const finalize = (fallbackContent?: string) => {
      setMessages((prev) => {
        const exists = prev.some((m) => m.id === pendingId);
        if (!exists) return prev;
        return prev.map((m) =>
          m.id === pendingId
            ? { ...m, pending: false, content: m.content || fallbackContent || "" }
            : m,
        );
      });
    };

    try {
      for await (const evt of chatApi.sendMessageStream(activeThreadId, content, {
        signal: abort.signal,
        agentMode: false,
      })) {
        if (abort.signal.aborted) break;
        if (evt.event === "title") {
          const data = evt.data as { title: string; session_id: string };
          setThreads((prev) => {
            const list = prev ?? [];
            const existing = list.find((th) => th.id === data.session_id);
            if (existing && existing.title === data.title) return list;
            if (existing) {
              return list.map((th) =>
                th.id === data.session_id ? { ...th, title: data.title } : th,
              );
            }
            return [
              {
                id: data.session_id,
                title: data.title,
                subjectId: subjectId ?? null,
                createdAt: new Date().toISOString(),
              },
              ...list,
            ];
          });
        } else if (evt.event === "token") {
          const data = evt.data as { delta: string };
          if (data?.delta) appendToken(data.delta);
        } else if (evt.event === "citations") {
          const data = evt.data as { citations: ChatMessageItem["citations"] };
          setCitations(normalizeCitations(data?.citations));
        } else if (evt.event === "done") {
          finalize();
          break;
        } else if (evt.event === "error") {
          const data = evt.data as { message: string };
          finalize(data?.message || t("chat.sendFailedBubble"));
          setError(data?.message || t("chat.sendFailedBubble"));
          break;
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t("chat.sendFailedBubble");
      finalize(message);
      setError(message);
    } finally {
      setStreaming(false);
      streamAbortRef.current = null;
      sendingRef.current = false;
    }
  }

  const sending = streaming || agentSending;

  return (
    <ModuleProvider value={{ moduleId, services }}>
      <div className="content__inner content__inner--wide" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
        <Breadcrumbs
          crumbs={
            subjectId
              ? [
                  { label: t("common.breadcrumb.subjects"), to: "/subjects" },
                  { label: subjectName, to: `/subjects/${subjectId}` },
                  { label: t("chat.title") },
                ]
              : [
                  { label: t("modules.classroomBanner", { defaultValue: "AI Classroom" }), to: "/subjects" },
                  { label: t("chat.title") },
                ]
          }
        />

        <div className="page-heading page-heading__row" style={{ marginTop: 14, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1>{t("chat.title")}</h1>
            <p className="subtitle" style={{ marginTop: 5 }}>
              {subjectId ? t("chat.subtitle", { subject: subjectName }) : t("chat.subtitleModule")}
            </p>
          </div>
          <label className="flex items-center gap-2 cursor-pointer" style={{ marginTop: 4 }}>
            <input
              type="checkbox"
              checked={agentMode}
              onChange={(e) => setAgentMode(e.target.checked)}
              className="checkbox"
              disabled={sending}
            />
            <span className="flex items-center gap-1 text-sm">
              <SparkleIcon size={14} />
              {t("chat.agentMode", { defaultValue: "Agent Mode" })}
            </span>
          </label>
        </div>

        <div className="chat-layout grow" style={{ minHeight: 480 }}>
          <aside aria-label={t("chat.chatsAria")}>
            <button type="button" className="btn btn--secondary btn--sm btn--block" onClick={() => void newThread()}>
              <PlusIcon size={13} />
              {t("chat.newChat")}
            </button>
            <div className="chat-thread-list" style={{ marginTop: 10 }}>
              {!threads && <div className="skeleton" style={{ height: 64 }} />}
              {threads?.map((thread) => (
                <button
                  key={thread.id}
                  type="button"
                  className={thread.id === activeThreadId ? "chat-thread-item active" : "chat-thread-item"}
                  onClick={() => setActiveThreadId(thread.id)}
                >
                  <span className="chat-thread-item__title">
                    {thread.title || t("modules.classroomBanner", { defaultValue: "AI Classroom" })}
                  </span>
                </button>
              ))}
              {threads && threads.length === 0 && (
                <p className="faint small" style={{ padding: "4px 2px" }}>
                  {t("chat.threadsEmpty")}
                </p>
              )}
            </div>
          </aside>

          {error ? (
            <ErrorState
              message={error}
              onRetry={() => void newThread()}
              retryLabel={t("chat.retryNewChat")}
            />
          ) : !activeThreadId ? (
            <div className="card chat-panel">
              <EmptyState
                plain
                icon={<ChatIcon size={20} />}
                title={t("chat.noThreadTitle")}
                description={t("chat.noThreadDescription")}
                action={
                  <button type="button" className="btn btn--primary" onClick={() => void newThread()}>
                    <PlusIcon size={14} />
                    {t("chat.newChat")}
                  </button>
                }
              />
            </div>
          ) : (
            <div className="card chat-panel">
              <div className="chat-messages" ref={scrollRef}>
                {messages.length === 0 && (
                  <p className="faint small" style={{ textAlign: "center", marginTop: 24 }}>
                    {t("chat.introHint")}
                  </p>
                )}
                {messages.map((message) => {
                  const agentMsg = message as AgentMessage;
                  if (agentMsg.toolCalls && agentMsg.toolCalls.length > 0) {
                    return (
                      <AgentMessageBubble key={message.id} message={agentMsg} />
                    );
                  }
                  return (
                    <div key={message.id} className={message.role === "user" ? "msg msg--user" : "msg msg--assistant"}>
                      <div className={message.pending && !message.content ? "msg__bubble pending" : "msg__bubble"}>
                        {message.pending && !message.content ? (
                          <span className="typing-dots" aria-label={t("chat.thinkingAria")}>
                            <span />
                            <span />
                            <span />
                          </span>
                        ) : (
                          message.content || t("chat.emptyResponse")
                        )}
                      </div>
                      {message.citations.length > 0 && (
                        <div className="citations-row">
                          <span className="citations-label">Sources</span>
                          {message.citations
                            .filter((c) => c.source_type !== "verification")
                            .map((citation, i) => {
                              const num = i + 1;
                              let label: string;
                              if (citation.source_type === "web") {
                                const title = citation.title || citation.url || "Web source";
                                const domain = citation.domain || "";
                                label = domain ? `${num} ${title} — ${domain}` : `${num} ${title}`;
                                return (
                                  <a
                                    key={citation.source_id ?? num}
                                    href={citation.url ?? undefined}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="citation-chip citation-chip--web"
                                    role="presentation"
                                  >
                                    {label}
                                  </a>
                                );
                              }
                              const title = citation.document_title || citation.subject_name || "Your notes";
                              const pages = citation.page_start
                                ? citation.page_end && citation.page_end !== citation.page_start
                                  ? `pp. ${citation.page_start}-${citation.page_end}`
                                  : `p. ${citation.page_start}`
                                : "";
                              label = `${num} ${title}${pages ? " · " + pages : ""}`;
                              return (
                                <span key={citation.source_id ?? num} className="citation-chip" role="presentation">
                                  {label}
                                </span>
                              );
                            })}
                        </div>
                      )}
                    </div>
                  );
                })}
                {agentMode && agentSending && toolCalls.length > 0 && (
                  <div className="active-tool-calls space-y-2 p-3 bg-blue-50 rounded-lg border border-blue-100 animate-pulse">
                    <div className="text-sm font-medium text-blue-700">Agent is working…</div>
                    <div className="space-y-1 mt-1">
                      {toolCalls.map((tc, i) => (
                        <ToolStatusIndicator key={i} toolCall={tc} compact />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <form
                className="chat-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  void send();
                }}
              >
                <input
                  className="input"
                  placeholder={agentMode ? t("chat.agentComposerPlaceholder", { defaultValue: "Ask me to create a test, find weak topics, plan revision…" }) : t("chat.composerPlaceholder")}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  aria-label={t("chat.messageAria")}
                  disabled={!activeThreadId || sending}
                />
                <button type="submit" className="btn btn--primary" disabled={!draft.trim() || sending}>
                  {t("common.actions.send")}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </ModuleProvider>
  );
}

// Local helper kept in this file because the page is the only consumer.
function normalizeCitations(raw: unknown): ChatMessageItem["citations"] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((r): import("../../types/domain").ChatCitation | null => {
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
        } as import("../../types/domain").ChatCitation;
      }
      return null;
    })
    .filter((c): c is import("../../types/domain").ChatCitation => c !== null);
}
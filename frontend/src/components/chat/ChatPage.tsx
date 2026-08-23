import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { ModuleProvider, useSubjectModule } from "../modules/ModuleContext";
import { EmptyState, ErrorState } from "../ui/primitives";
import { ChatIcon, PlusIcon } from "../ui/icons";
import { chatApi } from "../../services/api/chat";
import { useWorkspaceStore } from "../../state/workspaceStore";
import type { ChatMessageItem, ChatThreadSummary } from "../../types/domain";

/** Ask StudyAI (§25) — module-scoped chat; only when ChatService is enabled. */
export function ChatPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const subjects = useWorkspaceStore((s) => s.subjects);
  const subjectName = subjects.find((s) => s.id === subjectId)?.name ?? "";
  const { moduleId, services } = useSubjectModule(subjectId);
  const { t } = useTranslation();

  const [threads, setThreads] = useState<ChatThreadSummary[] | null>(null);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    chatApi
      .listSessions()
      .then((all) => {
        if (cancelled) return;
        const mine = all.filter((t) => !subjectId || t.subjectId === null || t.subjectId === subjectId);
        setThreads(mine);
        setActiveThreadId(mine[0]?.id ?? null);
      })
      .catch(() => !cancelled && setError(t("chat.loadSessionsFailed")));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectId]);

  useEffect(() => {
    if (!activeThreadId) return;
    let cancelled = false;
    setMessages([]);
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

  async function newThread() {
    setError(null);
    try {
      const thread = await chatApi.createSession(
        subjectId ?? "",
        subjectName
          ? t("chat.defaultThreadTitle", { subject: subjectName })
          : t("chat.newChat"),
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
    if (!content || !activeThreadId || sending) return;
    setSending(true);
    setDraft("");
    const pendingId = `pending-${crypto.randomUUID()}`;
    setMessages((prev) => [
      ...prev,
      { id: `u-${pendingId}`, role: "user", content, citations: [] },
      { id: pendingId, role: "assistant", content: "", citations: [], pending: true },
    ]);
    try {
      const reply = await chatApi.sendMessage(activeThreadId, content);
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== pendingId),
        reply.user,
        reply.assistant,
      ]);
    } catch {
      setMessages((prev) => prev.filter((m) => m.id !== pendingId));
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
      setSending(false);
    }
  }

  return (
    <ModuleProvider value={{ moduleId, services }}>
      <div className="content__inner content__inner--wide" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
        <Breadcrumbs
          crumbs={[
            { label: t("common.breadcrumb.subjects"), to: "/subjects" },
            ...(subjectName ? [{ label: subjectName, to: `/subjects/${subjectId}` }] : []),
            { label: t("chat.title") },
          ]}
        />

        <div className="page-heading page-heading__row" style={{ marginTop: 14 }}>
          <div>
            <h1>{t("chat.title")}</h1>
            <p className="subtitle" style={{ marginTop: 5 }}>
              {t("chat.subtitle", { subject: subjectName })}
            </p>
          </div>
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
                  <span className="chat-thread-item__title">{thread.title}</span>
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
                {messages.map((message) => (
                  <div key={message.id} className={message.role === "user" ? "msg msg--user" : "msg msg--assistant"}>
                    <div className={message.pending ? "msg__bubble pending" : "msg__bubble"}>
                      {message.pending ? (
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
                        {message.citations.map((citation, i) => (
                          <span key={i} className="citation-chip" role="presentation">
                            Page {citation.page}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
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
                  placeholder={t("chat.composerPlaceholder")}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  aria-label={t("chat.messageAria")}
                  disabled={!activeThreadId}
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

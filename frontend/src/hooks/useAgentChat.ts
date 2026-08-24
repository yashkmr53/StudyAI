/** Agent chat hook (Phase 2). */

import { useState, useCallback } from "react";
import { agentApi } from "../services/api/agent";
import type { AgentResponse, ToolCall, AgentTrace } from "../types/agent";
import type { ChatMessageItem } from "../types/domain";

interface UseAgentChatOptions {
  sessionId: string;
  onMessageSent?: (userMsg: ChatMessageItem, assistantMsg: ChatMessageItem) => void;
  onError?: (error: Error) => void;
}

export function useAgentChat({ sessionId, onMessageSent, onError }: UseAgentChatOptions) {
  const [sending, setSending] = useState(false);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [agentTrace, setAgentTrace] = useState<AgentTrace | null>(null);

  const sendMessage = useCallback(
    async (content: string): Promise<{ user: ChatMessageItem; assistant: ChatMessageItem } | null> => {
      if (!content.trim() || sending) return null;

      setSending(true);
      setToolCalls([]);
      setAgentTrace(null);

      try {
        const response = await agentApi.sendMessage(sessionId, content);

        // Extract tool calls from assistant message
        const assistantToolCalls = response.assistant.toolCalls || [];
        setToolCalls(assistantToolCalls);

        // Extract agent trace
        if (response.assistant.traceId) {
          setAgentTrace({
            traceId: response.assistant.traceId,
            iterations: response.assistant.iterations || 0,
            totalTokens: response.assistant.totalTokens || 0,
            totalLatencyMs: response.assistant.totalLatencyMs || 0,
            outcome: (response.assistant.outcome as AgentResponse["assistant"]["outcome"]) || "success",
            verificationStatus: response.assistant.verificationStatus,
            verificationScore: response.assistant.verificationScore,
          });
        }

        const userMsg: ChatMessageItem = {
          id: response.user.id,
          role: "user",
          content: response.user.content,
          citations: [],
        };

        const assistantMsg: ChatMessageItem = {
          id: response.assistant.id,
          role: "assistant",
          content: response.assistant.content,
          citations: response.assistant.citations || [],
        };

        onMessageSent?.(userMsg, assistantMsg);

        return { user: userMsg, assistant: assistantMsg };
      } catch (err) {
        const error = err instanceof Error ? err : new Error("Failed to send message");
        onError?.(error);
        return null;
      } finally {
        setSending(false);
      }
    },
    [sessionId, sending, onMessageSent, onError]
  );

  return {
    sendMessage,
    sending,
    toolCalls,
    agentTrace,
  };
}
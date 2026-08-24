# Phase 1 — Frontend Integration Guide

**Date:** 2026-08-24  
**Status:** DESIGN COMPLETE (Implementation pending)

---

## Overview

This document describes the frontend changes needed to integrate the StudyAI Agent with the existing "Ask StudyAI" chat interface.

## API Client (`frontend/src/services/api/agent.ts`)

```typescript
import { apiRequest } from "./client";
import type { AgentResponse, ToolCall, ToolMetadata } from "../../types/agent";

export const agentApi = {
  /** Send a message through the StudyAI Agent. */
  async sendMessage(sessionId: string, content: string): Promise<AgentResponse> {
    return apiRequest(`/agents/chat/`, {
      method: "POST",
      body: { session_id: sessionId, content },
    });
  },

  /** List all available agent tools with schemas. */
  async listTools(): Promise<ToolMetadata[]> {
    return apiRequest("/agents/tools/");
  },

  /** Get execution trace for debugging. */
  async getExecutionTrace(requestId: string): Promise<any> {
    return apiRequest(`/agents/executions/${requestId}/`);
  },
};
```

## TypeScript Types (`frontend/src/types/agent.ts`)

```typescript
export interface ToolCall {
  tool: string;
  status: "pending" | "running" | "success" | "error";
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string;
  latencyMs?: number;
}

export interface AgentResponse {
  user: ChatMessageItem;
  assistant: ChatMessageItem & {
    toolCalls?: ToolCall[];
    traceId?: string;
    iterations?: number;
    totalTokens?: number;
    totalLatencyMs?: number;
    outcome?: string;
    verificationStatus?: string;
    verificationScore?: number;
  };
}

export interface ToolMetadata {
  name: string;
  description: string;
  category: "retrieval" | "learning" | "evidence" | "document";
  inputSchema: JSONSchema;
  outputSchema: JSONSchema;
  requiresAuth: boolean;
  timeoutSeconds: number;
}

// JSON Schema type (simplified)
export interface JSONSchema {
  type: string;
  properties?: Record<string, JSONSchema>;
  required?: string[];
  items?: JSONSchema;
  enum?: string[];
  [key: string]: any;
}
```

## Tool Status Mapping

```typescript
// frontend/src/components/chat/ToolStatusIndicator.tsx
const TOOL_STATUS_LABELS: Record<string, string> = {
  search_notes: "Searching your notes...",
  search_reference_books: "Checking reference material...",
  get_mastery: "Analyzing mastery...",
  get_revision_plan: "Building revision plan...",
  get_previous_questions: "Loading previous questions...",
  generate_questions: "Generating questions...",
  create_test: "Creating test...",
  verify_evidence: "Verifying sources...",
  verify_citations: "Verifying citations...",
  get_document: "Loading document...",
  get_subject_context: "Loading subject context...",
};

const TOOL_CATEGORY_ICONS: Record<string, string> = {
  retrieval: "🔍",
  learning: "📚",
  evidence: "✅",
  document: "📄",
};

export function ToolStatusIndicator({ toolCall }: { toolCall: ToolCall }) {
  const label = TOOL_STATUS_LABELS[toolCall.tool] || toolCall.tool;
  const icon = TOOL_CATEGORY_ICONS[toolCall.tool] || "⚙️";
  
  const statusColors = {
    pending: "text-gray-500",
    running: "text-blue-500 animate-pulse",
    success: "text-green-500",
    error: "text-red-500",
  };

  return (
    <div className="tool-status-indicator flex items-center gap-2 text-sm">
      <span className={statusColors[toolCall.status]}>{icon}</span>
      <span className={statusColors[toolCall.status]}>{label}</span>
      {toolCall.status === "success" && toolCall.latencyMs && (
        <span className="text-gray-400 text-xs">({toolCall.latencyMs}ms)</span>
      )}
      {toolCall.status === "error" && toolCall.error && (
        <span className="text-red-500 text-xs">Error: {toolCall.error}</span>
      )}
    </div>
  );
}
```

## Enhanced Message Bubble (`frontend/src/components/chat/AgentMessageBubble.tsx`)

```tsx
import { ToolStatusIndicator } from "./ToolStatusIndicator";

export function AgentMessageBubble({ 
  message, 
  toolCalls = [],
  traceId,
  verificationStatus,
  verificationScore,
  iterations,
  totalLatencyMs
}: {
  message: ChatMessageItem;
  toolCalls?: ToolCall[];
  traceId?: string;
  verificationStatus?: string;
  verificationScore?: number;
  iterations?: number;
  totalLatencyMs?: number;
}) {
  return (
    <div className="msg msg--assistant agent-message">
      <div className="msg__bubble">{message.content}</div>
      
      {/* Citations */}
      {message.citations.length > 0 && (
        <div className="citations-row">
          {message.citations.map((citation, i) => (
            <span key={i} className="citation-chip">
              Page {citation.page}
            </span>
          ))}
        </div>
      )}

      {/* Verification Status */}
      {verificationStatus && (
        <div className="verification-status flex items-center gap-2 mt-2 text-sm">
          <span className="badge" style={{ 
            backgroundColor: verificationStatus === "supported" ? "#dcfce7" : 
                             verificationStatus === "partially_supported" ? "#fef3c7" : "#fee2e2",
            color: verificationStatus === "supported" ? "#166534" :
                   verificationStatus === "partially_supported" ? "#854d0e" : "#991b1b"
          }}>
            {verificationStatus.replace("_", " ")}
          </span>
          {verificationScore !== undefined && (
            <span className="text-gray-500">Score: {verificationScore.toFixed(2)}</span>
          )}
        </div>
      )}

      {/* Tool Calls Trace */}
      {toolCalls.length > 0 && (
        <details className="tool-calls-trace mt-2">
          <summary className="cursor-pointer text-sm text-gray-600">
            Show agent trace ({toolCalls.length} tools, {iterations} iterations, {totalLatencyMs}ms)
          </summary>
          <div className="mt-2 space-y-2">
            {toolCalls.map((tc, i) => (
              <div key={i} className="tool-call-entry p-2 bg-gray-50 rounded border">
                <ToolStatusIndicator toolCall={tc} />
                {tc.arguments && (
                  <details className="mt-1">
                    <summary className="text-xs text-gray-500">Arguments</summary>
                    <pre className="text-xs mt-1 p-2 bg-white rounded overflow-auto">
                      {JSON.stringify(tc.arguments, null, 2)}
                    </pre>
                  </details>
                )}
                {tc.result && (
                  <details className="mt-1">
                    <summary className="text-xs text-gray-500">Result</summary>
                    <pre className="text-xs mt-1 p-2 bg-white rounded overflow-auto max-h-48">
                      {JSON.stringify(tc.result, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        </details>
      )}

      {traceId && (
        <div className="trace-id text-xs text-gray-400 mt-2">
          Trace: {traceId}
        </div>
      )}
    </div>
  );
}
```

## Chat Page Integration (`frontend/src/components/chat/ChatPage.tsx`)

### Add Agent Mode Toggle

```tsx
// In ChatPage component
const [agentMode, setAgentMode] = useState(false);

// In the header section
<div className="flex items-center gap-2">
  <label className="flex items-center gap-1.5 text-sm cursor-pointer">
    <input
      type="checkbox"
      checked={agentMode}
      onChange={(e) => setAgentMode(e.target.checked)}
      className="checkbox"
    />
    <span>Agent Mode</span>
  </label>
</div>
```

### Use Agent API When Agent Mode Active

```tsx
// Replace chatApi.sendMessage with conditional logic
async function send() {
  const content = draft.trim();
  if (!content || !activeThreadId || sending) return;
  
  setSending(true);
  setDraft("");
  const pendingId = `pending-${crypto.randomUUID()}`;
  
  setMessages((prev) => [
    ...prev,
    { id: `u-${pendingId}`, role: "user", content, citations: [] },
    { id: pendingId, role: "assistant", content: "", citations: [], pending: true, toolCalls: [] },
  ]);

  try {
    let reply;
    if (agentMode) {
      // Use agentic endpoint
      reply = await agentApi.sendMessage(activeThreadId, content);
    } else {
      // Use classic RAG endpoint
      reply = await chatApi.sendMessage(activeThreadId, content);
    }
    
    setMessages((prev) => [
      ...prev.filter((m) => m.id !== pendingId),
      reply.user,
      { ...reply.assistant, toolCalls: reply.assistant.toolCalls || [] },
    ]);
  } catch {
    // Error handling...
  } finally {
    setSending(false);
  }
}
```

### Display Tool Calls in Real-time

For a better UX, show tool calls as they happen (requires WebSocket or polling):

```tsx
// Option 1: Poll for execution trace
useEffect(() => {
  if (!agentMode || !lastAssistantMessageId) return;
  
  const interval = setInterval(async () => {
    const trace = await agentApi.getExecutionTrace(lastAssistantMessageId);
    if (trace && trace.tool_call_sequence) {
      setToolCalls(trace.tool_call_sequence);
    }
  }, 1000);
  
  return () => clearInterval(interval);
}, [agentMode, lastAssistantMessageId]);
```

## Verification Status Badges

```css
/* frontend/src/components/chat/ChatPage.css or global styles */

.verification-status .badge {
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 500;
  font-size: 0.75rem;
}

.tool-status-indicator {
  transition: opacity 0.2s;
}

.tool-call-entry {
  border-left: 3px solid #e5e7eb;
}

.tool-call-entry.success {
  border-left-color: #22c55e;
}

.tool-call-entry.error {
  border-left-color: #ef4444;
}

.tool-call-entry.running {
  border-left-color: #3b82f6;
}
```

## Migration Path

1. **Phase 1a** (Current): Agent mode toggle + basic tool trace display
2. **Phase 1b**: Real-time tool status updates via polling/WebSocket
3. **Phase 1c**: Rich rendering of structured outputs (questions, tests, revision plans)
4. **Phase 2**: Artifact preview (PDF/PPTX/DOCX generation results)

## Backward Compatibility

- Existing chat sessions work unchanged
- Agent mode is opt-in via header or toggle
- Classic RAG mode remains default
- No database schema changes to chat messages

## Testing Checklist

- [ ] Agent mode toggle appears in chat header
- [ ] Sending message with agent mode shows tool status indicators
- [ ] Tool calls display with latency and success/error status
- [ ] Final answer shows verification status badge
- [ ] Trace details expandable with arguments/results
- [ ] Classic mode (agent mode off) works identically to before
- [ ] Cross-profile access blocked (403 response)
- [ ] Error states handled gracefully (tool failures, timeouts)
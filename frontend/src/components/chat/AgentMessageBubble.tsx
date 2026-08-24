/** Agent message bubble with tool trace (Phase 2). */

import { ToolStatusIndicator } from "./ToolStatusIndicator";
import type { AgentMessage } from "../../types/agent";

interface AgentMessageBubbleProps {
  message: AgentMessage;
}

export function AgentMessageBubble({ message }: AgentMessageBubbleProps) {
  const { toolCalls = [], agentTrace, citations = [], verificationStatus, verificationScore } = message;

  return (
    <div className="msg msg--assistant agent-message">
      <div className="msg__bubble">{message.content}</div>

      {/* Citations */}
      {citations.length > 0 && (
        <div className="citations-row mt-2 flex flex-wrap gap-1">
          {citations.map((citation, i) => (
            <span
              key={i}
              className="citation-chip inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-700 border border-gray-200"
            >
              Page {citation.page}
            </span>
          ))}
        </div>
      )}

      {/* Verification Status */}
      {verificationStatus && (
        <div className="verification-status mt-2 flex items-center gap-2 text-xs">
          <span
            className="px-2 py-0.5 rounded-full font-medium"
            style={{
              backgroundColor:
                verificationStatus === "supported"
                  ? "#dcfce7"
                  : verificationStatus === "partially_supported"
                  ? "#fef3c7"
                  : verificationStatus === "unsupported"
                  ? "#fee2e2"
                  : "#f3f4f6",
              color:
                verificationStatus === "supported"
                  ? "#166534"
                  : verificationStatus === "partially_supported"
                  ? "#854d0e"
                  : verificationStatus === "unsupported"
                  ? "#991b1b"
                  : "#374151",
            }}
          >
            {verificationStatus.replace("_", " ")}
          </span>
          {verificationScore !== undefined && (
            <span className="text-gray-500">Score: {verificationScore.toFixed(2)}</span>
          )}
        </div>
      )}

      {/* Tool Calls Trace */}
      {toolCalls.length > 0 && (
        <details className="tool-calls-trace mt-3">
          <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-800 flex items-center gap-1">
            <span>🔧</span>
            Show agent trace ({toolCalls.length} tools, {agentTrace?.iterations || 0} iterations, {agentTrace?.totalLatencyMs || 0}ms)
          </summary>
          <div className="mt-2 space-y-2 border-l-2 border-gray-200 pl-3">
            {toolCalls.map((tc, i) => (
              <div key={i} className="tool-call-entry">
                <ToolStatusIndicator toolCall={tc} />
                {tc.arguments && (
                  <details className="mt-1 ml-6">
                    <summary className="text-xs text-gray-500 cursor-pointer">Arguments</summary>
                    <pre className="text-xs mt-1 p-2 bg-gray-50 rounded overflow-auto max-h-48">
                      {JSON.stringify(tc.arguments, null, 2)}
                    </pre>
                  </details>
                )}
                {tc.result && (
                  <details className="mt-1 ml-6">
                    <summary className="text-xs text-gray-500 cursor-pointer">Result</summary>
                    <pre className="text-xs mt-1 p-2 bg-gray-50 rounded overflow-auto max-h-64">
                      {JSON.stringify(tc.result, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        </details>
      )}

      {agentTrace?.traceId && (
        <div className="trace-id text-xs text-gray-400 mt-2 font-mono">
          Trace: {agentTrace.traceId}
        </div>
      )}
    </div>
  );
}
/** Tool status indicator component (Phase 2). */

import type { ToolCall } from "../../types/agent";

const TOOL_STATUS_LABELS: Record<string, string> = {
  search_notes: "Searching your notes…",
  search_reference_books: "Checking reference material…",
  get_mastery: "Analyzing mastery…",
  get_revision_plan: "Building revision plan…",
  get_previous_questions: "Loading previous questions…",
  generate_questions: "Generating questions…",
  create_test: "Creating test…",
  verify_evidence: "Verifying sources…",
  verify_citations: "Verifying citations…",
  get_document: "Loading document…",
  get_subject_context: "Loading subject context…",
  mastery_aware_test_generation: "Generating mastery-aware test…",
};

const TOOL_CATEGORY_ICONS: Record<string, string> = {
  retrieval: "🔍",
  learning: "📚",
  evidence: "✅",
  document: "📄",
};

const STATUS_STYLES: Record<ToolCall["status"], string> = {
  pending: "text-gray-500",
  running: "text-blue-500 animate-pulse",
  success: "text-green-600",
  error: "text-red-600",
};

interface ToolStatusIndicatorProps {
  toolCall: ToolCall;
  compact?: boolean;
}

export function ToolStatusIndicator({ toolCall, compact = false }: ToolStatusIndicatorProps) {
  const label = TOOL_STATUS_LABELS[toolCall.tool] || toolCall.tool;
  const icon = TOOL_CATEGORY_ICONS[toolCall.tool] || "⚙️";
  const style = STATUS_STYLES[toolCall.status] || "text-gray-500";

  if (compact) {
    return (
      <span className={`inline-flex items-center gap-1 text-xs ${style}`}>
        <span>{icon}</span>
        <span>{label}</span>
        {toolCall.status === "success" && toolCall.latencyMs && (
          <span className="text-gray-400">({toolCall.latencyMs}ms)</span>
        )}
        {toolCall.status === "error" && toolCall.error && (
          <span className="text-red-500 ml-1">Error</span>
        )}
      </span>
    );
  }

  return (
    <div className="tool-status-indicator flex items-center gap-2 text-sm py-1 px-2 rounded bg-gray-50 border border-gray-100">
      <span className={style}>{icon}</span>
      <span className={style} style={{ flex: 1 }}>{label}</span>
      {toolCall.status === "running" && (
        <span className="text-gray-400 animate-pulse">●</span>
      )}
      {toolCall.status === "success" && toolCall.latencyMs && (
        <span className="text-gray-400 text-xs">({toolCall.latencyMs}ms)</span>
      )}
      {toolCall.status === "error" && toolCall.error && (
        <span className="text-red-500 text-xs">Error: {toolCall.error}</span>
      )}
    </div>
  );
}
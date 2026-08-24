/** Agent types (Phase 2). */

export interface ToolCall {
  tool: string;
  status: "pending" | "running" | "success" | "error";
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string;
  latencyMs?: number;
}

export interface AgentTrace {
  traceId: string;
  iterations: number;
  totalTokens: number;
  totalLatencyMs: number;
  outcome: "success" | "partial" | "failed" | "limit_reached";
  verificationStatus?: string;
  verificationScore?: number;
}

export interface AgentMessage extends ChatMessageItem {
  toolCalls?: ToolCall[];
  agentTrace?: AgentTrace;
  traceId?: string;
  iterations?: number;
  totalTokens?: number;
  totalLatencyMs?: number;
  outcome?: "success" | "partial" | "failed" | "limit_reached";
  verificationStatus?: string;
  verificationScore?: number;
}

export interface AgentResponse {
  user: ChatMessageItem;
  assistant: AgentMessage;
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

// Simplified JSON Schema type
export interface JSONSchema {
  type: string;
  properties?: Record<string, JSONSchema>;
  required?: string[];
  items?: JSONSchema;
  enum?: string[];
  [key: string]: any;
}

// Import ChatMessageItem from domain types
import type { ChatMessageItem } from "./domain";
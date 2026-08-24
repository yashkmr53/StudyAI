/** Agent API client (Phase 2). */

import { apiRequest } from "./client";
import type { AgentResponse, ToolMetadata, ToolCall } from "../../types/agent";

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
  async getExecutionTrace(requestId: string): Promise<{ tool_call_sequence: ToolCall[] }> {
    return apiRequest(`/agents/executions/${requestId}/`);
  },
};
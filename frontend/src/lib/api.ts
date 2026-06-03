/**
 * Backend contract helpers: thread identity and the rehydration endpoint.
 *
 * The chat stream itself is handled by the AI SDK transport (see
 * ChatProvider); this module covers everything around it.
 */
import type { UIMessage } from "ai";

/** A mutating tool call paused at a LangGraph interrupt, awaiting a decision. */
export type ApprovalRequest = {
  tool: string;
  args: Record<string, unknown>;
  tool_call_id: string;
  /** Human-readable names resolved from the ids in args. */
  display: Record<string, string>;
  interrupt_id: string;
};

export type ThreadState = {
  messages: UIMessage[];
  pending: ApprovalRequest[];
};

const THREAD_KEY = "clinical-ops-thread-id";

export function getOrCreateThreadId(): string {
  let id = localStorage.getItem(THREAD_KEY);
  if (!id) {
    id = newThreadId();
  }
  return id;
}

export function newThreadId(): string {
  const id = crypto.randomUUID();
  localStorage.setItem(THREAD_KEY, id);
  return id;
}

export async function fetchThreadState(threadId: string): Promise<ThreadState> {
  const response = await fetch(`/api/threads/${threadId}/state`);
  if (!response.ok) throw new Error(`Failed to load thread state: ${response.status}`);
  return response.json();
}

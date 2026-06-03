/**
 * Wires the chat together:
 *
 *   useChat (AI SDK) ── DefaultChatTransport ──► POST /api/chat (SSE)
 *        │
 *   useAISDKRuntime ──► assistant-ui components
 *
 * The provider also owns the approval workflow: the list of pending mutating
 * actions is fetched from the backend (the single source of truth — pending
 * approvals live in the LangGraph checkpointer) and approve/deny decisions
 * are sent as a `resume` payload on the same /api/chat endpoint, so the
 * continuation streams into the same conversation.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useAISDKRuntime } from "@assistant-ui/react-ai-sdk";
import {
  fetchThreadState,
  getOrCreateThreadId,
  newThreadId,
  type ApprovalRequest,
  type ThreadState,
} from "../lib/api";

type ChatContextValue = {
  pending: ApprovalRequest[];
  /** Decisions made in this session, keyed by tool_call_id (for badges). */
  decisions: Record<string, "approved" | "denied">;
  sendApproval: (request: ApprovalRequest, approved: boolean, reason?: string) => void;
  newChat: () => void;
  isRunning: boolean;
};

const ChatContext = createContext<ChatContextValue | null>(null);

export function useChatContext(): ChatContextValue {
  const value = useContext(ChatContext);
  if (!value) throw new Error("useChatContext must be used inside ChatProvider");
  return value;
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [threadId, setThreadId] = useState(getOrCreateThreadId);
  const [restored, setRestored] = useState<ThreadState | null>(null);

  // Rehydrate history + pending approvals before mounting the chat session,
  // so a page refresh (or backend restart) keeps pending actions addressable.
  useEffect(() => {
    let cancelled = false;
    fetchThreadState(threadId)
      .then((state) => !cancelled && setRestored(state))
      .catch(() => !cancelled && setRestored({ messages: [], pending: [] }));
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  if (restored === null) {
    return <div className="grid h-dvh place-items-center text-gray-400">Loading…</div>;
  }
  return (
    <ChatSession
      key={threadId} // remount on "new chat" so useChat starts fresh
      threadId={threadId}
      restored={restored}
      onNewChat={() => {
        setRestored(null);
        setThreadId(newThreadId());
      }}
    >
      {children}
    </ChatSession>
  );
}

function ChatSession({
  threadId,
  restored,
  onNewChat,
  children,
}: {
  threadId: string;
  restored: ThreadState;
  onNewChat: () => void;
  children: ReactNode;
}) {
  const [pending, setPending] = useState(restored.pending);
  const [decisions, setDecisions] = useState<Record<string, "approved" | "denied">>({});

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/chat",
        // Our backend keeps history in its checkpointer, so each request
        // carries only the thread id, the newest message, and (for approval
        // decisions) the resume payload.
        prepareSendMessagesRequest: ({ messages, body }) => ({
          body: { thread_id: threadId, messages: messages.slice(-1), ...body },
        }),
      }),
    [threadId],
  );

  const chat = useChat({ id: threadId, messages: restored.messages, transport });
  const runtime = useAISDKRuntime(chat, {
    // A pending approval must survive the user asking follow-up questions.
    cancelPendingToolCallsOnSend: false,
  });

  // The backend's checkpointer is the source of truth for pending approvals;
  // re-check whenever a run finishes (a run may have added or resolved one).
  const isRunning = chat.status === "submitted" || chat.status === "streaming";
  useEffect(() => {
    if (!isRunning) {
      fetchThreadState(threadId)
        .then((state) => setPending(state.pending))
        .catch(() => {});
    }
  }, [isRunning, threadId]);

  const sendApproval = (request: ApprovalRequest, approved: boolean, reason?: string) => {
    setPending((current) => current.filter((p) => p.interrupt_id !== request.interrupt_id));
    setDecisions((current) => ({
      ...current,
      [request.tool_call_id]: approved ? "approved" : "denied",
    }));
    void chat.sendMessage(
      // Visible in the transcript; the backend acts on the resume payload.
      { text: `${approved ? "✅ Approved" : "🚫 Denied"}: ${request.tool}` },
      { body: { resume: [{ interrupt_id: request.interrupt_id, approved, reason }] } },
    );
  };

  return (
    <ChatContext.Provider
      value={{ pending, decisions, sendApproval, newChat: onNewChat, isRunning }}
    >
      <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
    </ChatContext.Provider>
  );
}

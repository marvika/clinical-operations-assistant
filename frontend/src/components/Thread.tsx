/**
 * The chat surface, built from assistant-ui primitives (headless) with our
 * own styling — every piece of the HITL and transparency UX is explicit
 * application code, not framework behavior.
 */
import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import { ToolCallCard } from "./ToolCallCard";
import { PendingApprovals } from "./PendingApprovals";

const SUGGESTIONS = [
  "Which patients are scheduled for appointments in the next 7 days?",
  "Who has abnormal (HIGH) lab results in the last 14 days?",
  "Create an appointment for Patricia Adams with Dr. Alice Nguyen next week as a follow-up.",
];

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex h-full flex-col">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-4 pt-6">
        <div className="mx-auto max-w-3xl">
          <ThreadPrimitive.Empty>
            <EmptyState />
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages
            components={{ UserMessage, AssistantMessage }}
          />
        </div>
      </ThreadPrimitive.Viewport>
      <PendingApprovals />
      <Composer />
    </ThreadPrimitive.Root>
  );
}

function EmptyState() {
  return (
    <div className="py-16 text-center">
      <h2 className="mb-1 text-xl font-semibold text-gray-800">
        Clinical Operations Assistant
      </h2>
      <p className="mb-8 text-sm text-gray-500">
        Ask about patients, appointments and lab results — or schedule something.
      </p>
      <div className="mx-auto flex max-w-xl flex-col gap-2">
        {SUGGESTIONS.map((prompt) => (
          <ThreadPrimitive.Suggestion
            key={prompt}
            prompt={prompt}
            method="replace"
            autoSend
            className="rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-left text-sm text-gray-700 shadow-sm transition hover:border-gray-300 hover:bg-gray-50"
          >
            {prompt}
          </ThreadPrimitive.Suggestion>
        ))}
      </div>
    </div>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="mb-4 flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 text-sm text-white">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="mb-4 flex justify-start">
      <div className="w-full max-w-[90%] text-sm text-gray-800">
        <MessagePrimitive.Parts
          components={{ Text: MarkdownText, tools: { Fallback: ToolCallCard } }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}

function MarkdownText() {
  return (
    <MarkdownTextPrimitive className="prose prose-sm max-w-none prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5" />
  );
}

function Composer() {
  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <ComposerPrimitive.Root className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-gray-300 bg-white p-2 shadow-sm focus-within:border-blue-400">
        <ComposerPrimitive.Input
          rows={1}
          placeholder="Ask about patients, appointments, labs…"
          className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-gray-400"
        />
        <ThreadPrimitive.If running={false}>
          <ComposerPrimitive.Send className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40">
            Send
          </ComposerPrimitive.Send>
        </ThreadPrimitive.If>
        <ThreadPrimitive.If running>
          <ComposerPrimitive.Cancel className="rounded-lg bg-gray-200 px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-300">
            Stop
          </ComposerPrimitive.Cancel>
        </ThreadPrimitive.If>
      </ComposerPrimitive.Root>
    </div>
  );
}

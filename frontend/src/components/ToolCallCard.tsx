/**
 * Generic tool-call transparency card.
 *
 * Registered as the fallback renderer for every tool part, this is what makes
 * "which tools were called, with which parameters, and what came back"
 * visible in the transcript. Mutating tools waiting for approval show an
 * amber badge; the approve/deny buttons live in the PendingApprovals tray.
 */
import { useState } from "react";
import type { ToolCallMessagePartProps } from "@assistant-ui/react";
import { useChatContext } from "../chat/ChatProvider";

const wasDenied = (result: unknown): boolean =>
  typeof result === "object" && result !== null && (result as { denied?: boolean }).denied === true;

const badge = (
  props: ToolCallMessagePartProps,
  decision: "approved" | "denied" | undefined,
) => {
  if (props.isError) return { label: "error", className: "bg-red-100 text-red-700" };
  if (wasDenied(props.result)) return { label: "denied", className: "bg-gray-200 text-gray-600" };
  if (props.result !== undefined) return { label: "done", className: "bg-emerald-100 text-emerald-700" };
  // The decided call's result streams into a later message; mark this one.
  if (decision === "approved") return { label: "approved ↓", className: "bg-emerald-100 text-emerald-700" };
  if (decision === "denied") return { label: "denied ↓", className: "bg-gray-200 text-gray-600" };
  if (props.status.type === "running") return { label: "running", className: "bg-blue-100 text-blue-700" };
  return { label: "awaiting approval", className: "bg-amber-100 text-amber-800" };
};

export function ToolCallCard(props: ToolCallMessagePartProps) {
  const [open, setOpen] = useState(false);
  const { decisions } = useChatContext();
  const { label, className } = badge(props, decisions[props.toolCallId]);

  return (
    <div className="my-2 rounded-lg border border-gray-200 bg-gray-50 text-sm">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <span className="text-gray-400">{open ? "▾" : "▸"}</span>
        <span className="font-mono font-medium text-gray-800">{props.toolName}</span>
        <span className={`ml-auto rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
          {label}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-gray-200 px-3 py-2">
          <Section title="parameters" value={props.args} />
          {props.result !== undefined && <Section title="result" value={props.result} />}
        </div>
      )}
    </div>
  );
}

function Section({ title, value }: { title: string; value: unknown }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
        {title}
      </div>
      <pre className="overflow-x-auto rounded bg-white p-2 text-xs text-gray-700 ring-1 ring-gray-200">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

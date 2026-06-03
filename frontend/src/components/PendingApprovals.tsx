/**
 * The human-in-the-loop tray.
 *
 * Every pending mutating action — fresh from the stream or rehydrated after a
 * refresh/restart — appears here with the resolved names, and stays here
 * across turns until the coordinator approves or denies it.
 */
import { useState } from "react";
import { useChatContext } from "../chat/ChatProvider";
import type { ApprovalRequest } from "../lib/api";

export function PendingApprovals() {
  const { pending } = useChatContext();
  if (pending.length === 0) return null;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-3 px-4 pb-2">
      {pending.map((request) => (
        <ApprovalCard key={request.interrupt_id} request={request} />
      ))}
    </div>
  );
}

const FIELD_LABELS: Record<string, string> = {
  start_time: "Start",
  end_time: "End",
  type: "Type",
  summary: "Summary",
  service: "Service",
  planned_start: "Planned start",
  planned_end: "Planned end",
};

function ApprovalCard({ request }: { request: ApprovalRequest }) {
  const { sendApproval, isRunning } = useChatContext();
  const [reason, setReason] = useState("");

  const facts: [string, string][] = [
    ...Object.entries(request.display).map(
      ([key, value]) => [capitalize(key), value] as [string, string],
    ),
    ...Object.entries(request.args)
      .filter(([key]) => key in FIELD_LABELS)
      .map(([key, value]) => [FIELD_LABELS[key], formatValue(value)] as [string, string]),
  ];

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-lg">⏸</span>
        <span className="font-semibold text-amber-900">Approval required</span>
        <span className="ml-auto rounded bg-amber-200 px-2 py-0.5 font-mono text-xs text-amber-900">
          {request.tool}
        </span>
      </div>
      <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {facts.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="font-medium text-amber-800">{label}</dt>
            <dd className="text-amber-950">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={isRunning}
          onClick={() => sendApproval(request, true)}
          className="rounded-lg bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={isRunning}
          onClick={() => sendApproval(request, false, reason || undefined)}
          className="rounded-lg bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          Deny
        </button>
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Reason (optional, sent on deny)"
          className="min-w-0 flex-1 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-sm placeholder:text-amber-400 focus:outline-amber-500"
        />
      </div>
    </div>
  );
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return value.replace("T", " ").replace("+00:00", " UTC");
  return String(value);
}

"use client";

import { useState } from "react";

import { useAgents } from "@/lib/queries/useAgents";
import { useSessions } from "@/lib/queries/useSessions";

import { SessionsTable } from "./SessionsTable";

export function SessionsView() {
  const [agentId, setAgentId] = useState<string | null>(null);
  const { data, isPending, isError } = useSessions(agentId);
  const { data: agents } = useAgents();

  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm">
        Agent
        <select
          value={agentId ?? ""}
          onChange={(event) => setAgentId(event.target.value || null)}
          className="rounded border border-neutral-300 px-2 py-1 dark:border-neutral-700"
        >
          <option value="">All</option>
          {agents?.map((agent) => (
            <option key={agent.agent_id} value={agent.agent_id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>

      {isPending ? (
        <p className="text-sm text-neutral-500">Loading sessions…</p>
      ) : isError ? (
        <p role="alert" className="text-sm text-red-600">
          Couldn&apos;t load sessions.
        </p>
      ) : (
        <SessionsTable sessions={data} />
      )}
    </div>
  );
}

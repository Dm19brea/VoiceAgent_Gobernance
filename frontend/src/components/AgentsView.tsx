"use client";

import { useState } from "react";

import type { Agent } from "@/lib/api/types";
import { useAgents, useRegisterAgent } from "@/lib/queries/useAgents";

import { AgentForm, type AgentFormValues } from "./AgentForm";
import { AgentsTable } from "./AgentsTable";

const EMPTY_FORM: AgentFormValues = {
  vapi_assistant_id: "",
  name: "",
  objective: "",
  description: "",
};

export function AgentsView() {
  const { data, isPending, isError } = useAgents();
  const registerAgent = useRegisterAgent();
  const [formValues, setFormValues] = useState<AgentFormValues>(EMPTY_FORM);

  function handleEdit(agent: Agent) {
    setFormValues({
      vapi_assistant_id: agent.vapi_assistant_id,
      name: agent.name,
      objective: agent.objective,
      description: agent.description,
    });
  }

  function handleSubmit() {
    registerAgent.mutate(formValues, {
      onSuccess: () => setFormValues(EMPTY_FORM),
    });
  }

  const errorMessage = registerAgent.isError
    ? "Couldn't save agent. Please check the form and try again."
    : null;

  return (
    <div className="space-y-10">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Agents</h2>
        <div className="mt-4">
          {isPending && <p className="text-sm text-neutral-500">Loading agents…</p>}
          {isError && (
            <p role="alert" className="text-sm text-red-600">
              Couldn&apos;t load agents.
            </p>
          )}
          {!isPending && !isError && <AgentsTable agents={data} onEdit={handleEdit} />}
        </div>
      </div>
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Register / edit agent</h2>
        <div className="mt-4 max-w-md">
          <AgentForm
            values={formValues}
            onChange={setFormValues}
            onSubmit={handleSubmit}
            isPending={registerAgent.isPending}
            errorMessage={errorMessage}
          />
        </div>
      </div>
    </div>
  );
}

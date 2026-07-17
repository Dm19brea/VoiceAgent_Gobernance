"use client";

import { useState } from "react";

import type { Agent } from "@/lib/api/types";
import { useAgents, useDeleteAgent, useRegisterAgent, useSetAgentActivation } from "@/lib/queries/useAgents";

import { AgentForm, type AgentFormValues } from "./AgentForm";
import { AgentsTable } from "./AgentsTable";
import { Spinner } from "./ui/Spinner";

const EMPTY_FORM: AgentFormValues = {
  vapi_assistant_id: "",
  name: "",
  objective: "",
  description: "",
};

export function AgentsView() {
  const { data, isPending, isError } = useAgents();
  const registerAgent = useRegisterAgent();
  const deleteAgent = useDeleteAgent();
  const setAgentActivation = useSetAgentActivation();
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

  function handleDelete(agent: Agent) {
    if (window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) {
      deleteAgent.mutate(agent.agent_id);
    }
  }

  function handleToggleActivation(agent: Agent) {
    setAgentActivation.mutate({ agentId: agent.agent_id, activated: !agent.webhook_activated });
  }

  const errorMessage = registerAgent.isError
    ? "Couldn't save agent. Please check the form and try again."
    : null;

  const deleteErrorMessage = deleteAgent.isError ? "Couldn't delete agent. Please try again." : null;

  const activationErrorMessage = setAgentActivation.isError
    ? "Couldn't update agent activation. Please try again."
    : null;

  return (
    <div className="space-y-10">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Agents</h2>
        <div className="mt-4">
          {isPending && (
            <div className="flex items-center gap-2 text-sm text-neutral-500">
              <Spinner size="sm" label="Loading agents" />
              <span>Loading agents…</span>
            </div>
          )}
          {isError && (
            <p role="alert" className="text-sm text-red-600">
              Couldn&apos;t load agents.
            </p>
          )}
          {deleteErrorMessage && (
            <p role="alert" className="text-sm text-red-600">
              {deleteErrorMessage}
            </p>
          )}
          {activationErrorMessage && (
            <p role="alert" className="text-sm text-red-600">
              {activationErrorMessage}
            </p>
          )}
          {!isPending && !isError && (
            <AgentsTable
              agents={data}
              onEdit={handleEdit}
              onDelete={handleDelete}
              deletingAgentId={deleteAgent.isPending ? deleteAgent.variables : null}
              onToggleActivation={handleToggleActivation}
              togglingAgentId={setAgentActivation.isPending ? setAgentActivation.variables.agentId : null}
            />
          )}
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

import type { Agent } from "@/lib/api/types";

const HEADERS = ["Name", "Objective", "Vapi assistant", "Status", ""];

export function AgentsTable({
  agents,
  onEdit,
  onDelete,
  deletingAgentId,
}: Readonly<{
  agents: Agent[];
  onEdit: (agent: Agent) => void;
  onDelete: (agent: Agent) => void;
  deletingAgentId?: string | null;
}>) {
  if (agents.length === 0) {
    return <p className="text-sm text-neutral-500">No agents yet.</p>;
  }

  return (
    <table className="w-full border-collapse text-left text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-500 dark:border-neutral-800">
          {HEADERS.map((header) => (
            <th key={header} className="py-2 pr-4 font-medium">
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {agents.map((agent) => (
          <tr
            key={agent.agent_id}
            className="border-b border-neutral-100 dark:border-neutral-900"
          >
            <td className="py-2 pr-4">{agent.name}</td>
            <td className="py-2 pr-4">{agent.objective}</td>
            <td className="py-2 pr-4 font-mono text-xs">{agent.vapi_assistant_id}</td>
            <td className="py-2 pr-4">{agent.status}</td>
            <td className="py-2 pr-4">
              <button
                type="button"
                onClick={() => onEdit(agent)}
                className="text-blue-600 hover:underline dark:text-blue-400"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => onDelete(agent)}
                disabled={deletingAgentId === agent.agent_id}
                className="ml-3 text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
              >
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

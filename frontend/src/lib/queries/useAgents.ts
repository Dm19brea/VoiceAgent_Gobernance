import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { activateAgent, deactivateAgent, deleteAgent, getAgents, registerAgent } from "@/lib/api/client";
import type { Agent } from "@/lib/api/types";

export function useAgents() {
  return useQuery({ queryKey: ["agents"], queryFn: getAgents });
}

export function useRegisterAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: registerAgent,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteAgent,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useSetAgentActivation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ agentId, activated }: { agentId: string; activated: boolean }): Promise<Agent> =>
      activated ? activateAgent(agentId) : deactivateAgent(agentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

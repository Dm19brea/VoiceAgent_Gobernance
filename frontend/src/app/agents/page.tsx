import { AgentsView } from "@/components/AgentsView";

export default function AgentsPage() {
  return (
    <section className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Agents</h1>
        <div className="mt-6">
          <AgentsView />
        </div>
      </div>
    </section>
  );
}

import { ActiveSessionsLive } from "@/components/ActiveSessionsLive";
import { SessionsView } from "@/components/SessionsView";

export default function HomePage() {
  return (
    <section className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Sessions</h1>
        <div className="mt-6">
          <SessionsView />
        </div>
      </div>
      <ActiveSessionsLive />
    </section>
  );
}

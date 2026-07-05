import { SessionsView } from "@/components/SessionsView";

export default function HomePage() {
  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">Sessions</h1>
      <div className="mt-6">
        <SessionsView />
      </div>
    </section>
  );
}

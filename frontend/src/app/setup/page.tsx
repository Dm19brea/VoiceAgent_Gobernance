import { SetupView } from "@/components/SetupView";

export default function SetupPage() {
  return (
    <section className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Create your dashboard account</h1>
        <div className="mt-6">
          <SetupView />
        </div>
      </div>
    </section>
  );
}

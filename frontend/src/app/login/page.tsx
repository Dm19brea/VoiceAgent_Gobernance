import { LoginView } from "@/components/LoginView";

export default function LoginPage() {
  return (
    <section className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
        <div className="mt-6">
          <LoginView />
        </div>
      </div>
    </section>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { setupAccount } from "@/lib/api/client";
import { MIN_LENGTH, validatePassword, type PasswordRule } from "@/lib/auth/passwordPolicy";

const RULE_LABELS: Record<PasswordRule, string> = {
  min_length: `At least ${MIN_LENGTH} characters`,
  uppercase: "At least one uppercase letter",
  lowercase: "At least one lowercase letter",
  digit: "At least one digit",
  special: "At least one special character",
};

const ALL_RULES: PasswordRule[] = ["min_length", "uppercase", "lowercase", "digit", "special"];

export function SetupView() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [webhookSecret, setWebhookSecret] = useState<string | null>(null);

  const violations = validatePassword(password);
  const isCompliant = violations.length === 0;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsPending(true);
    try {
      const result = await setupAccount(username, password);
      setWebhookSecret(result.vapiWebhookSecret);
    } catch {
      setError("Could not create the account. It may already be configured.");
    } finally {
      setIsPending(false);
    }
  }

  if (webhookSecret) {
    return (
      <div className="max-w-lg space-y-4">
        <p className="text-sm">
          Account created. Copy your Vapi webhook secret now — it is shown only once and cannot
          be retrieved again.
        </p>
        <div className="flex items-center gap-2 rounded border border-neutral-300 bg-neutral-100 px-3 py-2 font-mono text-sm dark:border-neutral-700 dark:bg-neutral-900">
          <code className="break-all">{webhookSecret}</code>
        </div>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(webhookSecret);
          }}
          className="rounded border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-700"
        >
          Copy secret
        </button>
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          Paste this value into your Vapi assistant&apos;s server webhook secret configuration so
          Vapi requests are authenticated.
        </p>
        <button
          type="button"
          onClick={() => router.replace("/")}
          className="rounded bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
        >
          Continue
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-sm space-y-4">
      <div>
        <label htmlFor="setup-username" className="block text-sm font-medium">
          Username
        </label>
        <input
          id="setup-username"
          name="username"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          required
        />
      </div>
      <div>
        <label htmlFor="setup-password" className="block text-sm font-medium">
          Password
        </label>
        <input
          id="setup-password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          required
        />
        <ul className="mt-2 space-y-1 text-sm">
          {ALL_RULES.map((rule) => (
            <li
              key={rule}
              data-satisfied={!violations.includes(rule)}
              className={
                violations.includes(rule)
                  ? "text-neutral-500 dark:text-neutral-400"
                  : "text-green-700 dark:text-green-400"
              }
            >
              {RULE_LABELS[rule]}
            </li>
          ))}
        </ul>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={isPending || !isCompliant}
        className="rounded bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        Create account
      </button>
    </form>
  );
}

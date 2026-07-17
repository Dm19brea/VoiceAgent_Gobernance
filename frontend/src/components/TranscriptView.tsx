"use client";

import { useSessionEvents } from "@/lib/queries/useSessionEvents";
import { buildTranscript } from "@/lib/transcript/buildTranscript";
import type { TranscriptTurn } from "@/lib/api/types";

import { Spinner } from "./ui/Spinner";

function formatSilenceSeconds(durationMs: number): string {
  return (durationMs / 1000).toFixed(1);
}

function SilenceDivider({ durationMs }: Readonly<{ durationMs: number }>) {
  return (
    <p className="text-center text-xs text-neutral-400">
      {`── ⏸ ${formatSilenceSeconds(durationMs)}s de silencio ──`}
    </p>
  );
}

function TurnBubble({ turn }: Readonly<{ turn: TranscriptTurn }>) {
  const isAssistant = turn.role === "assistant";
  return (
    <div
      data-testid="transcript-turn"
      className={`animate-[var(--animate-fade-in)] max-w-[80%] rounded-[var(--radius-card)] border p-3 text-sm shadow-[var(--shadow-card)] transition-shadow hover:shadow-md ${
        isAssistant
          ? "self-start border-border bg-surface-muted"
          : "self-end border-brand/30 bg-accent/10"
      }`}
    >
      <div className="mb-1 flex items-center gap-2 text-xs font-medium text-muted">
        <span>{isAssistant ? "Agente" : "Usuario"}</span>
        {turn.interrupted && (
          <span
            data-testid="interruption-indicator"
            className="rounded-[var(--radius-badge)] bg-warning-surface px-2 py-0.5 text-warning-fg"
          >
            Interrupción
          </span>
        )}
      </div>
      <p>{turn.content}</p>
    </div>
  );
}

export function TranscriptView({ sessionId }: Readonly<{ sessionId: string }>) {
  const { data, isPending, isError } = useSessionEvents(sessionId);

  if (isPending) {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-500">
        <Spinner size="sm" label="Cargando transcripción" />
        <span>Cargando transcripción…</span>
      </div>
    );
  }

  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-600">
        No se pudo cargar la transcripción.
      </p>
    );
  }

  const turns = buildTranscript(data);

  if (turns.length === 0) {
    return (
      <p role="status" className="text-sm text-neutral-500">
        Esta sesión aún no tiene transcripción procesada.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {turns.map((turn) => (
        <div key={turn.turnIndex} className="flex flex-col gap-3">
          {turn.silenceBeforeMs !== null && <SilenceDivider durationMs={turn.silenceBeforeMs} />}
          <TurnBubble turn={turn} />
        </div>
      ))}
    </div>
  );
}

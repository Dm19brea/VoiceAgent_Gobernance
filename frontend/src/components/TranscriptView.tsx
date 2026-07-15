"use client";

import { useSessionEvents } from "@/lib/queries/useSessionEvents";
import { buildTranscript } from "@/lib/transcript/buildTranscript";
import type { TranscriptTurn } from "@/lib/api/types";

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
      className={`max-w-[80%] rounded-lg border p-3 text-sm ${
        isAssistant
          ? "self-start border-neutral-200 bg-neutral-50"
          : "self-end border-blue-200 bg-blue-50"
      }`}
    >
      <div className="mb-1 flex items-center gap-2 text-xs font-medium text-neutral-500">
        <span>{isAssistant ? "Agente" : "Usuario"}</span>
        {turn.interrupted && (
          <span
            data-testid="interruption-indicator"
            className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800"
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
    return <p className="text-sm text-neutral-500">Cargando transcripción…</p>;
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

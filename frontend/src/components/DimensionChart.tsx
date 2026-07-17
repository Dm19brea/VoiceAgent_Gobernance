"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, XAxis, YAxis } from "recharts";

import type { Scores } from "@/lib/api/types";

// Operational is intentionally omitted: the dimension is out of the MVP scope
// (no operational metrics exist, so it never scores).
const DIMENSIONS: ReadonlyArray<readonly [label: string, key: keyof Scores]> = [
  ["Conversational", "conversational"],
  ["Technical", "technical"],
  // The engine key stays "risk"; the label reads as safety because the score
  // is inverted-risk: 100 means no incidents were observed.
  ["Seguridad", "risk"],
];

export function DimensionChart({ scores }: Readonly<{ scores: Scores }>) {
  const data = DIMENSIONS.filter(([, key]) => scores[key] !== null).map(([label, key]) => ({
    label,
    score: scores[key] as number,
  }));

  const summary = data.map((entry) => `${entry.label} ${entry.score.toFixed(2)}`).join(", ");

  return (
    <div
      role="img"
      aria-label={`Dimension scores: ${summary}`}
      className="h-64 w-full rounded-[var(--radius-card)] bg-surface p-2 shadow-[var(--shadow-card)]"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
          <Bar dataKey="score" fill="var(--color-brand)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

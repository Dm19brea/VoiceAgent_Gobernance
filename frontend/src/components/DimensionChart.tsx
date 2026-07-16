"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, XAxis, YAxis } from "recharts";

import type { Scores } from "@/lib/api/types";

// Operational is intentionally omitted: the dimension is out of the MVP scope
// (no operational metrics exist, so it never scores).
const DIMENSIONS: ReadonlyArray<readonly [label: string, key: keyof Scores]> = [
  ["Conversational", "conversational"],
  ["Technical", "technical"],
  ["Risk", "risk"],
];

export function DimensionChart({ scores }: Readonly<{ scores: Scores }>) {
  const data = DIMENSIONS.filter(([, key]) => scores[key] !== null).map(([label, key]) => ({
    label,
    score: scores[key] as number,
  }));

  const summary = data.map((entry) => `${entry.label} ${entry.score.toFixed(2)}`).join(", ");

  return (
    <div role="img" aria-label={`Dimension scores: ${summary}`} className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-neutral-200" />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
          <Bar dataKey="score" fill="#2563eb" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

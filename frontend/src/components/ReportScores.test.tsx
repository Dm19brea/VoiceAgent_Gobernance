import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Report } from "@/lib/api/types";

import { ReportScores } from "./ReportScores";

const report: Report = {
  report_id: "r-1",
  session_id: "call-1",
  score_global: 81.4,
  scores: { conversational: 88, operational: null, technical: 74, risk: 70 },
  result: "passed",
  blocking_flags: [],
  generated_at: "2026-01-01T10:06:00Z",
};

describe("ReportScores", () => {
  it("renders the global score and result", () => {
    render(<ReportScores report={report} />);

    expect(screen.getByText(/81.4/)).toBeInTheDocument();
    expect(screen.getByText(/passed/i)).toBeInTheDocument();
  });

  it("renders each in-scope dimension score with two decimals", () => {
    render(<ReportScores report={report} />);

    expect(screen.getByText(/conversational/i)).toBeInTheDocument();
    expect(screen.getByText("88.00")).toBeInTheDocument();
    expect(screen.getByText("74.00")).toBeInTheDocument();
  });

  it("does not render the out-of-scope operational dimension", () => {
    render(<ReportScores report={report} />);

    expect(screen.queryByText(/operational/i)).not.toBeInTheDocument();
  });

  it("lists blocking flags when present", () => {
    render(
      <ReportScores
        report={{
          ...report,
          result: "failed",
          blocking_flags: [{ code: "session_not_completed", reason: "No completion event." }],
        }}
      />,
    );

    expect(screen.getByText(/session_not_completed/)).toBeInTheDocument();
  });
});

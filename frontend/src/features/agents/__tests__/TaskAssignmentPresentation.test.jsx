import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import AgentResultSummary from "../components/AgentResultSummary";
import { executeAgentRequest } from "../agentsApi";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const rawSummary = "Target Task: Web App Development | Team: Selected | Priority: high | Candidate Evaluations: 2";
const details = {
  task_title: "Web App Development", task_priority: "high", task_status: "in_progress",
  current_assignee: "Current candidate", required_skills: ["React", "FastAPI"],
  requested_candidate_count: 2, evaluated_candidate_count: 2, eligible_candidate_count: 1,
  human_decision_required: true,
  candidate_recommendations: [{
    rank: 1, candidate_name: "Eligible candidate", recommendation_label: "capacity_review_required",
    suitability_score: 0.91, required_skill_coverage: 1, matched_required_skill_count: 2,
    required_skill_count: 2, matched_skills: ["React", "FastAPI"], missing_required_skills: [],
    active_task_count: 1, overdue_task_count: 1, availability_status: "available", weekly_capacity_hours: 40,
    workload_summary: "Available | 1 overdue task | misleading positive label",
    recommendation_reason: "Review retention or reassignment after confirming capacity.",
    limitations: ["Confirm capacity and manager approval before assignment."],
  }],
  other_evaluated_candidates: [{candidate_name: "Rejected candidate", missing_required_skills: ["FastAPI"],
    matched_required_skill_count: 1, required_skill_count: 2, required_skill_coverage: 0.5,
    reason: "Missing mandatory required skill: FastAPI"}],
};
const result = {correlation_id: "opaque-support-reference", status: "completed", summary: rawSummary, confidence: 0.95,
  task_assignment_details: details, findings: [{agent: "task_assigning", summary: rawSummary, confidence: 0.95}]};

describe("Task Assignment manager presentation", () => {
  it("uses structured candidate cards without repeating the raw pipe summary", () => {
    render(<AgentResultSummary result={result} />);
    expect(screen.getByTestId("candidate-card-rank-1")).toBeInTheDocument();
    expect(screen.getByText("Web App Development")).toBeInTheDocument();
    expect(screen.queryByText(rawSummary)).not.toBeInTheDocument();
    expect(screen.queryByTestId("specialist-finding-task_assigning")).not.toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("Current candidate")).toBeInTheDocument();
    expect(screen.getByText("React, FastAPI")).toBeInTheDocument();
  });

  it("formats suitability percentages and humanized recommendation labels", () => {
    const { container } = render(<AgentResultSummary result={result} />);
    expect(screen.getByText("91%")).toBeInTheDocument();
    expect(screen.getByText("Capacity review required")).toBeInTheDocument();
    expect(screen.getByText("All required skills matched")).toBeInTheDocument();
    expect(container.textContent).not.toContain("capacity_review_required");
    expect(container.textContent).not.toContain("in_progress");
    expect(container.textContent).not.toContain("Missing: [None]");
    expect(screen.getByText("2 candidates evaluated.")).toBeInTheDocument();
  });

  it("renders rejected candidates and their verified missing skills", () => {
    render(<AgentResultSummary result={result} />);
    const rejected = screen.getByTestId("ineligible-candidate-0");
    expect(rejected).toHaveTextContent("Rejected candidate");
    expect(rejected).toHaveTextContent("Missing: FastAPI");
    expect(rejected).toHaveTextContent("Not currently eligible");
    expect(rejected).toHaveTextContent("1/2 (50%)");
  });

  it("separates availability and capacity from overdue workload risk", () => {
    render(<AgentResultSummary result={result} />);
    const availability = screen.getByRole("region", {name: "Availability and capacity"});
    const risk = screen.getByRole("region", {name: "Active workload and overdue risk"});
    expect(within(availability).getByText("Available")).toBeInTheDocument();
    expect(availability).toHaveTextContent("40 hours per week recorded capacity");
    expect(availability).not.toHaveTextContent("overdue");
    expect(risk).toHaveTextContent("1 active task, 1 overdue");
    expect(risk).toHaveTextContent("Overdue work requires capacity review.");
    expect(risk).not.toHaveTextContent("Available");
    expect(screen.queryByText(/misleading positive label/)).not.toBeInTheDocument();
  });

  it("shows advisory manager approval and candidate limitations", () => {
    render(<AgentResultSummary result={result} />);
    expect(screen.getByText(/Advisory only.*Manager makes final decision/i)).toBeInTheDocument();
    expect(screen.getByText("Confirm capacity and manager approval before assignment.")).toBeInTheDocument();
  });

  it("uses singular candidate grammar and copies only a privacy-safe structured summary", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: {writeText} });
    const secret = "private@example.com 507f1f77bcf86cd799439011 INTERNAL_ERROR";
    const { container } = render(<AgentResultSummary result={{...result,
      task_assignment_details: {...details, task_title: `Task ${secret}`, evaluated_candidate_count: 1,
        other_evaluated_candidates: []}}} />);
    expect(screen.getByText("1 candidate evaluated.")).toBeInTheDocument();
    await act(async () => fireEvent.click(screen.getByRole("button", {name: "Copy public analysis summary"})));
    expect(writeText).toHaveBeenCalledOnce();
    expect(writeText.mock.calls[0][0]).toContain("manager approval");
    expect(writeText.mock.calls[0][0]).not.toContain("Target Task:");
    for (const value of secret.split(" ")) {
      expect(container.innerHTML).not.toContain(value);
      expect(writeText.mock.calls[0][0]).not.toContain(value);
    }
  });

  it.each([
    {detail: "Request refused safely."},
    {status: "failed", safe_error_message: "Request refused safely.", detail: "Request refused safely.", findings: [], confidence: null},
    {detail: [{loc: ["body", "weeks_lookback"], msg: "Request refused safely."}]},
  ])("safely handles legacy and consistent HTTP error envelopes %#", async (envelope) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok: false, status: 403,
      headers: {get: () => "application/json"}, json: async () => envelope}));
    await expect(executeAgentRequest("token", {question: "Analyze collaboration blockers"})).rejects.toMatchObject({status: 403});
  });
});

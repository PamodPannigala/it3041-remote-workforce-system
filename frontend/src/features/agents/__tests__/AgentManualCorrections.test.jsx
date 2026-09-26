import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import AgentResultSummary from "../components/AgentResultSummary";
import { executeAgentRequest } from "../agentsApi";

afterEach(() => vi.restoreAllMocks());

const details = {
  task_title: "Web App Development", task_priority: "high", task_status: "in_progress",
  current_assignee: "Current team member", required_skills: ["React", "FastAPI"],
  requested_candidate_count: 3, evaluated_candidate_count: 2, eligible_candidate_count: 1,
  candidate_recommendations: [{ rank: 1, candidate_name: "Eligible team member",
    suitability_score: 0.91, recommendation_label: "capacity_review_required",
    required_skill_count: 2, matched_required_skill_count: 2, required_skill_coverage: 1,
    matched_skills: ["React", "FastAPI"], missing_required_skills: [],
    availability_status: "available", weekly_capacity_hours: 40, active_task_count: 1,
    overdue_task_count: 1, limitations: ["Confirm remaining capacity with the candidate."],
    recommendation_reason: "Both mandatory skills are verified." }],
  other_evaluated_candidates: [{ candidate_name: "Other team member", required_skill_count: 2,
    matched_required_skill_count: 1, required_skill_coverage: 0.5,
    missing_required_skills: ["FastAPI"], reason: "Missing mandatory required skill: FastAPI" }],
};
function display(overrides = {}) {
  return render(<AgentResultSummary result={{ status: "completed", confidence: 0.95,
    summary: "Target Task: raw | Team: raw | Priority: raw | Candidate Evaluations",
    findings: [{ agent: "task_assigning", summary: "RAW SPECIALIST PIPE | SUMMARY", confidence: 0.95 }],
    task_assignment_details: { ...details, ...overrides } }} />);
}

describe("Manual correction presentation", () => {
  it.each([1, 3])("keeps count badges and one explanatory sentence for %s evaluated candidates", (count) => {
    const { container } = display({ evaluated_candidate_count: count });
    expect(screen.getByText("Requested:")).toBeVisible();
    expect(screen.getByText("Eligible:")).toBeVisible();
    expect(screen.getByText("Evaluated:")).toBeVisible();
    expect(screen.getByText(`${count} candidate${count === 1 ? "" : "s"} evaluated.`)).toBeVisible();
    expect(container.textContent).not.toContain("eligible candidate found from");
    expect(container.textContent).not.toContain("evaluated team members");
    expect(screen.getByText("91%")).toBeVisible();
    expect(screen.getByText("Capacity review required")).toBeVisible();
  });
  it("uses structured candidate cards without duplicate pipe summaries", () => {
    const { container } = display();
    expect(screen.getByTestId("candidate-card-rank-1")).toBeVisible();
    expect(screen.getByText("Web App Development")).toBeVisible();
    expect(screen.getByText("Current team member")).toBeVisible();
    expect(screen.getByText("High")).toBeVisible();
    expect(screen.getByText("In progress")).toBeVisible();
    expect(container.textContent).not.toContain("Target Task:");
    expect(container.textContent).not.toContain("RAW SPECIALIST");
  });
  it("shows percentages humanized labels matched skills and manager approval", () => {
    const { container } = display();
    expect(screen.getByText("91%")).toBeVisible();
    expect(screen.getByText("Capacity review required")).toBeVisible();
    expect(screen.getByText("All required skills matched")).toBeVisible();
    expect(screen.getByText(/Manager makes final decision/)).toBeVisible();
    expect(screen.getByText("Confirm remaining capacity with the candidate.")).toBeVisible();
    expect(container.textContent).not.toContain("capacity_review_required");
    expect(container.textContent).not.toContain("Missing: [None]");
    expect(screen.getByText("2 candidates evaluated.")).toBeVisible();
  });
  it("separates available capacity from overdue workload risk", () => {
    display();
    const availability = screen.getByRole("region", { name: "Availability and capacity" });
    const risk = screen.getByRole("region", { name: "Active workload and overdue risk" });
    expect(within(availability).getByText("Available")).toBeVisible();
    expect(availability).toHaveTextContent("40 hours per week");
    expect(availability).not.toHaveTextContent("overdue");
    expect(risk).toHaveTextContent("1 active task, 1 overdue");
    expect(risk).toHaveTextContent("Overdue work requires capacity review.");
  });
  it("shows rejected candidates with verified missing skill reasons", () => {
    display();
    const rejected = screen.getByTestId("ineligible-candidate-0");
    expect(rejected).toHaveTextContent("Other team member");
    expect(rejected).toHaveTextContent("Not currently eligible");
    expect(rejected).toHaveTextContent("Missing: FastAPI");
  });
  it("uses singular grammar and does not invent missing skills for unverified requirements", () => {
    display({ evaluated_candidate_count: 1, required_skills: [], candidate_recommendations: [],
      eligible_candidate_count: 0, other_evaluated_candidates: [] });
    expect(screen.getByText("1 candidate evaluated.")).toBeVisible();
    expect(screen.getByText("Requirements not verified")).toBeVisible();
    expect(screen.getByTestId("zero-eligible-notice")).not.toHaveTextContent("currently hold all");
  });
  it.each([403, 422, 500])("handles legacy and full error contracts safely (%s)", async (status) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false, status,
      json: async () => ({ detail: [{ msg: "raw private comment and original prompt", input: "secret" }] }) });
    await expect(executeAgentRequest("session", { question: "Review collaboration" }))
      .rejects.toThrow("Request context is not supported for this analysis.");
  });
});

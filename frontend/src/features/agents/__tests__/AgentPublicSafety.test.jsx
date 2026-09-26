import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import AgentResultSummary from "../components/AgentResultSummary";
import AgentWorkspace from "../components/AgentWorkspace";
import AgentRequestForm from "../components/AgentRequestForm";
import AgentErrorPanel from "../components/AgentErrorPanel";
import { sanitizePublicValue } from "../publicProse";

afterEach(() => vi.restoreAllMocks());

describe("Public analysis display boundaries", () => {
  it("contaminated display fields cannot leak to text attributes clipboard or console", async () => {
    const secrets = ["507f1f77bcf86cd799439011", "leak@example.com", "INTERNAL_SQL_ERROR", "opaque-request-secret", "corr-leak-123", "opaque-conversation-reference"];
    const contaminated = `Verified observation ${secrets.join(" ")}`;
    const consoleSpies = ["log", "warn", "error", "info", "debug"].map((name) => vi.spyOn(console, name));
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const response = {
      correlation_id: "corr-leak-123", target_task_id: "opaque-request-secret", conversation_id: "opaque-conversation-reference", status: "partial", confidence: 0.7,
      summary: contaminated, limitations: [contaminated], recommended_actions: [contaminated], safe_error_message: contaminated,
      errors: [{ agent: "productivity", message: contaminated }],
      findings: [{ agent: "collaboration", summary: contaminated, confidence: 0.7, limitations: [contaminated], recommended_actions: [contaminated] }],
      task_assignment_details: {
        task_title: contaminated, requested_candidate_count: 1, evaluated_candidate_count: 1, eligible_candidate_count: 1,
        candidate_recommendations: [{ rank: 1, candidate_name: contaminated, job_title: contaminated, suitability_score: 0.7,
          required_skill_coverage: 1, matched_skills: [contaminated], missing_required_skills: [], workload_summary: contaminated,
          recommendation_label: "recommended", recommendation_reason: contaminated, limitations: [contaminated] }],
        other_evaluated_candidates: [{ candidate_name: contaminated, missing_required_skills: [contaminated], reason: contaminated }],
        ranking_factors: [contaminated],
      },
    };
    const { container } = render(<AgentResultSummary result={response} />);
    expect(container.textContent).toContain("Verified observation");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Copy public analysis summary" })); });
    expect(writeText).toHaveBeenCalledOnce();
    const consoleText = consoleSpies.flatMap((spy) => spy.mock.calls).flat().join(" ");
    for (const secret of secrets) {
      expect(container.innerHTML).not.toContain(secret);
      expect(writeText.mock.calls[0][0]).not.toContain(secret);
      expect(consoleText).not.toContain(secret);
    }
    expect(sanitizePublicValue(response).correlation_id).toBe(response.correlation_id);
  });

  it("employee direct workspace entry performs zero capability or resource requests", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AgentWorkspace user={{ role: "employee" }} token="session" />);
    expect(screen.getByRole("alert")).toHaveTextContent("managers and administrators");
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.queryByTestId("agent-workspace")).not.toBeInTheDocument();
  });

  it("team and task option display strings are sanitized", () => {
    const secret = "507f1f77bcf86cd799439011 contact@example.com INTERNAL_TASK_ERROR";
    const { container } = render(<AgentRequestForm targetTeamId="team-1" question="Review this task" teams={[{ id: "team-1", name: secret }]} tasks={[{ id: "task-1", team_id: "team-1", title: secret, priority: secret, status: secret }]} />);
    expect(screen.getByLabelText(/Target Team/)).toHaveAttribute("aria-required", "true");
    for (const value of secret.split(" ")) expect(container.textContent).not.toContain(value);
    expect(container.textContent).toContain("Select an authorized team");
  });

  it("malformed error messages are sanitized before display", () => {
    const { container } = render(<AgentErrorPanel error={{ message: "request-999 leak@example.com INTERNAL_DATABASE_ERROR 507f1f77bcf86cd799439011", status: 503 }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Service Unavailable");
    for (const secret of ["request-999", "leak@example.com", "INTERNAL_DATABASE_ERROR", "507f1f77bcf86cd799439011"]) expect(container.innerHTML).not.toContain(secret);
  });
});

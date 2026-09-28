import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import Dashboard from "../Dashboard";

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
  };
}

function renderEmployeeDashboard(summary) {
  global.fetch = vi.fn().mockImplementation(async (url) => {
    const urlString = String(url);
    if (urlString.includes("/teams/my-summary")) {
      return jsonResponse(summary);
    }
    if (urlString.includes("/profiles/me")) {
      return jsonResponse({ detail: "Employee profile not found" }, 404);
    }
    return jsonResponse({}, 404);
  });

  return render(
    <Dashboard
      initialTab="my-team"
      token="employee-token"
      user={{ name: "Pamod Sachintha", role: "employee" }}
    />,
  );
}

describe("Employee Dashboard team members", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the authorized members returned by the employee summary and the correct count", async () => {
    renderEmployeeDashboard({
      has_team: true,
      team_id: "507f1f77bcf86cd799439011",
      team_name: "Gama",
      manager_name: "Team Lead",
      members: [
        {
          name: "Active Teammate",
          role: "employee",
          email: "must-not-render@example.com",
          id: "507f1f77bcf86cd799439012",
          private_comments: "private comment",
          wellbeing_data: "private wellbeing",
          workload_details: "private workload",
          internal_error_code: "PRIVATE_ERROR",
        },
        { name: "Second Teammate", role: "employee" },
      ],
    });

    expect(await screen.findByText("Team Members (2)")).toBeInTheDocument();
    expect(screen.getByText("Active Teammate")).toBeInTheDocument();
    expect(screen.getByText("Second Teammate")).toBeInTheDocument();
    expect(screen.queryByText("No other members currently assigned.")).not.toBeInTheDocument();

    const renderedText = document.body.textContent;
    expect(renderedText).not.toContain("must-not-render@example.com");
    expect(renderedText).not.toContain("507f1f77bcf86cd799439012");
    expect(renderedText).not.toContain("private comment");
    expect(renderedText).not.toContain("private wellbeing");
    expect(renderedText).not.toContain("private workload");
    expect(renderedText).not.toContain("PRIVATE_ERROR");
  });

  it("shows the empty state only when the authorized member list is empty", async () => {
    renderEmployeeDashboard({
      has_team: true,
      team_id: "507f1f77bcf86cd799439011",
      team_name: "Solo Team",
      manager_name: "Team Lead",
      members: [],
    });

    expect(await screen.findByText("Team Members (0)")).toBeInTheDocument();
    expect(screen.getByText("No other members currently assigned.")).toBeInTheDocument();
  });
});

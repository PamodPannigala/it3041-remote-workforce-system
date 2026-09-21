import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EmployeePulseSurvey from "../components/EmployeePulseSurvey";
import ManagerPulseInsights from "../components/ManagerPulseInsights";
import AdminPulseAudit from "../components/AdminPulseAudit";
import Sidebar from "../../../layouts/Sidebar";
import MobileNavigation from "../../../layouts/MobileNavigation";

describe("Weekly Pulse Surveys Feature Suite", () => {
  const fakeToken = "valid-jwt-token-xyz";

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe("Employee Pulse Survey Workflow", () => {
    const employeeUser = {
      id: "64b1f28b4f1c2b3a4e5d6f11",
      name: "Alice Employee",
      email: "alice@example.com",
      role: "employee",
      team_id: "64b1f28b4f1c2b3a4e5d6f99",
    };

    const assignedTeam = {
      has_team: true,
      team_id: "64b1f28b4f1c2b3a4e5d6f99",
      team_name: "Alpha Workforce",
      manager: { name: "Mark Manager", email: "manager@example.com" },
      members: [],
    };

    it("renders all four required rating fields and optional comment field", async () => {
      global.fetch = vi.fn().mockImplementation(async (url) => {
        if (String(url).includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: [],
              total: 0,
              page: 1,
              limit: 10,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      // Verify all 4 required rating fields
      expect(screen.getByText(/1\. Workload Manageability/i)).toBeInTheDocument();
      expect(screen.getByText(/2\. Work-Life Balance/i)).toBeInTheDocument();
      expect(screen.getByText(/3\. Team Support/i)).toBeInTheDocument();
      expect(screen.getByText(/4\. Engagement/i)).toBeInTheDocument();

      // Verify optional comment
      expect(screen.getByLabelText(/Confidential Personal Note/i)).toBeInTheDocument();
      expect(screen.getByText(/0 \/ 1000 chars/i)).toBeInTheDocument();

      // Verify Responsible AI / Privacy Notice
      expect(screen.getByText(/Privacy & Responsible Use Guarantee/i)).toBeInTheDocument();
      expect(screen.getByText(/not used for medical or psychological diagnosis/i)).toBeInTheDocument();

      // Wait for history to load
      expect(await screen.findByText(/No Submission History Yet/i)).toBeInTheDocument();
    });

    it("prevents incomplete submission and disables submit button", async () => {
      const user = userEvent.setup();
      global.fetch = vi.fn().mockImplementation(async (url) => {
        if (String(url).includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ items: [], total: 0, page: 1, limit: 10, total_pages: 1 }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      const submitBtn = screen.getByRole("button", { name: /Submit Weekly Pulse/i });
      expect(submitBtn).toBeDisabled();

      // Select only 1 out of 4 ratings
      const radios = screen.getAllByRole("radio", { name: /^4/i });
      await user.click(radios[0]); // Workload
      expect(submitBtn).toBeDisabled();

      expect(await screen.findByText(/No Submission History Yet/i)).toBeInTheDocument();
    });

    it("sends only exact permitted request fields and successfully submits pulse response", async () => {
      const user = userEvent.setup();
      let capturedPayload = null;
      let capturedHeaders = null;
      let capturedUrl = null;

      global.fetch = vi.fn().mockImplementation(async (url, options = {}) => {
        const urlStr = String(url);
        if (urlStr.includes("/pulse-surveys/responses") && options.method === "POST") {
          capturedUrl = urlStr;
          capturedHeaders = options.headers;
          capturedPayload = JSON.parse(options.body);
          return {
            ok: true,
            status: 201,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              id: "64b1f28b4f1c2b3a4e5d6fa1",
              user_id: employeeUser.id,
              team_id: assignedTeam.team_id,
              team_name: assignedTeam.team_name,
              week_start: "2026-09-21T00:00:00Z",
              workload_manageability: 4,
              work_life_balance: 5,
              team_support: 3,
              engagement: 4,
              optional_comment: "Had a productive week balancing tasks.",
              submitted_at: "2026-09-21T10:00:00Z",
            }),
          };
        }
        if (urlStr.includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: capturedPayload
                ? [
                    {
                      id: "64b1f28b4f1c2b3a4e5d6fa1",
                      user_id: employeeUser.id,
                      team_id: assignedTeam.team_id,
                      team_name: assignedTeam.team_name,
                      week_start: "2026-09-21T00:00:00Z",
                      workload_manageability: capturedPayload.workload_manageability,
                      work_life_balance: capturedPayload.work_life_balance,
                      team_support: capturedPayload.team_support,
                      engagement: capturedPayload.engagement,
                      optional_comment: capturedPayload.optional_comment,
                      submitted_at: "2026-09-21T10:00:00Z",
                    },
                  ]
                : [],
              total: capturedPayload ? 1 : 0,
              page: 1,
              limit: 10,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      // Select all 4 ratings using distinct radiogroups
      const workloadRadios = screen.getAllByRole("radio", { name: /^4/i });
      await user.click(workloadRadios[0]); // Workload: 4

      const balanceRadios = screen.getAllByRole("radio", { name: /^5/i });
      await user.click(balanceRadios[1]); // Work-Life: 5

      const supportRadios = screen.getAllByRole("radio", { name: /^3/i });
      await user.click(supportRadios[2]); // Support: 3

      const engagementRadios = screen.getAllByRole("radio", { name: /^4/i });
      await user.click(engagementRadios[3]); // Engagement: 4

      // Type comment
      const commentInput = screen.getByLabelText(/Confidential Personal Note/i);
      await user.type(commentInput, "Had a productive week balancing tasks.");

      const submitBtn = screen.getByRole("button", { name: /Submit Weekly Pulse/i });
      expect(submitBtn).toBeEnabled();

      await user.click(submitBtn);

      // Verify POST call details
      await waitFor(() => {
        expect(capturedUrl).toBe("/api/pulse-surveys/responses");
      });
      expect(capturedHeaders["Authorization"]).toBe(`Bearer ${fakeToken}`);
      expect(capturedPayload).toEqual({
        workload_manageability: 4,
        work_life_balance: 5,
        team_support: 3,
        engagement: 4,
        optional_comment: "Had a productive week balancing tasks.",
      });

      // Verify NO client user_id, team_id, week_start, or submitted_at were sent
      expect(capturedPayload.user_id).toBeUndefined();
      expect(capturedPayload.team_id).toBeUndefined();
      expect(capturedPayload.week_start).toBeUndefined();
      expect(capturedPayload.submitted_at).toBeUndefined();

      // Verify confirmation message
      expect(await screen.findByText(/Your weekly pulse survey has been securely submitted/i)).toBeInTheDocument();
    });

    it("handles duplicate-week HTTP 409 conflict gracefully", async () => {
      const user = userEvent.setup();
      global.fetch = vi.fn().mockImplementation(async (url, options = {}) => {
        const urlStr = String(url);
        if (urlStr.includes("/pulse-surveys/responses") && options.method === "POST") {
          return {
            ok: false,
            status: 409,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              detail: "A pulse survey response has already been submitted for this week",
            }),
          };
        }
        if (urlStr.includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ items: [], total: 0, page: 1, limit: 10, total_pages: 1 }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      const radios = screen.getAllByRole("radio", { name: /^4/i });
      await user.click(radios[0]);
      await user.click(radios[1]);
      await user.click(radios[2]);
      await user.click(radios[3]);

      await user.click(screen.getByRole("button", { name: /Submit Weekly Pulse/i }));

      expect(
        await screen.findByText("You have already submitted this week's pulse survey.")
      ).toBeInTheDocument();
    });

    it("shows only the Employee's own response history and displays optional comments", async () => {
      global.fetch = vi.fn().mockImplementation(async (url) => {
        if (String(url).includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: [
                {
                  id: "64b1f28b4f1c2b3a4e5d6fa1",
                  user_id: employeeUser.id,
                  team_id: assignedTeam.team_id,
                  team_name: "Alpha Workforce",
                  week_start: "2026-09-21T00:00:00Z",
                  workload_manageability: 4,
                  work_life_balance: 5,
                  team_support: 4,
                  engagement: 4,
                  optional_comment: "Personal confidential note for myself.",
                  submitted_at: "2026-09-21T10:00:00Z",
                },
              ],
              total: 1,
              page: 1,
              limit: 10,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      expect(await screen.findByText(/Personal confidential note for myself/i)).toBeInTheDocument();
      expect(screen.getByText("Alpha Workforce")).toBeInTheDocument();
    });
  });

  describe("Employee Current-Week Edit Workflow", () => {
    const employeeUser = {
      id: "64b1f28b4f1c2b3a4e5d6f11",
      name: "Alice Employee",
      email: "alice@example.com",
      role: "employee",
      team_id: "64b1f28b4f1c2b3a4e5d6f99",
    };

    const assignedTeam = {
      has_team: true,
      team_id: "64b1f28b4f1c2b3a4e5d6f99",
      team_name: "Alpha Workforce",
      manager: { name: "Mark Manager", email: "manager@example.com" },
      members: [],
    };

    const now = new Date();
    const utcDay = now.getUTCDay();
    const diff = (utcDay === 0 ? -6 : 1) - utcDay;
    const currentMonday = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + diff, 0, 0, 0, 0));
    const currentWeekIso = currentMonday.toISOString();
    const pastWeekIso = new Date(currentMonday.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();

    it("renders Edit action for current-week response, but NOT for past-week response", async () => {
      global.fetch = vi.fn().mockImplementation(async (url) => {
        if (String(url).includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: [
                {
                  id: "resp-current-1",
                  user_id: employeeUser.id,
                  team_id: assignedTeam.team_id,
                  team_name: "Alpha Workforce",
                  week_start: currentWeekIso,
                  workload_manageability: 4,
                  work_life_balance: 4,
                  team_support: 4,
                  engagement: 4,
                  optional_comment: "Current week note",
                  submitted_at: "2026-09-21T10:00:00Z",
                  revision: 1,
                },
                {
                  id: "resp-past-1",
                  user_id: employeeUser.id,
                  team_id: assignedTeam.team_id,
                  team_name: "Alpha Workforce",
                  week_start: pastWeekIso,
                  workload_manageability: 3,
                  work_life_balance: 3,
                  team_support: 3,
                  engagement: 3,
                  optional_comment: "Past week note",
                  submitted_at: "2026-09-14T10:00:00Z",
                  revision: 1,
                },
              ],
              total: 2,
              page: 1,
              limit: 10,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      // Current week response should have "Current Week" badge and "Edit Response" button
      expect(await screen.findByText("Current Week")).toBeInTheDocument();
      const editButtons = screen.getAllByRole("button", { name: /Edit Response/i });
      expect(editButtons).toHaveLength(1);
      expect(editButtons[0]).toHaveAttribute("id", "edit-pulse-btn-resp-current-1");

      // Past week response has no edit button
      expect(document.getElementById("edit-pulse-btn-resp-past-1")).toBeNull();
    });

    it("opens edit modal prefilled with current values and cancels cleanly", async () => {
      const user = userEvent.setup();
      let fetchCalls = 0;

      global.fetch = vi.fn().mockImplementation(async (url) => {
        fetchCalls++;
        if (String(url).includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: [
                {
                  id: "resp-current-1",
                  user_id: employeeUser.id,
                  team_id: assignedTeam.team_id,
                  team_name: "Alpha Workforce",
                  week_start: currentWeekIso,
                  workload_manageability: 4,
                  work_life_balance: 5,
                  team_support: 3,
                  engagement: 4,
                  optional_comment: "Original reflections note",
                  submitted_at: "2026-09-21T10:00:00Z",
                  revision: 1,
                },
              ],
              total: 1,
              page: 1,
              limit: 10,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      const editBtn = await screen.findByRole("button", { name: /Edit Response/i });
      await user.click(editBtn);

      // Verify modal opened and prefilled
      expect(screen.getByRole("heading", { name: /Edit Weekly Pulse Check-In/i })).toBeInTheDocument();
      expect(
        screen.getByText(/You can edit your response until the current UTC week ends. Previous weeks are read-only./i)
      ).toBeInTheDocument();

      const commentInput = screen.getByDisplayValue("Original reflections note");
      expect(commentInput).toBeInTheDocument();

      // Click cancel
      const cancelBtn = screen.getByRole("button", { name: /Cancel/i });
      await user.click(cancelBtn);

      // Modal closed, no PATCH call made
      expect(screen.queryByRole("heading", { name: /Edit Weekly Pulse Check-In/i })).not.toBeInTheDocument();
      expect(fetchCalls).toBe(1); // Only initial load
    });

    it("sends exact PATCH request and updates response with Edited badge and timestamp", async () => {
      const user = userEvent.setup();
      let patchUrl = null;
      let patchMethod = null;
      let patchHeaders = null;
      let patchBody = null;

      global.fetch = vi.fn().mockImplementation(async (url, options = {}) => {
        const urlStr = String(url);
        if (urlStr.includes("/pulse-surveys/responses/resp-current-1") && options.method === "PATCH") {
          patchUrl = urlStr;
          patchMethod = options.method;
          patchHeaders = options.headers;
          patchBody = JSON.parse(options.body);

          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              id: "resp-current-1",
              user_id: employeeUser.id,
              team_id: assignedTeam.team_id,
              team_name: "Alpha Workforce",
              week_start: currentWeekIso,
              workload_manageability: 5,
              work_life_balance: 5,
              team_support: 3,
              engagement: 4,
              optional_comment: "Updated reflections note after midweek review.",
              submitted_at: "2026-09-21T10:00:00Z",
              updated_at: "2026-09-22T14:30:00Z",
              is_edited: true,
              revision: 2,
            }),
          };
        }

        if (urlStr.includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: [
                {
                  id: "resp-current-1",
                  user_id: employeeUser.id,
                  team_id: assignedTeam.team_id,
                  team_name: "Alpha Workforce",
                  week_start: currentWeekIso,
                  workload_manageability: patchBody ? patchBody.workload_manageability : 4,
                  work_life_balance: 5,
                  team_support: 3,
                  engagement: 4,
                  optional_comment: patchBody ? patchBody.optional_comment : "Original note",
                  submitted_at: "2026-09-21T10:00:00Z",
                  updated_at: patchBody ? "2026-09-22T14:30:00Z" : null,
                  is_edited: Boolean(patchBody),
                  revision: patchBody ? 2 : 1,
                },
              ],
              total: 1,
              page: 1,
              limit: 10,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      const editBtn = await screen.findByRole("button", { name: /Edit Response/i });
      await user.click(editBtn);

      // In modal: change workload rating to 5 using exact button ID
      const workloadOption5 = document.getElementById("edit-pulse-workload-option-5");
      expect(workloadOption5).toBeInTheDocument();
      await user.click(workloadOption5);

      // Change comment
      const commentInput = screen.getByDisplayValue("Original note");
      await user.clear(commentInput);
      await user.type(commentInput, "Updated reflections note after midweek review.");

      // Click save
      const saveBtn = screen.getByRole("button", { name: /Save Changes/i });
      await user.click(saveBtn);

      // Verify exact PATCH endpoint & payload
      await waitFor(() => {
        expect(patchUrl).toBe("/api/pulse-surveys/responses/resp-current-1");
      });
      expect(patchMethod).toBe("PATCH");
      expect(patchHeaders["Authorization"]).toBe(`Bearer ${fakeToken}`);
      expect(patchBody).toEqual({
        workload_manageability: 5,
        work_life_balance: 5,
        team_support: 3,
        engagement: 4,
        optional_comment: "Updated reflections note after midweek review.",
        expected_revision: 1,
      });

      // Verify success message and Edited badge
      expect(await screen.findByText(/Your weekly pulse response has been updated successfully/i)).toBeInTheDocument();
      expect(screen.getByText("Edited")).toBeInTheDocument();
      expect(screen.getByText(/Edited:/i)).toBeInTheDocument();
      expect(screen.getByText(/Submitted:/i)).toBeInTheDocument();
    });

    it("handles HTTP 409 conflict when another edit has occurred", async () => {
      const user = userEvent.setup();

      global.fetch = vi.fn().mockImplementation(async (url, options = {}) => {
        const urlStr = String(url);
        if (urlStr.includes("/pulse-surveys/responses/resp-current-1") && options.method === "PATCH") {
          return {
            ok: false,
            status: 409,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              detail: "Conflict: This pulse survey response was modified concurrently. Please refresh.",
            }),
          };
        }

        if (urlStr.includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: [
                {
                  id: "resp-current-1",
                  user_id: employeeUser.id,
                  team_id: assignedTeam.team_id,
                  team_name: "Alpha Workforce",
                  week_start: currentWeekIso,
                  workload_manageability: 4,
                  work_life_balance: 4,
                  team_support: 4,
                  engagement: 4,
                  optional_comment: "Original note",
                  submitted_at: "2026-09-21T10:00:00Z",
                  revision: 1,
                },
              ],
              total: 1,
              page: 1,
              limit: 10,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      const editBtn = await screen.findByRole("button", { name: /Edit Response/i });
      await user.click(editBtn);

      const saveBtn = screen.getByRole("button", { name: /Save Changes/i });
      await user.click(saveBtn);

      expect(
        await screen.findByText(/Conflict: This pulse survey response was modified concurrently/i)
      ).toBeInTheDocument();
    });

    it("handles closed-week HTTP 400 error cleanly", async () => {
      const user = userEvent.setup();

      global.fetch = vi.fn().mockImplementation(async (url, options = {}) => {
        const urlStr = String(url);
        if (urlStr.includes("/pulse-surveys/responses/resp-current-1") && options.method === "PATCH") {
          return {
            ok: false,
            status: 400,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              detail: "Previous-week responses are read-only and cannot be modified.",
            }),
          };
        }

        if (urlStr.includes("/pulse-surveys/my-responses")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: [
                {
                  id: "resp-current-1",
                  user_id: employeeUser.id,
                  team_id: assignedTeam.team_id,
                  team_name: "Alpha Workforce",
                  week_start: currentWeekIso,
                  workload_manageability: 4,
                  work_life_balance: 4,
                  team_support: 4,
                  engagement: 4,
                  optional_comment: "Original note",
                  submitted_at: "2026-09-21T10:00:00Z",
                  revision: 1,
                },
              ],
              total: 1,
              page: 1,
              limit: 10,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <EmployeePulseSurvey
          user={employeeUser}
          token={fakeToken}
          assignedTeam={assignedTeam}
        />
      );

      const editBtn = await screen.findByRole("button", { name: /Edit Response/i });
      await user.click(editBtn);

      const saveBtn = screen.getByRole("button", { name: /Save Changes/i });
      await user.click(saveBtn);

      expect(
        await screen.findByText(/The current UTC week has ended. Previous-week responses are read-only./i)
      ).toBeInTheDocument();
    });

    it("correctly renders 'Week of Sep 21, 2026', 'Current Week' badge, and 'Edit Response' button for naive ISO string under fixed clock", async () => {
      vi.useFakeTimers({ toFake: ["Date"] });
      vi.setSystemTime(new Date("2026-09-21T13:04:00Z"));

      try {
        global.fetch = vi.fn().mockImplementation(async (url) => {
          if (String(url).includes("/pulse-surveys/my-responses")) {
            return {
              ok: true,
              status: 200,
              headers: new Headers({ "content-type": "application/json" }),
              json: async () => ({
                items: [
                  {
                    id: "resp-naive-1",
                    user_id: employeeUser.id,
                    team_id: assignedTeam.team_id,
                    team_name: "Alpha Workforce",
                    week_start: "2026-09-21T00:00:00", // naive string as previously returned by backend
                    workload_manageability: 4,
                    work_life_balance: 4,
                    team_support: 4,
                    engagement: 4,
                    optional_comment: "Weekly reflection",
                    submitted_at: "2026-09-21T13:04:00",
                    revision: 1,
                  },
                ],
                total: 1,
                page: 1,
                limit: 10,
                total_pages: 1,
              }),
            };
          }
          return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
        });

        render(
          <EmployeePulseSurvey
            user={employeeUser}
            token={fakeToken}
            assignedTeam={assignedTeam}
          />
        );

        // Verify canonical UTC week label format
        expect(await screen.findByText("Week of Sep 21, 2026")).toBeInTheDocument();
        expect(screen.queryByText("Week of Sep 20, 2026")).not.toBeInTheDocument();

        // Verify Current Week badge and Edit button appear
        expect(screen.getByText("Current Week")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Edit Response/i })).toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    });

    it("preserves Current Week and Edit Response up to Sunday 23:59 UTC before rollover", async () => {
      vi.useFakeTimers({ toFake: ["Date"] });
      // Sunday Sep 27, 2026 23:59:50 UTC (end of the UTC week)
      vi.setSystemTime(new Date("2026-09-27T23:59:50Z"));

      try {
        global.fetch = vi.fn().mockImplementation(async (url) => {
          if (String(url).includes("/pulse-surveys/my-responses")) {
            return {
              ok: true,
              status: 200,
              headers: new Headers({ "content-type": "application/json" }),
              json: async () => ({
                items: [
                  {
                    id: "resp-sun-1",
                    user_id: employeeUser.id,
                    team_id: assignedTeam.team_id,
                    team_name: "Alpha Workforce",
                    week_start: "2026-09-21T00:00:00+00:00",
                    workload_manageability: 4,
                    work_life_balance: 4,
                    team_support: 4,
                    engagement: 4,
                    optional_comment: "Weekly reflection",
                    submitted_at: "2026-09-21T13:04:00+00:00",
                    revision: 1,
                  },
                ],
                total: 1,
                page: 1,
                limit: 10,
                total_pages: 1,
              }),
            };
          }
          return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
        });

        render(
          <EmployeePulseSurvey
            user={employeeUser}
            token={fakeToken}
            assignedTeam={assignedTeam}
          />
        );

        expect(await screen.findByText("Week of Sep 21, 2026")).toBeInTheDocument();
        expect(screen.getByText("Current Week")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Edit Response/i })).toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe("Manager Pulse Insights Workflow", () => {
    const managerUser = {
      id: "64b1f28b4f1c2b3a4e5d6f22",
      name: "Mark Manager",
      email: "manager@example.com",
      role: "manager",
    };

    const managedTeams = [
      { id: "64b1f28b4f1c2b3a4e5d6f99", name: "Engineering Squad", members: [{ id: "1" }, { id: "2" }] },
      { id: "64b1f28b4f1c2b3a4e5d6f88", name: "Product Design", members: [{ id: "3" }, { id: "4" }] },
    ];

    it("loads managed teams and requests team summary for selected team", async () => {
      let requestedUrl = "";

      global.fetch = vi.fn().mockImplementation(async (url) => {
        requestedUrl = String(url);
        if (requestedUrl.includes("/pulse-surveys/team-summary")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              available: true,
              team_id: "64b1f28b4f1c2b3a4e5d6f99",
              team_name: "Engineering Squad",
              week_start: "2026-09-21T00:00:00Z",
              response_count: 4,
              minimum_required: 3,
              averages: {
                workload_manageability: 4.25,
                work_life_balance: 3.75,
                team_support: 4.5,
                engagement: 4.0,
              },
              message: null,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <ManagerPulseInsights
          user={managerUser}
          token={fakeToken}
          managedTeams={managedTeams}
        />
      );

      await waitFor(() => {
        expect(requestedUrl).toContain("/api/pulse-surveys/team-summary?team_id=64b1f28b4f1c2b3a4e5d6f99");
      });

      // Verify aggregate scores are visible
      expect(await screen.findByText("4.25")).toBeInTheDocument();
      expect(screen.getByText("3.75")).toBeInTheDocument();
      expect(screen.getByText("4.50")).toBeInTheDocument();
      expect(screen.getByText("4.00")).toBeInTheDocument();
    });

    it("hides averages and shows clear privacy notice when below threshold (< 3 responses)", async () => {
      global.fetch = vi.fn().mockImplementation(async (url) => {
        if (String(url).includes("/pulse-surveys/team-summary")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              available: false,
              team_id: "64b1f28b4f1c2b3a4e5d6f99",
              team_name: "Engineering Squad",
              week_start: "2026-09-21T00:00:00Z",
              response_count: 2,
              minimum_required: 3,
              averages: null,
              message: "Insufficient responses to display aggregated metrics (minimum 3 required for privacy).",
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <ManagerPulseInsights
          user={managerUser}
          token={fakeToken}
          managedTeams={managedTeams}
        />
      );

      expect(
        await screen.findByText(/Insufficient Responses to Display Aggregate Metrics/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/minimum 3 required for privacy/i)).toBeInTheDocument();

      // Ensure NO fabricated 0 averages
      expect(screen.queryByText("0.00 / 5.00")).not.toBeInTheDocument();
    });

    it("never renders employee identities, individual ratings, or raw comments in Manager view", async () => {
      global.fetch = vi.fn().mockImplementation(async (url) => {
        if (String(url).includes("/pulse-surveys/team-summary")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              available: true,
              team_id: "64b1f28b4f1c2b3a4e5d6f99",
              team_name: "Engineering Squad",
              week_start: "2026-09-21T00:00:00Z",
              response_count: 3,
              minimum_required: 3,
              averages: {
                workload_manageability: 4.15,
                work_life_balance: 3.5,
                team_support: 4.85,
                engagement: 4.2,
              },
              message: null,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      const { container } = render(
        <ManagerPulseInsights
          user={managerUser}
          token={fakeToken}
          managedTeams={managedTeams}
        />
      );

      expect(await screen.findByText("4.15")).toBeInTheDocument();

      // Verify container contains no individual employee identifiers or comment leaks
      expect(container.textContent).not.toContain("Alice Employee");
      expect(container.textContent).not.toContain("Confidential Personal Note");
    });
  });

  describe("Admin Pulse Audit Workflow", () => {
    const adminTeams = [
      { id: "64b1f28b4f1c2b3a4e5d6f99", name: "Alpha Squad" },
      { id: "64b1f28b4f1c2b3a4e5d6f88", name: "Beta Operations" },
    ];

    it("uses read-only audit endpoints and renders organization team summaries with privacy thresholds", async () => {
      let requestedSummaryUrl = "";

      global.fetch = vi.fn().mockImplementation(async (url) => {
        const urlStr = String(url);
        if (urlStr.includes("/admin/pulse-surveys/summary")) {
          requestedSummaryUrl = urlStr;
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              week_start: "2026-09-21T00:00:00Z",
              items: [
                {
                  available: true,
                  team_id: "64b1f28b4f1c2b3a4e5d6f99",
                  team_name: "Alpha Squad",
                  week_start: "2026-09-21T00:00:00Z",
                  response_count: 5,
                  minimum_required: 3,
                  averages: {
                    workload_manageability: 4.2,
                    work_life_balance: 3.8,
                    team_support: 4.4,
                    engagement: 4.1,
                  },
                  message: null,
                },
                {
                  available: false,
                  team_id: "64b1f28b4f1c2b3a4e5d6f88",
                  team_name: "Beta Operations",
                  week_start: "2026-09-21T00:00:00Z",
                  response_count: 1,
                  minimum_required: 3,
                  averages: null,
                  message: "Insufficient responses to display aggregated metrics (minimum 3 required for privacy).",
                },
              ],
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <AdminPulseAudit
          adminTeams={adminTeams}
          token={fakeToken}
        />
      );

      await waitFor(() => {
        expect(requestedSummaryUrl).toContain("/api/admin/pulse-surveys/summary");
      });

      // Verify Read-only Privacy-Safe Audit badge
      expect(screen.getByText("Read-only Privacy-Safe Audit")).toBeInTheDocument();

      // Team 1 averages
      expect(await screen.findByText("4.20 / 5.00")).toBeInTheDocument();

      // Team 2 privacy mask
      expect(screen.getByText("Beta Operations")).toBeInTheDocument();
      expect(screen.getByText(/Privacy Threshold Enforced/i)).toBeInTheDocument();

      // Ensure NO mutation buttons (Create, Edit, Delete)
      expect(screen.queryByRole("button", { name: /create/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    });

    it("switches to submission audit logs sub-view and renders privacy-safe metadata table", async () => {
      const user = userEvent.setup();
      let requestedRecordsUrl = "";

      global.fetch = vi.fn().mockImplementation(async (url) => {
        const urlStr = String(url);
        if (urlStr.includes("/admin/pulse-surveys/summary")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ week_start: "2026-09-21T00:00:00Z", items: [] }),
          };
        }
        if (urlStr.includes("/admin/pulse-surveys")) {
          requestedRecordsUrl = urlStr;
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: [
                {
                  id: "64b1f28b4f1c2b3a4e5d6fa1",
                  team_id: "64b1f28b4f1c2b3a4e5d6f99",
                  team_name: "Alpha Squad",
                  week_start: "2026-09-21T00:00:00Z",
                  submitted_at: "2026-09-21T09:30:00Z",
                },
              ],
              total: 1,
              page: 1,
              limit: 20,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <AdminPulseAudit
          adminTeams={adminTeams}
          token={fakeToken}
        />
      );

      // Switch to records subview
      const logsTabBtn = screen.getByRole("button", { name: /Submission Audit Logs/i });
      await user.click(logsTabBtn);

      await waitFor(() => {
        expect(requestedRecordsUrl).toContain("/api/admin/pulse-surveys");
      });

      expect(await screen.findByRole("cell", { name: "Alpha Squad" })).toBeInTheDocument();
      expect(screen.getByText("Masked & Confidential")).toBeInTheDocument();
    });
  });

  describe("Role Navigation & Integration", () => {
    it("renders Weekly Pulse only for Employee", () => {
      render(
        <Sidebar
          user={{ role: "employee", name: "Emp" }}
          activeTab="weekly-pulse"
          onTabChange={() => {}}
          onLogout={() => {}}
        />
      );

      expect(screen.getByRole("button", { name: /Weekly Pulse/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Pulse Insights/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Pulse Audit/i })).not.toBeInTheDocument();
    });

    it("renders Pulse Insights only for Manager", () => {
      render(
        <Sidebar
          user={{ role: "manager", name: "Mgr" }}
          activeTab="pulse-insights"
          onTabChange={() => {}}
          onLogout={() => {}}
        />
      );

      expect(screen.getByRole("button", { name: /Pulse Insights/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Weekly Pulse/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Pulse Audit/i })).not.toBeInTheDocument();
    });

    it("renders Pulse Audit only for Admin", () => {
      render(
        <Sidebar
          user={{ role: "admin", name: "Adm" }}
          activeTab="pulse-audit"
          onTabChange={() => {}}
          onLogout={() => {}}
        />
      );

      expect(screen.getByRole("button", { name: /Pulse Audit/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Weekly Pulse/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Pulse Insights/i })).not.toBeInTheDocument();
    });
  });
});

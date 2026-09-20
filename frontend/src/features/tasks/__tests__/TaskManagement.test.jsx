import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

import EmployeeTasks from "../components/EmployeeTasks";
import ManagerTaskBoard from "../components/ManagerTaskBoard";
import AdminTaskAudit from "../components/AdminTaskAudit";

describe("EmployeeTasks Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockTasks = [
    {
      id: "task-101",
      title: "Develop JWT Authentication",
      description: "Implement access token parsing and expiry verification.",
      team_id: "team-1",
      created_by: "mgr-1",
      assigned_to: "emp-1",
      required_skills: ["React", "FastAPI"],
      priority: "high",
      status: "in_progress",
      due_date: "2026-10-15T12:00:00Z",
      estimated_hours: 12.0,
      progress_history: [
        {
          id: "prog-1",
          user_id: "emp-1",
          percentage: 45,
          notes: "Auth headers and decode logic completed.",
          logged_at: "2026-09-20T10:00:00Z",
        },
      ],
      blockers: [],
      created_at: "2026-09-18T09:00:00Z",
      updated_at: "2026-09-20T10:00:00Z",
    },
    {
      id: "task-102",
      title: "Write Database Migrations",
      description: "Setup schema migrations for tasks and progress history.",
      team_id: "team-1",
      created_by: "mgr-1",
      assigned_to: "emp-1",
      required_skills: ["MongoDB"],
      priority: "urgent",
      status: "blocked",
      due_date: "2026-10-01T12:00:00Z",
      estimated_hours: 8.0,
      progress_history: [],
      blockers: [
        {
          id: "blk-1",
          user_id: "emp-1",
          description: "Database cluster permissions missing.",
          is_resolved: false,
          resolved_at: null,
          resolved_by: null,
          created_at: "2026-09-19T14:00:00Z",
        },
      ],
      created_at: "2026-09-19T11:00:00Z",
      updated_at: "2026-09-19T14:00:00Z",
    },
  ];

  it("renders assigned tasks, metric cards, and task badges", async () => {
    global.fetch = vi.fn().mockImplementation(async (url) => {
      if (String(url).includes("/api/tasks/my-tasks")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: mockTasks,
            total: 2,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<EmployeeTasks token="emp-token" onSessionExpired={vi.fn()} />);

    expect(await screen.findByText("Develop JWT Authentication")).toBeInTheDocument();
    expect(screen.getByText("Write Database Migrations")).toBeInTheDocument();
    expect(screen.getByText("Assigned Workload")).toBeInTheDocument();
    expect(screen.getAllByText("Blocked").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("In Progress").length).toBeGreaterThanOrEqual(1);
  });

  it("renders empty state when no tasks are assigned", async () => {
    global.fetch = vi.fn().mockImplementation(async (url) => {
      if (String(url).includes("/api/tasks/my-tasks")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: [],
            total: 0,
            page: 1,
            limit: 10,
            total_pages: 0,
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<EmployeeTasks token="emp-token" onSessionExpired={vi.fn()} />);

    expect(await screen.findByText(/No Assigned Tasks/i)).toBeInTheDocument();
  });

  it("opens task details modal and renders description and progress history", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn().mockImplementation(async (url) => {
      if (String(url).includes("/api/tasks/my-tasks")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: mockTasks,
            total: 2,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<EmployeeTasks token="emp-token" onSessionExpired={vi.fn()} />);

    const detailsButtons = await screen.findAllByRole("button", { name: /details/i });
    await user.click(detailsButtons[0]);

    expect(screen.getAllByText("Implement access token parsing and expiry verification.").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Auth headers and decode logic completed.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /close/i }).length).toBeGreaterThanOrEqual(1);
  });

  it("successfully updates task status and does not allow employees to see edit controls", async () => {
    const user = userEvent.setup();
    let statusUpdated = false;

    global.fetch = vi.fn().mockImplementation(async (url, opts) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/tasks/my-tasks")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: [mockTasks[0]],
            total: 1,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      if (urlStr.includes("/api/tasks/task-101/status") && opts.method === "PATCH") {
        statusUpdated = true;
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            ...mockTasks[0],
            status: "completed",
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<EmployeeTasks token="emp-token" onSessionExpired={vi.fn()} />);

    await screen.findByText("Develop JWT Authentication");

    // Employees should not see any Edit Task buttons
    expect(screen.queryByRole("button", { name: /edit task/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();

    const statusSelect = screen.getByLabelText(/update status for develop jwt authentication/i);
    await user.selectOptions(statusSelect, "completed");

    await waitFor(() => {
      expect(statusUpdated).toBe(true);
    });
  });

  it("proves no arbitrary 10% progress increase occurs on in_progress transition and initial modal is current percentage", async () => {
    const user = userEvent.setup();
    const todoTask = {
      id: "task-fresh",
      title: "Fresh Todo Deliverable",
      description: "Newly assigned task with 0 progress.",
      team_id: "team-1",
      created_by: "mgr-1",
      assigned_to: "emp-1",
      required_skills: ["Python"],
      priority: "medium",
      status: "todo",
      due_date: "2026-10-20T12:00:00Z",
      estimated_hours: 5.0,
      progress_history: [],
      blockers: [],
      created_at: "2026-09-20T10:00:00Z",
      updated_at: "2026-09-20T10:00:00Z",
    };

    let sentStatus = null;
    global.fetch = vi.fn().mockImplementation(async (url, opts) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/tasks/my-tasks")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: [todoTask],
            total: 1,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      if (urlStr.includes("/api/tasks/task-fresh/status") && opts.method === "PATCH") {
        sentStatus = JSON.parse(opts.body).status;
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            ...todoTask,
            status: "in_progress",
            // backend keeps progress_history empty on in_progress transition
            progress_history: [],
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<EmployeeTasks token="emp-token" onSessionExpired={vi.fn()} />);

    await screen.findByText("Fresh Todo Deliverable");

    // Check initial displayed progress is 0%
    expect(screen.getByText("0%")).toBeInTheDocument();

    // Transition from todo to in_progress
    const statusSelect = screen.getByLabelText(/update status for fresh todo deliverable/i);
    await user.selectOptions(statusSelect, "in_progress");

    await waitFor(() => {
      expect(sentStatus).toBe("in_progress");
    });

    // Still 0% progress, no arbitrary 10%
    expect(screen.getByText("0%")).toBeInTheDocument();

    // Open progress modal: initial percentage slider value must be 0% (not 10%)
    const logProgBtn = screen.getByRole("button", { name: /log progress/i });
    await user.click(logProgBtn);

    expect(screen.getByRole("heading", { name: /log progress update/i })).toBeInTheDocument();
    expect(screen.getAllByText("0%").length).toBeGreaterThanOrEqual(1);
  });

  it("successfully logs a progress update", async () => {
    const user = userEvent.setup();
    let progressAdded = false;

    global.fetch = vi.fn().mockImplementation(async (url, opts) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/tasks/my-tasks")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: [mockTasks[0]],
            total: 1,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      if (urlStr.includes("/api/tasks/task-101/progress") && opts.method === "POST") {
        progressAdded = true;
        const body = JSON.parse(opts.body);
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            ...mockTasks[0],
            progress_history: [
              ...mockTasks[0].progress_history,
              {
                id: "prog-2",
                user_id: "emp-1",
                percentage: body.percentage,
                notes: body.notes,
                logged_at: "2026-09-20T15:00:00Z",
              },
            ],
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<EmployeeTasks token="emp-token" onSessionExpired={vi.fn()} />);

    const logProgBtn = await screen.findByRole("button", { name: /log progress/i });
    await user.click(logProgBtn);

    expect(screen.getByRole("heading", { name: /log progress update/i })).toBeInTheDocument();

    const notesInput = screen.getByLabelText(/update notes/i);
    await user.type(notesInput, "Implemented test suites with 100% coverage.");

    const submitBtn = screen.getByRole("button", { name: /submit progress/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(progressAdded).toBe(true);
    });
  });

  it("handles 401 by triggering onSessionExpired", async () => {
    const handleExpired = vi.fn();
    global.fetch = vi.fn().mockImplementation(async () => {
      return {
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ detail: "Token expired" }),
      };
    });

    render(<EmployeeTasks token="expired-token" onSessionExpired={handleExpired} />);

    await waitFor(() => {
      expect(handleExpired).toHaveBeenCalled();
    });
  });
});

describe("ManagerTaskBoard Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockManagedTeams = [
    {
      id: "team-alpha",
      name: "Alpha Squad",
      manager_id: "mgr-1",
      members: [
        { id: "emp-1", name: "Alice Developer", email: "alice@example.com" },
        { id: "emp-2", name: "Bob Engineer", email: "bob@example.com" },
      ],
    },
  ];

  const mockManagerTasks = [
    {
      id: "task-201",
      title: "Design Responsive Navigation",
      description: "Build mobile drawer and desktop sidebar.",
      team_id: "team-alpha",
      created_by: "mgr-1",
      assigned_to: "emp-1",
      required_skills: ["Tailwind", "React"],
      priority: "medium",
      status: "in_progress",
      due_date: "2026-10-10T18:00:00Z",
      estimated_hours: 10.0,
      progress_history: [],
      blockers: [
        {
          id: "blk-201",
          user_id: "emp-1",
          description: "Awaiting brand icon SVGs.",
          is_resolved: false,
          resolution_note: null,
          resolved_at: null,
          resolved_by: null,
          created_at: "2026-09-20T08:00:00Z",
        },
      ],
      created_at: "2026-09-19T10:00:00Z",
      updated_at: "2026-09-20T08:00:00Z",
    },
  ];

  it("renders manager team task board with team selector and tasks", async () => {
    global.fetch = vi.fn().mockImplementation(async (url) => {
      if (String(url).includes("/api/tasks/managed")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: mockManagerTasks,
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
      <ManagerTaskBoard
        managedTeams={mockManagedTeams}
        token="mgr-token"
        onSessionExpired={vi.fn()}
      />
    );

    expect(await screen.findByText("Design Responsive Navigation")).toBeInTheDocument();
    expect(screen.getByText("Team Task Governance")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\+ create task/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit/i })).toBeInTheDocument();
  });

  it("opens create task modal and submits valid task for team", async () => {
    const user = userEvent.setup();
    let createdPayload = null;

    global.fetch = vi.fn().mockImplementation(async (url, opts) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/tasks/managed")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: mockManagerTasks,
            total: 1,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      if (urlStr.endsWith("/api/tasks") && opts.method === "POST") {
        createdPayload = JSON.parse(opts.body);
        return {
          ok: true,
          status: 201,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "task-202",
            ...createdPayload,
            status: "todo",
            progress_history: [],
            blockers: [],
            created_at: "2026-09-20T16:00:00Z",
            updated_at: "2026-09-20T16:00:00Z",
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(
      <ManagerTaskBoard
        managedTeams={mockManagedTeams}
        token="mgr-token"
        onSessionExpired={vi.fn()}
      />
    );

    const openBtn = await screen.findByRole("button", { name: /\+ create task/i });
    await user.click(openBtn);

    expect(screen.getByRole("heading", { name: /create team task/i })).toBeInTheDocument();

    const titleInput = screen.getByLabelText(/task title/i);
    await user.type(titleInput, "Refactor API Error Handlers");

    const submitBtn = screen.getByRole("button", { name: /^create task$/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(createdPayload).not.toBeNull();
      expect(createdPayload.title).toBe("Refactor API Error Handlers");
      expect(createdPayload.team_id).toBe("team-alpha");
    });
  });

  it("manager can edit task metadata with pre-populated form and sends PATCH request", async () => {
    const user = userEvent.setup();
    let patchPayload = null;

    global.fetch = vi.fn().mockImplementation(async (url, opts) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/tasks/managed")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: mockManagerTasks,
            total: 1,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      if (urlStr.includes("/api/tasks/task-201") && opts.method === "PATCH") {
        patchPayload = JSON.parse(opts.body);
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            ...mockManagerTasks[0],
            ...patchPayload,
            updated_at: "2026-09-20T18:00:00Z",
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(
      <ManagerTaskBoard
        managedTeams={mockManagedTeams}
        token="mgr-token"
        onSessionExpired={vi.fn()}
      />
    );

    const editBtn = await screen.findByRole("button", { name: /edit/i });
    await user.click(editBtn);

    // Form opens with Edit Task heading and pre-populated values
    expect(screen.getByRole("heading", { name: /edit task/i })).toBeInTheDocument();
    const modal = screen.getByRole("dialog");
    const titleInput = screen.getByLabelText(/task title/i);
    expect(titleInput).toHaveValue("Design Responsive Navigation");

    // Modify title and priority inside modal
    await user.clear(titleInput);
    await user.type(titleInput, "Design Premium Responsive Navigation");

    const prioritySelect = document.getElementById("task-priority-select");
    await user.selectOptions(prioritySelect, "urgent");

    // Submit edit form
    const saveBtn = screen.getByRole("button", { name: /save changes/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(patchPayload).not.toBeNull();
      expect(patchPayload.title).toBe("Design Premium Responsive Navigation");
      expect(patchPayload.priority).toBe("urgent");
    });

    // Check updated title rendered in heading and success alert shown
    expect(
      await screen.findByRole("heading", { name: "Design Premium Responsive Navigation" })
    ).toBeInTheDocument();
    expect(screen.getByText(/updated successfully/i)).toBeInTheDocument();
  });

  it("opens accessible blocker resolution confirmation modal requiring a note and resolves blocker", async () => {
    const user = userEvent.setup();
    let resolveBody = null;

    global.fetch = vi.fn().mockImplementation(async (url, opts) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/tasks/managed")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: mockManagerTasks,
            total: 1,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      if (urlStr.includes("/api/tasks/task-201/blockers/blk-201/resolve") && opts.method === "PATCH") {
        resolveBody = JSON.parse(opts.body);
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            ...mockManagerTasks[0],
            status: "in_progress",
            blockers: [
              {
                ...mockManagerTasks[0].blockers[0],
                is_resolved: true,
                resolution_note: resolveBody.resolution_note,
                resolved_at: "2026-09-20T17:00:00Z",
                resolved_by: "mgr-1",
              },
            ],
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(
      <ManagerTaskBoard
        managedTeams={mockManagedTeams}
        token="mgr-token"
        onSessionExpired={vi.fn()}
      />
    );

    const resolveBtn = await screen.findByRole("button", { name: /resolve blocker/i });
    await user.click(resolveBtn);

    // Modal opens displaying original blocker description and single-blocker explanation
    expect(screen.getByRole("heading", { name: /resolve task blocker/i })).toBeInTheDocument();
    expect(screen.getByText("Awaiting brand icon SVGs.")).toBeInTheDocument();
    expect(
      screen.getByText("Resolving this blocker will return the task to In Progress when no active blockers remain.")
    ).toBeInTheDocument();

    const noteInput = screen.getByLabelText(/resolution note/i);
    await user.type(noteInput, "Supplied Figma SVG exports and updated assets folder.");

    const confirmBtn = screen.getByRole("button", { name: /confirm blocker resolution/i });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(resolveBody).not.toBeNull();
      expect(resolveBody.resolution_note).toBe("Supplied Figma SVG exports and updated assets folder.");
    });

    expect(await screen.findByText(/Blocker resolved/i)).toBeInTheDocument();
  });
});

describe("AdminTaskAudit Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockAdminTeams = [
    { id: "team-1", name: "Core Platform" },
  ];

  const mockAuditTasks = [
    {
      id: "64f1234567890abcdef12345",
      title: "Security Penetration Audit",
      description: "Verify OWASP top 10 compliance.",
      team_id: "64f9876543210fedcba54321",
      team_name: "Core Platform",
      created_by: "64faaaaaaaaaaaaaaaaaaaaa",
      created_by_name: "Carol Manager",
      created_by_email: "carol@example.com",
      assigned_to: "64fbbbbbbbbbbbbbbbbbbbbb",
      assigned_to_name: "Dave Engineer",
      assigned_to_email: "dave@example.com",
      required_skills: ["Security"],
      priority: "urgent",
      status: "in_progress",
      due_date: "2026-10-30T12:00:00Z",
      estimated_hours: 20.0,
      progress_history: [
        {
          id: "prog-1",
          user_id: "64fbbbbbbbbbbbbbbbbbbbbb",
          user_name: "Dave Engineer",
          user_email: "dave@example.com",
          percentage: 40,
          notes: "Port scanning complete.",
          logged_at: "2026-09-20T10:00:00Z",
        },
      ],
      blockers: [
        {
          id: "blk-hist-1",
          user_id: "64fbbbbbbbbbbbbbbbbbbbbb",
          user_name: "Dave Engineer",
          user_email: "dave@example.com",
          description: "Missing staging environment API tokens.",
          is_resolved: true,
          resolution_note: "Provided staging credentials via encrypted secret vault.",
          resolved_at: "2026-09-20T11:00:00Z",
          resolved_by: "64faaaaaaaaaaaaaaaaaaaaa",
          resolved_by_name: "Carol Manager",
          resolved_by_email: "carol@example.com",
          created_at: "2026-09-19T09:00:00Z",
        },
        {
          id: "blk-hist-legacy",
          user_id: "64fbbbbbbbbbbbbbbbbbbbbb",
          user_name: "Dave Engineer",
          user_email: "dave@example.com",
          description: "Legacy dependency version mismatch.",
          is_resolved: true,
          resolution_note: null,
          resolved_at: "2026-09-18T15:00:00Z",
          resolved_by: "64faaaaaaaaaaaaaaaaaaaaa",
          resolved_by_name: "Carol Manager",
          resolved_by_email: "carol@example.com",
          created_at: "2026-09-18T10:00:00Z",
        },
      ],
      created_at: "2026-09-19T09:00:00Z",
      updated_at: "2026-09-20T11:00:00Z",
    },
    {
      id: "64fccccccccccccccccccccc",
      title: "Unassigned Backlog Deliverable",
      description: "Architecture blueprint documentation.",
      team_id: "64f9876543210fedcba54321",
      team_name: "Core Platform",
      created_by: "64faaaaaaaaaaaaaaaaaaaaa",
      created_by_name: "Carol Manager",
      created_by_email: "carol@example.com",
      assigned_to: null,
      assigned_to_name: null,
      assigned_to_email: null,
      required_skills: ["Architecture"],
      priority: "medium",
      status: "todo",
      due_date: "2026-11-01T12:00:00Z",
      estimated_hours: 8.0,
      progress_history: [],
      blockers: [],
      created_at: "2026-09-20T12:00:00Z",
      updated_at: "2026-09-20T12:00:00Z",
    },
  ];

  it("renders read-only audit table with human-readable identities and no raw ObjectIds", async () => {
    global.fetch = vi.fn().mockImplementation(async (url) => {
      if (String(url).includes("/api/admin/tasks")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: mockAuditTasks,
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
      <AdminTaskAudit
        adminTeams={mockAdminTeams}
        token="admin-token"
        onSessionExpired={vi.fn()}
      />
    );

    expect(await screen.findByText("Security Penetration Audit")).toBeInTheDocument();
    expect(screen.getByText("Read-Only Audit Visibility")).toBeInTheDocument();

    // Must display blocker count
    expect(screen.getByText(/0 open \/ 2 resolved/i)).toBeInTheDocument();

    // Read-only: no creation or edit buttons
    expect(screen.queryByRole("button", { name: /\+ create task/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();

    // Inspect first task details
    const user = userEvent.setup();
    const inspectBtns = screen.getAllByRole("button", { name: /inspect/i });
    await user.click(inspectBtns[0]);

    // Check human-readable assignee and secondary email
    expect(screen.getByRole("heading", { name: /security penetration audit/i })).toBeInTheDocument();
    expect(screen.getAllByText("Dave Engineer").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("dave@example.com").length).toBeGreaterThanOrEqual(1);

    // Check reporter and resolver human-readable names and emails in timeline
    expect(screen.getByText("Missing staging environment API tokens.")).toBeInTheDocument();
    expect(screen.getByText(/Provided staging credentials via encrypted secret vault/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Carol Manager/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/carol@example\.com/i).length).toBeGreaterThanOrEqual(1);

    // Check legacy resolution note explicit fallback text
    expect(
      screen.getByText("No resolution note recorded (legacy record).")
    ).toBeInTheDocument();

    // Verify raw database ObjectIds are NEVER rendered in the UI
    expect(screen.queryByText(/64f1234567890abcdef12345/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/64f9876543210fedcba54321/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/64faaaaaaaaaaaaaaaaaaaaa/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/64fbbbbbbbbbbbbbbbbbbbbb/i)).not.toBeInTheDocument();
  });

  it("renders 'Unassigned' in details modal when task has no assigned employee", async () => {
    global.fetch = vi.fn().mockImplementation(async (url) => {
      if (String(url).includes("/api/admin/tasks")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: mockAuditTasks,
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
      <AdminTaskAudit
        adminTeams={mockAdminTeams}
        token="admin-token"
        onSessionExpired={vi.fn()}
      />
    );

    const user = userEvent.setup();
    const inspectBtns = await screen.findAllByRole("button", { name: /inspect/i });
    // Inspect second task (Unassigned Backlog Deliverable)
    await user.click(inspectBtns[1]);
    expect(screen.getByRole("heading", { name: /unassigned backlog deliverable/i })).toBeInTheDocument();
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
  });
});


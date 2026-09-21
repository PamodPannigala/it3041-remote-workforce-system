import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

import TeamMessages from "../components/TeamMessages";
import AdminMessageAudit from "../components/AdminMessageAudit";
import MessageComposer from "../components/MessageComposer";
import MessageItem from "../components/MessageItem";

describe("Collaboration Messages Feature Suite", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockEmployeeUser = {
    id: "64b1f28b4f1c2b3a4e5d6f01",
    name: "Jane Employee",
    email: "jane.employee@example.com",
    role: "employee",
    team_id: "64b1f28b4f1c2b3a4e5d6f99",
  };

  const mockOtherUser = {
    id: "64b1f28b4f1c2b3a4e5d6f02",
    name: "Bob Colleague",
    email: "bob.colleague@example.com",
    role: "employee",
  };

  const mockManagerUser = {
    id: "64b1f28b4f1c2b3a4e5d6f03",
    name: "Sarah Manager",
    email: "sarah.manager@example.com",
    role: "manager",
  };

  const mockAdminUser = {
    id: "64b1f28b4f1c2b3a4e5d6f04",
    name: "Alex Admin",
    email: "alex.admin@example.com",
    role: "admin",
  };

  const mockAssignedTeam = {
    has_team: true,
    team_id: "64b1f28b4f1c2b3a4e5d6f99",
    team_name: "Engineering Alpha",
    manager_name: "Sarah Manager",
    manager_email: "sarah.manager@example.com",
  };

  const mockManagedTeams = [
    {
      id: "64b1f28b4f1c2b3a4e5d6f99",
      name: "Engineering Alpha",
      manager_id: "64b1f28b4f1c2b3a4e5d6f03",
      members: [
        { id: "64b1f28b4f1c2b3a4e5d6f01", name: "Jane Employee", email: "jane.employee@example.com" },
        { id: "64b1f28b4f1c2b3a4e5d6f02", name: "Bob Colleague", email: "bob.colleague@example.com" },
      ],
    },
    {
      id: "64b1f28b4f1c2b3a4e5d6f88",
      name: "Design Beta",
      manager_id: "64b1f28b4f1c2b3a4e5d6f03",
      members: [],
    },
  ];

  const mockMessages = [
    {
      id: "64b1f28b4f1c2b3a4e5d6fa1",
      team_id: "64b1f28b4f1c2b3a4e5d6f99",
      sender_id: "64b1f28b4f1c2b3a4e5d6f01", // Jane's message
      content: "Hello team, I just pushed the feature branch for code review!",
      created_at: "2026-09-21T10:00:00Z",
      updated_at: "2026-09-21T10:00:00Z",
      edited_at: null,
      is_deleted: false,
      deleted_at: null,
      sender_name: "Jane Employee",
      sender_email: "jane.employee@example.com",
      team_name: "Engineering Alpha",
    },
    {
      id: "64b1f28b4f1c2b3a4e5d6fa2",
      team_id: "64b1f28b4f1c2b3a4e5d6f99",
      sender_id: "64b1f28b4f1c2b3a4e5d6f02", // Bob's message
      content: "Thanks Jane, reviewing the PR right now.",
      created_at: "2026-09-21T10:05:00Z",
      updated_at: "2026-09-21T10:05:00Z",
      edited_at: null,
      is_deleted: false,
      deleted_at: null,
      sender_name: "Bob Colleague",
      sender_email: "bob.colleague@example.com",
      team_name: "Engineering Alpha",
    },
    {
      id: "64b1f28b4f1c2b3a4e5d6fa3",
      team_id: "64b1f28b4f1c2b3a4e5d6f99",
      sender_id: "64b1f28b4f1c2b3a4e5d6f02", // Bob's deleted message
      content: null, // regular user response returns null
      created_at: "2026-09-21T09:30:00Z",
      updated_at: "2026-09-21T09:35:00Z",
      edited_at: null,
      is_deleted: true,
      deleted_at: "2026-09-21T09:35:00Z",
      sender_name: "Bob Colleague",
      sender_email: "bob.colleague@example.com",
      team_name: "Engineering Alpha",
    },
  ];

  /* =========================================================================
   * 1. EMPLOYEE SUITE
   * ========================================================================= */
  describe("Employee Workflow", () => {
    it("loads assigned team messages and renders sender information", async () => {
      global.fetch = vi.fn().mockImplementation(async (url) => {
        if (String(url).includes("/api/collaboration/messages")) {
          return {
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: mockMessages,
              total: 3,
              page: 1,
              limit: 20,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <TeamMessages
          user={mockEmployeeUser}
          token="emp-token"
          onSessionExpired={vi.fn()}
          assignedTeam={mockAssignedTeam}
        />
      );

      // Verify active team feed title and description
      expect(await screen.findByText("Team Collaboration Messages")).toBeInTheDocument();
      expect(screen.getByText(/Engineering Alpha/)).toBeInTheDocument();

      // Verify message contents rendered
      expect(screen.getByText("Hello team, I just pushed the feature branch for code review!")).toBeInTheDocument();
      expect(screen.getByText("Thanks Jane, reviewing the PR right now.")).toBeInTheDocument();

      // Verify "You" badge appears on own message
      expect(screen.getByText("You")).toBeInTheDocument();

      // Verify soft-deleted message displays "Message deleted" and DOES NOT reveal raw content
      expect(screen.getByText("Message deleted")).toBeInTheDocument();

      // Verify no raw database ObjectIds are rendered in visible UI
      expect(screen.queryByText("64b1f28b4f1c2b3a4e5d6fa1")).not.toBeInTheDocument();
      expect(screen.queryByText("64b1f28b4f1c2b3a4e5d6f99")).not.toBeInTheDocument();
    });

    it("employee creates a new message and updates feed", async () => {
      const user = userEvent.setup();

      let capturedPostBody = null;
      global.fetch = vi.fn().mockImplementation(async (url, options) => {
        const urlStr = String(url);
        if (urlStr.includes("/api/collaboration/messages")) {
          if (options?.method === "POST") {
            capturedPostBody = JSON.parse(options.body);
            return {
              ok: true,
              status: 201,
              headers: new Headers({ "content-type": "application/json" }),
              json: async () => ({
                id: "64b1f28b4f1c2b3a4e5d6fa4",
                team_id: capturedPostBody.team_id,
                sender_id: mockEmployeeUser.id,
                content: capturedPostBody.content,
                created_at: "2026-09-21T10:15:00Z",
                updated_at: "2026-09-21T10:15:00Z",
                edited_at: null,
                is_deleted: false,
                deleted_at: null,
                sender_name: mockEmployeeUser.name,
                sender_email: mockEmployeeUser.email,
                team_name: "Engineering Alpha",
              }),
            };
          }
          return {
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: mockMessages,
              total: 3,
              page: 1,
              limit: 20,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <TeamMessages
          user={mockEmployeeUser}
          token="emp-token"
          onSessionExpired={vi.fn()}
          assignedTeam={mockAssignedTeam}
        />
      );

      expect(await screen.findByText("Hello team, I just pushed the feature branch for code review!")).toBeInTheDocument();

      // Compose message
      const composerInput = screen.getByLabelText(/compose team message/i);
      await user.type(composerInput, "Standup is starting in 5 minutes on the main channel.");

      // Check character count indicator
      expect(screen.getByText(/53 \/ 4000/)).toBeInTheDocument();

      // Submit
      const sendBtn = screen.getByRole("button", { name: /send message/i });
      await user.click(sendBtn);

      // Verify POST body had correct team_id and content
      expect(capturedPostBody).toEqual({
        team_id: "64b1f28b4f1c2b3a4e5d6f99",
        content: "Standup is starting in 5 minutes on the main channel.",
      });

      // Verify new message appears in list
      expect(await screen.findByText("Standup is starting in 5 minutes on the main channel.")).toBeInTheDocument();
      expect(screen.getByText(/message posted successfully/i)).toBeInTheDocument();
    });

    it("employee can edit their own message", async () => {
      const user = userEvent.setup();
      let capturedPatchBody = null;

      global.fetch = vi.fn().mockImplementation(async (url, options) => {
        const urlStr = String(url);
        if (urlStr.includes("/api/collaboration/messages/64b1f28b4f1c2b3a4e5d6fa1")) {
          if (options?.method === "PATCH") {
            capturedPatchBody = JSON.parse(options.body);
            return {
              ok: true,
              headers: new Headers({ "content-type": "application/json" }),
              json: async () => ({
                ...mockMessages[0],
                content: capturedPatchBody.content,
                edited_at: "2026-09-21T10:20:00Z",
              }),
            };
          }
        }
        if (urlStr.includes("/api/collaboration/messages")) {
          return {
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: mockMessages,
              total: 3,
              page: 1,
              limit: 20,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <TeamMessages
          user={mockEmployeeUser}
          token="emp-token"
          onSessionExpired={vi.fn()}
          assignedTeam={mockAssignedTeam}
        />
      );

      // Wait for load
      expect(await screen.findByText("Hello team, I just pushed the feature branch for code review!")).toBeInTheDocument();

      // Click Edit on Jane's own message
      const editBtn = screen.getByRole("button", { name: /edit message/i });
      await user.click(editBtn);

      // Verify Edit Modal opens with pre-filled content
      expect(screen.getByRole("heading", { name: /edit message/i })).toBeInTheDocument();
      const editTextarea = screen.getByLabelText(/message content/i);
      expect(editTextarea).toHaveValue("Hello team, I just pushed the feature branch for code review!");

      // Update content
      await user.clear(editTextarea);
      await user.type(editTextarea, "Hello team, I pushed the updated PR with test coverage!");
      await user.click(screen.getByRole("button", { name: /save changes/i }));

      // Verify PATCH body
      expect(capturedPatchBody).toEqual({
        content: "Hello team, I pushed the updated PR with test coverage!",
      });

      // Verify updated content in list
      expect(await screen.findByText("Hello team, I pushed the updated PR with test coverage!")).toBeInTheDocument();
      expect(screen.getByText(/message updated successfully/i)).toBeInTheDocument();
    });

    it("employee can delete their own message after confirmation", async () => {
      const user = userEvent.setup();
      let deleteCalled = false;

      global.fetch = vi.fn().mockImplementation(async (url, options) => {
        const urlStr = String(url);
        if (urlStr.includes("/api/collaboration/messages/64b1f28b4f1c2b3a4e5d6fa1") && options?.method === "DELETE") {
          deleteCalled = true;
          return {
            ok: true,
            status: 204,
            headers: new Headers(),
          };
        }
        if (urlStr.includes("/api/collaboration/messages")) {
          return {
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: mockMessages,
              total: 3,
              page: 1,
              limit: 20,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <TeamMessages
          user={mockEmployeeUser}
          token="emp-token"
          onSessionExpired={vi.fn()}
          assignedTeam={mockAssignedTeam}
        />
      );

      expect(await screen.findByText("Hello team, I just pushed the feature branch for code review!")).toBeInTheDocument();

      // Click Delete
      const deleteBtn = screen.getByRole("button", { name: /delete message/i });
      await user.click(deleteBtn);

      // Verify confirmation dialog
      expect(screen.getByRole("heading", { name: /delete message/i })).toBeInTheDocument();
      expect(screen.getByText(/are you sure you want to delete this message/i)).toBeInTheDocument();

      // Confirm Delete
      await user.click(screen.getByRole("button", { name: /confirm delete/i }));

      expect(deleteCalled).toBe(true);
      expect(await screen.findByText(/message deleted successfully/i)).toBeInTheDocument();
    });

    it("employee cannot see edit/delete controls on another sender's message", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          items: [mockMessages[1]], // Bob's message only
          total: 1,
          page: 1,
          limit: 20,
          total_pages: 1,
        }),
      });

      render(
        <TeamMessages
          user={mockEmployeeUser} // Logged in as Jane
          token="emp-token"
          onSessionExpired={vi.fn()}
          assignedTeam={mockAssignedTeam}
        />
      );

      expect(await screen.findByText("Thanks Jane, reviewing the PR right now.")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /edit message/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /delete message/i })).not.toBeInTheDocument();
    });

    it("renders empty state when employee has no team assigned", () => {
      render(
        <TeamMessages
          user={{ ...mockEmployeeUser, team_id: null }}
          token="emp-token"
          onSessionExpired={vi.fn()}
          assignedTeam={{ has_team: false }}
        />
      );

      expect(screen.getByRole("heading", { name: /no team assigned/i })).toBeInTheDocument();
      expect(screen.getByText(/you are not currently assigned to any workforce team/i)).toBeInTheDocument();
    });
  });

  /* =========================================================================
   * 2. MANAGER SUITE
   * ========================================================================= */
  describe("Manager Workflow", () => {
    it("manager selects managed team, loads messages, and posts team message", async () => {
      const user = userEvent.setup();
      let capturedTeamIdParam = null;
      let capturedPostBody = null;

      global.fetch = vi.fn().mockImplementation(async (url, options) => {
        const urlStr = String(url);
        if (urlStr.includes("/api/collaboration/messages")) {
          if (options?.method === "POST") {
            capturedPostBody = JSON.parse(options.body);
            return {
              ok: true,
              status: 201,
              headers: new Headers({ "content-type": "application/json" }),
              json: async () => ({
                id: "64b1f28b4f1c2b3a4e5d6fa5",
                team_id: capturedPostBody.team_id,
                sender_id: mockManagerUser.id,
                content: capturedPostBody.content,
                created_at: "2026-09-21T11:00:00Z",
                updated_at: "2026-09-21T11:00:00Z",
                edited_at: null,
                is_deleted: false,
                deleted_at: null,
                sender_name: mockManagerUser.name,
                sender_email: mockManagerUser.email,
                team_name: "Engineering Alpha",
              }),
            };
          }
          const parsedUrl = new URL(urlStr, "http://localhost");
          capturedTeamIdParam = parsedUrl.searchParams.get("team_id");
          return {
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: mockMessages,
              total: 3,
              page: 1,
              limit: 20,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <TeamMessages
          user={mockManagerUser}
          token="mgr-token"
          onSessionExpired={vi.fn()}
          managedTeams={mockManagedTeams}
        />
      );

      // Verify manager team selector rendered
      expect(await screen.findByLabelText(/select managed team/i)).toBeInTheDocument();
      expect(capturedTeamIdParam).toBe("64b1f28b4f1c2b3a4e5d6f99");

      // Post a manager message
      const composer = screen.getByLabelText(/compose team message/i);
      await user.type(composer, "Sprint planning is scheduled for tomorrow 10am.");
      await user.click(screen.getByRole("button", { name: /send message/i }));

      expect(capturedPostBody).toEqual({
        team_id: "64b1f28b4f1c2b3a4e5d6f99",
        content: "Sprint planning is scheduled for tomorrow 10am.",
      });

      expect(await screen.findByText("Sprint planning is scheduled for tomorrow 10am.")).toBeInTheDocument();
    });

    it("manager cannot edit or delete employee messages", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          items: [mockMessages[0], mockMessages[1]], // Both are employee messages
          total: 2,
          page: 1,
          limit: 20,
          total_pages: 1,
        }),
      });

      render(
        <TeamMessages
          user={mockManagerUser} // Sarah Manager
          token="mgr-token"
          onSessionExpired={vi.fn()}
          managedTeams={mockManagedTeams}
        />
      );

      expect(await screen.findByText("Hello team, I just pushed the feature branch for code review!")).toBeInTheDocument();
      // Manager should NOT see edit or delete buttons for employee messages
      expect(screen.queryByRole("button", { name: /edit message/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /delete message/i })).not.toBeInTheDocument();
    });

    it("manager can edit/delete their own message", async () => {
      const managerMsg = {
        id: "64b1f28b4f1c2b3a4e5d6fa9",
        team_id: "64b1f28b4f1c2b3a4e5d6f99",
        sender_id: mockManagerUser.id,
        content: "Manager announcement: Release 2.0 is live!",
        created_at: "2026-09-21T08:00:00Z",
        updated_at: "2026-09-21T08:00:00Z",
        edited_at: null,
        is_deleted: false,
        deleted_at: null,
        sender_name: mockManagerUser.name,
        sender_email: mockManagerUser.email,
        team_name: "Engineering Alpha",
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          items: [managerMsg],
          total: 1,
          page: 1,
          limit: 20,
          total_pages: 1,
        }),
      });

      render(
        <TeamMessages
          user={mockManagerUser}
          token="mgr-token"
          onSessionExpired={vi.fn()}
          managedTeams={mockManagedTeams}
        />
      );

      expect(await screen.findByText("Manager announcement: Release 2.0 is live!")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /edit message/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /delete message/i })).toBeInTheDocument();
    });

    it("renders empty state when manager has no managed teams", () => {
      render(
        <TeamMessages
          user={mockManagerUser}
          token="mgr-token"
          onSessionExpired={vi.fn()}
          managedTeams={[]}
        />
      );

      expect(screen.getByRole("heading", { name: /no managed teams/i })).toBeInTheDocument();
    });
  });

  /* =========================================================================
   * 3. ADMIN SUITE
   * ========================================================================= */
  describe("Admin Read-Only Audit Workflow", () => {
    const mockAdminAuditMessages = [
      {
        id: "64b1f28b4f1c2b3a4e5d6fa1",
        team_id: "64b1f28b4f1c2b3a4e5d6f99",
        sender_id: "64b1f28b4f1c2b3a4e5d6f01",
        content: "Active message from Jane for audit inspection",
        created_at: "2026-09-21T10:00:00Z",
        updated_at: "2026-09-21T10:00:00Z",
        edited_at: null,
        is_deleted: false,
        deleted_at: null,
        sender_name: "Jane Employee",
        sender_email: "jane.employee@example.com",
        team_name: "Engineering Alpha",
      },
      {
        id: "64b1f28b4f1c2b3a4e5d6fa3",
        team_id: "64b1f28b4f1c2b3a4e5d6f99",
        sender_id: "64b1f28b4f1c2b3a4e5d6f02",
        content: "Retained soft-deleted message text for compliance audit", // Returned for admin!
        created_at: "2026-09-21T09:30:00Z",
        updated_at: "2026-09-21T09:35:00Z",
        edited_at: null,
        is_deleted: true,
        deleted_at: "2026-09-21T09:35:00Z",
        sender_name: "Bob Colleague",
        sender_email: "bob.colleague@example.com",
        team_name: "Engineering Alpha",
      },
    ];

    it("uses admin audit endpoint and renders read-only audit log with retained deleted content", async () => {
      let capturedAuditUrl = null;

      global.fetch = vi.fn().mockImplementation(async (url) => {
        capturedAuditUrl = String(url);
        if (capturedAuditUrl.includes("/api/admin/collaboration/messages")) {
          return {
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              items: mockAdminAuditMessages,
              total: 2,
              page: 1,
              limit: 20,
              total_pages: 1,
            }),
          };
        }
        return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
      });

      render(
        <AdminMessageAudit
          adminTeams={mockManagedTeams}
          token="admin-token"
          onSessionExpired={vi.fn()}
        />
      );

      // Verify read-only header badge
      expect(await screen.findByText("Collaboration Message Audit")).toBeInTheDocument();
      expect(screen.getByText("Read-only Audit")).toBeInTheDocument();
      expect(capturedAuditUrl).toContain("/api/admin/collaboration/messages");

      // Verify active and soft-deleted messages with retained content
      expect(screen.getByText("Active message from Jane for audit inspection")).toBeInTheDocument();
      expect(screen.getByText("Retained soft-deleted message text for compliance audit")).toBeInTheDocument();
      expect(screen.getByText("Deleted")).toBeInTheDocument();
      expect(screen.getByText("Active")).toBeInTheDocument();

      // Ensure NO mutation controls exist
      expect(screen.queryByRole("button", { name: /send message/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /edit message/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /delete message/i })).not.toBeInTheDocument();
    });

    it("admin can inspect single audit record in full detail modal", async () => {
      const user = userEvent.setup();

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          items: mockAdminAuditMessages,
          total: 2,
          page: 1,
          limit: 20,
          total_pages: 1,
        }),
      });

      render(
        <AdminMessageAudit
          adminTeams={mockManagedTeams}
          token="admin-token"
          onSessionExpired={vi.fn()}
        />
      );

      expect(await screen.findByText("Retained soft-deleted message text for compliance audit")).toBeInTheDocument();

      // Click Inspect on deleted message
      const inspectButtons = screen.getAllByRole("button", { name: /inspect/i });
      await user.click(inspectButtons[1]);

      // Inspection modal opens
      expect(screen.getByRole("heading", { name: /audit record inspection/i })).toBeInTheDocument();
      expect(screen.getByText(/Retained Soft-Deleted Message Content/i)).toBeInTheDocument();
      expect(screen.getAllByText("Retained soft-deleted message text for compliance audit").length).toBeGreaterThanOrEqual(2);
      expect(screen.getByText("Soft-Deleted")).toBeInTheDocument();

      // Close modal
      await user.click(screen.getByRole("button", { name: "Close inspection modal" }));
      expect(screen.queryByRole("heading", { name: /audit record inspection/i })).not.toBeInTheDocument();
    });

    it("filters audit records by team and deleted visibility", async () => {
      const user = userEvent.setup();
      let lastFetchedUrl = "";

      global.fetch = vi.fn().mockImplementation(async (url) => {
        lastFetchedUrl = String(url);
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: [],
            total: 0,
            page: 1,
            limit: 20,
            total_pages: 0,
          }),
        };
      });

      render(
        <AdminMessageAudit
          adminTeams={mockManagedTeams}
          token="admin-token"
          onSessionExpired={vi.fn()}
        />
      );

      // Change team filter
      const teamFilter = await screen.findByLabelText(/filter audit by team/i);
      await user.selectOptions(teamFilter, "64b1f28b4f1c2b3a4e5d6f99");
      expect(lastFetchedUrl).toContain("team_id=64b1f28b4f1c2b3a4e5d6f99");

      // Change visibility filter to Active Only
      const statusFilter = screen.getByLabelText(/filter audit by visibility status/i);
      await user.selectOptions(statusFilter, "active");
      expect(lastFetchedUrl).toContain("include_deleted=false");
    });
  });

  /* =========================================================================
   * 4. COMPOSER & ITEM COMPONENT EDGE CASES
   * ========================================================================= */
  describe("Component Unit Behaviors", () => {
    it("MessageComposer disables send button when content is whitespace only", async () => {
      const user = userEvent.setup();
      render(
        <MessageComposer
          teamId="team-1"
          token="test-token"
          onMessageSent={vi.fn()}
          onSessionExpired={vi.fn()}
        />
      );

      const sendBtn = screen.getByRole("button", { name: /send message/i });
      expect(sendBtn).toBeDisabled();

      const textarea = screen.getByLabelText(/compose team message/i);
      await user.type(textarea, "     ");
      expect(sendBtn).toBeDisabled();

      await user.type(textarea, "Actual message");
      expect(sendBtn).toBeEnabled();
    });

    it("MessageItem falls back to 'Unknown User' when sender_name is null", () => {
      const msgWithoutName = {
        ...mockMessages[0],
        sender_name: null,
        sender_email: null,
      };

      render(
        <MessageItem
          message={msgWithoutName}
          currentUserId="other-user"
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      );

      expect(screen.getByText("Unknown User")).toBeInTheDocument();
    });
  });
});

import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

describe("Frontend Authentication, Session Persistence, and Dashboard Flows", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("renders login form by default with necessary inputs and updated footer", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create an account/i })).toBeInTheDocument();
    expect(screen.getByText("IT3041 Remote Workforce System")).toBeInTheDocument();
  });

  it("switches to registration form and validates inputs", async () => {
    const user = userEvent.setup();
    render(<App />);

    // Switch to register
    await user.click(screen.getByRole("button", { name: /create an account/i }));
    expect(screen.getByRole("heading", { name: /create account/i })).toBeInTheDocument();

    // Try short password
    await user.type(screen.getByLabelText(/full name/i), "Test Employee");
    await user.type(screen.getByLabelText(/email address/i), "test@example.com");
    await user.type(screen.getByLabelText(/^password/i), "short");
    await user.type(screen.getByLabelText(/confirm password/i), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    const errorAlert = await screen.findByRole("alert");
    expect(errorAlert).toHaveTextContent("Password must be at least 15 characters long.");
  });

  it("handles successful registration and redirects to login with message", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        id: "64b1f28b4f1c2b3a4e5d6f70",
        name: "New Worker",
        email: "worker@example.com",
        role: "employee",
      }),
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: /create an account/i }));

    await user.type(screen.getByLabelText(/full name/i), "New Worker");
    await user.type(screen.getByLabelText(/email address/i), "worker@example.com");
    await user.type(screen.getByLabelText(/^password/i), "ValidPassword12345!");
    await user.type(screen.getByLabelText(/confirm password/i), "ValidPassword12345!");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/registration successful/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
  });

  it("handles login failure with generic error", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 401,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Invalid email or password" }),
    });

    render(<App />);
    await user.type(screen.getByLabelText(/email address/i), "invalid@example.com");
    await user.type(screen.getByLabelText(/^password/i), "WrongPassword12345!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });

  it("stores token in sessionStorage after successful login and displays dashboard", async () => {
    const user = userEvent.setup();

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/login")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ access_token: "jwt-token-12345", token_type: "bearer", expires_in: 900 }),
        };
      }
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "64b1f28b4f1c2b3a4e5d6f70",
            name: "Alex Johnson",
            email: "alex.johnson@example.com",
            role: "employee",
          }),
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            has_team: true,
            team_id: "64b1f28b4f1c2b3a4e5d6f99",
            team_name: "Engineering Core",
            manager_name: "Sarah Manager",
            manager_email: "sarah@example.com",
          }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "64b1f28b4f1c2b3a4e5d6f88",
            user_id: "64b1f28b4f1c2b3a4e5d6f70",
            job_title: "Full-Stack Developer",
            skills: ["React", "FastAPI"],
            availability_status: "available",
            weekly_capacity_hours: 40,
          }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    await user.type(screen.getByLabelText(/email address/i), "alex.johnson@example.com");
    await user.type(screen.getByLabelText(/^password/i), "CorrectPassword12345!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // Verify dashboard header and profile
    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
    expect(screen.getAllByText("Alex Johnson").length).toBeGreaterThanOrEqual(1);

    // Verify token saved to sessionStorage
    expect(sessionStorage.getItem("token")).toBe("jwt-token-12345");
  });

  it("restores session from sessionStorage on app mount/refresh and loads verified role", async () => {
    // Pre-populate token in sessionStorage
    sessionStorage.setItem("token", "persisted-jwt-token");

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "64b1f28b4f1c2b3a4e5d6f22",
            name: "Persisted Manager",
            email: "persisted.mgr@example.com",
            role: "manager",
          }),
        };
      }
      if (urlStr.includes("/teams/managed")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => [
            {
              id: "64b1f28b4f1c2b3a4e5d6f33",
              name: "Restored Squad",
              manager_id: "64b1f28b4f1c2b3a4e5d6f22",
              manager_name: "Persisted Manager",
              manager_email: "persisted.mgr@example.com",
              members: [],
            },
          ],
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "64b1f28b4f1c2b3a4e5d6f88",
            user_id: "64b1f28b4f1c2b3a4e5d6f22",
            job_title: "Engineering Manager",
            skills: ["Leadership", "Architecture"],
            availability_status: "available",
            weekly_capacity_hours: 40,
          }),
        };
      }
      if (urlStr.includes("/profiles/team/")) {
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

    render(<App />);

    // Should load dashboard directly with restored identity without showing login form
    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
    expect(screen.getAllByText("Persisted Manager").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Restored Squad")).toBeInTheDocument();
    expect(sessionStorage.getItem("token")).toBe("persisted-jwt-token");
  });

  it("clears sessionStorage and returns to login when stored token is invalid or returns 401", async () => {
    // Set invalid or expired token
    sessionStorage.setItem("token", "expired-or-invalid-jwt");

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: false,
          status: 401,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Token has expired" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    // Should transition to login screen and clear token from sessionStorage
    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(sessionStorage.getItem("token")).toBeNull();
  });

  it("clears stored token from sessionStorage on sign out", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("token", "token-to-be-cleared");

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "64b1f28b4f1c2b3a4e5d6f70",
            name: "Alex Johnson",
            email: "alex.johnson@example.com",
            role: "employee",
          }),
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: false }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: false,
          status: 404,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Employee profile not found" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
    expect(sessionStorage.getItem("token")).toBe("token-to-be-cleared");

    // Click Sign Out
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    // Verify redirected to login and token removed from sessionStorage
    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(sessionStorage.getItem("token")).toBeNull();
  });

  it("renders admin user management directory and team controls without profile edit controls", async () => {
    const user = userEvent.setup();

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/login")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ access_token: "admin-jwt", token_type: "bearer", expires_in: 900 }),
        };
      }
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "64b1f28b4f1c2b3a4e5d6f11",
            name: "Super Administrator",
            email: "admin@example.com",
            role: "admin",
          }),
        };
      }
      if (urlStr.includes("/admin/users")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: [
              {
                id: "64b1f28b4f1c2b3a4e5d6f11",
                name: "Super Administrator",
                email: "admin@example.com",
                role: "admin",
                is_active: true,
              },
              {
                id: "64b1f28b4f1c2b3a4e5d6f22",
                name: "John Manager",
                email: "john.mgr@example.com",
                role: "manager",
                is_active: true,
              },
            ],
            total: 2,
            page: 1,
            limit: 10,
            total_pages: 1,
          }),
        };
      }
      if (urlStr.includes("/admin/teams")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => [
            {
              id: "64b1f28b4f1c2b3a4e5d6f33",
              name: "Alpha Team",
              manager_id: "64b1f28b4f1c2b3a4e5d6f22",
              manager_name: "John Manager",
              manager_email: "john.mgr@example.com",
              members: [],
            },
          ],
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    await user.type(screen.getByLabelText(/email address/i), "admin@example.com");
    await user.type(screen.getByLabelText(/^password/i), "AdminPassword12345!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /user access management/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /team structure & membership/i })).toBeInTheDocument();
    expect(screen.getByText("Alpha Team")).toBeInTheDocument();
    expect(screen.getByText("john.mgr@example.com")).toBeInTheDocument();

    // Admin dashboard should NOT contain work profile sections
    expect(screen.queryByText(/my work profile/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/team work profiles/i)).not.toBeInTheDocument();
  });
});

describe("Employee Work Profiles Features", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  const mockEmployeeUser = {
    id: "64b1f28b4f1c2b3a4e5d6f70",
    name: "Pamod Sachintha",
    email: "pamod@example.com",
    role: "employee",
  };

  const mockProfile = {
    id: "64b1f28b4f1c2b3a4e5d6fa1",
    user_id: "64b1f28b4f1c2b3a4e5d6f70",
    job_title: "Senior Software Engineer",
    skills: ["React", "FastAPI", "MongoDB"],
    availability_status: "available",
    weekly_capacity_hours: 40,
    created_at: "2026-09-20T10:00:00Z",
    updated_at: "2026-09-20T10:00:00Z",
  };

  it("renders existing employee work profile with chips and status badge", async () => {
    sessionStorage.setItem("token", "emp-token-1");

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockEmployeeUser,
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: true, team_name: "Engineering" }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockProfile,
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    expect(await screen.findByText("Senior Software Engineer")).toBeInTheDocument();
    expect(screen.getByText("40 hours per week")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText("FastAPI")).toBeInTheDocument();
    expect(screen.getByText("MongoDB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit profile/i })).toBeInTheDocument();
  });

  it("displays friendly empty state and allows creating profile when GET /profiles/me returns 404", async () => {
    sessionStorage.setItem("token", "emp-token-2");
    const user = userEvent.setup();

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockEmployeeUser,
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: false }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: false,
          status: 404,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Employee profile not found" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    expect(await screen.findByText(/no work profile created yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/requested profile not found/i)).not.toBeInTheDocument();

    const createBtn = screen.getByRole("button", { name: /create work profile/i });
    await user.click(createBtn);

    // Form inputs are now visible
    expect(screen.getByLabelText(/job title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/skills & expertise/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create profile/i })).toBeInTheDocument();
  });

  it("employee successfully creates a profile and normalizes skills", async () => {
    sessionStorage.setItem("token", "emp-token-3");
    const user = userEvent.setup();

    let capturedPutBody = null;

    global.fetch = vi.fn().mockImplementation(async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockEmployeeUser,
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: false }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        if (options?.method === "PUT") {
          capturedPutBody = JSON.parse(options.body);
          return {
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              id: "64b1f28b4f1c2b3a4e5d6fa2",
              user_id: mockEmployeeUser.id,
              job_title: capturedPutBody.job_title,
              skills: capturedPutBody.skills,
              availability_status: capturedPutBody.availability_status,
              weekly_capacity_hours: capturedPutBody.weekly_capacity_hours,
            }),
          };
        }
        return {
          ok: false,
          status: 404,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Employee profile not found" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    // Click Create Work Profile
    const createBtn = await screen.findByRole("button", { name: /create work profile/i });
    await user.click(createBtn);

    // Fill form
    await user.type(screen.getByLabelText(/job title/i), "Frontend Engineer");
    await user.type(screen.getByLabelText(/skills & expertise/i), " Vue.js , TypeScript , React ");
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    // Select availability
    await user.selectOptions(screen.getByLabelText(/availability status/i), "busy");

    // Change capacity
    const capacityInput = screen.getByLabelText(/weekly capacity/i);
    await user.clear(capacityInput);
    await user.type(capacityInput, "35");

    // Submit
    await user.click(screen.getByRole("button", { name: /create profile/i }));

    // Verify submission body had normalized skills
    expect(capturedPutBody).toEqual({
      job_title: "Frontend Engineer",
      skills: ["Vue.js", "TypeScript", "React"],
      availability_status: "busy",
      weekly_capacity_hours: 35,
    });

    // Verify success banner and updated profile summary rendered
    expect(await screen.findByText(/work profile saved successfully/i)).toBeInTheDocument();
    expect(screen.getByText("Frontend Engineer")).toBeInTheDocument();
    expect(screen.getByText("Busy")).toBeInTheDocument();
    expect(screen.getByText("35 hours per week")).toBeInTheDocument();
    expect(screen.getByText("Vue.js")).toBeInTheDocument();
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
  });

  it("employee successfully updates existing profile", async () => {
    sessionStorage.setItem("token", "emp-token-4");
    const user = userEvent.setup();

    let capturedPutBody = null;

    global.fetch = vi.fn().mockImplementation(async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockEmployeeUser,
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: false }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        if (options?.method === "PUT") {
          capturedPutBody = JSON.parse(options.body);
          return {
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
              ...mockProfile,
              job_title: capturedPutBody.job_title,
              availability_status: capturedPutBody.availability_status,
            }),
          };
        }
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockProfile,
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    // Wait for profile to load
    expect(await screen.findByText("Senior Software Engineer")).toBeInTheDocument();

    // Click Edit
    await user.click(screen.getByRole("button", { name: /edit profile/i }));

    // Change Job Title and Status
    const titleInput = screen.getByLabelText(/job title/i);
    await user.clear(titleInput);
    await user.type(titleInput, "Staff Architect");
    await user.selectOptions(screen.getByLabelText(/availability status/i), "on_leave");

    // Submit
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText(/work profile saved successfully/i)).toBeInTheDocument();
    expect(screen.getByText("Staff Architect")).toBeInTheDocument();
    expect(screen.getByText("On Leave")).toBeInTheDocument();
  });

  it("validates required fields and invalid weekly capacity (0-80)", async () => {
    sessionStorage.setItem("token", "emp-token-5");
    const user = userEvent.setup();

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockEmployeeUser,
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: false }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: false,
          status: 404,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Not found" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    const createBtn = await screen.findByRole("button", { name: /create work profile/i });
    await user.click(createBtn);

    // Leave job title blank and set capacity to 100
    const capacityInput = screen.getByLabelText(/weekly capacity/i);
    await user.clear(capacityInput);
    await user.type(capacityInput, "100");

    await user.click(screen.getByRole("button", { name: /create profile/i }));

    expect(await screen.findByText("Job title is required.")).toBeInTheDocument();
    expect(screen.getByText("Weekly capacity must be between 0 and 80 hours.")).toBeInTheDocument();
  });

  it("handles API failure gracefully with user-friendly error message", async () => {
    sessionStorage.setItem("token", "emp-token-6");
    const user = userEvent.setup();

    global.fetch = vi.fn().mockImplementation(async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockEmployeeUser,
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: false }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        if (options?.method === "PUT") {
          return {
            ok: false,
            status: 422,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ detail: "Invalid weekly capacity hours specified." }),
          };
        }
        return {
          ok: false,
          status: 404,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Not found" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    const createBtn = await screen.findByRole("button", { name: /create work profile/i });
    await user.click(createBtn);

    await user.type(screen.getByLabelText(/job title/i), "Dev");
    await user.click(screen.getByRole("button", { name: /create profile/i }));

    expect(await screen.findByText("Invalid weekly capacity hours specified.")).toBeInTheDocument();
  });

  it("disables save button and displays loading indicator while profile submission is in flight", async () => {
    sessionStorage.setItem("token", "emp-token-inflight");
    const user = userEvent.setup();

    let resolvePutPromise;
    const putPromise = new Promise((resolve) => {
      resolvePutPromise = resolve;
    });

    global.fetch = vi.fn().mockImplementation(async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockEmployeeUser,
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: false }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        if (options?.method === "PUT") {
          return await putPromise;
        }
        return {
          ok: false,
          status: 404,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Not found" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    const createBtn = await screen.findByRole("button", { name: /create work profile/i });
    await user.click(createBtn);

    await user.type(screen.getByLabelText(/job title/i), "Software Architect");
    const submitBtn = screen.getByRole("button", { name: /create profile/i });

    // Click submit and verify button becomes disabled with loading indicator
    await user.click(submitBtn);
    expect(submitBtn).toBeDisabled();
    expect(screen.getByText(/saving profile/i)).toBeInTheDocument();

    // Resolve PUT promise
    resolvePutPromise({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        ...mockProfile,
        job_title: "Software Architect",
      }),
    });

    // Verify it transitions to summary and is no longer submitting
    expect(await screen.findByText("Software Architect")).toBeInTheDocument();
  });

  it("handles 401 session expiry when calling profile endpoints", async () => {
    sessionStorage.setItem("token", "emp-token-7");

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockEmployeeUser,
        };
      }
      if (urlStr.includes("/teams/my-summary")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: false }),
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: false,
          status: 401,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Could not validate credentials" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    // Should redirect to login and clear token
    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(sessionStorage.getItem("token")).toBeNull();
  });
});

describe("Manager Team Work Profiles and Self-Profile Management", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  const mockManagerUser = {
    id: "64b1f28b4f1c2b3a4e5d6f22",
    name: "Demo Manager",
    email: "manager@example.com",
    role: "manager",
  };

  const mockManagedTeams = [
    {
      id: "64b1f28b4f1c2b3a4e5d6f33",
      name: "Engineering Alpha",
      manager_id: "64b1f28b4f1c2b3a4e5d6f22",
      manager_name: "Demo Manager",
      manager_email: "manager@example.com",
      members: [
        {
          id: "64b1f28b4f1c2b3a4e5d6f71",
          name: "Alice Developer",
          email: "alice@example.com",
          role: "employee",
          is_active: true,
        },
        {
          id: "64b1f28b4f1c2b3a4e5d6f72",
          name: "Bob Designer",
          email: "bob@example.com",
          role: "employee",
          is_active: true,
        },
      ],
    },
  ];

  it("manager sees read-only team profiles and 'Profile not completed' fallback", async () => {
    sessionStorage.setItem("token", "mgr-token-1");

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockManagerUser,
        };
      }
      if (urlStr.includes("/teams/managed")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockManagedTeams,
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "64b1f28b4f1c2b3a4e5d6f90",
            user_id: mockManagerUser.id,
            job_title: "Lead Engineering Manager",
            skills: ["Leadership", "Agile"],
            availability_status: "available",
            weekly_capacity_hours: 40,
          }),
        };
      }
      if (urlStr.includes("/profiles/team/")) {
        // Alice has profile, Bob does NOT
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            items: [
              {
                id: "64b1f28b4f1c2b3a4e5d6fa3",
                user_id: "64b1f28b4f1c2b3a4e5d6f71",
                job_title: "Full-Stack Engineer",
                skills: ["React", "Python"],
                availability_status: "available",
                weekly_capacity_hours: 40,
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

    render(<App />);

    // Manager self profile
    expect(await screen.findByText("Lead Engineering Manager")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit profile/i })).toBeInTheDocument();

    // Team profiles section
    expect(await screen.findByRole("heading", { name: /team work profiles/i })).toBeInTheDocument();
    const teamSection = document.getElementById("manager-team-profiles-section");
    expect(within(teamSection).getByText("Alice Developer")).toBeInTheDocument();
    expect(within(teamSection).getByText("Full-Stack Engineer")).toBeInTheDocument();
    expect(within(teamSection).getByText("React")).toBeInTheDocument();
    expect(within(teamSection).getByText("Python")).toBeInTheDocument();

    // Bob has no profile -> "Profile not completed"
    expect(within(teamSection).getByText("Bob Designer")).toBeInTheDocument();
    expect(within(teamSection).getByText("Profile not completed")).toBeInTheDocument();

    // Verify there are no employee profile edit buttons in the team profiles table
    const editBtnsInTeam = within(teamSection).queryAllByRole("button", { name: /edit/i });
    expect(editBtnsInTeam.length).toBe(0);
  });

  it("manager without a team sees the correct empty state", async () => {
    sessionStorage.setItem("token", "mgr-token-2");

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockManagerUser,
        };
      }
      if (urlStr.includes("/teams/managed")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => [],
        };
      }
      if (urlStr.includes("/profiles/me")) {
        return {
          ok: false,
          status: 404,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ detail: "Not found" }),
        };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({}) };
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: /your managed teams/i })).toBeInTheDocument();
    const noTeamsNotices = await screen.findAllByText(/no managed teams assigned/i);
    expect(noTeamsNotices.length).toBeGreaterThanOrEqual(1);
  });
});

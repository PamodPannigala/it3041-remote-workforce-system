import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

  it("renders admin user management directory and team controls for admin role", async () => {
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
  });

  it("handles unassigned employee empty state gracefully", async () => {
    const user = userEvent.setup();

    global.fetch = vi.fn().mockImplementation(async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/auth/login")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ access_token: "tok", token_type: "bearer", expires_in: 900 }),
        };
      }
      if (urlStr.includes("/auth/me")) {
        return {
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            id: "64b1f28b4f1c2b3a4e5d6f70",
            name: "Unassigned Employee",
            email: "unassigned@example.com",
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
      return {
        ok: false,
        status: 404,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ detail: "Not found" }),
      };
    });

    render(<App />);
    await user.type(screen.getByLabelText(/email address/i), "unassigned@example.com");
    await user.type(screen.getByLabelText(/^password/i), "Password123456789!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
    expect(await screen.findByText(/no team assigned/i)).toBeInTheDocument();
  });
});

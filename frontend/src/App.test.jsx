import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

describe("Frontend Authentication and Dashboard Flows", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders login form by default with necessary inputs", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create an account/i })).toBeInTheDocument();
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

  it("executes successful login, loads /auth/me, displays dashboard, and logs out", async () => {
    const user = userEvent.setup();

    // Mock 1: /api/auth/login
    // Mock 2: /api/auth/me
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          access_token: "mock-valid-jwt-token",
          token_type: "bearer",
          expires_in: 900,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          id: "64b1f28b4f1c2b3a4e5d6f70",
          name: "Alex Johnson",
          email: "alex.johnson@example.com",
          role: "employee",
        }),
      });

    render(<App />);

    await user.type(screen.getByLabelText(/email address/i), "alex.johnson@example.com");
    await user.type(screen.getByLabelText(/^password/i), "CorrectPassword12345!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // Verify dashboard content
    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
    expect(screen.getAllByText("Alex Johnson").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("alex.johnson@example.com")).toBeInTheDocument();
    expect(screen.getAllByText("employee").length).toBeGreaterThanOrEqual(1);

    // Verify specialist agents are shown as "Not implemented"
    expect(screen.getAllByText(/not implemented/i).length).toBe(4);

    // Logout
    await user.click(screen.getByRole("button", { name: /sign out/i }));
    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
  });

  it("demonstrates 403 access denial in dashboard without logging user out", async () => {
    const user = userEvent.setup();

    // Mock login, /auth/me, and /admin/access-check
    global.fetch = vi
      .fn()
      .mockImplementation(async (url) => {
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
              name: "Employee User",
              email: "emp@example.com",
              role: "employee",
            }),
          };
        }
        if (urlStr.includes("/admin/access-check")) {
          return {
            ok: false,
            status: 403,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ detail: "Operation not permitted" }),
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
    await user.type(screen.getByLabelText(/email address/i), "emp@example.com");
    await user.type(screen.getByLabelText(/^password/i), "Password123456789!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();

    // Click test admin access
    await user.click(screen.getByRole("button", { name: /test admin access/i }));

    // Should display 403 error message but remain on dashboard
    expect(await screen.findByText(/access denied \(http 403\)/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
  });
});

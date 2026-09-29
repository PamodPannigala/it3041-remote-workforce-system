import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import AppShell from "../AppShell";
import MobileNavigation from "../MobileNavigation";
import Sidebar from "../Sidebar";
import Topbar from "../Topbar";
import Dashboard from "../../pages/Dashboard";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const users = {
  employee: { name: "Employee User", email: "employee@example.com", role: "employee" },
  manager: { name: "Manager User", email: "manager@example.com", role: "manager" },
  admin: { name: "Admin User", email: "admin@example.com", role: "admin" },
};

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
  };
}

describe("Authenticated shared layout", () => {
  it.each([
    ["employee", "Weekly Pulse Survey"],
    ["manager", "Team Tasks"],
    ["admin", "User Directory"],
  ])("renders the sticky %s header with only the actual page title", (role, title) => {
    render(<Topbar user={users[role]} activeTabTitle={title} onOpenMobileNav={vi.fn()} />);

    const header = screen.getByTestId("authenticated-header");
    const titleArea = screen.getByTestId("page-title-area");
    expect(header).toHaveClass("sticky", "top-0", "z-40", "bg-white");
    expect(titleArea).toHaveTextContent(title);
    expect(titleArea).not.toHaveTextContent("Workspace");
    expect(titleArea).not.toHaveTextContent("/");
    expect(within(header).getByText("Session Active")).toBeInTheDocument();
    expect(within(header).getByText(role)).toBeInTheDocument();
    expect(within(header).getByText(users[role].name)).toBeInTheDocument();
    expect(within(titleArea).getByRole("heading", { name: title })).toHaveClass("truncate");
  });

  it("keeps the sticky header in normal flow beside the fixed desktop sidebar", () => {
    const { container } = render(
      <AppShell
        user={users.manager}
        activeTab="overview"
        activeTabTitle="Overview"
        onTabChange={vi.fn()}
        onLogout={vi.fn()}
      >
        <div>Scrollable content</div>
      </AppShell>,
    );

    const shell = container.firstElementChild;
    const sidebar = container.querySelector("aside");
    const contentColumn = screen.getByTestId("authenticated-header").parentElement;
    expect(shell).toHaveClass("overflow-x-clip");
    expect(sidebar).toHaveClass("fixed", "md:flex", "z-20");
    expect(contentColumn).toHaveClass("md:pl-64", "min-w-0");
    expect(screen.getByTestId("authenticated-header")).toHaveClass("z-40", "shrink-0");
  });

  it("removes the authenticated version badge and keeps the brand to two non-wrapping lines", () => {
    const { rerender } = render(
      <Sidebar user={users.manager} activeTab="overview" onTabChange={vi.fn()} onLogout={vi.fn()} />,
    );

    expect(screen.queryByText("v1.0")).not.toBeInTheDocument();
    expect(screen.getByText("Remote Workforce")).toHaveClass("whitespace-nowrap");
    expect(screen.getByText("System")).toHaveClass("whitespace-nowrap");

    rerender(
      <MobileNavigation
        isOpen
        user={users.manager}
        activeTab="overview"
        onTabChange={vi.fn()}
        onClose={vi.fn()}
        onLogout={vi.fn()}
      />,
    );
    expect(screen.queryByText("v1.0")).not.toBeInTheDocument();
    expect(screen.getByText("Remote Workforce")).toHaveClass("whitespace-nowrap");
    expect(screen.getByText("System")).toHaveClass("whitespace-nowrap");
  });

  it("shows AI Insights to managers in desktop and mobile navigation but never to admins", () => {
    const { rerender } = render(
      <Sidebar user={users.manager} activeTab="overview" onTabChange={vi.fn()} onLogout={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "AI Insights" })).toBeInTheDocument();

    rerender(
      <MobileNavigation
        isOpen
        user={users.manager}
        activeTab="overview"
        onTabChange={vi.fn()}
        onClose={vi.fn()}
        onLogout={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "AI Insights" })).toBeInTheDocument();

    rerender(
      <Sidebar user={users.admin} activeTab="overview" onTabChange={vi.fn()} onLogout={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "AI Insights" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Teams" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Task Audit" })).toBeInTheDocument();

    rerender(
      <MobileNavigation
        isOpen
        user={users.admin}
        activeTab="overview"
        onTabChange={vi.fn()}
        onClose={vi.fn()}
        onLogout={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "AI Insights" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Teams" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pulse Audit" })).toBeInTheDocument();
  });

  it("safely redirects an admin AI workspace entry to the unchanged admin overview", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url) => {
      const path = String(url);
      if (path.includes("/admin/users")) {
        return jsonResponse({ items: [], page: 1, limit: 10, total: 0, total_pages: 0 });
      }
      if (path.includes("/admin/teams")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Dashboard initialTab="ai-insights" user={users.admin} token="admin-token" />);

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByText("User Access Management")).toBeInTheDocument();
    expect(screen.getByText("Team Structure & Membership")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-workspace")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/agents/"),
      expect.anything(),
    );
  });
});

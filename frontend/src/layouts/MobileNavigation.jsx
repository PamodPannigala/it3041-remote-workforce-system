import React from "react";
import BrandLogo from "../components/BrandLogo";
import Badge from "../components/ui/Badge";

export default function MobileNavigation({
  isOpen,
  onClose,
  user,
  activeTab,
  onTabChange,
  onLogout,
}) {
  if (!isOpen) return null;

  const role = user?.role || "employee";

  const navItemsByRole = {
    employee: [
      { id: "overview", label: "Overview" },
      { id: "my-team", label: "My Team" },
      { id: "work-profile", label: "Work Profile" },
      { id: "my-tasks", label: "My Tasks" },
      { id: "team-messages", label: "Team Messages" },
      { id: "weekly-pulse", label: "Weekly Pulse" },
    ],
    manager: [
      { id: "overview", label: "Overview" },
      { id: "managed-teams", label: "Managed Teams" },
      { id: "work-profile", label: "Work Profile" },
      { id: "team-profiles", label: "Team Profiles" },
      { id: "team-tasks", label: "Team Tasks" },
      { id: "team-messages", label: "Team Messages" },
      { id: "pulse-insights", label: "Pulse Insights" },
      { id: "ai-insights", label: "AI Insights" },
    ],
    admin: [
      { id: "overview", label: "Overview" },
      { id: "users", label: "Users" },
      { id: "teams", label: "Teams" },
      { id: "task-audit", label: "Task Audit" },
      { id: "message-audit", label: "Message Audit" },
      { id: "pulse-audit", label: "Pulse Audit" },
      { id: "ai-insights", label: "AI Insights" },
    ],
  };

  const currentNav = navItemsByRole[role] || navItemsByRole.employee;

  const activeStylesByRole = {
    employee: "bg-blue-600 text-white border border-blue-500 font-semibold",
    manager: "bg-amber-400 text-slate-950 border border-amber-300 font-semibold",
    admin: "bg-violet-600 text-white border border-violet-500 font-semibold",
  };

  const activeStyle = activeStylesByRole[role] || activeStylesByRole.employee;

  return (
    <div className="fixed inset-0 z-50 md:hidden flex" role="dialog" aria-modal="true" aria-label="Main navigation">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm transition-opacity duration-200"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div className="relative w-[min(86vw,21rem)] bg-[#111827] border-r border-slate-700/70 flex flex-col justify-between h-full max-h-[100dvh] z-10 p-5 shadow-2xl">
        <div>
          {/* Header */}
          <div className="flex items-center justify-between pb-4 border-b border-slate-700/70">
            <BrandLogo />
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white transition-colors"
              aria-label="Close menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* User Badge */}
          <div className="py-3 flex items-center justify-between border-b border-slate-700/70 mb-4">
            <span className="text-xs text-slate-400">Signed in as</span>
            <Badge variant={role} size="sm">
              {role}
            </Badge>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1 overflow-y-auto max-h-[calc(100dvh-13rem)] pr-1" aria-label="Mobile Navigation">
            {currentNav.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    onTabChange(item.id);
                    onClose();
                  }}
                  aria-current={isActive ? "page" : undefined}
                  className={`w-full flex items-center px-4 py-3 rounded-lg border text-sm text-left transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white ${
                    isActive
                      ? activeStyle
                      : "border-transparent text-slate-200 hover:bg-slate-800/80 hover:text-white"
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-slate-700/70">
          <div className="text-xs text-slate-400 mb-3 truncate">
            {user?.name} ({user?.email})
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold text-rose-200 bg-rose-950/30 border border-rose-900/60 hover:bg-rose-900/50 transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            <span>Sign Out</span>
          </button>
        </div>
      </div>
    </div>
  );
}

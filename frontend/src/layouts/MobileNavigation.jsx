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
    ],
    manager: [
      { id: "overview", label: "Overview" },
      { id: "managed-teams", label: "Managed Teams" },
      { id: "work-profile", label: "Work Profile" },
      { id: "team-profiles", label: "Team Profiles" },
      { id: "team-tasks", label: "Team Tasks" },
    ],
    admin: [
      { id: "overview", label: "Overview" },
      { id: "users", label: "Users" },
      { id: "teams", label: "Teams" },
      { id: "task-audit", label: "Task Audit" },
    ],
  };

  const currentNav = navItemsByRole[role] || navItemsByRole.employee;

  const activeStylesByRole = {
    employee: "bg-blue-600/15 text-blue-400 border border-blue-500/30 font-semibold",
    manager: "bg-amber-600/15 text-amber-300 border border-amber-500/30 font-semibold",
    admin: "bg-violet-600/15 text-violet-300 border border-violet-500/30 font-semibold",
  };

  const activeStyle = activeStylesByRole[role] || activeStylesByRole.employee;

  return (
    <div className="fixed inset-0 z-50 md:hidden flex" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/70 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div className="relative w-4/5 max-w-xs bg-slate-900 border-r border-slate-800 flex flex-col justify-between h-full z-10 p-5 shadow-2xl">
        <div>
          {/* Header */}
          <div className="flex items-center justify-between pb-4 border-b border-slate-800">
            <BrandLogo />
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              aria-label="Close menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* User Badge */}
          <div className="py-3 flex items-center justify-between border-b border-slate-800/60 mb-4">
            <span className="text-xs text-slate-400">Signed in as</span>
            <Badge variant={role} size="sm">
              {role}
            </Badge>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1.5" aria-label="Mobile Navigation">
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
                  className={`w-full flex items-center px-4 py-3 rounded-xl text-sm text-left transition-colors ${
                    isActive
                      ? activeStyle
                      : "text-slate-300 hover:bg-slate-800/60 hover:text-white"
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-slate-800">
          <div className="text-xs text-slate-400 mb-3 truncate">
            {user?.name} ({user?.email})
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold text-rose-300 bg-rose-950/30 border border-rose-900/50 hover:bg-rose-900/50 transition-colors"
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

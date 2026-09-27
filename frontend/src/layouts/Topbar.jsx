import React from "react";
import Badge from "../components/ui/Badge";

export default function Topbar({
  user,
  activeTabTitle = "Overview",
  onOpenMobileNav,
  isSidebarCollapsed = false,
  onToggleSidebar,
}) {
  const role = user?.role || "employee";

  return (
    <header className="min-h-16 border-b border-slate-200/80 bg-white/95 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between sticky top-0 z-30 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      {/* Left: Navigation Toggle & Page Title */}
      <div className="flex items-center gap-2 sm:gap-3 min-w-0">
        <button
          type="button"
          onClick={onOpenMobileNav}
          className="md:hidden p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          aria-label="Open navigation menu"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <button
          type="button"
          onClick={onToggleSidebar}
          className="hidden md:inline-flex p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!isSidebarCollapsed}
          aria-controls="desktop-sidebar"
          title={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <rect x="3.5" y="4.5" width="17" height="15" rx="2" strokeWidth="1.8" />
            <path strokeLinecap="round" strokeWidth="1.8" d="M9 5v14m4-10 2.5 3-2.5 3" />
          </svg>
        </button>

        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-slate-400 hidden sm:inline">
            Workspace
          </span>
          <span className="text-xs text-slate-300 hidden sm:inline">/</span>
          <h1 className="text-sm sm:text-base font-bold font-heading text-slate-900 truncate">
            {activeTabTitle}
          </h1>
        </div>
      </div>

      {/* Right: Security Pill & Compact User Avatar */}
      <div className="flex items-center gap-3 sm:gap-4">
        <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-xs font-medium text-emerald-800">
          <span className="w-2 h-2 rounded-full bg-emerald-600" />
          <span>Session Active</span>
        </div>

        <Badge variant={role} size="sm">
          {role}
        </Badge>

        <div className="h-4 w-px bg-slate-200 hidden sm:block" />

        {/* Compact User Identity / Avatar */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-xs font-bold text-slate-700 shrink-0">
            {user?.name ? user.name.charAt(0).toUpperCase() : "U"}
          </div>
          <span className="text-xs font-semibold text-slate-800 hidden md:inline truncate max-w-40">
            {user?.name}
          </span>
        </div>
      </div>
    </header>
  );
}

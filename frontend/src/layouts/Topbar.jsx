import React from "react";
import Badge from "../components/ui/Badge";

export default function Topbar({
  user,
  activeTabTitle = "Overview",
  onOpenMobileNav,
}) {
  const role = user?.role || "employee";

  return (
    <header
      className="h-16 shrink-0 border-b border-slate-200/80 bg-white px-4 sm:px-6 flex items-center justify-between sticky top-0 z-40"
      data-testid="authenticated-header"
    >
      {/* Left: Mobile Toggle & Page Title */}
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <button
          type="button"
          onClick={onOpenMobileNav}
          className="md:hidden p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
          aria-label="Open navigation menu"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <div className="min-w-0 flex-1" data-testid="page-title-area">
          <h1 className="text-sm sm:text-base font-bold font-heading text-slate-900 truncate" title={activeTabTitle}>
            {activeTabTitle}
          </h1>
        </div>
      </div>

      {/* Right: Security Pill & Compact User Avatar */}
      <div className="flex items-center gap-3 sm:gap-4 shrink-0 ml-3">
        <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200/80 text-xs font-medium text-emerald-700">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>Session Active</span>
        </div>

        <Badge variant={role} size="sm">
          {role}
        </Badge>

        <div className="h-4 w-px bg-slate-200 hidden sm:block" />

        {/* Compact User Identity / Avatar */}
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-xs font-bold text-slate-700">
            {user?.name ? user.name.charAt(0).toUpperCase() : "U"}
          </div>
          <span className="text-xs font-semibold text-slate-800 hidden md:inline">
            {user?.name}
          </span>
        </div>
      </div>
    </header>
  );
}

import React from "react";
import Badge from "../ui/Badge";

export default function Topbar({
  user,
  activeTabTitle = "Overview",
  onOpenMobileNav,
}) {
  const role = user?.role || "employee";

  return (
    <header className="h-16 border-b border-slate-200/80 bg-white/95 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between sticky top-0 z-30">
      {/* Left: Mobile Toggle & Page Title */}
      <div className="flex items-center gap-3">
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

        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-400 hidden sm:inline">
            Workspace
          </span>
          <span className="text-xs text-slate-300 hidden sm:inline">/</span>
          <h1 className="text-sm sm:text-base font-bold font-heading text-slate-900">
            {activeTabTitle}
          </h1>
        </div>
      </div>

      {/* Right: Security Pill & Compact User Avatar */}
      <div className="flex items-center gap-3 sm:gap-4">
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

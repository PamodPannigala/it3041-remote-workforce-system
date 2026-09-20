import React from "react";

export default function Badge({
  children,
  variant = "default",
  size = "md",
  className = "",
  dot = false,
  ...props
}) {
  const sizeStyles = {
    sm: "text-[11px] px-2 py-0.5 font-medium rounded-full",
    md: "text-xs px-2.5 py-1 font-semibold rounded-full",
    lg: "text-sm px-3 py-1.5 font-semibold rounded-lg",
  };

  const variantStyles = {
    default: "bg-slate-100 text-slate-700 border border-slate-200",
    // Role Badges
    employee: "bg-blue-50 text-blue-700 border border-blue-200 font-semibold",
    manager: "bg-amber-50 text-amber-800 border border-amber-200 font-semibold",
    admin: "bg-violet-50 text-violet-700 border border-violet-200 font-semibold",

    // Availability & Status Badges
    available: "bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium",
    active: "bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium",
    busy: "bg-amber-50 text-amber-800 border border-amber-200 font-medium",
    on_leave: "bg-violet-50 text-violet-700 border border-violet-200 font-medium",
    inactive: "bg-rose-50 text-rose-700 border border-rose-200 font-medium",
    danger: "bg-rose-50 text-rose-700 border border-rose-200 font-medium",
    info: "bg-cyan-50 text-cyan-700 border border-cyan-200 font-medium",
    slate: "bg-slate-100 text-slate-600 border border-slate-200 font-medium",

    // Task Status Badges
    todo: "bg-slate-100 text-slate-700 border border-slate-300 font-medium",
    in_progress: "bg-blue-50 text-blue-700 border border-blue-200 font-medium",
    blocked: "bg-rose-50 text-rose-700 border border-rose-200 font-semibold",
    completed: "bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium",

    // Task Priority Badges
    low: "bg-slate-50 text-slate-600 border border-slate-200 font-medium",
    medium: "bg-blue-50 text-blue-700 border border-blue-200 font-medium",
    high: "bg-amber-50 text-amber-800 border border-amber-200 font-medium",
    urgent: "bg-rose-50 text-rose-700 border border-rose-200 font-semibold",
  };

  const dotColors = {
    available: "bg-emerald-500",
    active: "bg-emerald-500",
    busy: "bg-amber-500",
    on_leave: "bg-violet-500",
    inactive: "bg-rose-500",
    employee: "bg-blue-500",
    manager: "bg-amber-500",
    admin: "bg-violet-500",
    todo: "bg-slate-400",
    in_progress: "bg-blue-500",
    blocked: "bg-rose-500",
    completed: "bg-emerald-500",
    low: "bg-slate-400",
    medium: "bg-blue-500",
    high: "bg-amber-500",
    urgent: "bg-rose-500",
    default: "bg-slate-400",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 transition-colors duration-150 ${sizeStyles[size] || sizeStyles.md} ${variantStyles[variant] || variantStyles.default} ${className}`}
      {...props}
    >
      {dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full ${dotColors[variant] || dotColors.default}`}
        />
      )}
      <span>{children}</span>
    </span>
  );
}

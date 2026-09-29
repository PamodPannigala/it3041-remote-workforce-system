import React from "react";
import Badge from "../components/ui/Badge";

export default function PageHeader({
  title,
  description,
  role = "employee",
  action = null,
  stats = null,
  className = "",
}) {
  const roleAccents = {
    employee: "border-l-blue-600",
    manager: "border-l-amber-500",
    admin: "border-l-violet-600",
  };

  return (
    <div
      className={`rounded-xl p-5 sm:p-6 mb-6 bg-white border border-slate-200 border-l-4 ${roleAccents[role] || roleAccents.employee} shadow-sm ${className}`}
    >
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 mb-1.5 flex-wrap">
            <h2 className="text-xl sm:text-2xl font-bold font-heading text-slate-900">
              {title}
            </h2>
            <Badge variant={role} size="sm">
              {role}
            </Badge>
          </div>
          {description && (
            <p className="text-sm text-slate-600 max-w-2xl leading-relaxed">
              {description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3 self-stretch md:self-auto flex-wrap">
          {stats}
          {action}
        </div>
      </div>
    </div>
  );
}

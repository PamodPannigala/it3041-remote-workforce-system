import React from "react";
import Badge from "../ui/Badge";

export default function PageHeader({
  title,
  description,
  role = "employee",
  action = null,
  stats = null,
  className = "",
}) {
  const roleGradients = {
    employee: "from-blue-50/90 via-white to-cyan-50/60 border-blue-200/80 shadow-sm",
    manager: "from-amber-50/90 via-white to-orange-50/60 border-amber-200/80 shadow-sm",
    admin: "from-violet-50/90 via-white to-indigo-50/60 border-violet-200/80 shadow-sm",
  };

  return (
    <div
      className={`rounded-2xl p-5 sm:p-6 mb-6 bg-gradient-to-r ${roleGradients[role] || roleGradients.employee} border relative overflow-hidden ${className}`}
    >
      {/* Decorative subtle orb */}
      <div className="absolute top-0 right-0 -mt-8 -mr-8 w-48 h-48 rounded-full bg-blue-500/[0.04] blur-3xl pointer-events-none" />

      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 relative z-10">
        <div>
          <div className="flex items-center gap-2.5 mb-1.5 flex-wrap">
            <h2 className="text-xl sm:text-2xl font-extrabold font-heading text-slate-900 tracking-tight">
              {title}
            </h2>
            <Badge variant={role} size="sm">
              {role}
            </Badge>
          </div>
          {description && (
            <p className="text-xs sm:text-sm text-slate-600 max-w-2xl leading-relaxed">
              {description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3 self-start md:self-auto flex-wrap">
          {stats}
          {action}
        </div>
      </div>
    </div>
  );
}

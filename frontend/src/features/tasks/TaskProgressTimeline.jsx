import React from "react";
import Badge from "../../components/ui/Badge";

function formatDate(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

export default function TaskProgressTimeline({
  progressHistory = [],
  blockers = [],
  onResolveBlocker = null,
  isManager = false,
  className = "",
}) {
  const hasHistory = progressHistory.length > 0;
  const hasBlockers = blockers.length > 0;

  if (!hasHistory && !hasBlockers) {
    return (
      <div className={`p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-center ${className}`}>
        <p className="text-xs text-slate-500 italic">No progress logs or blockers recorded yet.</p>
      </div>
    );
  }

  return (
    <div className={`space-y-5 ${className}`}>
      {/* Blockers Section */}
      {hasBlockers && (
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h5 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Reported Blockers ({blockers.length})
            </h5>
            {blockers.some((b) => !b.is_resolved) && (
              <Badge variant="blocked" size="sm">
                Active Blocker
              </Badge>
            )}
          </div>

          <div className="space-y-2.5">
            {blockers.map((b) => (
              <div
                key={b.id}
                className={`p-3.5 rounded-xl border transition-colors ${
                  b.is_resolved
                    ? "bg-slate-50/90 border-slate-200 text-slate-700"
                    : "bg-rose-50/80 border-rose-200 text-rose-950"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`text-xs font-bold ${
                          b.is_resolved ? "text-slate-700" : "text-rose-900"
                        }`}
                      >
                        {b.is_resolved ? "✓ Resolved Blocker" : "⛔ Blocker Issue"}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        Reported on {formatDate(b.created_at)}
                        {b.user_name ? (
                          <>
                            {" "}by <span className="font-semibold text-slate-700">{b.user_name}</span>
                            {b.user_email && <span className="text-slate-400 font-normal"> ({b.user_email})</span>}
                          </>
                        ) : null}
                      </span>
                    </div>

                    <p className="text-xs leading-relaxed text-slate-800 break-words">
                      {b.description}
                    </p>

                    {/* Resolution details */}
                    {b.is_resolved && (
                      <div className="mt-2 p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-950 space-y-1">
                        <p className="text-xs leading-relaxed text-emerald-900 break-words">
                          <span className="font-semibold text-emerald-800">Resolution Note: </span>
                          {b.resolution_note || "No resolution note recorded (legacy record)."}
                        </p>
                        <p className="text-[11px] text-emerald-700 font-medium">
                          Resolved on {formatDate(b.resolved_at)}
                          {b.resolved_by_name ? (
                            <>
                              {" "}by <span className="font-semibold text-emerald-900">{b.resolved_by_name}</span>
                              {b.resolved_by_email && (
                                <span className="text-emerald-700/80 font-normal"> ({b.resolved_by_email})</span>
                              )}
                            </>
                          ) : null}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Manager Resolve Action */}
                  {isManager && !b.is_resolved && onResolveBlocker && (
                    <button
                      type="button"
                      onClick={() => onResolveBlocker(b)}
                      className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 shadow-xs transition-colors shrink-0"
                    >
                      Resolve
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Progress History Timeline */}
      {hasHistory && (
        <div className="space-y-2.5">
          <h5 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Progress Updates ({progressHistory.length})
          </h5>

          <div className="space-y-2">
            {progressHistory
              .slice()
              .reverse()
              .map((p) => (
                <div
                  key={p.id}
                  className="p-3 rounded-xl bg-white border border-slate-200/80 shadow-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-blue-600 font-mono">
                        {p.percentage}% Completed
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {formatDate(p.logged_at)}
                      </span>
                      {p.user_name && (
                        <span className="text-[11px] text-slate-500 font-medium">
                          by <span className="text-slate-700">{p.user_name}</span>
                          {p.user_email && (
                            <span className="text-slate-400 font-normal"> ({p.user_email})</span>
                          )}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Micro Progress Bar */}
                  <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                      style={{ width: `${Math.min(Math.max(p.percentage, 0), 100)}%` }}
                    />
                  </div>

                  <p className="text-xs text-slate-700 leading-relaxed break-words">
                    {p.notes}
                  </p>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

import React, { useRef } from "react";
import Badge from "../../../components/ui/Badge";

const SPECIALIST_LABELS = {
  productivity: { name: "Productivity", variant: "employee" },
  collaboration: { name: "Collaboration", variant: "available" },
  wellbeing: { name: "Well-being", variant: "info" },
  task_assigning: { name: "Task Assignment", variant: "manager" },
  coordinator: { name: "Coordinator", variant: "slate" },
};

function formatSpecialistLabel(spec) {
  if (!spec) return "";
  const conf = SPECIALIST_LABELS[spec];
  if (conf) return conf;
  const formatted = String(spec).replace(/_/g, " ");
  return {
    name: formatted.charAt(0).toUpperCase() + formatted.slice(1),
    variant: "default",
  };
}

export default function AgentIntentSelector({
  intents = [],
  selectedIntent,
  onSelectIntent,
  disabled = false,
  className = "",
}) {
  const itemRefs = useRef([]);

  if (!intents || intents.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-500 text-xs text-center">
        No analysis capabilities available for your current role.
      </div>
    );
  }

  // Find index of currently selected intent
  const selectedIndex = intents.findIndex((i) => i.intent === selectedIntent);
  const activeFocusIndex = selectedIndex >= 0 ? selectedIndex : 0;

  const handleKeyDown = (e, index) => {
    if (disabled || intents.length === 0) return;

    let targetIndex = null;

    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      targetIndex = (index + 1) % intents.length;
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      targetIndex = (index - 1 + intents.length) % intents.length;
    } else if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      onSelectIntent(intents[index].intent);
      return;
    }

    if (targetIndex !== null) {
      const nextIntent = intents[targetIndex];
      onSelectIntent(nextIntent.intent);
      if (itemRefs.current[targetIndex]) {
        itemRefs.current[targetIndex].focus();
      }
    }
  };

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="flex items-center justify-between">
        <label
          id="intent-selector-label"
          className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
        >
          Select Analysis Capability <span className="text-rose-500">*</span>
        </label>
        <span className="text-xs text-slate-500">
          {intents.length} {intents.length === 1 ? "capability" : "capabilities"} available
        </span>
      </div>

      <div
        role="radiogroup"
        aria-labelledby="intent-selector-label"
        className="grid grid-cols-1 md:grid-cols-2 gap-3"
      >
        {intents.map((item, index) => {
          const isSelected = selectedIntent === item.intent;
          // Roving tabIndex: selected item gets 0; if none selected, index 0 gets 0; all others -1
          const tabIndex = disabled ? -1 : isSelected || (selectedIndex < 0 && index === 0) ? 0 : -1;
          // Canonical backend schema uses target_specialists only (no legacy fallback)
          const specialists = item.target_specialists || [];

          return (
            <div
              key={item.intent}
              ref={(el) => (itemRefs.current[index] = el)}
              role="radio"
              aria-checked={isSelected}
              tabIndex={tabIndex}
              onClick={() => !disabled && onSelectIntent(item.intent)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              className={`p-4 rounded-xl border transition-all text-left cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${
                isSelected
                  ? "bg-blue-50/70 border-blue-500 shadow-sm ring-1 ring-blue-500"
                  : "bg-white border-slate-200/90 hover:border-slate-300 hover:bg-slate-50/50"
              } ${disabled ? "opacity-50 cursor-not-allowed pointer-events-none" : ""}`}
              data-testid={`intent-card-${item.intent}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-3.5 h-3.5 rounded-full border flex items-center justify-center shrink-0 ${
                        isSelected
                          ? "border-blue-600 bg-blue-600"
                          : "border-slate-300 bg-white"
                      }`}
                      aria-hidden="true"
                    >
                      {isSelected && (
                        <span className="w-1.5 h-1.5 rounded-full bg-white" />
                      )}
                    </span>
                    <h4 className="text-sm font-bold text-slate-900 truncate">
                      {item.name || item.intent}
                    </h4>
                  </div>
                  <p className="text-xs text-slate-600 mt-1 leading-relaxed line-clamp-2">
                    {item.description || "Specialist workforce telemetry analysis."}
                  </p>
                </div>

                {item.requires_team_scope && (
                  <Badge variant="slate" size="sm" className="shrink-0 text-[10px]">
                    Team Required
                  </Badge>
                )}
              </div>

              {/* Specialists coordination */}
              {specialists.length > 0 && (
                <div className="mt-3 pt-2.5 border-t border-slate-100 flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] uppercase font-bold text-slate-600 tracking-wider">
                    {specialists.length > 1 ? "Coordinated By:" : "Specialist:"}
                  </span>
                  {specialists.map((spec) => {
                    const conf = formatSpecialistLabel(spec);
                    return (
                      <Badge
                        key={spec}
                        variant={conf.variant}
                        size="sm"
                        className="text-[10px] px-1.5 py-0.5"
                      >
                        {conf.name}
                      </Badge>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

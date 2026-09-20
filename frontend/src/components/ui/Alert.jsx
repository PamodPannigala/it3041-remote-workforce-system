import React from "react";

export default function Alert({
  children,
  variant = "info",
  title = null,
  onDismiss = null,
  className = "",
  ...props
}) {
  const variantStyles = {
    info: "bg-blue-50 border-blue-200 text-blue-900 shadow-sm",
    success: "bg-emerald-50 border-emerald-200 text-emerald-900 shadow-sm",
    warning: "bg-amber-50 border-amber-200 text-amber-900 shadow-sm",
    error: "bg-rose-50 border-rose-200 text-rose-900 shadow-sm",
    danger: "bg-rose-50 border-rose-200 text-rose-900 shadow-sm",
  };

  const iconColors = {
    info: "text-blue-600",
    success: "text-emerald-600",
    warning: "text-amber-600",
    error: "text-rose-600",
    danger: "text-rose-600",
  };

  return (
    <div
      role="alert"
      className={`p-4 rounded-xl border flex items-start gap-3 ${variantStyles[variant] || variantStyles.info} ${className}`}
      {...props}
    >
      <div className={`shrink-0 mt-0.5 ${iconColors[variant] || iconColors.info}`}>
        {variant === "success" && (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
          </svg>
        )}
        {(variant === "error" || variant === "danger") && (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        )}
        {variant === "warning" && (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        )}
        {variant === "info" && (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        )}
      </div>

      <div className="flex-1 min-w-0">
        {title && <h4 className="font-semibold text-sm mb-1">{title}</h4>}
        <div className="text-sm leading-relaxed">{children}</div>
      </div>

      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 p-1 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-black/5 transition-colors"
          aria-label="Dismiss"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}

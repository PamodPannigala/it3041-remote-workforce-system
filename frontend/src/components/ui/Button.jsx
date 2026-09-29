import React from "react";

export default function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  className = "",
  type = "button",
  icon = null,
  onClick,
  ...props
}) {
  const baseStyles =
    "inline-flex cursor-pointer items-center justify-center rounded-lg font-semibold select-none transition-[transform,background-color,border-color,color,box-shadow,filter] duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-white enabled:hover:-translate-y-px enabled:active:translate-y-0 enabled:active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none disabled:transform-none motion-reduce:transform-none motion-reduce:transition-none";

  const sizeStyles = {
    sm: "px-2.5 py-1.5 text-xs gap-1.5",
    md: "px-4 py-2 text-sm gap-2",
    lg: "px-5 py-2.5 text-base gap-2.5",
  };

  const variantStyles = {
    primary:
      "border border-indigo-600 bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-sm shadow-blue-500/25 enabled:hover:from-blue-700 enabled:hover:to-indigo-700 enabled:hover:shadow-md enabled:hover:shadow-blue-500/25 focus-visible:ring-blue-500",
    secondary:
      "border border-slate-300 bg-slate-50 text-slate-700 shadow-sm enabled:hover:border-blue-300 enabled:hover:bg-blue-50/70 enabled:hover:text-slate-900 enabled:hover:shadow-md focus-visible:ring-blue-500",
    outline:
      "border border-slate-300 bg-white/90 text-slate-700 shadow-sm enabled:hover:border-blue-300 enabled:hover:bg-blue-50/60 enabled:hover:text-blue-800 enabled:hover:shadow-md focus-visible:ring-blue-500",
    ghost:
      "bg-transparent text-slate-600 enabled:hover:bg-slate-100 enabled:hover:text-slate-900 focus-visible:ring-slate-400",
    danger:
      "border border-rose-600 bg-rose-600 text-white shadow-sm shadow-rose-600/20 enabled:hover:border-rose-700 enabled:hover:bg-rose-700 enabled:hover:shadow-md enabled:hover:shadow-rose-600/20 focus-visible:ring-rose-500",
    dangerOutline:
      "border border-rose-300 bg-rose-50 text-rose-700 shadow-sm enabled:hover:border-rose-400 enabled:hover:bg-rose-100 enabled:hover:text-rose-800 enabled:hover:shadow-md focus-visible:ring-rose-500",
    success:
      "border border-emerald-600 bg-emerald-600 text-white shadow-sm shadow-emerald-500/20 enabled:hover:border-emerald-700 enabled:hover:bg-emerald-700 enabled:hover:shadow-md enabled:hover:shadow-emerald-500/20 focus-visible:ring-emerald-500",
    amber:
      "border border-amber-600 bg-amber-600 text-white shadow-sm shadow-amber-500/20 enabled:hover:border-amber-700 enabled:hover:bg-amber-700 enabled:hover:shadow-md enabled:hover:shadow-amber-500/20 focus-visible:ring-amber-500",
    violet:
      "border border-violet-600 bg-violet-600 text-white shadow-sm shadow-violet-500/20 enabled:hover:border-violet-700 enabled:hover:bg-violet-700 enabled:hover:shadow-md enabled:hover:shadow-violet-500/20 focus-visible:ring-violet-500",
  };

  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      onClick={onClick}
      className={`${baseStyles} ${sizeStyles[size] || sizeStyles.md} ${variantStyles[variant] || variantStyles.primary} ${className}`}
      {...props}
    >
      {loading && (
        <svg
          className="animate-spin -ml-0.5 mr-1.5 h-4 w-4 text-current"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      )}
      {!loading && icon}
      <span>{children}</span>
    </button>
  );
}

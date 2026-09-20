import React from "react";

export function Card({
  children,
  className = "",
  hover = false,
  variant = "default",
  ...props
}) {
  const variantStyles = {
    default: "bg-white border-slate-200/80 shadow-sm",
    elevated: "bg-white border-slate-200 shadow-md",
    glass: "bg-white/90 backdrop-blur-md border-slate-200 shadow-sm",
    employee: "bg-white border-slate-200/80 shadow-sm border-l-4 border-l-blue-500",
    manager: "bg-white border-slate-200/80 shadow-sm border-l-4 border-l-amber-500",
    admin: "bg-white border-slate-200/80 shadow-sm border-l-4 border-l-violet-500",
  };

  const hoverStyle = hover
    ? "transition-all duration-200 hover:border-slate-300 hover:shadow-md hover:-translate-y-0.5"
    : "";

  return (
    <div
      className={`rounded-xl border text-slate-900 ${variantStyles[variant] || variantStyles.default} ${hoverStyle} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className = "", ...props }) {
  return (
    <div className={`p-5 sm:p-6 border-b border-slate-100 ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({ children, className = "", ...props }) {
  return (
    <h3
      className={`text-lg sm:text-xl font-bold font-heading text-slate-900 tracking-tight flex items-center gap-2 ${className}`}
      {...props}
    >
      {children}
    </h3>
  );
}

export function CardDescription({ children, className = "", ...props }) {
  return (
    <p className={`text-sm text-slate-500 mt-1 leading-relaxed ${className}`} {...props}>
      {children}
    </p>
  );
}

export function CardContent({ children, className = "", ...props }) {
  return (
    <div className={`p-5 sm:p-6 ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardFooter({ children, className = "", ...props }) {
  return (
    <div
      className={`p-4 sm:p-6 bg-slate-50/70 border-t border-slate-100 rounded-b-xl flex items-center justify-between ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export default Card;

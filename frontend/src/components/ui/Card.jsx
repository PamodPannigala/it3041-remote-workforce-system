import React from "react";

export function Card({
  children,
  className = "",
  hover = false,
  variant = "default",
  ...props
}) {
  const variantStyles = {
    default: "bg-white border-slate-200/90 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-18px_rgba(15,23,42,0.22)]",
    elevated: "bg-white border-slate-200/90 shadow-[0_2px_5px_rgba(15,23,42,0.06),0_16px_36px_-22px_rgba(15,23,42,0.28)]",
    glass: "bg-white/90 backdrop-blur-md border-white/80 shadow-[0_1px_3px_rgba(15,23,42,0.05),0_12px_30px_-20px_rgba(37,99,235,0.22)]",
    employee: "bg-white border-slate-200/90 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_10px_26px_-20px_rgba(37,99,235,0.28)] border-l-4 border-l-blue-500",
    manager: "bg-white border-slate-200/90 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_10px_26px_-20px_rgba(245,158,11,0.25)] border-l-4 border-l-amber-500",
    admin: "bg-white border-slate-200/90 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_10px_26px_-20px_rgba(139,92,246,0.26)] border-l-4 border-l-violet-500",
  };

  const hoverStyle = hover
    ? "cursor-pointer transition-[transform,border-color,box-shadow] duration-200 hover:border-blue-300 hover:shadow-[0_4px_10px_rgba(15,23,42,0.08),0_18px_38px_-22px_rgba(37,99,235,0.28)] hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 motion-reduce:transform-none motion-reduce:transition-none"
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

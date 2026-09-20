import React from "react";

export function BrandIcon({ size = 28, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="brandGrad" x1="2" y1="2" x2="30" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3b82f6" />
          <stop offset="0.5" stopColor="#8b5cf6" />
          <stop offset="1" stopColor="#06b6d4" />
        </linearGradient>
        <linearGradient id="nodeGrad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#60a5fa" />
          <stop offset="1" stopColor="#a78bfa" />
        </linearGradient>
      </defs>

      {/* Hexagonal Outer Frame */}
      <path
        d="M16 3L27 9.5V22.5L16 29L5 22.5V9.5L16 3Z"
        stroke="url(#brandGrad)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="rgba(59, 130, 246, 0.08)"
      />

      {/* Network Connectors */}
      <line x1="16" y1="11" x2="10" y2="20" stroke="url(#nodeGrad)" strokeWidth="1.5" strokeDasharray="2 2" />
      <line x1="16" y1="11" x2="22" y2="20" stroke="url(#nodeGrad)" strokeWidth="1.5" strokeDasharray="2 2" />
      <line x1="10" y1="20" x2="22" y2="20" stroke="url(#nodeGrad)" strokeWidth="1.5" />

      {/* Central Leadership Node */}
      <circle cx="16" cy="11" r="3" fill="#38bdf8" />
      <circle cx="16" cy="11" r="1.2" fill="#0f172a" />

      {/* Distributed Worker Nodes */}
      <circle cx="10" cy="20" r="2.5" fill="#818cf8" />
      <circle cx="22" cy="20" r="2.5" fill="#c084fc" />
    </svg>
  );
}

export default function BrandLogo({ size = 28, showTag = true, subtitle = "System", dark = false }) {
  return (
    <div className="flex items-center gap-3">
      <BrandIcon size={size} />
      <div className="flex flex-col">
        <span className={`font-extrabold font-heading text-sm sm:text-base leading-tight tracking-tight ${dark ? "text-slate-100" : "text-slate-900"}`}>
          Remote Workforce
        </span>
        {subtitle && (
          <span className={`text-[10px] font-semibold tracking-wider uppercase ${dark ? "text-slate-400" : "text-slate-500"}`}>
            {subtitle}
          </span>
        )}
      </div>
      {showTag && (
        <span className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono font-medium rounded bg-blue-50 text-blue-600 border border-blue-200">
          v1.0
        </span>
      )}
    </div>
  );
}

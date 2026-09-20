import React from "react";
import { BrandIcon } from "./BrandLogo";

export default function AuthHero() {
  return (
    <div
      className="p-8 sm:p-12 lg:p-16 flex flex-col justify-between relative bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 border-r border-slate-800/80 overflow-hidden"
      aria-label="Product introduction"
    >
      {/* Ambient background mesh */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none overflow-hidden">
        <div className="absolute -top-24 -left-24 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 -right-24 w-96 h-96 bg-violet-500/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-24 left-1/3 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl" />
      </div>

      {/* Top Brand */}
      <div className="relative z-10 flex items-center gap-3">
        <BrandIcon size={36} />
        <span className="font-extrabold font-heading text-lg text-slate-100 tracking-tight">
          Remote Workforce System
        </span>
      </div>

      {/* Center Content */}
      <div className="relative z-10 my-10 space-y-6 max-w-xl">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-xs font-semibold text-blue-400">
          <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
          <span>Enterprise Workforce Platform</span>
        </div>

        <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold font-heading text-slate-100 tracking-tight leading-tight">
          Empower every team.<br />
          <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-cyan-400 bg-clip-text text-transparent">
            Wherever work happens.
          </span>
        </h1>

        <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
          A secure workforce intelligence platform for clearer collaboration, balanced workloads, and responsible team management.
        </p>

        {/* Abstract Connected Workforce Vector Graphic */}
        <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 shadow-2xl backdrop-blur-sm" aria-hidden="true">
          <svg viewBox="0 0 480 200" className="w-full h-auto" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="netGrad" x1="0" y1="0" x2="480" y2="200" gradientUnits="userSpaceOnUse">
                <stop stopColor="#3b82f6" stopOpacity="0.4" />
                <stop offset="0.5" stopColor="#8b5cf6" stopOpacity="0.3" />
                <stop offset="1" stopColor="#06b6d4" stopOpacity="0.4" />
              </linearGradient>
              <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#60a5fa" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
              </radialGradient>
            </defs>

            {/* Background Dot Pattern */}
            <pattern id="dotGrid" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
              <circle cx="2" cy="2" r="1" fill="#334155" fillOpacity="0.4" />
            </pattern>
            <rect width="480" height="200" fill="url(#dotGrid)" />

            {/* Flow curves */}
            <path d="M 80,100 Q 160,30 240,100 T 400,100" stroke="url(#netGrad)" strokeWidth="2" strokeDasharray="4 4" />
            <path d="M 120,150 C 180,80 300,140 360,60" stroke="url(#netGrad)" strokeWidth="1.5" />
            <path d="M 240,100 L 240,160" stroke="url(#netGrad)" strokeWidth="1.5" />
            <path d="M 160,50 L 320,150" stroke="url(#netGrad)" strokeWidth="1.5" strokeOpacity="0.4" />

            {/* Hub Nodes */}
            <g transform="translate(240, 100)">
              <circle cx="0" cy="0" r="24" fill="url(#nodeGlow)" />
              <circle cx="0" cy="0" r="10" fill="#0f172a" stroke="#38bdf8" strokeWidth="2" />
              <circle cx="0" cy="0" r="3.5" fill="#38bdf8" />
            </g>
            <g transform="translate(80, 100)">
              <circle cx="0" cy="0" r="16" fill="url(#nodeGlow)" />
              <circle cx="0" cy="0" r="8" fill="#0f172a" stroke="#818cf8" strokeWidth="2" />
              <circle cx="0" cy="0" r="2.5" fill="#818cf8" />
            </g>
            <g transform="translate(400, 100)">
              <circle cx="0" cy="0" r="16" fill="url(#nodeGlow)" />
              <circle cx="0" cy="0" r="8" fill="#0f172a" stroke="#c084fc" strokeWidth="2" />
              <circle cx="0" cy="0" r="2.5" fill="#c084fc" />
            </g>
            <g transform="translate(160, 50)">
              <circle cx="0" cy="0" r="6" fill="#0f172a" stroke="#34d399" strokeWidth="1.5" />
              <circle cx="0" cy="0" r="2" fill="#34d399" />
            </g>
            <g transform="translate(320, 150)">
              <circle cx="0" cy="0" r="6" fill="#0f172a" stroke="#fbbf24" strokeWidth="1.5" />
              <circle cx="0" cy="0" r="2" fill="#fbbf24" />
            </g>
          </svg>

          {/* Stat Badges Overlay */}
          <div className="mt-3 pt-3 border-t border-slate-800/80 grid grid-cols-3 gap-2 text-center">
            <div>
              <p className="text-[10px] uppercase font-bold text-slate-400">Security</p>
              <p className="text-xs font-semibold text-slate-200">Argon2id + JWT</p>
            </div>
            <div className="border-x border-slate-800">
              <p className="text-[10px] uppercase font-bold text-slate-400">Access</p>
              <p className="text-xs font-semibold text-slate-200">Strict RBAC</p>
            </div>
            <div>
              <p className="text-[10px] uppercase font-bold text-slate-400">Boundary</p>
              <p className="text-xs font-semibold text-slate-200">Team Scoped</p>
            </div>
          </div>
        </div>

        {/* Feature Highlights */}
        <div className="flex flex-wrap gap-2 pt-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs text-slate-300">
            <span>🛡️</span> Role-Governed Operations
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs text-slate-300">
            <span>📊</span> Workload & Capacity Profiles
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs text-slate-300">
            <span>⚡</span> Zero-Trust Architecture
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="relative z-10 text-xs text-slate-500">
        IT3041 Advanced Remote Workforce Management System
      </div>
    </div>
  );
}

import React from "react";

export default function AuthHero() {
  return (
    <section
      className="relative hidden overflow-hidden border-r border-white/10 bg-gradient-to-br from-slate-950/90 via-indigo-950/88 to-blue-950/90 p-8 text-slate-100 backdrop-blur-xl lg:flex lg:flex-col lg:justify-between xl:p-10"
      aria-label="Product introduction"
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/55 to-transparent" aria-hidden="true" />
      <div className="pointer-events-none absolute -left-20 -top-20 h-64 w-64 rounded-full bg-blue-400/20 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -bottom-20 -right-16 h-64 w-64 rounded-full bg-violet-400/20 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute left-1/3 top-1/3 h-40 w-40 rounded-full bg-cyan-300/10 blur-3xl" aria-hidden="true" />

      <div className="relative space-y-5">
        <span className="inline-flex rounded-full border border-blue-300/20 bg-blue-400/10 px-3 py-1 text-xs font-semibold text-blue-200">
          Secure workforce collaboration
        </span>
        <div className="space-y-3">
          <h1 className="max-w-md font-heading text-3xl font-extrabold leading-tight tracking-tight xl:text-4xl">
            Clearer teamwork, wherever work happens.
          </h1>
          <p className="max-w-md text-sm leading-relaxed text-slate-300">
            Coordinate teams, understand capacity, and support better workforce decisions in one focused workspace.
          </p>
        </div>
      </div>

      <div className="presentation-float-card relative mt-8" data-presentation-float="protected-access">
        <div className="flex items-center gap-3 rounded-xl border border-white/15 bg-white/[0.08] p-4 shadow-[0_16px_40px_-24px_rgba(56,189,248,0.55),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-md transition-[transform,border-color,box-shadow,background-color] duration-250 hover:-translate-y-0.5 hover:border-cyan-200/30 hover:bg-white/[0.1] hover:shadow-[0_20px_44px_-22px_rgba(56,189,248,0.65),inset_0_1px_0_rgba(255,255,255,0.12)] motion-reduce:transform-none motion-reduce:transition-none">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-400/10 text-emerald-300" aria-hidden="true">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </span>
          <div>
            <p className="text-sm font-semibold text-slate-100">Protected access</p>
            <p className="text-xs leading-relaxed text-slate-400">Role-aware sessions keep each workspace appropriately scoped.</p>
          </div>
        </div>
      </div>
    </section>
  );
}

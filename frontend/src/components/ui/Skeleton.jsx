import React from "react";

export function Skeleton({ className = "", ...props }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-slate-200/80 ${className}`}
      {...props}
    />
  );
}

export function SkeletonCard({ className = "" }) {
  return (
    <div className={`p-6 rounded-xl border border-slate-200 bg-white space-y-4 ${className}`}>
      <div className="flex items-center space-x-4">
        <Skeleton className="h-12 w-12 rounded-full" />
        <div className="space-y-2 flex-1">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
      <Skeleton className="h-20 w-full rounded-lg" />
      <div className="flex justify-between pt-2">
        <Skeleton className="h-8 w-24 rounded-lg" />
        <Skeleton className="h-8 w-24 rounded-lg" />
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 4, cols = 4, className = "" }) {
  return (
    <div className={`w-full rounded-xl border border-slate-200 bg-white p-4 space-y-4 ${className}`}>
      <div className="flex justify-between border-b border-slate-100 pb-3">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-4 w-20" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex justify-between items-center py-2 border-b border-slate-100">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-4 w-16" />
          ))}
        </div>
      ))}
    </div>
  );
}

export default Skeleton;

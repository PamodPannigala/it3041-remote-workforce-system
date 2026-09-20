import React from "react";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";

export function getAvailabilityBadge(status) {
  switch (status) {
    case "available":
      return <Badge variant="available" dot>Available</Badge>;
    case "busy":
      return <Badge variant="busy" dot>Busy</Badge>;
    case "on_leave":
      return <Badge variant="on_leave" dot>On Leave</Badge>;
    default:
      return <Badge variant="slate">{status || "Unknown"}</Badge>;
  }
}

export default function ProfileSummary({
  profile,
  onEdit,
  isReadOnly = false,
}) {
  if (!profile) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm space-y-5 text-slate-900">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
        <div>
          <h3 className="text-lg sm:text-xl font-bold font-heading text-slate-900">
            {profile.job_title || "No Title Specified"}
          </h3>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            {getAvailabilityBadge(profile.availability_status)}
            <span className="text-xs font-semibold text-slate-600">
              {profile.weekly_capacity_hours} hours per week
            </span>
          </div>
        </div>

        {!isReadOnly && onEdit && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onEdit}
          >
            Edit Profile
          </Button>
        )}
      </div>

      <div className="space-y-2">
        <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
          Skills & Competencies
        </span>
        {profile.skills && profile.skills.length > 0 ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {profile.skills.map((skill, index) => (
              <span
                key={`${skill}-${index}`}
                className="px-3 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200/80"
              >
                {skill}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-xs text-slate-400 italic">No skills listed yet.</span>
        )}
      </div>
    </div>
  );
}

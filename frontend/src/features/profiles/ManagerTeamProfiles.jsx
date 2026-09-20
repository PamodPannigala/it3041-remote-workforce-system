import React, { useEffect, useState } from "react";
import { getTeamProfiles } from "../../api/profiles";
import { getAvailabilityBadge } from "./ProfileSummary";
import Alert from "../../components/ui/Alert";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../components/ui/Card";

export default function ManagerTeamProfiles({
  managedTeams = [],
  token,
  onSessionExpired,
}) {
  const [selectedTeamId, setSelectedTeamId] = useState(
    managedTeams.length > 0 ? managedTeams[0].id : ""
  );
  const [teamProfilesData, setTeamProfilesData] = useState({
    items: [],
    page: 1,
    limit: 10,
    total: 0,
    total_pages: 1,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Update selected team if managedTeams changes and current selection is invalid
  useEffect(() => {
    if (managedTeams.length > 0 && !managedTeams.some((t) => t.id === selectedTeamId)) {
      setSelectedTeamId(managedTeams[0].id);
    }
  }, [managedTeams, selectedTeamId]);

  const loadProfiles = async (teamId, page = 1) => {
    if (!teamId || !token) return;
    setLoading(true);
    setError("");
    try {
      const data = await getTeamProfiles(token, teamId, page, 10);
      setTeamProfilesData(data || { items: [], page: 1, limit: 10, total: 0, total_pages: 1 });
    } catch (err) {
      if (err.status === 401 && onSessionExpired) {
        onSessionExpired();
      } else if (err.status === 403) {
        setError("Access denied: You do not have permission to view profiles for this team.");
      } else {
        setError(err.message || "Failed to load team work profiles.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedTeamId) {
      loadProfiles(selectedTeamId, 1);
    }
  }, [selectedTeamId, token]);

  if (!managedTeams || managedTeams.length === 0) {
    return (
      <Card id="manager-team-profiles-section">
        <CardHeader>
          <CardTitle>Team Work Profiles</CardTitle>
          <CardDescription>
            Work profiles, skills, and capacities of your team members.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No Managed Teams Assigned"
            description="You have not been assigned as manager to any team yet."
          />
        </CardContent>
      </Card>
    );
  }

  const activeTeam = managedTeams.find((t) => t.id === selectedTeamId) || managedTeams[0];
  const members = activeTeam?.members || [];

  // Build combined map of profiles by user_id
  const profilesByUserId = new Map();
  (teamProfilesData.items || []).forEach((p) => {
    if (p.user_id) {
      profilesByUserId.set(p.user_id, p);
    }
  });

  return (
    <Card id="manager-team-profiles-section" className="overflow-hidden">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <CardTitle>Team Work Profiles</CardTitle>
          <CardDescription>
            Read-only visibility into team member competencies, capacity, and current availability.
          </CardDescription>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {managedTeams.length > 1 && (
            <div className="relative">
              <select
                className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 pr-8"
                value={selectedTeamId}
                onChange={(e) => setSelectedTeamId(e.target.value)}
                aria-label="Select Team"
              >
                {managedTeams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => loadProfiles(selectedTeamId, teamProfilesData.page)}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "Refresh Profiles"}
          </Button>
        </div>
      </CardHeader>

      {error && (
        <div className="p-4 border-b border-slate-100">
          <Alert variant="error">
            {error}
          </Alert>
        </div>
      )}

      <CardContent className="p-0">
        {members.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No Team Members"
              description="This team does not currently have any active members assigned."
            />
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-800">
                <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200">
                  <tr>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Team Member</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Job Title</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Availability</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Capacity</th>
                    <th scope="col" className="py-3.5 px-4 sm:px-6">Skills & Expertise</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {members.map((member) => {
                    const profile = profilesByUserId.get(member.id);
                    const hasProfile = Boolean(profile);

                    return (
                      <tr key={member.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3.5 px-4 sm:px-6">
                          <div className="font-semibold text-slate-900">
                            {member.name}
                          </div>
                          <div className="text-xs text-slate-500">
                            {member.email}
                          </div>
                        </td>

                        <td className="py-3.5 px-4 sm:px-6">
                          {hasProfile && profile.job_title ? (
                            <span className="font-medium text-slate-800">{profile.job_title}</span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>

                        <td className="py-3.5 px-4 sm:px-6">
                          {hasProfile ? (
                            getAvailabilityBadge(profile.availability_status)
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                              Profile not completed
                            </span>
                          )}
                        </td>

                        <td className="py-3.5 px-4 sm:px-6">
                          {hasProfile && profile.weekly_capacity_hours !== undefined ? (
                            <span className="font-medium text-slate-700">{profile.weekly_capacity_hours} hrs/wk</span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>

                        <td className="py-3.5 px-4 sm:px-6">
                          {hasProfile && profile.skills && profile.skills.length > 0 ? (
                            <div className="flex flex-wrap gap-1.5 max-w-xs">
                              {profile.skills.map((skill, idx) => (
                                <span
                                  key={`${skill}-${idx}`}
                                  className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-50 text-blue-700 border border-blue-200/80"
                                >
                                  {skill}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-xs text-slate-400">
                              {hasProfile ? "No skills listed" : "—"}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {teamProfilesData.total_pages > 1 && (
              <div className="p-4 bg-slate-50/80 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
                <span>Total Profiles: {teamProfilesData.total}</span>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => loadProfiles(selectedTeamId, teamProfilesData.page - 1)}
                    disabled={teamProfilesData.page <= 1 || loading}
                  >
                    Previous
                  </Button>
                  <span className="px-2">
                    Page {teamProfilesData.page} of {teamProfilesData.total_pages}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => loadProfiles(selectedTeamId, teamProfilesData.page + 1)}
                    disabled={teamProfilesData.page >= teamProfilesData.total_pages || loading}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

import React, { useEffect, useState } from "react";
import { useAuth } from "../features/auth/AuthContext";
import {
  assignTeamMember,
  createTeam,
  getAdminTeams,
  getAdminUsers,
  getManagedTeams,
  getMyTeamSummary,
  reassignTeamManager,
  removeTeamMember,
  updateUserRole,
  updateUserStatus,
} from "../features/teams/teamsApi";
import { getMyProfile, updateMyProfile } from "../features/profiles/profilesApi";
import EmployeeProfileForm from "../features/profiles/components/EmployeeProfileForm";
import ProfileSummary from "../features/profiles/components/ProfileSummary";
import ManagerTeamProfiles from "../features/profiles/components/ManagerTeamProfiles";
import EmployeeTasks from "../features/tasks/components/EmployeeTasks";
import ManagerTaskBoard from "../features/tasks/components/ManagerTaskBoard";
import AdminTaskAudit from "../features/tasks/components/AdminTaskAudit";

import AppShell from "../layouts/AppShell";
import PageHeader from "../layouts/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Alert from "../components/ui/Alert";
import EmptyState from "../components/ui/EmptyState";
import { SkeletonCard, SkeletonTable } from "../components/ui/Skeleton";

export default function Dashboard() {
  const { user, token, handleSessionExpired, logout } = useAuth();

  // Navigation Tab View State
  const [activeTab, setActiveTab] = useState("overview");

  // Admin User Directory State
  const [usersList, setUsersList] = useState([]);
  const [userPagination, setUserPagination] = useState({ page: 1, limit: 10, total: 0, total_pages: 1 });
  const [usersLoading, setUsersLoading] = useState(false);
  const [userActionError, setUserActionError] = useState("");
  const [userActionSuccess, setUserActionSuccess] = useState("");

  // Admin Teams State
  const [adminTeams, setAdminTeams] = useState([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");
  const [newTeamManagerId, setNewTeamManagerId] = useState("");
  const [teamActionError, setTeamActionError] = useState("");
  const [teamActionSuccess, setTeamActionSuccess] = useState("");
  const [selectedMemberPerTeam, setSelectedMemberPerTeam] = useState({});

  // Manager State
  const [managedTeams, setManagedTeams] = useState([]);
  const [managedLoading, setManagedLoading] = useState(false);
  const [managedError, setManagedError] = useState("");

  // Employee State
  const [employeeTeamSummary, setEmployeeTeamSummary] = useState(null);
  const [employeeTeamLoading, setEmployeeTeamLoading] = useState(false);
  const [employeeTeamError, setEmployeeTeamError] = useState("");

  // Work Profile State (Employee & Manager)
  const [myProfile, setMyProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileSuccess, setProfileSuccess] = useState("");
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileSubmitting, setProfileSubmitting] = useState(false);
  const [profileFormError, setProfileFormError] = useState("");

  // Load Admin Data
  const loadAdminUsers = async (page = 1) => {
    if (user?.role !== "admin") return;
    setUsersLoading(true);
    setUserActionError("");
    try {
      const data = await getAdminUsers(token, page, 10);
      setUsersList(data.items || []);
      setUserPagination({
        page: data.page,
        limit: data.limit,
        total: data.total,
        total_pages: data.total_pages,
      });
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setUserActionError(err.message || "Failed to load user directory.");
      }
    } finally {
      setUsersLoading(false);
    }
  };

  const loadAdminTeams = async () => {
    if (user?.role !== "admin") return;
    setTeamsLoading(true);
    setTeamActionError("");
    try {
      const data = await getAdminTeams(token);
      setAdminTeams(data || []);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to load teams.");
      }
    } finally {
      setTeamsLoading(false);
    }
  };

  // Load Manager Data
  const loadManagerTeams = async () => {
    if (user?.role !== "manager") return;
    setManagedLoading(true);
    setManagedError("");
    try {
      const data = await getManagedTeams(token);
      setManagedTeams(data || []);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setManagedError(err.message || "Failed to load managed teams.");
      }
    } finally {
      setManagedLoading(false);
    }
  };

  // Load Employee Data
  const loadEmployeeTeam = async () => {
    if (user?.role !== "employee") return;
    setEmployeeTeamLoading(true);
    setEmployeeTeamError("");
    try {
      const data = await getMyTeamSummary(token);
      setEmployeeTeamSummary(data);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setEmployeeTeamError(err.message || "Failed to load team summary.");
      }
    } finally {
      setEmployeeTeamLoading(false);
    }
  };

  // Load My Profile Data (Employee / Manager)
  const loadMyProfile = async () => {
    if (!user || user.role === "admin") return;
    setProfileLoading(true);
    setProfileError("");
    try {
      const profileData = await getMyProfile(token);
      setMyProfile(profileData);
      setIsEditingProfile(false);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else if (err.status === 404) {
        setMyProfile(null);
        setIsEditingProfile(false);
      } else {
        setProfileError(err.message || "Failed to load work profile.");
      }
    } finally {
      setProfileLoading(false);
    }
  };

  // Profile Form Submission
  const handleProfileSubmit = async (formData) => {
    setProfileSubmitting(true);
    setProfileFormError("");
    setProfileSuccess("");
    try {
      const savedProfile = await updateMyProfile(token, formData);
      setMyProfile(savedProfile);
      setIsEditingProfile(false);
      setProfileSuccess("Work profile saved successfully.");
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setProfileFormError(err.message || "Failed to save work profile.");
      }
    } finally {
      setProfileSubmitting(false);
    }
  };

  useEffect(() => {
    if (!token || !user) return;
    setIsEditingProfile(false);
    setActiveTab("overview");

    if (user.role === "admin") {
      loadAdminUsers(1);
      loadAdminTeams();
    } else if (user.role === "manager") {
      loadManagerTeams();
      loadMyProfile();
    } else if (user.role === "employee") {
      loadEmployeeTeam();
      loadMyProfile();
    }
  }, [token, user?.role]);

  // Admin Actions
  const handleRoleChange = async (targetUserId, newRole) => {
    setUserActionError("");
    setUserActionSuccess("");
    try {
      await updateUserRole(token, targetUserId, newRole);
      setUserActionSuccess("User role updated successfully.");
      loadAdminUsers(userPagination.page);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setUserActionError(err.message || "Failed to update user role.");
      }
    }
  };

  const handleStatusToggle = async (targetUserId, currentIsActive) => {
    setUserActionError("");
    setUserActionSuccess("");
    const newStatus = !currentIsActive;
    try {
      await updateUserStatus(token, targetUserId, newStatus);
      setUserActionSuccess(`User ${newStatus ? "activated" : "deactivated"} successfully.`);
      loadAdminUsers(userPagination.page);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setUserActionError(err.message || "Failed to update user status.");
      }
    }
  };

  const handleCreateTeam = async (e) => {
    e.preventDefault();
    setTeamActionError("");
    setTeamActionSuccess("");

    if (!newTeamName.trim()) {
      setTeamActionError("Team name is required.");
      return;
    }
    if (!newTeamManagerId) {
      setTeamActionError("Please select a manager.");
      return;
    }

    try {
      await createTeam(token, {
        name: newTeamName.trim(),
        manager_id: newTeamManagerId,
      });
      setTeamActionSuccess("Team created successfully.");
      setNewTeamName("");
      setNewTeamManagerId("");
      loadAdminTeams();
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to create team.");
      }
    }
  };

  const handleReassignManager = async (teamId, newManagerId) => {
    setTeamActionError("");
    setTeamActionSuccess("");
    try {
      await reassignTeamManager(token, teamId, newManagerId);
      setTeamActionSuccess("Team manager reassigned successfully.");
      loadAdminTeams();
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to reassign team manager.");
      }
    }
  };

  const handleAssignMember = async (teamId) => {
    const memberId = selectedMemberPerTeam[teamId];
    if (!memberId) return;

    setTeamActionError("");
    setTeamActionSuccess("");
    try {
      await assignTeamMember(token, teamId, memberId);
      setTeamActionSuccess("Team member assigned successfully.");
      setSelectedMemberPerTeam((prev) => ({ ...prev, [teamId]: "" }));
      loadAdminTeams();
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to assign team member.");
      }
    }
  };

  const handleRemoveMember = async (teamId, memberId) => {
    setTeamActionError("");
    setTeamActionSuccess("");
    try {
      await removeTeamMember(token, teamId, memberId);
      setTeamActionSuccess("Team member removed successfully.");
      loadAdminTeams();
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to remove team member.");
      }
    }
  };

  // Helper getters
  const activeManagers = usersList.filter((u) => u.role === "manager" && u.is_active);
  const activeEmployees = usersList.filter((u) => u.role === "employee" && u.is_active);

  // Tab Title Resolution
  const getTabTitle = () => {
    const titles = {
      overview: "Overview",
      "my-team": "My Team",
      "work-profile": "Work Profile",
      "my-tasks": "My Tasks",
      "managed-teams": "Managed Teams",
      "team-profiles": "Team Profiles",
      "team-tasks": "Team Tasks",
      users: "User Directory",
      teams: "Team Management",
      "task-audit": "Task Audit",
    };
    return titles[activeTab] || "Overview";
  };

  // ==========================================
  // EMPLOYEE VIEW RENDER
  // ==========================================
  const renderEmployeeDashboard = () => {
    const showOverview = activeTab === "overview";
    const showTeam = activeTab === "overview" || activeTab === "my-team";
    const showProfile = activeTab === "overview" || activeTab === "work-profile";

    return (
      <div className="space-y-6">
        {/* Hero Banner */}
        <PageHeader
          title="Workspace Dashboard"
          description={
            employeeTeamSummary?.team_name
              ? `Assigned to ${employeeTeamSummary.team_name}. Review your workload, update capabilities, and coordinate with your team.`
              : "Review your workload, update your work profile, and stay connected with your distributed team."
          }
          role="employee"
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                loadEmployeeTeam();
                loadMyProfile();
              }}
            >
              Refresh Overview
            </Button>
          }
        />

        {/* Overview Concise Metrics */}
        {showOverview && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Team Status</span>
                <p className="text-sm font-bold text-slate-900 truncate">
                  {employeeTeamSummary?.has_team && employeeTeamSummary?.team_name ? employeeTeamSummary.team_name : "Unassigned"}
                </p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Profile Status</span>
                <p className="text-sm font-bold text-slate-900 capitalize truncate">
                  {myProfile ? myProfile.availability_status.replace("_", " ") : "Incomplete"}
                </p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-violet-50 border border-violet-100 flex items-center justify-center text-violet-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Weekly Capacity</span>
                <p className="text-sm font-bold text-slate-900 truncate">
                  {myProfile && myProfile.weekly_capacity_hours !== undefined ? `${myProfile.weekly_capacity_hours} hrs/wk` : "0 hrs/wk"}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Work Profile Section */}
        {showProfile && (
          <Card id="my-profile-section" variant="employee">
            <CardHeader>
              <CardTitle>Employee Work Profile</CardTitle>
              <CardDescription>
                Your professional skills, capacity, and current availability status.
              </CardDescription>
            </CardHeader>

            <CardContent>
              {profileSuccess && (
                <Alert variant="success" className="mb-4" onDismiss={() => setProfileSuccess("")}>
                  {profileSuccess}
                </Alert>
              )}

              {profileError && (
                <Alert variant="error" className="mb-4">
                  {profileError}
                </Alert>
              )}

              {profileLoading ? (
                <SkeletonCard />
              ) : isEditingProfile ? (
                <EmployeeProfileForm
                  initialData={myProfile}
                  onSubmit={handleProfileSubmit}
                  onCancel={myProfile ? () => setIsEditingProfile(false) : null}
                  isSubmitting={profileSubmitting}
                  serverError={profileFormError}
                />
              ) : myProfile ? (
                <ProfileSummary
                  profile={myProfile}
                  onEdit={() => setIsEditingProfile(true)}
                />
              ) : (
                <EmptyState
                  title="No Work Profile Created Yet"
                  description="You have not created your work profile yet. Provide your job title, competencies, and weekly hours to help balance tasks."
                  action={
                    <Button
                      variant="primary"
                      onClick={() => setIsEditingProfile(true)}
                    >
                      Create Work Profile
                    </Button>
                  }
                />
              )}
            </CardContent>
          </Card>
        )}

        {/* Assigned Team Section */}
        {showTeam && (
          <Card id="employee-team-summary-section">
            <CardHeader>
              <CardTitle>My Assigned Team</CardTitle>
              <CardDescription>
                Details of your assigned workforce team and collaborating members.
              </CardDescription>
            </CardHeader>

            <CardContent>
              {employeeTeamError && (
                <Alert variant="error" className="mb-4">
                  {employeeTeamError}
                </Alert>
              )}

              {employeeTeamLoading ? (
                <SkeletonCard />
              ) : employeeTeamSummary && employeeTeamSummary.has_team && employeeTeamSummary.team_name ? (
                <div className="space-y-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl bg-slate-50 border border-slate-200/80">
                    <div>
                      <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Team Name</span>
                      <h4 className="text-lg font-bold text-slate-900">{employeeTeamSummary.team_name}</h4>
                    </div>
                    {employeeTeamSummary.manager && (
                      <div>
                        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Manager</span>
                        <p className="text-sm font-semibold text-slate-700">
                          {employeeTeamSummary.manager.name} ({employeeTeamSummary.manager.email})
                        </p>
                      </div>
                    )}
                  </div>

                  <div>
                    <h5 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
                      Team Members ({employeeTeamSummary.members?.length || 0})
                    </h5>
                    {employeeTeamSummary.members && employeeTeamSummary.members.length > 0 ? (
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {employeeTeamSummary.members.map((member) => (
                          <div
                            key={member.id}
                            className="p-3 rounded-lg bg-white border border-slate-200/80 shadow-sm flex items-center gap-3"
                          >
                            <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 text-xs font-bold text-slate-700 flex items-center justify-center shrink-0">
                              {member.name.charAt(0).toUpperCase()}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="text-xs font-semibold text-slate-900 truncate">{member.name}</p>
                              <p className="text-[11px] text-slate-500 truncate">{member.email}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500 italic">No other members currently assigned.</p>
                    )}
                  </div>
                </div>
              ) : (
                <EmptyState
                  title="No Team Assigned"
                  description="You are not currently assigned to any team. An administrator will assign you shortly."
                />
              )}
            </CardContent>
          </Card>
        )}

        {/* My Tasks Section */}
        {activeTab === "my-tasks" && (
          <EmployeeTasks token={token} onSessionExpired={handleSessionExpired} />
        )}
      </div>
    );
  };

  // ==========================================
  // MANAGER VIEW RENDER
  // ==========================================
  const renderManagerDashboard = () => {
    const showOverview = activeTab === "overview";
    const showTeams = activeTab === "overview" || activeTab === "managed-teams";
    const showProfile = activeTab === "overview" || activeTab === "work-profile";
    const showTeamProfiles = activeTab === "overview" || activeTab === "team-profiles";

    const totalMembersCount = managedTeams.reduce(
      (acc, t) => acc + (t.members ? t.members.length : 0),
      0
    );

    return (
      <div className="space-y-6">
        {/* Hero Banner */}
        <PageHeader
          title="Workspace Dashboard"
          description={`Managing ${managedTeams.length} active ${managedTeams.length === 1 ? "team" : "teams"} with ${totalMembersCount} total team ${totalMembersCount === 1 ? "member" : "members"}.`}
          role="manager"
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                loadManagerTeams();
                loadMyProfile();
              }}
            >
              Refresh Workspace
            </Button>
          }
        />

        {/* Overview Concise Metrics */}
        {showOverview && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Managed Teams</span>
                <p className="text-sm font-bold text-slate-900 truncate">
                  {managedTeams.length} {managedTeams.length === 1 ? "Team" : "Teams"}
                </p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Managed Members</span>
                <p className="text-sm font-bold text-slate-900 truncate">
                  {totalMembersCount} {totalMembersCount === 1 ? "Member" : "Members"}
                </p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Manager Availability</span>
                <p className="text-sm font-bold text-slate-900 capitalize truncate">
                  {myProfile ? myProfile.availability_status.replace("_", " ") : "Incomplete"}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Manager Work Profile */}
        {showProfile && (
          <Card id="my-profile-section" variant="manager">
            <CardHeader>
              <CardTitle>Manager Work Profile</CardTitle>
              <CardDescription>
                Your own profile, skills, and weekly capacity.
              </CardDescription>
            </CardHeader>

            <CardContent>
              {profileSuccess && (
                <Alert variant="success" className="mb-4" onDismiss={() => setProfileSuccess("")}>
                  {profileSuccess}
                </Alert>
              )}

              {profileError && (
                <Alert variant="error" className="mb-4">
                  {profileError}
                </Alert>
              )}

              {profileLoading ? (
                <SkeletonCard />
              ) : isEditingProfile ? (
                <EmployeeProfileForm
                  initialData={myProfile}
                  onSubmit={handleProfileSubmit}
                  onCancel={myProfile ? () => setIsEditingProfile(false) : null}
                  isSubmitting={profileSubmitting}
                  serverError={profileFormError}
                />
              ) : myProfile ? (
                <ProfileSummary
                  profile={myProfile}
                  onEdit={() => setIsEditingProfile(true)}
                />
              ) : (
                <EmptyState
                  title="No Profile Created"
                  description="You have not created your work profile yet. Create one to specify your domain expertise."
                  action={
                    <Button
                      variant="primary"
                      onClick={() => setIsEditingProfile(true)}
                    >
                      Create Work Profile
                    </Button>
                  }
                />
              )}
            </CardContent>
          </Card>
        )}

        {/* Managed Teams Section */}
        {showTeams && (
          <Card id="manager-teams-section">
            <CardHeader>
              <CardTitle>Your Managed Teams</CardTitle>
              <CardDescription>
                View members assigned to your managed teams.
              </CardDescription>
            </CardHeader>

            <CardContent>
              {managedError && (
                <Alert variant="error" className="mb-4">
                  {managedError}
                </Alert>
              )}

              {managedLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-4">
                  <SkeletonCard />
                  <SkeletonCard />
                </div>
              ) : managedTeams.length === 0 ? (
                <EmptyState
                  title="No Managed Teams Assigned"
                  description="You are not currently assigned as manager to any team. Contact an administrator for team delegation."
                />
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-4">
                  {managedTeams.map((team) => {
                    const memberCount = team.members?.length || 0;
                    return (
                      <div
                        key={team.id}
                        className="p-5 rounded-xl bg-slate-50 border border-slate-200/80 flex flex-col justify-between shadow-sm"
                      >
                        <div>
                          <div className="flex items-center justify-between pb-3 border-b border-slate-200">
                            <h4 className="text-base font-bold text-slate-900 font-heading">{team.name}</h4>
                            <Badge variant="manager" size="sm">
                              {memberCount} {memberCount === 1 ? "member" : "members"}
                            </Badge>
                          </div>

                          <div className="mt-4 space-y-2">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                              Team Roster
                            </span>
                            {team.members && team.members.length > 0 ? (
                              <ul className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                                {team.members.map((m) => (
                                  <li
                                    key={m.id}
                                    className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-200/60 text-xs shadow-xs"
                                  >
                                    <span className="font-medium text-slate-800">{m.name}</span>
                                    <span className="text-slate-500">{m.email}</span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-xs text-slate-500 italic">No members assigned yet.</p>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Team Work Profiles Table */}
        {showTeamProfiles && (
          <ManagerTeamProfiles
            managedTeams={managedTeams}
            token={token}
            onSessionExpired={handleSessionExpired}
          />
        )}

        {/* Team Tasks Section */}
        {activeTab === "team-tasks" && (
          <ManagerTaskBoard
            managedTeams={managedTeams}
            token={token}
            onSessionExpired={handleSessionExpired}
          />
        )}
      </div>
    );
  };

  // ==========================================
  // ADMIN VIEW RENDER
  // ==========================================
  const renderAdminDashboard = () => {
    const showOverview = activeTab === "overview";
    const showUsers = activeTab === "overview" || activeTab === "users";
    const showTeams = activeTab === "overview" || activeTab === "teams";

    return (
      <div className="space-y-6">
        {/* Hero Banner */}
        <PageHeader
          title="Workspace Dashboard"
          description={`Governing ${userPagination.total || usersList.length} ${userPagination.total === 1 ? "user" : "users"} across ${adminTeams.length} organization ${adminTeams.length === 1 ? "team" : "teams"} with strict RBAC enforcement.`}
          role="admin"
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                loadAdminUsers(userPagination.page);
                loadAdminTeams();
              }}
            >
              Refresh Governance
            </Button>
          }
        />

        {/* Overview Concise Metrics */}
        {showOverview && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-violet-50 border border-violet-100 flex items-center justify-center text-violet-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Total Users</span>
                <p className="text-sm font-bold text-slate-900 truncate">
                  {userPagination.total || usersList.length} {userPagination.total === 1 ? "User" : "Users"}
                </p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Active Teams</span>
                <p className="text-sm font-bold text-slate-900 truncate">
                  {adminTeams.length} {adminTeams.length === 1 ? "Team" : "Teams"}
                </p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center gap-3 hover:border-slate-300 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Active Managers</span>
                <p className="text-sm font-bold text-slate-900 truncate">
                  {activeManagers.length} {activeManagers.length === 1 ? "Manager" : "Managers"}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* User Management Directory */}
        {showUsers && (
          <Card id="user-management-section">
            <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <CardTitle>User Access Management</CardTitle>
                <CardDescription>
                  Manage user accounts, roles (employee, manager, admin), and system access status.
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadAdminUsers(userPagination.page)}
                disabled={usersLoading}
              >
                {usersLoading ? "Refreshing..." : "Refresh Users"}
              </Button>
            </CardHeader>

            <CardContent className="p-0">
              {userActionSuccess && (
                <div className="p-4 border-b border-slate-200">
                  <Alert variant="success" onDismiss={() => setUserActionSuccess("")}>
                    {userActionSuccess}
                  </Alert>
                </div>
              )}

              {userActionError && (
                <div className="p-4 border-b border-slate-200">
                  <Alert variant="error" onDismiss={() => setUserActionError("")}>
                    {userActionError}
                  </Alert>
                </div>
              )}

              {usersLoading ? (
                <div className="p-4">
                  <SkeletonTable rows={5} cols={5} />
                </div>
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm text-slate-700">
                      <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200">
                        <tr>
                          <th scope="col" className="py-3.5 px-4 sm:px-6">Name</th>
                          <th scope="col" className="py-3.5 px-4 sm:px-6">Email</th>
                          <th scope="col" className="py-3.5 px-4 sm:px-6">Role</th>
                          <th scope="col" className="py-3.5 px-4 sm:px-6">Status</th>
                          <th scope="col" className="py-3.5 px-4 sm:px-6">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {usersList.map((u) => {
                          const isSelf = u.id === user?.id;
                          return (
                            <tr key={u.id} className="hover:bg-slate-50/80 transition-colors">
                              <td className="py-3.5 px-4 sm:px-6 font-semibold text-slate-900">
                                {u.name} {isSelf && <span className="text-xs text-blue-600 font-normal">(You)</span>}
                              </td>
                              <td className="py-3.5 px-4 sm:px-6 text-slate-500">{u.email}</td>
                              <td className="py-3.5 px-4 sm:px-6">
                                <select
                                  value={u.role}
                                  onChange={(e) => handleRoleChange(u.id, e.target.value)}
                                  disabled={isSelf}
                                  className="px-2.5 py-1 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50"
                                  aria-label={`Change role for ${u.name}`}
                                >
                                  <option value="employee">Employee</option>
                                  <option value="manager">Manager</option>
                                  <option value="admin">Admin</option>
                                </select>
                              </td>
                              <td className="py-3.5 px-4 sm:px-6">
                                <Badge variant={u.is_active ? "active" : "inactive"} dot>
                                  {u.is_active ? "Active" : "Inactive"}
                                </Badge>
                              </td>
                              <td className="py-3.5 px-4 sm:px-6">
                                <Button
                                  variant={u.is_active ? "dangerOutline" : "secondary"}
                                  size="sm"
                                  onClick={() => handleStatusToggle(u.id, u.is_active)}
                                  disabled={isSelf}
                                >
                                  {u.is_active ? "Deactivate" : "Activate"}
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {userPagination.total_pages > 1 && (
                    <div className="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
                      <span>Total Registered Users: {userPagination.total}</span>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => loadAdminUsers(userPagination.page - 1)}
                          disabled={userPagination.page <= 1 || usersLoading}
                        >
                          Previous
                        </Button>
                        <span className="px-2">
                          Page {userPagination.page} of {userPagination.total_pages}
                        </span>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => loadAdminUsers(userPagination.page + 1)}
                          disabled={userPagination.page >= userPagination.total_pages || usersLoading}
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
        )}

        {/* Team Management */}
        {showTeams && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
            {/* Create Team Form (Sticky Sidebar on Desktop) */}
            <Card id="admin-create-team-form" className="lg:col-span-1 lg:sticky lg:top-24 self-start">
              <CardHeader>
                <CardTitle>Create Team</CardTitle>
                <CardDescription>
                  Define a new team and assign an active manager.
                </CardDescription>
              </CardHeader>

              <CardContent>
                <form onSubmit={handleCreateTeam} className="space-y-4">
                  <div className="space-y-1.5">
                    <label htmlFor="team-name-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                      Team Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      id="team-name-input"
                      type="text"
                      placeholder="e.g., Core Engineering"
                      value={newTeamName}
                      onChange={(e) => setNewTeamName(e.target.value)}
                      required
                      className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label htmlFor="team-manager-select" className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                      Team Manager <span className="text-rose-500">*</span>
                    </label>
                    <select
                      id="team-manager-select"
                      value={newTeamManagerId}
                      onChange={(e) => setNewTeamManagerId(e.target.value)}
                      required
                      className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors"
                    >
                      <option value="">Select an active manager...</option>
                      {activeManagers.map((mgr) => (
                        <option key={mgr.id} value={mgr.id}>
                          {mgr.name} ({mgr.email})
                        </option>
                      ))}
                    </select>
                  </div>

                  <Button
                    id="create-team-submit-btn"
                    type="submit"
                    variant="primary"
                    className="w-full"
                  >
                    Create Team
                  </Button>
                </form>
              </CardContent>
            </Card>

            {/* Admin Team Structure */}
            <Card id="admin-teams-section" className="lg:col-span-2">
              <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <CardTitle>Team Structure & Membership</CardTitle>
                  <CardDescription>
                    Reassign team managers and allocate active employees to teams.
                  </CardDescription>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadAdminTeams}
                  disabled={teamsLoading}
                >
                  {teamsLoading ? "Refreshing..." : "Refresh Teams"}
                </Button>
              </CardHeader>

              <CardContent className="space-y-4">
                {teamActionSuccess && (
                  <Alert variant="success" onDismiss={() => setTeamActionSuccess("")}>
                    {teamActionSuccess}
                  </Alert>
                )}

                {teamActionError && (
                  <Alert variant="error" onDismiss={() => setTeamActionError("")}>
                    {teamActionError}
                  </Alert>
                )}

                {teamsLoading ? (
                  <div className="space-y-4">
                    <SkeletonCard />
                    <SkeletonCard />
                  </div>
                ) : adminTeams.length === 0 ? (
                  <EmptyState
                    title="No Teams Established"
                    description="Create your first organization team using the form on the left."
                  />
                ) : (
                  <div className="space-y-4">
                    {adminTeams.map((team) => {
                      const memberCount = team.members?.length || 0;
                      return (
                        <div
                          key={team.id}
                          className="p-5 rounded-xl bg-slate-50 border border-slate-200/80 space-y-4 shadow-sm"
                        >
                          {/* Team Header */}
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200">
                            <div>
                              <h4 className="text-base font-bold text-slate-900 font-heading">{team.name}</h4>
                              <span className="text-xs text-slate-500">
                                {memberCount} {memberCount === 1 ? "member" : "members"}
                              </span>
                            </div>

                            {/* Manager Reassignment Dropdown */}
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-slate-500">Manager:</span>
                              <select
                                value={team.manager_id || ""}
                                onChange={(e) => handleReassignManager(team.id, e.target.value)}
                                className="px-2.5 py-1 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                                aria-label="Reassign Team Manager"
                              >
                                {activeManagers.map((mgr) => (
                                  <option key={mgr.id} value={mgr.id}>
                                    {mgr.name}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </div>

                          {/* Members Roster */}
                          <div className="space-y-2">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                              Team Members
                            </span>
                            {team.members && team.members.length > 0 ? (
                              <ul className="space-y-1.5">
                                {team.members.map((m) => (
                                  <li
                                    key={m.id}
                                    className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-200/80 text-xs shadow-xs"
                                  >
                                    <div>
                                      <span className="font-semibold text-slate-800">{m.name}</span>
                                      <span className="text-slate-500 ml-2">({m.email})</span>
                                    </div>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 text-xs"
                                      onClick={() => handleRemoveMember(team.id, m.id)}
                                    >
                                      Remove
                                    </Button>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-xs text-slate-500 italic">No members currently in this team.</p>
                            )}
                          </div>

                          {/* Assign Employee Row */}
                          <div className="pt-3 border-t border-slate-200 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                            <select
                              value={selectedMemberPerTeam[team.id] || ""}
                              onChange={(e) =>
                                setSelectedMemberPerTeam((prev) => ({
                                  ...prev,
                                  [team.id]: e.target.value,
                                }))
                              }
                              className="flex-1 min-w-0 px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                              aria-label="Select employee to assign"
                            >
                              <option value="">Assign employee to team...</option>
                              {activeEmployees
                                .filter((emp) => !team.members?.some((m) => m.id === emp.id))
                                .map((emp) => (
                                  <option key={emp.id} value={emp.id}>
                                    {emp.name} ({emp.email})
                                  </option>
                                ))}
                            </select>
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => handleAssignMember(team.id)}
                              disabled={!selectedMemberPerTeam[team.id]}
                            >
                              Add
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Task Audit Section */}
        {activeTab === "task-audit" && (
          <AdminTaskAudit
            adminTeams={adminTeams}
            token={token}
            onSessionExpired={handleSessionExpired}
          />
        )}
      </div>
    );
  };

  return (
    <AppShell
      user={user}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      activeTabTitle={getTabTitle()}
      onLogout={logout}
    >
      {user?.role === "admin" && renderAdminDashboard()}
      {user?.role === "manager" && renderManagerDashboard()}
      {user?.role === "employee" && renderEmployeeDashboard()}
    </AppShell>
  );
}

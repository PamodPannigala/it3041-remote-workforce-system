import React, { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
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
} from "../api/teams";

export default function Dashboard() {
  const { user, token, handleSessionExpired } = useAuth();

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

  useEffect(() => {
    if (!token || !user) return;
    if (user.role === "admin") {
      loadAdminUsers(1);
      loadAdminTeams();
    } else if (user.role === "manager") {
      loadManagerTeams();
    } else if (user.role === "employee") {
      loadEmployeeTeam();
    }
  }, [user?.role, token]);

  // Handle Role Change
  const handleRoleChange = async (userId, newRole) => {
    setUserActionError("");
    setUserActionSuccess("");
    try {
      await updateUserRole(token, userId, newRole);
      setUserActionSuccess(`User role updated to '${newRole}'.`);
      await loadAdminUsers(userPagination.page);
      await loadAdminTeams();
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setUserActionError(err.message || "Failed to update role.");
      }
    }
  };

  // Handle Status Toggle
  const handleStatusToggle = async (userId, currentStatus) => {
    setUserActionError("");
    setUserActionSuccess("");
    try {
      await updateUserStatus(token, userId, !currentStatus);
      setUserActionSuccess(`User account ${!currentStatus ? "activated" : "deactivated"} successfully.`);
      await loadAdminUsers(userPagination.page);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setUserActionError(err.message || "Failed to update user status.");
      }
    }
  };

  // Handle Create Team
  const handleCreateTeam = async (e) => {
    e.preventDefault();
    if (!newTeamName.trim() || !newTeamManagerId) {
      setTeamActionError("Please provide both team name and an assigned manager.");
      return;
    }
    setTeamActionError("");
    setTeamActionSuccess("");
    try {
      await createTeam(token, newTeamName.trim(), newTeamManagerId);
      setTeamActionSuccess(`Team '${newTeamName.trim()}' created successfully.`);
      setNewTeamName("");
      setNewTeamManagerId("");
      await loadAdminTeams();
      await loadAdminUsers(userPagination.page);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to create team.");
      }
    }
  };

  // Handle Reassign Manager
  const handleReassignManager = async (teamId, newManagerId) => {
    setTeamActionError("");
    setTeamActionSuccess("");
    try {
      await reassignTeamManager(token, teamId, newManagerId);
      setTeamActionSuccess("Team manager reassigned successfully.");
      await loadAdminTeams();
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to reassign team manager.");
      }
    }
  };

  // Handle Member Assignment
  const handleAssignMember = async (teamId) => {
    const selectedUserId = selectedMemberPerTeam[teamId];
    if (!selectedUserId) {
      setTeamActionError("Please select an employee to assign.");
      return;
    }
    setTeamActionError("");
    setTeamActionSuccess("");
    try {
      await assignTeamMember(token, teamId, selectedUserId);
      setTeamActionSuccess("Employee assigned to team successfully.");
      setSelectedMemberPerTeam((prev) => ({ ...prev, [teamId]: "" }));
      await loadAdminTeams();
      await loadAdminUsers(userPagination.page);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to assign member.");
      }
    }
  };

  // Handle Member Removal
  const handleRemoveMember = async (teamId, userId) => {
    setTeamActionError("");
    setTeamActionSuccess("");
    try {
      await removeTeamMember(token, teamId, userId);
      setTeamActionSuccess("Member removed from team.");
      await loadAdminTeams();
      await loadAdminUsers(userPagination.page);
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else {
        setTeamActionError(err.message || "Failed to remove member.");
      }
    }
  };

  const activeManagers = usersList.filter((u) => u.role === "manager" && u.is_active);
  const activeEmployees = usersList.filter((u) => u.role === "employee" && u.is_active);

  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <h1>Workspace Dashboard</h1>
        <p>Remote workforce management and team workspace</p>
      </div>

      {/* User Profile Card */}
      <div className="profile-card" id="profile-card">
        <div className="profile-field">
          <span className="profile-label">Full Name</span>
          <span className="profile-value" id="profile-name">{user?.name}</span>
        </div>
        <div className="profile-field">
          <span className="profile-label">Email Address</span>
          <span className="profile-value" id="profile-email">{user?.email}</span>
        </div>
        <div className="profile-field">
          <span className="profile-label">Assigned Role</span>
          <span className={`role-pill role-${user?.role}`} id="profile-role">
            {user?.role}
          </span>
        </div>
        <div className="profile-field">
          <span className="profile-label">Account Status</span>
          <span className="profile-value" style={{ color: "#34d399" }}>
            Active
          </span>
        </div>
      </div>

      {/* ================= ADMIN SECTION ================= */}
      {user?.role === "admin" && (
        <>
          {/* User Management */}
          <div className="management-section" id="admin-user-management">
            <div className="management-header">
              <div>
                <h2 className="management-title">User Access Management</h2>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                  Manage user roles and account status across the organization.
                </p>
              </div>
              <button
                className="btn btn-outline"
                onClick={() => loadAdminUsers(userPagination.page)}
                disabled={usersLoading}
                type="button"
              >
                {usersLoading ? "Refreshing..." : "Refresh Users"}
              </button>
            </div>

            {userActionError && (
              <div className="alert alert-error" role="alert">
                <span>⛔</span>
                <span>{userActionError}</span>
              </div>
            )}
            {userActionSuccess && (
              <div className="alert alert-success" role="alert">
                <span>✓</span>
                <span>{userActionSuccess}</span>
              </div>
            )}

            <div className="data-table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Team</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {usersList.length === 0 ? (
                    <tr>
                      <td colSpan="6" style={{ textAlign: "center", padding: "2rem" }}>
                        {usersLoading ? "Loading users..." : "No users found."}
                      </td>
                    </tr>
                  ) : (
                    usersList.map((u) => {
                      const isSelf = u.id === user.id;
                      return (
                        <tr key={u.id}>
                          <td style={{ fontWeight: 600 }}>{u.name} {isSelf && <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>(You)</span>}</td>
                          <td>{u.email}</td>
                          <td>
                            <select
                              className="select-input"
                              value={u.role}
                              onChange={(e) => handleRoleChange(u.id, e.target.value)}
                              disabled={isSelf || usersLoading}
                              aria-label={`Role for ${u.name}`}
                            >
                              <option value="employee">Employee</option>
                              <option value="manager">Manager</option>
                              <option value="admin">Admin</option>
                            </select>
                          </td>
                          <td>
                            <span className={`status-badge ${u.is_active ? "status-active" : "status-inactive"}`}>
                              {u.is_active ? "Active" : "Inactive"}
                            </span>
                          </td>
                          <td>{u.team_name || "—"}</td>
                          <td>
                            <button
                              type="button"
                              className={`action-btn-sm ${u.is_active ? "btn-toggle-active" : "btn-toggle-inactive"}`}
                              onClick={() => handleStatusToggle(u.id, u.is_active)}
                              disabled={isSelf || usersLoading}
                            >
                              {u.is_active ? "Deactivate" : "Activate"}
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="pagination-bar">
              <span>Total: {userPagination.total} users</span>
              <div className="pagination-controls">
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => loadAdminUsers(userPagination.page - 1)}
                  disabled={userPagination.page <= 1 || usersLoading}
                >
                  Previous
                </button>
                <span style={{ display: "flex", alignItems: "center", padding: "0 0.5rem" }}>
                  Page {userPagination.page} of {userPagination.total_pages}
                </span>
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => loadAdminUsers(userPagination.page + 1)}
                  disabled={userPagination.page >= userPagination.total_pages || usersLoading}
                >
                  Next
                </button>
              </div>
            </div>
          </div>

          {/* Teams and Membership Management */}
          <div className="management-section" id="admin-team-management">
            <div className="management-header">
              <div>
                <h2 className="management-title">Team Structure & Membership</h2>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                  Create organizational teams, assign managers, and manage team members.
                </p>
              </div>
              <button
                className="btn btn-outline"
                onClick={loadAdminTeams}
                disabled={teamsLoading}
                type="button"
              >
                {teamsLoading ? "Refreshing..." : "Refresh Teams"}
              </button>
            </div>

            {teamActionError && (
              <div className="alert alert-error" role="alert">
                <span>⛔</span>
                <span>{teamActionError}</span>
              </div>
            )}
            {teamActionSuccess && (
              <div className="alert alert-success" role="alert">
                <span>✓</span>
                <span>{teamActionSuccess}</span>
              </div>
            )}

            {/* Create Team Form */}
            <div className="team-form-card">
              <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>Create New Team</h3>
              <form onSubmit={handleCreateTeam} className="team-form-grid">
                <div>
                  <label className="form-label" htmlFor="new-team-name">Team Name</label>
                  <input
                    id="new-team-name"
                    type="text"
                    className="form-input"
                    placeholder="e.g., Engineering Alpha"
                    value={newTeamName}
                    onChange={(e) => setNewTeamName(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="form-label" htmlFor="new-team-manager">Assigned Manager</label>
                  <select
                    id="new-team-manager"
                    className="form-input select-input"
                    value={newTeamManagerId}
                    onChange={(e) => setNewTeamManagerId(e.target.value)}
                    required
                  >
                    <option value="">Select an active manager...</option>
                    {activeManagers.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.email})
                      </option>
                    ))}
                  </select>
                </div>
                <button type="submit" className="btn btn-primary" style={{ marginTop: 0 }}>
                  Create Team
                </button>
              </form>
            </div>

            {/* Teams Grid */}
            <div className="teams-grid">
              {adminTeams.length === 0 ? (
                <div className="empty-state" style={{ gridColumn: "1 / -1" }}>
                  <strong>No teams configured yet</strong>
                  <p>Create your first team above by assigning an active manager.</p>
                </div>
              ) : (
                adminTeams.map((team) => (
                  <div key={team.id} className="team-card">
                    <div>
                      <div className="team-card-header">
                        <span className="team-card-title">{team.name}</span>
                        <span className="role-pill role-manager" style={{ fontSize: "0.7rem" }}>
                          {team.members.length} {team.members.length === 1 ? "member" : "members"}
                        </span>
                      </div>
                      <div className="team-manager-info">
                        <div>Manager: <span className="team-manager-name">{team.manager_name || "Unassigned"}</span> ({team.manager_email})</div>
                        <div style={{ marginTop: "0.4rem", display: "flex", gap: "0.4rem", alignItems: "center" }}>
                          <span style={{ fontSize: "0.75rem" }}>Reassign:</span>
                          <select
                            className="select-input"
                            style={{ fontSize: "0.75rem", padding: "0.2rem 0.4rem" }}
                            value={team.manager_id}
                            onChange={(e) => handleReassignManager(team.id, e.target.value)}
                          >
                            {activeManagers.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.name}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)", marginTop: "0.75rem" }}>
                        Team Members:
                      </div>
                      {team.members.length === 0 ? (
                        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontStyle: "italic", margin: "0.4rem 0" }}>
                          No employees assigned yet.
                        </p>
                      ) : (
                        <ul className="team-members-list">
                          {team.members.map((member) => (
                            <li key={member.id} className="team-member-item">
                              <span>{member.name} ({member.email})</span>
                              <button
                                type="button"
                                className="btn-remove-sm"
                                onClick={() => handleRemoveMember(team.id, member.id)}
                                title="Remove employee from team"
                              >
                                ✕ Remove
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    {/* Member Assignment Control */}
                    <div style={{ marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-color)", display: "flex", gap: "0.4rem" }}>
                      <select
                        className="select-input"
                        style={{ flex: 1, fontSize: "0.8rem" }}
                        value={selectedMemberPerTeam[team.id] || ""}
                        onChange={(e) =>
                          setSelectedMemberPerTeam((prev) => ({
                            ...prev,
                            [team.id]: e.target.value,
                          }))
                        }
                      >
                        <option value="">Assign employee...</option>
                        {activeEmployees.map((emp) => (
                          <option key={emp.id} value={emp.id}>
                            {emp.name} ({emp.email})
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ padding: "0.3rem 0.6rem", fontSize: "0.8rem" }}
                        onClick={() => handleAssignMember(team.id)}
                      >
                        Add
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}

      {/* ================= MANAGER SECTION ================= */}
      {user?.role === "manager" && (
        <div className="management-section" id="manager-teams-view">
          <div className="management-header">
            <div>
              <h2 className="management-title">Your Managed Teams</h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                View and manage members assigned to your team.
              </p>
            </div>
            <button
              className="btn btn-outline"
              onClick={loadManagerTeams}
              disabled={managedLoading}
              type="button"
            >
              {managedLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>

          {managedError && (
            <div className="alert alert-error" role="alert">
              <span>⛔</span>
              <span>{managedError}</span>
            </div>
          )}

          {managedTeams.length === 0 ? (
            <div className="empty-state">
              <strong>No Managed Teams Assigned</strong>
              <p>You have not been assigned as manager to any team yet. Contact your workspace administrator.</p>
            </div>
          ) : (
            <div className="teams-grid">
              {managedTeams.map((team) => (
                <div key={team.id} className="team-card">
                  <div className="team-card-header">
                    <span className="team-card-title">{team.name}</span>
                    <span className="role-pill role-manager" style={{ fontSize: "0.75rem" }}>
                      {team.members.length} {team.members.length === 1 ? "member" : "members"}
                    </span>
                  </div>

                  <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
                    Assigned Team Members:
                  </div>

                  {team.members.length === 0 ? (
                    <div className="empty-state" style={{ padding: "1.5rem 1rem" }}>
                      <p style={{ fontSize: "0.85rem" }}>No employees assigned to this team yet.</p>
                    </div>
                  ) : (
                    <ul className="team-members-list">
                      {team.members.map((member) => (
                        <li key={member.id} className="team-member-item">
                          <div>
                            <span style={{ fontWeight: 600 }}>{member.name}</span>
                            <span style={{ display: "block", fontSize: "0.75rem", color: "var(--text-muted)" }}>{member.email}</span>
                          </div>
                          <span className={`status-badge ${member.is_active ? "status-active" : "status-inactive"}`}>
                            {member.is_active ? "Active" : "Inactive"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ================= EMPLOYEE SECTION ================= */}
      {user?.role === "employee" && (
        <div className="management-section" id="employee-team-view">
          <div className="management-header">
            <div>
              <h2 className="management-title">My Assigned Team</h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                Your assigned workspace team and manager details.
              </p>
            </div>
          </div>

          {employeeTeamError && (
            <div className="alert alert-error" role="alert">
              <span>⛔</span>
              <span>{employeeTeamError}</span>
            </div>
          )}

          {employeeTeamLoading ? (
            <div style={{ textAlign: "center", padding: "2rem" }}>Loading team summary...</div>
          ) : employeeTeamSummary && employeeTeamSummary.has_team ? (
            <div className="profile-card" style={{ marginBottom: 0 }}>
              <div className="profile-field">
                <span className="profile-label">Team Name</span>
                <span className="profile-value" style={{ color: "var(--accent-primary)" }}>
                  {employeeTeamSummary.team_name}
                </span>
              </div>
              <div className="profile-field">
                <span className="profile-label">Reporting Manager</span>
                <span className="profile-value">{employeeTeamSummary.manager_name || "Unassigned"}</span>
              </div>
              <div className="profile-field">
                <span className="profile-label">Manager Contact</span>
                <span className="profile-value" style={{ fontSize: "0.95rem" }}>
                  {employeeTeamSummary.manager_email || "—"}
                </span>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <strong>No Team Assigned</strong>
              <p>You are not currently assigned to any team. Contact your workspace administrator for team assignment.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { checkAdminAccess, checkManagementAccess } from "../api/auth";

const SPECIALIST_AGENTS = [
  {
    id: "productivity",
    title: "Productivity Agent",
    description:
      "Analyzes focus patterns, task completion metrics, and output efficiency with privacy safeguards.",
    branch: "feature/productivity-agent",
  },
  {
    id: "collaboration",
    title: "Collaboration Agent",
    description:
      "Evaluates team communication balance, cross-functional interactions, and synchronous load.",
    branch: "feature/collaboration-agent",
  },
  {
    id: "wellbeing",
    title: "Wellbeing Agent",
    description:
      "Monitors workload fatigue indicators, boundary maintenance, and sustainable work habits.",
    branch: "feature/wellbeing-agent",
  },
  {
    id: "task-assignment",
    title: "Task Assignment Agent",
    description:
      "Provides responsible, evidence-based recommendations requiring human manager approval.",
    branch: "feature/task-assignment-agent",
  },
];

export default function Dashboard() {
  const { user, token, handleSessionExpired } = useAuth();
  const [checkLoading, setCheckLoading] = useState(false);
  const [checkResult, setCheckResult] = useState(null);

  const testEndpoint = async (type) => {
    setCheckLoading(true);
    setCheckResult(null);
    try {
      if (type === "admin") {
        const res = await checkAdminAccess(token);
        setCheckResult({
          success: true,
          message: `Admin access confirmed (Endpoint: /admin/access-check -> ${res.access})`,
        });
      } else if (type === "management") {
        const res = await checkManagementAccess(token);
        setCheckResult({
          success: true,
          message: `Management access confirmed (Endpoint: /management/access-check -> ${res.access})`,
        });
      }
    } catch (err) {
      if (err.status === 401) {
        handleSessionExpired();
      } else if (err.status === 403) {
        setCheckResult({
          success: false,
          message: `Access Denied (HTTP 403): Your role '${user.role}' is not authorized for this route.`,
        });
      } else {
        setCheckResult({
          success: false,
          message: err.message || "Request failed.",
        });
      }
    } finally {
      setCheckLoading(false);
    }
  };

  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <h1>Workspace Dashboard</h1>
        <p>Authenticated identity verified via backend /auth/me endpoint</p>
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
            Active (In-Memory Session)
          </span>
        </div>
      </div>

      {/* Backend Role Guard Verification Sandbox */}
      <div className="guard-sandbox">
        <h2>Backend Role Guard Verification</h2>
        <p>
          Test your current JWT credentials against protected backend endpoints.
          Employees are restricted from admin and management endpoints.
        </p>

        <div className="guard-buttons">
          <button
            id="test-management-btn"
            className="btn btn-secondary"
            onClick={() => testEndpoint("management")}
            disabled={checkLoading}
            type="button"
          >
            Test Management Access (/management/access-check)
          </button>
          <button
            id="test-admin-btn"
            className="btn btn-secondary"
            onClick={() => testEndpoint("admin")}
            disabled={checkLoading}
            type="button"
          >
            Test Admin Access (/admin/access-check)
          </button>
        </div>

        {checkResult && (
          <div
            id="guard-result-alert"
            className={`guard-result alert ${
              checkResult.success ? "alert-success" : "alert-error"
            }`}
          >
            <span>{checkResult.success ? "✓" : "⛔"}</span>
            <span>{checkResult.message}</span>
          </div>
        )}
      </div>

      {/* Specialist Agents Section */}
      <div className="specialist-section">
        <h2 className="section-title">Specialist AI Agents</h2>
        <p className="section-subtitle">
          Specialist modules will be developed on their designated feature branches. No synthetic or simulated results are displayed.
        </p>

        <div className="agents-grid">
          {SPECIALIST_AGENTS.map((agent) => (
            <div key={agent.id} className="agent-card">
              <div>
                <div className="agent-card-header">
                  <span className="agent-card-title">{agent.title}</span>
                  <span className="agent-status-badge">Not implemented</span>
                </div>
                <p className="agent-card-desc">{agent.description}</p>
              </div>
              <div className="agent-card-branch">{agent.branch}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

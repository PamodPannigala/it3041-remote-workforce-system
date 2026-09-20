import React from "react";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <header className="navbar">
      <div className="nav-brand">
        <span className="nav-title">Remote Workforce System</span>
        <span className="nav-tag">v0.1.0</span>
      </div>

      <div className="nav-actions">
        {isAuthenticated && user && (
          <>
            <div className="user-badge">
              <span className="user-name">{user.name}</span>
              <span className={`role-pill role-${user.role}`}>{user.role}</span>
            </div>
            <button
              id="logout-btn"
              className="btn btn-outline"
              onClick={logout}
              type="button"
            >
              Sign Out
            </button>
          </>
        )}
      </div>
    </header>
  );
}

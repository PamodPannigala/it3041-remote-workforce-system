import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";

export default function LoginForm({ onSwitchToRegister, successMessage }) {
  const { login, loading, error: authError, setError: setAuthError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError("");
    setAuthError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setLocalError("Email address is required.");
      return;
    }
    if (!password) {
      setLocalError("Password is required.");
      return;
    }

    try {
      await login(trimmedEmail, password);
    } catch {
      // Error is set in AuthContext
    }
  };

  const displayError = localError || authError;

  return (
    <div className="auth-card">
      <div className="auth-header">
        <h1>Welcome Back</h1>
        <p>Sign in to your remote workforce account</p>
      </div>

      {successMessage && (
        <div className="alert alert-success" id="success-alert" role="status">
          <span>✓</span>
          <span>{successMessage}</span>
        </div>
      )}

      {displayError && (
        <div className="alert alert-error" id="error-alert" role="alert">
          <span>⚠️</span>
          <span>{displayError}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="form-group">
          <label className="form-label" htmlFor="login-email">
            Email Address
          </label>
          <input
            id="login-email"
            type="email"
            className="form-input"
            placeholder="name@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            autoComplete="email"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="login-password">
            Password
          </label>
          <input
            id="login-password"
            type="password"
            className="form-input"
            placeholder="••••••••••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            autoComplete="current-password"
            required
          />
        </div>

        <button
          id="login-submit-btn"
          type="submit"
          className="btn btn-primary"
          disabled={loading}
        >
          {loading ? (
            <>
              <span className="spinner"></span>
              Authenticating...
            </>
          ) : (
            "Sign In"
          )}
        </button>
      </form>

      <div className="auth-switch">
        <span>Don't have an account?</span>
        <button
          id="switch-to-register-btn"
          type="button"
          onClick={onSwitchToRegister}
          disabled={loading}
        >
          Create an account
        </button>
      </div>
    </div>
  );
}

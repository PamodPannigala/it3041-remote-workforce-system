import React, { useState } from "react";
import { registerUser } from "../api/auth";

export default function RegisterForm({ onSwitchToLogin, onRegistrationSuccess }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    const trimmedName = name.trim();
    const trimmedEmail = email.trim();

    if (!trimmedName || trimmedName.length < 2) {
      setError("Name must be at least 2 characters long.");
      return;
    }
    if (!trimmedEmail) {
      setError("Valid email address is required.");
      return;
    }
    if (password.length < 15) {
      setError("Password must be at least 15 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await registerUser({
        name: trimmedName,
        email: trimmedEmail,
        password: password,
      });
      onRegistrationSuccess("Registration successful! Please sign in with your credentials.");
    } catch (err) {
      setError(err.message || "Failed to register account.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-card">
      <div className="auth-header">
        <h1>Create Account</h1>
        <p>Register as a new team member</p>
      </div>

      {error && (
        <div className="alert alert-error" id="register-error-alert" role="alert">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="form-group">
          <label className="form-label" htmlFor="register-name">
            Full Name
          </label>
          <input
            id="register-name"
            type="text"
            className="form-input"
            placeholder="Jane Doe"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            autoComplete="name"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="register-email">
            Email Address
          </label>
          <input
            id="register-email"
            type="email"
            className="form-input"
            placeholder="jane.doe@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            autoComplete="email"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="register-password">
            Password
          </label>
          <input
            id="register-password"
            type="password"
            className="form-input"
            placeholder="At least 15 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            autoComplete="new-password"
            required
          />
          <span className="input-hint">Must contain at least 15 characters.</span>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="register-confirm-password">
            Confirm Password
          </label>
          <input
            id="register-confirm-password"
            type="password"
            className="form-input"
            placeholder="Repeat your password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            disabled={loading}
            autoComplete="new-password"
            required
          />
        </div>

        <button
          id="register-submit-btn"
          type="submit"
          className="btn btn-primary"
          disabled={loading}
        >
          {loading ? (
            <>
              <span className="spinner"></span>
              Creating Account...
            </>
          ) : (
            "Create Account"
          )}
        </button>
      </form>

      <div className="auth-switch">
        <span>Already have an account?</span>
        <button
          id="switch-to-login-btn"
          type="button"
          onClick={onSwitchToLogin}
          disabled={loading}
        >
          Sign in
        </button>
      </div>
    </div>
  );
}

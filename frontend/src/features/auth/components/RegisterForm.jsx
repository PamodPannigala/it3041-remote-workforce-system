import React, { useState } from "react";
import { registerUser } from "../authApi";
import Alert from "../../../components/ui/Alert";
import Button from "../../../components/ui/Button";

export default function RegisterForm({ onSwitchToLogin, onRegistrationSuccess }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <div className="w-full max-w-xl mx-auto space-y-4">
      {/* Header */}
      <div className="space-y-1.5 text-center sm:text-left">
        <h1 className="text-2xl font-extrabold font-heading text-slate-900 tracking-tight">
          Create Account
        </h1>
        <p className="text-sm text-slate-500">
          Register as a new team member
        </p>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="error" id="register-error-alert">
          {error}
        </Alert>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} noValidate className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
        {/* Full Name */}
        <div className="space-y-1.5">
          <label
            htmlFor="register-name"
            className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
          >
            Full Name
          </label>
          <input
            id="register-name"
            type="text"
            placeholder="Jane Doe"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            autoComplete="name"
            required
            className="w-full px-3.5 py-2.5 bg-white/90 border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-sm shadow-sm hover:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-blue-500/15 focus:border-blue-600 focus:shadow-[0_8px_20px_-14px_rgba(37,99,235,0.65)] transition-[border-color,box-shadow,background-color] duration-200 disabled:opacity-50"
          />
        </div>

        {/* Email Address */}
        <div className="space-y-1.5">
          <label
            htmlFor="register-email"
            className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
          >
            Email Address
          </label>
          <input
            id="register-email"
            type="email"
            placeholder="jane.doe@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            autoComplete="email"
            required
            className="w-full px-3.5 py-2.5 bg-white/90 border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-sm shadow-sm hover:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-blue-500/15 focus:border-blue-600 focus:shadow-[0_8px_20px_-14px_rgba(37,99,235,0.65)] transition-[border-color,box-shadow,background-color] duration-200 disabled:opacity-50"
          />
        </div>

        {/* Password */}
        <div className="space-y-1.5">
          <label
            htmlFor="register-password"
            className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
          >
            Password
          </label>
          <div className="relative">
            <input
              id="register-password"
              type={showPassword ? "text" : "password"}
              placeholder="At least 15 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoComplete="new-password"
              required
              className="w-full px-3.5 py-2.5 pr-11 bg-white/90 border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-sm shadow-sm hover:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-blue-500/15 focus:border-blue-600 focus:shadow-[0_8px_20px_-14px_rgba(37,99,235,0.65)] transition-[border-color,box-shadow,background-color] duration-200 disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              tabIndex={-1}
              className="absolute inset-y-1 right-1 flex items-center rounded-md px-2 text-slate-400 transition-colors duration-200 hover:bg-indigo-50 hover:text-indigo-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1"
            >
              {showPassword ? (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
          <p className="text-xs text-slate-500">Must contain at least 15 characters.</p>
        </div>

        {/* Confirm Password */}
        <div className="space-y-1.5">
          <label
            htmlFor="register-confirm-password"
            className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
          >
            Confirm Password
          </label>
          <div className="relative">
            <input
              id="register-confirm-password"
              type={showPassword ? "text" : "password"}
              placeholder="Repeat your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={loading}
              autoComplete="new-password"
              required
              className="w-full px-3.5 py-2.5 bg-white/90 border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-sm shadow-sm hover:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-blue-500/15 focus:border-blue-600 focus:shadow-[0_8px_20px_-14px_rgba(37,99,235,0.65)] transition-[border-color,box-shadow,background-color] duration-200 disabled:opacity-50"
            />
          </div>
        </div>

        {/* Submit */}
        <Button
          id="register-submit-btn"
          type="submit"
          variant="primary"
          size="lg"
          loading={loading}
          className="auth-primary-button w-full sm:col-span-2"
        >
          {loading ? "Creating Account..." : "Create Account"}
        </Button>
      </form>

      {/* Switch to Login */}
      <div className="pt-3 border-t border-slate-200/70 text-center text-sm text-slate-500">
        <span>Already have an account? </span>
        <button
          id="switch-to-login-btn"
          type="button"
          onClick={onSwitchToLogin}
          disabled={loading}
          className="ml-1 rounded-sm font-semibold text-blue-600 underline decoration-transparent underline-offset-4 transition-[color,text-decoration-color] duration-200 hover:text-indigo-700 hover:decoration-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
        >
          Sign in
        </button>
      </div>
    </div>
  );
}

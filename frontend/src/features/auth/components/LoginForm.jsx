import React, { useState } from "react";
import { useAuth } from "../AuthContext";
import Alert from "../../../components/ui/Alert";
import Button from "../../../components/ui/Button";

export default function LoginForm({ onSwitchToRegister, successMessage }) {
  const { login, loading, error: authError, setError: setAuthError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <div className="w-full max-w-md mx-auto space-y-6">
      {/* Header */}
      <div className="space-y-1.5 text-center sm:text-left">
        <h1 className="text-2xl sm:text-3xl font-extrabold font-heading text-slate-900 tracking-tight">
          Welcome Back
        </h1>
        <p className="text-sm text-slate-500">
          Sign in to your remote workforce account
        </p>
      </div>

      {/* Success Banner */}
      {successMessage && (
        <Alert variant="success" id="success-alert" role="status">
          {successMessage}
        </Alert>
      )}

      {/* Error Alert */}
      {displayError && (
        <Alert variant="error" id="error-alert">
          {displayError}
        </Alert>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {/* Email */}
        <div className="space-y-1.5">
          <label
            htmlFor="login-email"
            className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
          >
            Email Address
          </label>
          <div className="relative">
            <input
              id="login-email"
              type="email"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              autoComplete="email"
              required
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-colors disabled:opacity-50"
            />
          </div>
        </div>

        {/* Password */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label
              htmlFor="login-password"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
            >
              Password
            </label>
          </div>
          <div className="relative">
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              placeholder="••••••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoComplete="current-password"
              required
              className="w-full px-3.5 py-2.5 pr-10 bg-white border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-colors disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              tabIndex={-1}
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600"
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
        </div>

        {/* Submit */}
        <Button
          id="login-submit-btn"
          type="submit"
          variant="primary"
          size="lg"
          loading={loading}
          className="w-full mt-2"
        >
          {loading ? "Authenticating..." : "Sign In"}
        </Button>
      </form>

      {/* Switch to Register */}
      <div className="pt-4 border-t border-slate-100 text-center text-sm text-slate-500">
        <span>Don't have an account? </span>
        <button
          id="switch-to-register-btn"
          type="button"
          onClick={onSwitchToRegister}
          disabled={loading}
          className="font-semibold text-blue-600 hover:text-blue-700 hover:underline ml-1"
        >
          Create an account
        </button>
      </div>
    </div>
  );
}

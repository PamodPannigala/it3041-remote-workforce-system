import React, { useState } from "react";
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import Navbar from "./features/auth/components/Navbar";
import AuthHero from "./features/auth/components/AuthHero";
import LoginForm from "./features/auth/components/LoginForm";
import RegisterForm from "./features/auth/components/RegisterForm";
import Dashboard from "./pages/Dashboard";

function AppContent() {
  const { isAuthenticated, initialLoading } = useAuth();
  const [view, setView] = useState("login"); // "login" | "register"
  const [successMessage, setSuccessMessage] = useState("");

  const handleSwitchToRegister = () => {
    setSuccessMessage("");
    setView("register");
  };

  const handleSwitchToLogin = () => {
    setView("login");
  };

  const handleRegistrationSuccess = (message) => {
    setSuccessMessage(message);
    setView("login");
  };

  if (initialLoading) {
    return (
      <div className="min-h-screen bg-[#F6F8FC] text-slate-900 flex flex-col justify-between font-sans">
        <Navbar />
        <main className="flex-1 flex items-center justify-center p-6">
          <div className="flex flex-col items-center gap-4 p-8 rounded-2xl border border-slate-200 bg-white shadow-xl">
            <svg
              className="animate-spin h-8 w-8 text-blue-600"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <p className="text-sm font-medium text-slate-600">Verifying secure session...</p>
          </div>
        </main>
        <footer className="py-4 px-6 border-t border-slate-200/80 text-center text-xs text-slate-500 bg-white/80">
          <p>IT3041 Remote Workforce System</p>
        </footer>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Dashboard />;
  }

  return (
    <div className="relative isolate min-h-screen overflow-x-hidden bg-gradient-to-br from-blue-50/90 via-indigo-50/75 to-cyan-50/85 text-slate-900 flex flex-col justify-between font-sans">
      <div
        className="pointer-events-none absolute inset-0 overflow-hidden"
        aria-hidden="true"
        data-auth-decoration="gradient-orbs"
      >
        <span
          className="auth-orb auth-orb-one absolute -left-28 top-20 h-80 w-80 rounded-full bg-gradient-to-br from-blue-300/35 to-cyan-300/25 blur-3xl"
          aria-hidden="true"
          data-auth-orb="blue-cyan"
        />
        <span
          className="auth-orb auth-orb-two absolute -right-32 top-10 h-96 w-96 rounded-full bg-gradient-to-br from-violet-300/30 to-indigo-300/25 blur-3xl"
          aria-hidden="true"
          data-auth-orb="violet-indigo"
        />
        <span
          className="auth-orb auth-orb-three absolute bottom-0 left-[42%] h-72 w-72 rounded-full bg-gradient-to-br from-cyan-200/30 to-blue-300/20 blur-3xl"
          aria-hidden="true"
          data-auth-orb="cyan-blue"
        />
      </div>
      <Navbar />

      <main className="relative z-10 flex-1 flex items-center justify-center p-3 sm:p-4 lg:p-5">
        <div className="w-full max-w-4xl overflow-hidden rounded-2xl border border-white/80 bg-white/55 shadow-[0_32px_80px_-32px_rgba(30,41,59,0.38),0_14px_36px_-24px_rgba(79,70,229,0.28)] ring-1 ring-white/40 backdrop-blur-2xl transition-shadow duration-300 hover:shadow-[0_36px_90px_-34px_rgba(30,41,59,0.42),0_18px_44px_-26px_rgba(79,70,229,0.32)] motion-reduce:transition-none grid grid-cols-1 lg:grid-cols-[0.9fr_1.1fr]">
          {/* Left: Product Hero */}
          <AuthHero />

          {/* Right: Authentication Card */}
          <div className="flex flex-col justify-center border-white/60 bg-white/78 p-5 shadow-[inset_1px_0_0_rgba(255,255,255,0.6)] backdrop-blur-xl sm:p-6 lg:border-l lg:p-8">
            {view === "login" ? (
              <LoginForm
                onSwitchToRegister={handleSwitchToRegister}
                successMessage={successMessage}
              />
            ) : (
              <RegisterForm
                onSwitchToLogin={handleSwitchToLogin}
                onRegistrationSuccess={handleRegistrationSuccess}
              />
            )}
          </div>
        </div>
      </main>

      <footer className="relative z-10 py-2 px-6 border-t border-white/70 text-center text-xs text-slate-500 bg-white/60 backdrop-blur-md">
        <p>IT3041 Remote Workforce System</p>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

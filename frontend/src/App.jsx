import React, { useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Navbar from "./components/Navbar";
import AuthHero from "./components/AuthHero";
import LoginForm from "./components/LoginForm";
import RegisterForm from "./components/RegisterForm";
import Dashboard from "./components/Dashboard";

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
    <div className="min-h-screen bg-[#F6F8FC] text-slate-900 flex flex-col justify-between font-sans">
      <Navbar />

      <main className="flex-1 flex items-center justify-center p-4 sm:p-6 lg:p-10">
        <div className="w-full max-w-5xl rounded-2xl border border-slate-200/80 bg-white shadow-2xl overflow-hidden grid grid-cols-1 lg:grid-cols-2">
          {/* Left: Product Hero */}
          <AuthHero />

          {/* Right: Authentication Card */}
          <div className="p-6 sm:p-10 lg:p-12 flex flex-col justify-center bg-white">
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

      <footer className="py-4 px-6 border-t border-slate-200/80 text-center text-xs text-slate-500 bg-white/80">
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

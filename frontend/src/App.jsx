import React, { useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Navbar from "./components/Navbar";
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
      <div className="app-container">
        <Navbar />
        <main className="main-content">
          <div style={{ textAlign: "center", padding: "3rem" }}>
            <div className="spinner" style={{ width: "2rem", height: "2rem", borderWidth: "3px" }}></div>
            <p style={{ marginTop: "1rem", color: "var(--text-secondary)" }}>Verifying session...</p>
          </div>
        </main>
        <footer className="footer">
          <p>IT3041 Remote Workforce System</p>
        </footer>
      </div>
    );
  }

  return (
    <div className="app-container">
      <Navbar />

      {isAuthenticated ? (
        <Dashboard />
      ) : (
        <main className="main-content">
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
        </main>
      )}

      <footer className="footer">
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

import React, { createContext, useContext, useState, useCallback } from "react";
import { loginUser, getMe } from "../api/auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // Session token and user state stored strictly in memory
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    setError(null);
    try {
      const tokenData = await loginUser({ email, password });
      const accessToken = tokenData.access_token;
      
      // Verify identity via /auth/me before granting session
      const userData = await getMe(accessToken);
      
      setToken(accessToken);
      setUser(userData);
      return userData;
    } catch (err) {
      setError(err.message || "Failed to log in.");
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setError(null);
  }, []);

  const handleSessionExpired = useCallback(() => {
    setToken(null);
    setUser(null);
    setError("Session expired or invalid. Please sign in again.");
  }, []);

  const value = {
    token,
    user,
    isAuthenticated: Boolean(token && user),
    loading,
    error,
    setError,
    login,
    logout,
    handleSessionExpired,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

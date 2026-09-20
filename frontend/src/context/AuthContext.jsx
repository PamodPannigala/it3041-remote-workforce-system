import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { getMe, loginUser } from "../api/auth";

const TOKEN_STORAGE_KEY = "token";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);

  // Restore session token from sessionStorage on startup
  useEffect(() => {
    let isMounted = true;
    const storedToken = sessionStorage.getItem(TOKEN_STORAGE_KEY);

    if (!storedToken) {
      setInitialLoading(false);
      return;
    }

    getMe(storedToken)
      .then((userData) => {
        if (isMounted) {
          setToken(storedToken);
          setUser(userData);
        }
      })
      .catch(() => {
        if (isMounted) {
          sessionStorage.removeItem(TOKEN_STORAGE_KEY);
          setToken(null);
          setUser(null);
        }
      })
      .finally(() => {
        if (isMounted) {
          setInitialLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    setError(null);
    try {
      const tokenData = await loginUser({ email, password });
      const accessToken = tokenData.access_token;

      // Verify identity via /auth/me before granting session
      const userData = await getMe(accessToken);

      sessionStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
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
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setError(null);
  }, []);

  const handleSessionExpired = useCallback(() => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setError("Session expired or invalid. Please sign in again.");
  }, []);

  const value = {
    token,
    user,
    isAuthenticated: Boolean(token && user),
    loading,
    initialLoading,
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

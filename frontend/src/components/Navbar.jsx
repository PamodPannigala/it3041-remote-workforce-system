import React from "react";
import { useAuth } from "../context/AuthContext";
import BrandLogo from "./BrandLogo";
import Badge from "./ui/Badge";
import Button from "./ui/Button";

export default function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <header className="h-16 px-4 sm:px-6 bg-white/95 border-b border-slate-200/80 backdrop-blur-xl flex items-center justify-between sticky top-0 z-40">
      <BrandLogo />

      <div className="flex items-center gap-3">
        {isAuthenticated && user && (
          <>
            <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full bg-slate-50 border border-slate-200 text-xs">
              <span className="font-semibold text-slate-800">{user.name}</span>
              <Badge variant={user.role} size="sm">{user.role}</Badge>
            </div>
            <Button
              id="logout-btn"
              variant="outline"
              size="sm"
              onClick={logout}
              type="button"
            >
              Sign Out
            </Button>
          </>
        )}
      </div>
    </header>
  );
}

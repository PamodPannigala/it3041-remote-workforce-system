import React, { useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import MobileNavigation from "./MobileNavigation";

export default function AppShell({
  user,
  activeTab,
  onTabChange,
  activeTabTitle,
  onLogout,
  children,
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem("rws.sidebarCollapsed") === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem("rws.sidebarCollapsed", String(sidebarCollapsed));
    } catch {
      // Storage may be unavailable in private or restricted browser contexts.
    }
  }, [sidebarCollapsed]);

  return (
    <div className="min-h-screen bg-[var(--app-canvas)] text-slate-900 flex relative overflow-x-hidden font-sans">
      <Sidebar
        user={user}
        activeTab={activeTab}
        onTabChange={onTabChange}
        onLogout={onLogout}
        isCollapsed={sidebarCollapsed}
        className="hidden md:flex fixed inset-y-0 left-0 h-screen z-20 transition-[width] duration-200 ease-out"
      />

      {/* Mobile Drawer */}
      <MobileNavigation
        isOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        user={user}
        activeTab={activeTab}
        onTabChange={onTabChange}
        onLogout={onLogout}
      />

      {/* Main Content Area */}
      <div className={`flex-1 flex flex-col min-w-0 transition-[padding] duration-200 ease-out ${sidebarCollapsed ? "md:pl-20" : "md:pl-64"}`}>
        <Topbar
          user={user}
          activeTabTitle={activeTabTitle}
          onOpenMobileNav={() => setMobileNavOpen(true)}
          isSidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={() => setSidebarCollapsed((collapsed) => !collapsed)}
        />

        <main className="flex-1 w-full max-w-screen-2xl mx-auto px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
          {children}
        </main>

        <footer className="py-4 px-4 sm:px-6 border-t border-slate-200/80 text-center text-xs text-slate-500 bg-white/80">
          <p>© {new Date().getFullYear()} IT3041 Remote Workforce System. All rights reserved.</p>
        </footer>
      </div>
    </div>
  );
}

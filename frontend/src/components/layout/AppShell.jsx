import React, { useState } from "react";
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

  return (
    <div className="min-h-screen bg-[#F6F8FC] text-slate-900 flex relative overflow-x-hidden font-sans">
      {/* Ambient background subtle tint */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-500/[0.03] rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-indigo-500/[0.03] rounded-full blur-3xl" />
      </div>

      {/* Desktop Sidebar (Anchored Dark Navy) */}
      <Sidebar
        user={user}
        activeTab={activeTab}
        onTabChange={onTabChange}
        onLogout={onLogout}
        className="hidden md:flex fixed inset-y-0 left-0 w-64 h-screen z-20"
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
      <div className="flex-1 flex flex-col min-w-0 z-10 md:pl-64">
        <Topbar
          user={user}
          activeTabTitle={activeTabTitle}
          onOpenMobileNav={() => setMobileNavOpen(true)}
        />

        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>

        <footer className="py-6 px-4 border-t border-slate-200 text-center text-xs text-slate-500 bg-white">
          <p>© {new Date().getFullYear()} IT3041 Remote Workforce System. All rights reserved.</p>
        </footer>
      </div>
    </div>
  );
}

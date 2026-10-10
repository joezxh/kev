"use client";

import { ReactNode } from "react";
import { StudioSidebar } from "@/components/studio/Sidebar";
import { StudioTopbar } from "@/components/studio/Topbar";

export function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <div className="studio flex min-h-screen flex-col">
      <StudioTopbar />
      <div className="flex flex-1">
        <StudioSidebar />
        <main className="min-w-0 flex-1 p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

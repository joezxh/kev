"use client";

import { ReactNode } from "react";
import { StudioSidebar } from "@/components/studio/Sidebar";

export function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[calc(100vh-3.5rem)]">
      <StudioSidebar />
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}

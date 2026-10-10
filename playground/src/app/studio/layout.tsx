import { ReactNode } from "react";
import { StudioLayout } from "@/components/studio/Layout";

export default function KevStudioLayout({ children }: { children: ReactNode }) {
  return <StudioLayout>{children}</StudioLayout>;
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLang } from "@/lib/i18n";
import { cn } from "cn";

export function StudioTabs({
  tabs,
  className,
}: {
  tabs: { href: string; label?: string; labelKey?: string }[];
  className?: string;
}) {
  const pathname = usePathname();
  const { t } = useLang();
  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {tabs.map((tab) => {
        const active = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "rounded-md px-2.5 py-1 font-mono text-xs transition-colors",
              active
                ? "bg-[#1e3a8a] text-foreground"
                : "text-muted-foreground hover:bg-[#161616] hover:text-foreground",
            )}
          >
            {tab.labelKey ? t(tab.labelKey) : tab.label}
          </Link>
        );
      })}
    </div>
  );
}
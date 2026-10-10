"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/console", key: "console.nav.overview", exact: true },
  { href: "/console/datasets", key: "console.nav.data" },
  { href: "/console/train", key: "console.nav.train" },
  { href: "/console/eval", key: "console.nav.eval" },
  { href: "/console/images", key: "console.nav.image" },
  { href: "/console/deploy", key: "console.nav.deploy" },
  { href: "/console/apikeys", key: "console.nav.apikeys" },
  { href: "/console/usage", key: "console.nav.usage" },
  { href: "/console/distill-providers", key: "console.nav.distill" },
  { href: "/console/scenarios", key: "console.nav.scenarios" },
];

/**
 * 控制台外壳。用仓库既有的 sidebar token（globals.css 的 --sidebar-*），
 * 它们一直定义着却从没用过 —— 正好是仪表盘要的。
 */
export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = useLang();

  return (
    <TooltipProvider>
      <div className="flex min-h-full">
        <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground">
          <div className="border-b border-sidebar-border px-4 py-3">
            <Link href="/" className="text-xs text-muted-foreground hover:text-foreground">{t("console.back")}</Link>
            <div className="text-sm font-semibold">{t("console.title")}</div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs">
              <Link
                href="/console"
                className={cn("hover:text-foreground", pathname.startsWith("/console") && "font-medium text-foreground")}
              >
                {t("kev.nav.console")}
              </Link>
              <Link
                href="/studio"
                className={cn("hover:text-foreground", pathname.startsWith("/studio") && "font-medium text-foreground")}
              >
                {t("console.nav.studio")}
              </Link>
            </div>
          </div>
          <nav className="flex flex-1 flex-col gap-0.5 p-2">
            {NAV.map((item) => {
              const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "rounded-md px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent",
                    "hover:text-sidebar-accent-foreground",
                    active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
                  )}
                >
                  {t(item.key)}
                </Link>
              );
            })}
          </nav>
          <p className="border-t border-sidebar-border px-4 py-3 text-xs text-muted-foreground">
            {t("console.argv.hint")}
          </p>
        </aside>
        <main className="min-w-0 flex-1 p-6">{children}</main>
        <Toaster />
      </div>
    </TooltipProvider>
  );
}
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  CheckCircle2,
  Cpu,
  Database,
  FolderKanban,
  Gauge,
  KeyRound,
  Layers,
  LayoutDashboard,
  Receipt,
  Rocket,
  UploadCloud,
  Users,
  Webhook,
  type LucideIcon,
} from "lucide-react";
import { useLang } from "@/lib/i18n";
import { cn } from "cn";

type NavItem = { href: string; label: string; icon: LucideIcon; badge?: string };
type NavGroup = { title: string; items: NavItem[] };

const GROUPS: NavGroup[] = [
  {
    title: "studio.nav.data",
    items: [
      { href: "/studio/domains", label: "studio.nav.domains", icon: Layers },
      { href: "/studio/datasets", label: "studio.nav.datasets", icon: Database },
      { href: "/studio/goldset", label: "studio.nav.goldset", icon: CheckCircle2 },
    ],
  },
  {
    title: "studio.nav.lifecycle",
    items: [
      { href: "/studio/train", label: "studio.nav.train", icon: Cpu },
      { href: "/studio/eval", label: "studio.nav.eval", icon: Activity },
      { href: "/studio/deploy", label: "studio.nav.deploy", icon: Rocket },
      { href: "/studio/publish", label: "studio.nav.publish", icon: UploadCloud },
    ],
  },
  {
    title: "studio.nav.system",
    items: [
      { href: "/studio", label: "studio.nav.overview", icon: LayoutDashboard },
      { href: "/studio/overview", label: "studio.nav.monitoring", icon: Bell },
      { href: "/studio/apikeys", label: "studio.nav.apikeys", icon: KeyRound },
      { href: "/studio/usage", label: "studio.nav.usage", icon: BarChart3 },
    ],
  },
  {
    title: "studio.nav.admin",
    items: [
      { href: "/studio/projects", label: "studio.nav.projects", icon: FolderKanban, badge: "soon" },
      { href: "/studio/members", label: "studio.nav.members", icon: Users, badge: "soon" },
      { href: "/studio/quota", label: "studio.nav.quota", icon: Gauge, badge: "soon" },
      { href: "/studio/webhooks", label: "studio.nav.webhooks", icon: Webhook, badge: "soon" },
      { href: "/studio/billing", label: "studio.nav.billing", icon: Receipt, badge: "soon" },
    ],
  },
];

export function StudioSidebar() {
  const { t } = useLang();
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/studio"
      ? pathname === "/studio"
      : pathname === href || pathname.startsWith(href + "/");

  return (
    <aside className="w-56 shrink-0 space-y-4 border-r border-border bg-[#111111] p-3">
      {GROUPS.map((group) => (
        <div key={group.title} className="space-y-1">
          <div className="px-2 text-[10px] font-medium uppercase tracking-wider text-[#5c5c5c]">
            {t(group.title)}
          </div>
          {group.items.map((item) => {
            const active = isActive(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2 rounded px-2 py-1.5 text-[13px] transition-colors",
                  active
                    ? "bg-[#1e3a8a] text-foreground"
                    : "text-muted-foreground hover:bg-[#161616] hover:text-foreground",
                )}
              >
                <Icon className="h-3.5 w-3.5 opacity-70" />
                <span className="flex-1">{t(item.label)}</span>
                {item.badge && (
                  <span className="rounded bg-[#1c1c1c] px-1.5 py-0.5 text-[10px] text-[#f59e0b]">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </aside>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLang } from "@/lib/i18n";

const NAV_GROUPS = [
  {
    title: "studio.nav.data",
    items: [
      { href: "/kev.studio/domains", label: "studio.nav.domains" },
      { href: "/kev.studio/datasets", label: "studio.nav.datasets" },
      { href: "/kev.studio/goldset", label: "studio.nav.goldset" },
    ],
  },
  {
    title: "studio.nav.lifecycle",
    items: [
      { href: "/kev.studio/train", label: "studio.nav.train" },
      { href: "/kev.studio/eval", label: "studio.nav.eval" },
      { href: "/kev.studio/deploy", label: "studio.nav.deploy" },
      { href: "/kev.studio/publish", label: "studio.nav.publish" },
    ],
  },
  {
    title: "studio.nav.system",
    items: [
      { href: "/kev.studio/overview", label: "studio.nav.overview" },
      { href: "/kev.studio/apikeys", label: "studio.nav.apikeys" },
      { href: "/kev.studio/usage", label: "studio.nav.usage" },
    ],
  },
];

export function StudioSidebar() {
  const { t } = useLang();
  const pathname = usePathname();

  return (
    <aside className="w-56 shrink-0 border-r border-border p-3 space-y-4">
      <div>
        <h2 className="text-sm font-semibold">{t("studio.title")}</h2>
        <p className="text-xs text-muted-foreground">{t("studio.subtitle")}</p>
      </div>
      {NAV_GROUPS.map((group) => (
        <div key={group.title} className="space-y-1">
          <div className="text-xs font-medium text-muted-foreground uppercase">
            {t(group.title)}
          </div>
          {group.items.map((item) => {
            const active = pathname === item.href ||
                          (pathname?.startsWith(item.href + "/") ?? false);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  "block rounded-md px-2 py-1 text-sm transition-colors " +
                  (active
                    ? "bg-accent font-medium"
                    : "hover:bg-accent/50")
                }
              >
                {t(item.label)}
              </Link>
            );
          })}
        </div>
      ))}
    </aside>
  );
}

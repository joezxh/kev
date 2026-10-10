"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";

const CHAPTERS = [
  { href: "/kev.studio/domains", titleKey: "studio.nav.domains" },
  { href: "/kev.studio/datasets", titleKey: "studio.nav.datasets" },
  { href: "/kev.studio/goldset", titleKey: "studio.nav.goldset" },
  { href: "/kev.studio/train", titleKey: "studio.nav.train" },
  { href: "/kev.studio/eval", titleKey: "studio.nav.eval" },
  { href: "/kev.studio/deploy", titleKey: "studio.nav.deploy" },
  { href: "/kev.studio/publish", titleKey: "studio.nav.publish" },
  { href: "/kev.studio/apikeys", titleKey: "studio.nav.apikeys" },
  { href: "/kev.studio/usage", titleKey: "studio.nav.usage" },
  { href: "/kev.studio/overview", titleKey: "studio.nav.overview" },
];

export default function StudioOverviewPage() {
  const { t } = useLang();
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold">{t("studio.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("studio.subtitle")}</p>
      </header>
      <div className="grid gap-3 sm:grid-cols-3">
        {CHAPTERS.map((chapter) => (
          <Link
            key={chapter.href}
            href={chapter.href}
            className="rounded-md border border-border p-3 transition-colors hover:bg-accent"
          >
            <div className="text-sm font-medium">{t(chapter.titleKey)}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}

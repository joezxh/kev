"use client";

import { useLang } from "@/lib/i18n";

const SLUGS: Record<string, string> = {
  datasets: "studio.nav.datasets",
  goldset: "studio.nav.goldset",
  train: "studio.nav.train",
  eval: "studio.nav.eval",
  deploy: "studio.nav.deploy",
  publish: "studio.nav.publish",
  apikeys: "studio.nav.apikeys",
  usage: "studio.nav.usage",
  overview: "studio.nav.overview",
};

export default function StudioPlaceholderPage({ params }: { params: { slug: string } }) {
  const { t } = useLang();
  const titleKey = SLUGS[params.slug] ?? "studio.title";
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold">{t(titleKey)}</h1>
      </header>
      <p className="text-sm text-muted-foreground italic">{t("studio.placeholder")}</p>
    </div>
  );
}

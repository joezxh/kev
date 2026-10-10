"use client";

import { useLang } from "@/lib/i18n";
import { DomainsManager } from "@/components/studio/DomainsManager";
import { PageHead } from "@/components/studio/primitives";

export default function StudioDomainsPage() {
  const { t } = useLang();
  return (
    <div className="space-y-6">
      <PageHead title={t("studio.domains.title")} subtitle={t("studio.domains.subtitle")} />
      <DomainsManager />
    </div>
  );
}

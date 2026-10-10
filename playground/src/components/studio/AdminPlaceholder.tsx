"use client";

import { useLang } from "@/lib/i18n";
import { EmptyState, PageHead } from "./primitives";

export function AdminPlaceholder({ titleKey }: { titleKey: string }) {
  const { t } = useLang();
  return (
    <div className="space-y-4">
      <PageHead title={t(titleKey)} subtitle={t("studio.admin.comingSoon")} />
      <EmptyState title={t("studio.admin.comingSoon")} hint={t(titleKey)} />
    </div>
  );
}

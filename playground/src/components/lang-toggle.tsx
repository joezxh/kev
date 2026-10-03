"use client";

import { useLang } from "@/lib/i18n";

export function LangToggle() {
  const { lang, setLang, t } = useLang();
  return (
    <button
      type="button"
      onClick={() => setLang(lang === "en" ? "zh" : "en")}
      className="rounded-md border border-border px-2.5 py-1 text-[13px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
      aria-label="Switch language"
    >
      {t("lang.toggle")}
    </button>
  );
}

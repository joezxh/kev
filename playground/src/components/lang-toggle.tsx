"use client";

import { useLang } from "@/lib/i18n";
import { cn } from "cn";

export function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <div
      role="group"
      aria-label="Language"
      className="flex shrink-0 items-center rounded-md border border-border p-0.5 text-[12px]"
    >
      {(["zh", "en"] as const).map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setLang(l)}
          aria-pressed={lang === l}
          className={cn(
            "rounded px-2 py-0.5 font-medium transition-colors",
            lang === l ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {l === "zh" ? "中文" : "EN"}
        </button>
      ))}
    </div>
  );
}

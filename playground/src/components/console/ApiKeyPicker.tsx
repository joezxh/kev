"use client";
import { useEffect, useState } from "react";
import { apikeyStore, type SavedKey } from "@/lib/apikey-store";
import { useLang } from "@/lib/i18n";

export function ApiKeyPicker() {
  const { t, lang } = useLang();
  const [keys, setKeys] = useState<SavedKey[]>([]);
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    setKeys(apikeyStore.loadKeys());
    setCurrent(apikeyStore.getCurrent());
  }, []);

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">{t("console.apikeys.use")}</span>
      <select
        className="h-8 rounded-md border border-border bg-background px-2 text-xs"
        value={current ?? ""}
        onChange={(e) => { apikeyStore.setCurrent(e.target.value); setCurrent(e.target.value); }}
      >
        <option value="">{lang === "zh" ? "未选择" : "none"}</option>
        {keys.map((k) => (
          <option key={k.id} value={k.key}>{k.prefix}</option>
        ))}
      </select>
      {keys.length === 0 && (
        <a className="text-xs underline" href="/console/apikeys">
          {t("console.apikeys.createHint")}
        </a>
      )}
    </div>
  );
}

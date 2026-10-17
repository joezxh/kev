"use client";
// 字符串数组编辑器（variety 等）：每项一行可编辑，支持增删。
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useLang } from "@/lib/i18n";

export function StringListEditor({ value, onChange }: { value: unknown; onChange: (v: string[]) => void }) {
  const { t } = useLang();
  const items = Array.isArray(value) ? value.map((v) => (typeof v === "string" ? v : String(v ?? ""))) : [];
  return (
    <div className="space-y-1">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-1">
          <Input
            className="h-7 text-xs"
            value={item}
            onChange={(e) => { const next = items.slice(); next[i] = e.target.value; onChange(next); }}
          />
          <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs text-muted-foreground"
            onClick={() => onChange(items.filter((_, j) => j !== i))}>
            {t("console.spec.kv.remove")}
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => onChange([...items, ""])}>
        + {t("console.spec.kv.addItem")}
      </Button>
    </div>
  );
}

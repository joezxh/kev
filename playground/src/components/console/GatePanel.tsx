"use client";

import { useLang } from "@/lib/i18n";
import type { Gate } from "@/lib/console";

/**
 * 验收门槛面板。G4 的提示语要说清因果：CI 含 0 说明数据不够或增益太小，
 * 收益排序第 1 位是「更多更好的数据」—— 改数据不是加量、也不是调超参。
 */
export function GatePanel({ gates, title }: { gates: Gate[]; title?: string }) {
  const { t } = useLang();
  const failed = gates.filter((gate) => !gate.ok).length;

  return (
    <section className="rounded-md border border-border bg-[#111111]">
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <h3 className="text-sm font-medium">{title ?? t("console.eval.gates")}</h3>
        <span
          className={
            failed
              ? "rounded-md border border-border px-2 py-0.5 text-xs text-[#ef4444]"
              : "rounded-md border border-border px-2 py-0.5 text-xs text-[#22c55e]"
          }
        >
          {failed ? t("console.eval.blocked", { n: failed }) : t("console.eval.allPass")}
        </span>
      </header>
      {gates.length === 0 ? (
        <p className="px-3 py-2 text-sm text-muted-foreground">该阶段不设闸门</p>
      ) : (
        <ul className="divide-y divide-border">
          {gates.map((gate) => (
            <li key={gate.id} className="px-3 py-2 text-sm">
              <div className="flex items-start gap-2">
                <span className={gate.ok ? "text-[#22c55e]" : "text-[#ef4444]"}>
                  {gate.ok ? "✓" : "✗"}
                </span>
                <span className="font-mono text-xs text-muted-foreground">{gate.id}</span>
                <span className={gate.ok ? "text-muted-foreground" : "text-[#ef4444]"}>
                  {gate.detail}
                </span>
              </div>
              {!gate.ok && gate.actual && (
                <p className="mt-0.5 pl-8 text-xs text-muted-foreground">
                  实测 {gate.actual} · 需要 {gate.need}
                </p>
              )}
              {!gate.ok && gate.id === "G4" && (
                <p className="mt-0.5 pl-8 text-xs text-muted-foreground">{t("console.eval.g4hint")}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
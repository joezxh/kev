"use client";

import { useLang } from "@/lib/i18n";

// 轨制徽标的颜色映射（track = rule|distill|both|llm，其余归为未判定）。
// 从 app/console/scenarios/page.tsx 提取为共享组件：console「场景管理」页与 studio「域与场景」页复用同一视觉。
export const TRACK_STYLE: Record<string, string> = {
  rule: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
  distill: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
  both: "bg-teal-500/15 text-teal-600 dark:text-teal-400",
  llm: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
};
export const TRACK_KEYS = ["rule", "distill", "both", "llm"];

export function TrackBadge({ track, label }: { track: string; label: string }) {
  const { t } = useLang();
  const key = TRACK_KEYS.includes(track) ? track : "unknown";
  const style = TRACK_STYLE[track] ?? "bg-muted text-muted-foreground";
  const text = t(`console.scenarios.track.${key}`);
  return (
    <span title={`${label}: ${text}`}
          className={`inline-flex shrink-0 items-center rounded px-1 py-px text-[9px] font-medium leading-tight ${style}`}>
      {text}
    </span>
  );
}

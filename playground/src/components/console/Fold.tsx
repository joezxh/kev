"use client";

import { ReactNode } from "react";

/**
 * 可折叠面板：原生 <details> 实现，无额外依赖，默认展开。
 * 用于作业详情区的「损失曲线 / 跟随输出」分区。JobMonitor 内部的交互元素
 * （图表、日志区）在 <details> 内也能正常工作。
 */
export function Fold({
  title, summary, children, defaultOpen = true,
}: {
  title: string; summary?: string; children: ReactNode; defaultOpen?: boolean;
}) {
  return (
    <details open={defaultOpen} className="rounded-md border border-border">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-sm font-medium">
        <span>{title}</span>
        {summary && <span className="text-xs text-muted-foreground">{summary}</span>}
      </summary>
      <div className="px-3 pb-3 pt-1">{children}</div>
    </details>
  );
}

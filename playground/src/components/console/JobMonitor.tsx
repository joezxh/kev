"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { streamJob, subscribeStream, type JobStatus, type Metric } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { LossChart } from "./LossChart";
import { estimateRemaining } from "./format";
import { cn } from "@/lib/utils";

type Line = { id: number; stream: string; line: string };

const MAX_LINES = 5000;

/**
 * 作业详情页的实时区：指标曲线 + 日志尾。
 *
 * 只在作业处于活动状态时订阅；终态后 SSE 会自己发 status 帧并关闭。
 */
export function JobMonitor({ jobId, status, onStatus }: {
  jobId: string;
  status: JobStatus;
  onStatus?: (status: JobStatus) => void;
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [follow, setFollow] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);
  const { t } = useLang();

  const live = status === "pending" || status === "queued" || status === "running";

  useEffect(() => {
    if (!live) return;
    const stop = subscribeStream(streamJob(jobId), {
      onLog: (event) => setLines((previous) => {
        const next = [...previous, { id: event.id, stream: event.stream, line: event.line }];
        // 浏览器内存上限：只留最近的行，早期日志在磁盘上的 job.log 里
        return next.length > MAX_LINES ? next.slice(next.length - MAX_LINES) : next;
      }),
      onMetric: (metric) => setMetrics((previous) => {
        const next = [...previous, metric];
        return next.length > 2000 ? next.slice(next.length - 2000) : next;
      }),
      onStatus: (payload) => onStatus?.(payload.status),
    });
    return stop;
  }, [jobId, live, onStatus]);

  useEffect(() => {
    if (follow) endRef.current?.scrollIntoView({ block: "end" });
  }, [lines, follow]);

  const last = metrics[metrics.length - 1];

  return (
    <div className="space-y-4">
      {last && (
        <p className="text-sm text-muted-foreground">
          ep{last.ep} step {last.step}/{last.total} · {last.sec.toFixed(3)}s/rec · 预计剩余{" "}
          {estimateRemaining(last.step, last.total, last.sec)}
        </p>
      )}
      <LossChart points={metrics} />
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {t("console.jobs.follow")} · {lines.length} 行（仅浏览器内，全量在 job.log）
          </span>
          <Button size="sm" variant={follow ? "secondary" : "ghost"} onClick={() => setFollow((v) => !v)}>
            {follow ? t("console.jobs.paused") : t("console.jobs.follow")}
          </Button>
        </div>
        <ScrollArea className="h-72 rounded-md border border-border bg-muted/30">
          <pre className="p-3 font-mono text-xs leading-relaxed">
            {lines.length === 0
              ? <span className="text-muted-foreground">（暂无输出）</span>
              : lines.map((row) => (
                <div key={row.id} className={cn(row.stream === "stderr" && "text-destructive")}>
                    {row.line}
                  </div>
                ))}
            <div ref={endRef} />
          </pre>
        </ScrollArea>
      </div>
    </div>
  );
}
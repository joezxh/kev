"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { streamJob, subscribeStream, type JobStatus, type Metric } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { Fold } from "./Fold";
import { LossChart } from "./LossChart";
import { estimateRemaining } from "./format";
import { cn } from "@/lib/utils";

type Line = { id: number; stream: string; line: string };

const MAX_LINES = 5000;

/**
 * 作业详情页的实时区：指标曲线 + 日志尾。
 *
 * 无论作业是否终态都订阅：SSE 端点对历史事件做首屏回填（after_id=0 全量重放），
 * 终态作业回放完就发 status 帧并关闭。这样结果页照样有损失曲线与跟随日志 ——
 * 之前只在 live 时订阅，跳到结果页日志区永远是空的。
 */
export function JobMonitor({ jobId, onStatus }: {
  jobId: string;
  onStatus?: (status: JobStatus) => void;
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [follow, setFollow] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);
  const { t, lang } = useLang();

  useEffect(() => {
    return subscribeStream(streamJob(jobId), {
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
  }, [jobId, onStatus]);

  useEffect(() => {
    if (follow) endRef.current?.scrollIntoView({ block: "end" });
  }, [lines, follow]);

  const last = metrics[metrics.length - 1];

  return (
    <div className="space-y-3">
      <Fold title={lang === "zh" ? "损失曲线" : "Loss curve"}
            summary={last ? `ep${last.ep} step ${last.step}/${last.total}` : undefined}>
        {last && (
          <p className="text-sm text-muted-foreground">
            ep{last.ep} step {last.step}/{last.total} · {last.sec.toFixed(3)}s/rec · 预计剩余{" "}
            {estimateRemaining(last.step, last.total, last.sec)}
          </p>
        )}
        <LossChart points={metrics} />
      </Fold>
      <Fold title={t("console.jobs.follow")} summary={`${lines.length} 行`}>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {lines.length} 行（仅浏览器内，全量在 job.log）
            </span>
            <Button size="sm" variant={follow ? "secondary" : "ghost"} onClick={() => setFollow((v) => !v)}>
              {follow ? t("console.jobs.paused") : t("console.jobs.follow")}
            </Button>
          </div>
          {/* 原生 overflow-auto：共享 ScrollArea 只有纵向滚动条，长行会横向溢出 panel */}
          <div className="h-72 overflow-auto rounded-md border border-border bg-muted/30">
            <pre className="p-3 font-mono text-xs leading-relaxed whitespace-pre">
              {lines.length === 0
                ? <span className="text-muted-foreground">（暂无输出）</span>
                : lines.map((row) => (
                  <div key={row.id} className={cn(row.stream === "stderr" && "text-destructive")}>
                      {row.line}
                    </div>
                  ))}
              <div ref={endRef} />
            </pre>
          </div>
        </div>
      </Fold>
    </div>
  );
}

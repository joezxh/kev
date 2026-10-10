"use client";

import { useCallback, type ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type JobDetail, type JobStatus } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobMonitor } from "./JobMonitor";
import { STATUS_LABELS, STAGE_LABELS, renderArgv } from "./format";
import { usePoll } from "./usePoll";

const TONE: Record<JobStatus, "default" | "secondary" | "destructive" | "outline"> = {
  pending: "outline", queued: "secondary", running: "secondary",
  succeeded: "default", failed: "destructive", canceled: "outline", interrupted: "outline",
};

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

/**
 * 作业详情面板。被两处复用：
 * - 独立作业详情页 /console/jobs/[id]（与 /studio 详情页）
 * - 数据页内嵌的「生成中 / 生成结果」卡片
 *
 * 实时日志与损失曲线交给 JobMonitor（订阅 SSE，终态作业也会首屏回填历史事件），
 * 这里只负责作业元信息、命令预览、产物与失败信息 —— 两处的展示逻辑因此不分裂成两套。
 */
export function JobDetailPanel({ jobId }: { jobId: string }) {
  const { t, lang } = useLang();
  const load = useCallback(() => api.job(jobId).catch(() => null), [jobId]);
  const { value: job, refresh } = usePoll<JobDetail | null>(load, null);

  if (!job) {
    return <p className="text-sm text-muted-foreground">{t("console.jobs.loading")}</p>;
  }

  const act = async (action: "cancel" | "retry") => {
    if (action === "cancel") await api.cancel(jobId);
    else await api.retry(jobId);
    void refresh();
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={TONE[job.status] ?? "outline"}>
          {STATUS_LABELS[job.status]?.[lang] ?? job.status}
        </Badge>
        <span className="text-sm text-muted-foreground">
          {STAGE_LABELS[job.stage]?.[lang] ?? job.stage}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{job.kind}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label={t("console.jobs.scenario")}>{job.scenario}</Field>
        <Field label={t("console.jobs.run")}>
          <span className="font-mono text-xs">{job.title}</span>
        </Field>
        <Field label={t("console.jobs.attempt")}>{job.attempt > 1 ? `r${job.attempt}` : "—"}</Field>
        <Field label={t("console.jobs.created")}>{job.created_at.slice(0, 19)}</Field>
      </div>

      {job.argv.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">{t("console.jobs.command")}</div>
          <pre className="overflow-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-xs">
            {renderArgv(job.argv)}
          </pre>
        </div>
      )}

      {/* 不论终态都订阅：SSE 首屏回填历史事件，结果页同样有损失曲线与日志。 */}
      <JobMonitor jobId={jobId} />

      {(job.status === "failed" || job.status === "canceled" || job.status === "interrupted") && (
        <Alert variant="destructive">
          <AlertTitle>{STATUS_LABELS[job.status]?.[lang] ?? job.status}</AlertTitle>
          <AlertDescription>
            <pre className="whitespace-pre-wrap font-mono text-xs">
              {job.error ?? t("console.jobs.noError")}
            </pre>
          </AlertDescription>
        </Alert>
      )}

      {job.artifacts.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">{t("console.jobs.artifacts")}</div>
          <ul className="divide-y divide-border rounded-md border border-border">
            {job.artifacts.map((artifact) => (
              <li key={artifact.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                <span className="truncate">
                  <span className="font-mono text-xs">{artifact.name}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{artifact.path}</span>
                </span>
                <a
                  className="shrink-0 font-mono text-xs text-primary hover:underline"
                  href={`/api/console/artifacts/${encodeURIComponent(artifact.id)}/content`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("console.jobs.view")}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex gap-2">
        {job.status === "running" && (
          <Button size="sm" variant="ghost" onClick={() => void act("cancel")}>
            {t("console.jobs.cancel")}
          </Button>
        )}
        {(job.status === "failed" || job.status === "canceled" || job.status === "interrupted") && (
          <Button size="sm" variant="ghost" onClick={() => void act("retry")}>
            {t("console.jobs.retry")}
          </Button>
        )}
      </div>
    </div>
  );
}

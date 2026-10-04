"use client";

import { use, useCallback, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { ApiError, api, type JobDetail, type JobStatus } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { GatePanel } from "@/components/console/GatePanel";
import { JobMonitor } from "@/components/console/JobMonitor";
import { usePoll } from "@/components/console/usePoll";
import { renderArgv } from "@/components/console/format";

export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, lang } = useLang();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gateError, setGateError] = useState<ApiError | null>(null);

  const load = useCallback(() => api.job(id), [id]);
  const polled = usePoll(load, null as JobDetail | null);
  const detail = job ?? polled.value;

  const act = async (action: "cancel" | "retry") => {
    setError(null);
    try {
      if (action === "cancel") await api.cancel(id);
      else await api.retry(id);
      setJob(null);
      window.location.reload();
    } catch (problem) {
      setGateError(problem as ApiError);
    }
  };

  if (polled.error && !detail) {
    return <Alert variant="destructive"><AlertTitle>{polled.error}</AlertTitle></Alert>;
  }
  if (!detail) {
    return <p className="text-sm text-muted-foreground">{lang === "zh" ? "加载中…" : "Loading…"}</p>;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold">
          {detail.kind} · <span className="font-mono">{detail.title}</span>
        </h1>
        <p className="text-xs text-muted-foreground">
          {detail.scenario} · {detail.status}
          {detail.exit_code !== null && ` · exit ${detail.exit_code}`}
          {detail.attempt > 1 && ` · r${detail.attempt}`}
        </p>
      </header>

      {detail.status === "interrupted" && (
        <Alert>
          <AlertTitle>{t("console.jobs.interrupted")}</AlertTitle>
          <AlertDescription>
            <Button size="sm" onClick={() => void act("retry")}>{t("console.jobs.retry")}</Button>
          </AlertDescription>
        </Alert>
      )}

      {detail.status === "failed" && (
        <Alert variant="destructive">
          <AlertTitle>
            {lang === "zh" ? "作业失败" : "Job failed"}
            {detail.exit_code !== null && ` (${detail.exit_code})`}
          </AlertTitle>
          <AlertDescription>
            <pre className="whitespace-pre-wrap font-mono text-xs">{detail.error}</pre>
          </AlertDescription>
        </Alert>
      )}

      {gateError && (
        <Alert variant="destructive">
          <AlertTitle>{gateError.detail.kind}</AlertTitle>
          <AlertDescription>
            <p>{gateError.message}</p>
            {gateError.gates().length > 0 && <GatePanel gates={gateError.gates()} />}
          </AlertDescription>
        </Alert>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium">
          {lang === "zh" ? "命令" : "Command"}
          <Button size="sm" variant="ghost" className="ml-2"
                  onClick={() => void navigator.clipboard.writeText(renderArgv(detail.argv))}>
            {t("console.argv.copy")}
          </Button>
        </h2>
        <ScrollArea className="max-h-32 rounded-md border border-border bg-muted/40">
          <pre className="p-3 font-mono text-xs break-all">{renderArgv(detail.argv)}</pre>
        </ScrollArea>
        {Object.keys(detail.env_overlay).length > 0 && (
          <p className="text-xs text-muted-foreground">
            env（{lang === "zh" ? "只含非敏感键；凭据由编排服务注入，从不下发" : "non-sensitive keys only; secrets are injected by the orchestrator and never sent here"}）：
            {Object.entries(detail.env_overlay).map(([k, v]) => `${k}=${v}`).join(" ")}
          </p>
        )}
      </section>

      <Separator />

      <section className="space-y-2">
        <h2 className="text-sm font-medium">{t("console.train.monitor")}</h2>
        <JobMonitor jobId={detail.id} status={detail.status as JobStatus}
                    onStatus={() => window.location.reload()} />
      </section>

      {detail.notes.length > 0 && (
        <Alert>
          <AlertTitle>{lang === "zh" ? "运行期提示" : "Run notes"}</AlertTitle>
          <AlertDescription>
            <ul className="space-y-0.5 font-mono text-xs">
              {detail.notes.map((note, index) => (
                <li key={index}>{JSON.stringify(note)}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <Separator />

      <section className="space-y-2">
        <h2 className="text-sm font-medium">{t("console.jobs.artifacts")}</h2>
        {detail.artifacts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {lang === "zh" ? "还没有产物" : "No artifacts yet"}
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {detail.artifacts.map((artifact) => (
              <li key={artifact.id} className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono text-xs">{artifact.id}</span>
                <span className="text-xs text-muted-foreground">{artifact.path}</span>
                {artifact.bytes !== null && (
                  <span className="text-xs text-muted-foreground">
                    {(artifact.bytes / 1024).toFixed(1)} KB
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type Job } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { STATUS_LABELS, STAGE_LABELS } from "./format";

const TONE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  succeeded: "default", running: "secondary", queued: "secondary",
  pending: "outline", failed: "destructive", canceled: "outline", interrupted: "outline",
};

export function JobTable({ jobs, onChanged }: { jobs: Job[]; onChanged?: () => void }) {
  const { lang, t } = useLang();

  if (jobs.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">{t("console.jobs.empty")}</p>;
  }

  const act = async (id: string, action: "cancel" | "retry") => {
    await (action === "cancel" ? api.cancel(id) : api.retry(id));
    onChanged?.();
  };

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("console.jobs.detail") === "Detail" ? "Status" : "状态"}</TableHead>
          <TableHead>{lang === "zh" ? "阶段" : "Stage"}</TableHead>
          <TableHead>{lang === "zh" ? "类型" : "Kind"}</TableHead>
          <TableHead>{lang === "zh" ? "场景" : "Scenario"}</TableHead>
          <TableHead>{lang === "zh" ? "运行名" : "Run"}</TableHead>
          <TableHead>{lang === "zh" ? "尝试" : "Try"}</TableHead>
          <TableHead>{lang === "zh" ? "创建" : "Created"}</TableHead>
          <TableHead className="text-right">{lang === "zh" ? "操作" : "Actions"}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <TableRow key={job.id}>
            <TableCell>
              <Badge variant={TONE[job.status] ?? "outline"}>
                {STATUS_LABELS[job.status]?.[lang] ?? job.status}
              </Badge>
            </TableCell>
            <TableCell className="text-sm">{STAGE_LABELS[job.stage]?.[lang] ?? job.stage}</TableCell>
            <TableCell className="font-mono text-xs">{job.kind}</TableCell>
            <TableCell className="text-sm">{job.scenario}</TableCell>
            <TableCell className="font-mono text-xs">{job.title}</TableCell>
            <TableCell className="text-xs text-muted-foreground">
              {job.attempt > 1 ? `r${job.attempt}` : "—"}
            </TableCell>
            <TableCell className="text-xs text-muted-foreground">{job.created_at.slice(5, 19)}</TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-1">
                {/* base-ui 的 Button 不支持 asChild，所以用 buttonVariants 直接给 Link 上样式 */}
                <Link href={`/console/jobs/${job.id}`}
                      className={buttonVariants({ variant: "ghost", size: "sm" })}>
                  {t("console.jobs.detail")}
                </Link>
                {job.status === "running" && (
                  <Button size="sm" variant="ghost" onClick={() => void act(job.id, "cancel")}>
                    {t("console.jobs.cancel")}
                  </Button>
                )}
                {(job.status === "failed" || job.status === "canceled" || job.status === "interrupted") && (
                  <Button size="sm" variant="ghost" onClick={() => void act(job.id, "retry")}>
                    {t("console.jobs.retry")}
                  </Button>
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
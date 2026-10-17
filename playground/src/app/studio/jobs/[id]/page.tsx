"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useLang } from "@/lib/i18n";
import { api } from "@/lib/console";
import { useProjects } from "@/components/studio/ProjectSwitcher";
import { JobDetailPanel } from "@/components/console/JobDetailPanel";

/** 作业归属项目的徽标（D1）：legacy（project_id=''）不显示。 */
function ProjectBadge({ jobId }: { jobId: string }) {
  const { t } = useLang();
  const { projects } = useProjects();
  const [pid, setPid] = useState<string>("");
  useEffect(() => {
    let alive = true;
    api.job(jobId)
      .then((j) => {
        if (alive) setPid(j.project_id ?? "");
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [jobId]);
  if (!pid) return null;
  const name = projects.find((p) => p.id === pid)?.name ?? pid.slice(0, 6);
  return (
    <Link href={`/studio/projects/${pid}`} className="text-xs text-muted-foreground hover:text-foreground">
      {t("studio.board.col.project")}: {name}
    </Link>
  );
}

export default function StudioJobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { t } = useLang();

  // 该详情页由提交作业后跳转、以及各列表（数据集 / 金标 / 总览…）点击状态进入，
  // 来源页不固定，故返回用浏览器历史 back()；直接打开 URL（无历史）时兜底回 /studio。
  const back = () => {
    if (typeof window !== "undefined" && window.history.length > 1) router.back();
    else router.push("/studio");
  };

  return (
    <div className="space-y-4">
      <Button size="sm" variant="ghost" onClick={back}>
        ← {t("console.jobs.back")}
      </Button>
      <div className="flex justify-end">
        <ProjectBadge jobId={id} />
      </div>
      <JobDetailPanel jobId={id} />
    </div>
  );
}

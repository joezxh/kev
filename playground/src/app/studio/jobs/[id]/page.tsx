"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useLang } from "@/lib/i18n";
import { JobDetailPanel } from "@/components/console/JobDetailPanel";

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
      <JobDetailPanel jobId={id} />
    </div>
  );
}

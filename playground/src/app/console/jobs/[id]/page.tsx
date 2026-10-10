"use client";

import { use } from "react";
import { JobDetailPanel } from "@/components/console/JobDetailPanel";

/**
 * 独立作业详情页。展示逻辑全部在 JobDetailPanel —— 数据页内嵌的「生成中 / 生成结果」
 * 用的是同一份组件，保证两处的 job.log 提取与产物内容展示不会长成两套。
 */
export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <JobDetailPanel jobId={id} />;
}

import type { Job } from "@/lib/console";

/**
 * 每个阶段的最新作业（按 created_at 取最大）。
 * 概览页用它渲染「各阶段上一次作业状态」。
 */
export function latestJobPerStage(jobs: Job[]): Record<string, Job> {
  const out: Record<string, Job> = {};
  for (const job of jobs) {
    const current = out[job.stage];
    if (!current || job.created_at > current.created_at) out[job.stage] = job;
  }
  return out;
}

/** 按 stage 分组，保留输入顺序（列表页据此分区展示）。 */
export function groupJobsByStage(jobs: Job[]): Record<string, Job[]> {
  const out: Record<string, Job[]> = {};
  for (const job of jobs) {
    (out[job.stage] ??= []).push(job);
  }
  return out;
}

"use client";

import { useCallback, Fragment, useState } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { api, type Job } from "@/lib/console";
import { usePoll } from "@/components/console/usePoll";
import { EmptyState, FilterChip, Kpi, Pager, SearchInput, StatusBadge, Toolbar } from "./primitives";
import { FileViewerDialog, JobFilesStrip, type ViewerSpec } from "./JobFiles";

const DEFAULT_PAGE_SIZE = 10;
const DEFAULT_PAGE_SIZE_OPTIONS = [5, 10, 20, 50];

function durationOf(job: Job): string {
  if (!job.started_at) return "—";
  const end = job.finished_at ? new Date(job.finished_at) : new Date();
  const secs = Math.max(0, (end.getTime() - new Date(job.started_at).getTime()) / 1000);
  if (secs < 60) return `${secs.toFixed(0)}s`;
  const m = Math.floor(secs / 60);
  return `${m}m ${(secs - m * 60).toFixed(0)}s`;
}

const STATUS_FILTERS = ["all", "running", "succeeded", "failed", "pending", "canceled"];

/** 由数据集列表下钻时传入的外部筛选（按 场景 / 领域 / 数据集 过滤 jobs）。 */
export type JobFilter = {
  key: string;
  label: string;
  test: (job: Job) => boolean;
};

export function JobBoard({
  stage,
  kinds,
  hrefFor,
  jobsProp,
  defaultPageSize = DEFAULT_PAGE_SIZE,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  externalFilter,
  onClearExternal,
  showFiles,
}: {
  stage?: string;
  kinds?: string[];
  hrefFor: (id: string) => string;
  /** 直接传入作业列表（避免重复拉取）；省略则内部自行拉取。 */
  jobsProp?: Job[];
  /** 每页默认行数。 */
  defaultPageSize?: number;
  /** 每页行数可选项。 */
  pageSizeOptions?: number[];
  /** 外部下钻筛选条件；存在时在列表上方显示「按 X 筛选」与「全部」清除按钮。 */
  externalFilter?: JobFilter | null;
  /** 点击「全部」清除外部筛选。 */
  onClearExternal?: () => void;
  /** 每个作业行下方展开详情条：输出产物 / 输入 / 执行脚本，点击弹窗查看文件内容（不跳转）。 */
  showFiles?: boolean;
}) {
  const { t } = useLang();
  const load = useCallback(() => api.jobs(stage ? { stage } : undefined), [stage]);
  const { value: fetched, error } = usePoll<Job[]>(load, []);
  const jobs = jobsProp ?? fetched;

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  // 文件查看弹窗的目标；null 即关闭。整张表共享一个弹窗实例。
  const [viewer, setViewer] = useState<ViewerSpec | null>(null);

  const filtered = jobs.filter((job) => {
    if (kinds && !kinds.includes(job.kind)) return false;
    if (statusFilter !== "all" && job.status !== statusFilter) return false;
    if (q) {
      const hay = `${job.id} ${job.kind} ${job.scenario} ${job.title}`.toLowerCase();
      if (!hay.includes(q.toLowerCase())) return false;
    }
    if (externalFilter && !externalFilter.test(job)) return false;
    return true;
  });

  // 过滤 / 每页行数变化时回到第一页。用 React 官方的「渲染期调整状态」模式：
  // 效果等价于旧的 effect 写法，但少一次级联渲染，也不再触发 set-state-in-effect 报错。
  const filterKey = `${q}|${statusFilter}|${pageSize}|${externalFilter?.key ?? ""}`;
  const [lastFilterKey, setLastFilterKey] = useState(filterKey);
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey);
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paged = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  const count = (s: string) => jobs.filter((j) => j.status === s).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label={t("studio.board.kpi.total")} value={jobs.length} />
        <Kpi
          label={t("studio.board.kpi.running")}
          value={<span className="text-[#3b82f6]">{count("running")}</span>}
        />
        <Kpi
          label={t("studio.board.kpi.succeeded")}
          value={<span className="text-[#22c55e]">{count("succeeded")}</span>}
        />
        <Kpi
          label={t("studio.board.kpi.failed")}
          value={<span className="text-[#ef4444]">{count("failed")}</span>}
        />
      </div>

      <Toolbar>
        <SearchInput value={q} onChange={setQ} placeholder={t("studio.board.search")} />
        {STATUS_FILTERS.map((s) => (
          <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)}>
            {s === "all" ? t("studio.board.all") : s}
          </FilterChip>
        ))}
        {externalFilter && (
          <span className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">
              {t("studio.datasets.filterActive", { label: externalFilter.label })}
            </span>
            <button
              type="button"
              onClick={onClearExternal}
              className="rounded border border-border px-2 py-1 transition-colors hover:bg-[#161616]"
            >
              {t("studio.datasets.clearFilter")}
            </button>
          </span>
        )}
      </Toolbar>

      {!jobsProp && error && <p className="text-xs text-[#ef4444]">{error}</p>}

      {filtered.length === 0 ? (
        <EmptyState title={t("studio.board.empty")} />
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2">{t("studio.board.col.status")}</th>
                <th className="px-3 py-2">{t("studio.board.col.id")}</th>
                <th className="px-3 py-2">{t("studio.board.col.kind")}</th>
                <th className="px-3 py-2">{t("studio.board.col.scenario")}</th>
                <th className="px-3 py-2">{t("studio.board.col.run")}</th>
                <th className="px-3 py-2">{t("studio.board.col.created")}</th>
                <th className="px-3 py-2 text-right">⏱</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((job) => (
                <Fragment key={job.id}>
                  <tr className="border-b border-border/60 transition-colors hover:bg-[#161616]">
                    <td className="px-3 py-2">
                      <Link href={hrefFor(job.id)}>
                        <StatusBadge status={job.status} />
                      </Link>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{job.id}</td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{job.kind}</td>
                    <td className="px-3 py-2">{job.scenario}</td>
                    <td className="px-3 py-2 font-mono text-xs">{job.title}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{job.created_at.slice(0, 19)}</td>
                    <td className="px-3 py-2 text-right text-xs text-muted-foreground">{durationOf(job)}</td>
                  </tr>
                  {showFiles && (
                    <tr className="border-b border-border/60 bg-[#0d0d0d]">
                      <td colSpan={7} className="px-3 py-2">
                        <JobFilesStrip job={job} onOpen={setViewer} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pager
        page={safePage}
        totalPages={totalPages}
        pageSize={pageSize}
        pageSizeOptions={pageSizeOptions}
        onPage={setPage}
        onPageSize={setPageSize}
        labels={{
          prev: t("studio.board.prev"),
          next: t("studio.board.next"),
          pageOf: (p, tot) => t("studio.board.pageOf", { page: p, total: tot }),
          rowsPerPage: t("studio.datasets.rowsPerPage"),
        }}
      />

      {showFiles && <FileViewerDialog spec={viewer} onClose={() => setViewer(null)} />}
    </div>
  );
}

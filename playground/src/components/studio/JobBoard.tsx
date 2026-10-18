"use client";

import { useCallback, useEffect, Fragment, useState } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { api, type Bundle, type Job } from "@/lib/console";
import { usePoll } from "@/components/console/usePoll";
import { useStageTitles } from "@/components/console/StageInsights";
import { EmptyState, FilterChip, Kpi, Pager, SearchInput, StatusBadge, Toolbar } from "./primitives";
import { FileViewerDialog, JobFilesStrip, type ViewerSpec } from "./JobFiles";
import { useProjects } from "./ProjectSwitcher";
import { useSelectedProject } from "@/lib/project-context";

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

// 只有终态作业可删（与服务端守卫一致）：进行中的行不给删除入口，先取消、等进终态。
const DELETABLE: Job["status"][] = ["succeeded", "failed", "canceled", "interrupted"];

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
  onDeleted,
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
  /** 行内删除成功后的回调：外部传 jobsProp 时（如数据集页）自己的 refresh 碰不到父级数据源，
   *  靠它立即重拉；否则删掉的行会挂到父轮询下一拍才能消失。 */
  onDeleted?: () => void;
}) {
  const { t } = useLang();
  const load = useCallback(() => api.jobs(stage ? { stage } : undefined), [stage]);
  const { value: fetched, error, refresh } = usePoll<Job[]>(load, []);
  const jobs = jobsProp ?? fetched;

  // 项目归属（D14）：选了项目就默认只看本项目，可切「全部项目」回到今天的全量；
  // 未选项目时没有开关、列表天然是全量。legacy 行（project_id=''）只在「全部」出现。
  const [projectId] = useSelectedProject();
  const { projects } = useProjects();
  const [scopeSel, setScopeSel] = useState<"current" | "all" | null>(null);
  const scope = scopeSel ?? (projectId ? "current" : "all");
  const projectName = (id: string): string | null => projects.find((p) => p.id === id)?.name ?? null;

  // bundle 快查（D4）：芯片只改本列表的可见行，不展开任何详情。只取当前项目的 bundle，
  // 一次拉取即可（bundle 列表低频，不需轮询）；内部状态与下钻的 externalFilter 互不干扰。
  const stageTitles = useStageTitles();
  const [bundleSel, setBundleSel] = useState<string | null>(null);
  const [projectBundles, setProjectBundles] = useState<Bundle[]>([]);
  useEffect(() => {
    let alive = true;
    const load = projectId ? api.bundles(projectId) : Promise.resolve([] as Bundle[]);
    load.then((b) => alive && setProjectBundles(b)).catch(() => alive && setProjectBundles([]));
    return () => { alive = false; };
  }, [projectId]);

  const scoped =
    scope === "current" && projectId ? jobs.filter((job) => job.project_id === projectId) : jobs;

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  // 文件查看弹窗的目标；null 即关闭。整张表共享一个弹窗实例。
  const [viewer, setViewer] = useState<ViewerSpec | null>(null);

  const filtered = scoped.filter((job) => {
    if (kinds && !kinds.includes(job.kind)) return false;
    if (statusFilter !== "all" && job.status !== statusFilter) return false;
    if (q) {
      const hay = `${job.id} ${job.kind} ${t(`console.data.kind.${job.kind}`)} ${job.scenario} ${job.title} ${job.bundle_name ?? ""}`.toLowerCase();
      if (!hay.includes(q.toLowerCase())) return false;
    }
    if (bundleSel && job.bundle_id !== bundleSel) return false;
    if (externalFilter && !externalFilter.test(job)) return false;
    return true;
  });

  // 过滤 / 每页行数变化时回到第一页。用 React 官方的「渲染期调整状态」模式：
  // 效果等价于旧的 effect 写法，但少一次级联渲染，也不再触发 set-state-in-effect 报错。
  const filterKey = `${q}|${statusFilter}|${pageSize}|${externalFilter?.key ?? ""}|${scope}|${projectId ?? ""}|${bundleSel ?? ""}`;
  const [lastFilterKey, setLastFilterKey] = useState(filterKey);
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey);
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paged = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  const count = (s: string) => scoped.filter((j) => j.status === s).length;

  // 行内删除：确认文案与详情页同一句（说清会级联删它产生的数据）；409 拒删理由直接 alert。
  const remove = async (job: Job) => {
    if (!window.confirm(t("console.jobs.deleteConfirm"))) return;
    try {
      await api.deleteJob(job.id);
      void refresh();
      onDeleted?.();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label={t("studio.board.kpi.total")} value={scoped.length} />
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
        {projectId && (
          <span className="flex items-center gap-1">
            <FilterChip active={scope === "current"} onClick={() => setScopeSel("current")}>
              {t("studio.board.scopeCurrent")}
            </FilterChip>
            <FilterChip active={scope === "all"} onClick={() => setScopeSel("all")}>
              {t("studio.board.scopeAll")}
            </FilterChip>
          </span>
        )}
        {STATUS_FILTERS.map((s) => (
          <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)}>
            {s === "all" ? t("studio.board.all") : s}
          </FilterChip>
        ))}
        {projectId && scope === "current" && projectBundles.length > 0 && (
          <span className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground">{t("studio.board.bundleLabel")}:</span>
            <FilterChip active={bundleSel === null} onClick={() => setBundleSel(null)}>
              {t("studio.board.bundleAll")}
            </FilterChip>
            {projectBundles.map((b) => (
              <FilterChip key={b.id} active={bundleSel === b.id}
                          onClick={() => setBundleSel(bundleSel === b.id ? null : b.id)}>
                {b.name}
              </FilterChip>
            ))}
          </span>
        )}
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
                <th className="px-3 py-2">{t("studio.board.col.stage")}</th>
                <th className="px-3 py-2">{t("studio.board.col.scenario")}</th>
                <th className="px-3 py-2">{t("studio.board.col.run")}</th>
                <th className="px-3 py-2">{t("studio.board.col.created")}</th>
                <th className="px-3 py-2">{t("studio.board.col.project")}</th>
                <th className="px-3 py-2">{t("studio.board.col.bundle")}</th>
                <th className="px-3 py-2 text-right">⏱</th>
                <th className="px-3 py-2 text-right">{t("studio.board.col.actions")}</th>
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
                    <td className="px-3 py-2 text-xs" title={stageTitles[job.kind] ?? undefined}>
                      <span>{t(`console.data.kind.${job.kind}`)}</span>{" "}
                      <span className="font-mono text-muted-foreground">{job.kind}</span>
                    </td>
                    <td className="px-3 py-2">{job.scenario}</td>
                    <td className="px-3 py-2 font-mono text-xs">{job.title}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{job.created_at.slice(0, 19)}</td>
                    <td className="px-3 py-2 text-xs">
                      {job.project_id ? (
                        <Link
                          href={`/studio/projects/${job.project_id}`}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          {projectName(job.project_id) ?? job.project_id.slice(0, 6)}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground/60">{t("studio.board.legacy")}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {job.bundle_id ? (
                        <button
                          type="button"
                          onClick={() => setBundleSel(job.bundle_id)}
                          className="text-muted-foreground hover:text-foreground hover:underline"
                        >
                          {job.bundle_name ?? job.bundle_id.slice(0, 6)}
                        </button>
                      ) : (
                        <span className="text-muted-foreground/60">{t("studio.board.bundleNone")}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-muted-foreground">{durationOf(job)}</td>
                    <td className="px-3 py-2 text-right">
                      {DELETABLE.includes(job.status) && (
                        <button
                          type="button"
                          onClick={() => void remove(job)}
                          className="text-xs text-[#ef4444] transition-colors hover:underline"
                        >
                          {t("console.jobs.delete")}
                        </button>
                      )}
                    </td>
                  </tr>
                  {showFiles && (
                    <tr className="border-b border-border/60 bg-[#0d0d0d]">
                      <td colSpan={10} className="px-3 py-2">
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

"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api, type Artifact, type Job, type StageParams } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobStagePage, type FieldSpec } from "@/components/console/JobStagePage";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";
import { EmptyState, FilterChip, Pager } from "@/components/studio/primitives";
import { JobBoard, type JobFilter } from "@/components/studio/JobBoard";
import { useProjects } from "@/components/studio/ProjectSwitcher";
import { useSelectedProject } from "@/lib/project-context";
import Link from "next/link";

const KINDS: Record<string, { kind: string; fields: FieldSpec[] }> = {
  plan_size: { kind: "plan_size", fields: [] },
  generate: { kind: "generate", fields: [
    { key: "data", label: "--data", hint: "数据目录，默认 data/<场景>；留空用默认" },
    { key: "n", label: "--n", hint: "787 = 5 个 spec 都是 4 问题/记录时的计划量" },
    { key: "seed", label: "--seed" },
  ] },
  distill: { kind: "distill", fields: [
    { key: "provider_id", label: "provider", required: true, kind: "select", optionsUrl: "/console/api/distill-providers", hint: "蒸馏配置在「蒸馏配置」页创建；未选则无凭据" },
    { key: "category", label: "--category", hint: "默认取场景名" },
    { key: "examples", label: "--examples", hint: "可选：真实标注记录的 JSONL，作为 few-shot 范例" },
    { key: "n_examples", label: "--n-examples" },
    { key: "concurrency", label: "--concurrency" },
    { key: "n", label: "--n" },
    { key: "schedule", label: "--schedule", hint: "HH:MM（可选；守护模式下必填）" },
    { key: "state_dir", label: "--state-dir", hint: "进度状态目录（用量采集依据）" },
  ] },
  distill_daemon: { kind: "distill_daemon", fields: [
    { key: "provider_id", label: "provider", required: true, kind: "select", optionsUrl: "/console/api/distill-providers", hint: "蒸馏配置在「蒸馏配置」页创建；未选则无凭据" },
    { key: "category", label: "--category", hint: "默认取场景名" },
    { key: "examples", label: "--examples" },
    { key: "n_examples", label: "--n-examples" },
    { key: "concurrency", label: "--concurrency" },
    { key: "n", label: "--n" },
    { key: "schedule", label: "--schedule", required: true, hint: "HH:MM；每天蒸馏到当日配额后睡到本地该时刻（必填）" },
    { key: "state_dir", label: "--state-dir" },
  ] },
  goldset: { kind: "goldset", fields: [
    { key: "n", label: "--n", hint: "150-250 是有用区间" },
    { key: "seed", label: "--seed" },
    { key: "out", label: "--out", hint: "默认 <数据目录>.gold.jsonl" },
  ] },
  split: { kind: "split", fields: [
    { key: "calibration", label: "--calibration" },
    { key: "development", label: "--development" },
    { key: "seed", label: "--seed" },
    { key: "holdout", label: "--holdout", hint: "金标对半分进 calibration/development，永不进 train" },
  ] },
  precheck: { kind: "precheck", fields: [
    { key: "init_from", label: "--init-from", hint: "A1 用 kev-0.8b；A2/B 用裸基座的 tokenizer" },
    { key: "split", kind: "select", label: "--split", options: ["train", "calibration", "development"].map((v) => ({ value: v, label: v })) },
  ] },
  make_examples: { kind: "make_examples", fields: [
    { key: "data", label: "--data", required: true, hint: "已标注 JSONL，如 data/critical-value.jsonl（必填）" },
    { key: "n", label: "--n", hint: "范例条数，默认 8" },
    { key: "seed", label: "--seed" },
    { key: "out", label: "--out", hint: "默认 <data 同目录>/examples.jsonl" },
  ] },
};

// 每个任务的默认参数值（与后端 build() 的默认值对齐）。
// 之前用单一 initial 会把 n=787 强加到 goldset(默认 200)/make_examples(默认 8) 上，造成误导。
const DEFAULTS: Record<string, Record<string, string>> = {
  plan_size: {},
  generate: { n: "787", seed: "0" },
  distill: { n: "787", concurrency: "3" },
  distill_daemon: { n: "787", concurrency: "3" },
  goldset: { n: "200", seed: "0" },
  split: { calibration: "0.15", development: "0.15", seed: "0" },
  precheck: { init_from: "jaredpalmer/kev-0.8b", split: "train" },
  make_examples: { n: "8", seed: "0" },
};

// 数据轨流程图：主干由 train 阶段的闸门 G1/G2/G3 反推——
// G1 读 precheck、G2 读 split 的 summary 与 plan_size 的计划、G3 读 split 的 summary，
// 而 split 读生成器写出的 dataset。所以「计划→生产→划分→预检」这四步是训练前必执行的主干，
// 其余（蒸馏/守护是生成的替代轨、生成范例喂给蒸馏、金标喂给划分 --holdout）都是可选增强。
type FlowNode = { kind: string; required: boolean; note?: string };
type FlowPhase = { caption: { zh: string; en: string }; nodes: FlowNode[] };

const FLOW_PHASES: FlowPhase[] = [
  { caption: { zh: "计划", en: "Plan" }, nodes: [{ kind: "plan_size", required: true }] },
  { caption: { zh: "生产数据", en: "Produce" }, nodes: [
    { kind: "generate", required: true },
    { kind: "distill", required: false },
    { kind: "distill_daemon", required: false },
  ] },
  { caption: { zh: "划分", en: "Split" }, nodes: [{ kind: "split", required: true }] },
  { caption: { zh: "预检", en: "Precheck" }, nodes: [{ kind: "precheck", required: true }] },
];

const FLOW_AUX: FlowNode[] = [
  { kind: "make_examples", required: false, note: "distill --examples" },
  { kind: "goldset", required: false, note: "split --holdout" },
];

type TabId = "datasets" | "jobs" | "submit";

const TABS: { id: TabId; labelKey: string }[] = [
  { id: "datasets", labelKey: "studio.datasets.tab.datasets" },
  { id: "jobs", labelKey: "studio.datasets.tab.jobs" },
  { id: "submit", labelKey: "studio.datasets.tab.submit" },
];

/** 数据集 → 生成它的作业：job.artifacts_out 含数据集 id。 */
function buildArtifactToJob(jobs: Job[]): Record<string, Job> {
  const map: Record<string, Job> = {};
  for (const job of jobs) {
    for (const artifact of job.artifacts_out ?? []) map[artifact] = job;
  }
  return map;
}

function datasetScenario(artifact: Artifact, genJob?: Job): string {
  if (genJob?.scenario) return genJob.scenario;
  const name = artifact.id.includes(":") ? artifact.id.split(":")[1] : artifact.id;
  return name.split("/")[0];
}

export default function StudioDatasetsPage() {
  const { t, lang } = useLang();
  const [tab, setTab] = useState<TabId>("datasets");
  const [jobFilter, setJobFilter] = useState<JobFilter | null>(null);

  const datasets = usePoll(api.datasets, [] as Artifact[]);
  const jobs = usePoll(useCallback(() => api.jobs(), []), [] as Job[]);
  const domains = usePoll(useCallback(() => api.scenarioDomains(lang), [lang]), []);

  const artifactToJob = useMemo(() => buildArtifactToJob(jobs.value ?? []), [jobs.value]);
  const scenarioToDomain = useMemo(() => {
    const map: Record<string, string> = {};
    const labelToSlug: Record<string, string> = {};
    for (const domain of domains.value ?? []) {
      labelToSlug[domain.label] = domain.slug;
      for (const scenario of domain.scenarios) map[scenario.slug] = domain.label;
    }
    return { map, labelToSlug };
  }, [domains.value]);

  // 从数据集列表下钻：按 数据集 / 场景 / 领域 过滤 jobs 并切到 jobs 栏。
  const drill = (filter: JobFilter) => { setJobFilter(filter); setTab("jobs"); };
  const drillByDataset = (id: string) =>
    drill({ key: `dataset:${id}`, label: id, test: (j) => (j.artifacts_out ?? []).includes(id) });
  const drillByScenario = (scenario: string) =>
    drill({ key: `scenario:${scenario}`, label: scenario, test: (j) => j.scenario === scenario });
  const drillByDomain = (domainLabel: string) => {
    const slug = scenarioToDomain.labelToSlug[domainLabel];
    const scenarios = new Set((domains.value ?? []).find((d) => d.slug === slug)?.scenarios.map((s) => s.slug) ?? []);
    drill({ key: `domain:${slug}`, label: domainLabel, test: (j) => scenarios.has(j.scenario) });
  };

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">{t("studio.nav.datasets")}</h1>

      <div className="flex flex-wrap gap-1.5">
        {TABS.map((tabItem) => (
          <button
            key={tabItem.id}
            type="button"
            onClick={() => setTab(tabItem.id)}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              tab === tabItem.id ? "bg-[#1e3a8a] text-[#3b82f6]" : "text-muted-foreground hover:bg-[#161616]"
            }`}
          >
            {t(tabItem.labelKey)}
          </button>
        ))}
      </div>

      {tab === "datasets" && (
        <DatasetTable
          datasets={datasets.value ?? []}
          artifactToJob={artifactToJob}
          scenarioToDomain={scenarioToDomain.map}
          onDrillDataset={drillByDataset}
          onDrillScenario={drillByScenario}
          onDrillDomain={drillByDomain}
        />
      )}

      {tab === "jobs" && (
        <JobBoard
          kinds={Object.keys(KINDS)}
          hrefFor={(id) => `/studio/jobs/${id}`}
          jobsProp={jobs.value ?? []}
          defaultPageSize={5}
          externalFilter={jobFilter}
          onClearExternal={() => setJobFilter(null)}
          showFiles
        />
      )}

      {tab === "submit" && (
        <SubmitPanel />
      )}
    </div>
  );
}

function DatasetTable({
  datasets, artifactToJob, scenarioToDomain, onDrillDataset, onDrillScenario, onDrillDomain,
}: {
  datasets: Artifact[];
  artifactToJob: Record<string, Job>;
  scenarioToDomain: Record<string, string>;
  onDrillDataset: (id: string) => void;
  onDrillScenario: (scenario: string) => void;
  onDrillDomain: (domainLabel: string) => void;
}) {
  const { t } = useLang();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [q, setQ] = useState("");

  // 产物无 project_id 列（D2）：归属经 artifact → 生成作业 → job.project_id 派生。
  const [projectId] = useSelectedProject();
  const { projects } = useProjects();
  const [scopeSel, setScopeSel] = useState<"current" | "all" | null>(null);
  const scope = scopeSel ?? (projectId ? "current" : "all");
  const projectName = (id: string) => projects.find((p) => p.id === id)?.name ?? id.slice(0, 6);

  const filtered = datasets.filter((artifact) => {
    if (scope === "current" && projectId) {
      const pid = artifactToJob[artifact.id]?.project_id ?? "";
      if (pid !== projectId) return false;
    }
    if (!q) return true;
    const hay = `${artifact.id} ${artifact.path}`.toLowerCase();
    return hay.includes(q.toLowerCase());
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paged = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  return (
    <div className="space-y-3">
      {projectId && (
        <div className="flex items-center gap-1">
          <FilterChip active={scope === "current"} onClick={() => setScopeSel("current")}>
            {t("studio.board.scopeCurrent")}
          </FilterChip>
          <FilterChip active={scope === "all"} onClick={() => setScopeSel("all")}>
            {t("studio.board.scopeAll")}
          </FilterChip>
        </div>
      )}

      <input
        value={q}
        onChange={(e) => { setQ(e.target.value); setPage(1); }}
        placeholder={t("studio.board.search")}
        className="w-full max-w-sm rounded border border-border bg-[#111111] px-3 py-1.5 text-[13px] outline-none focus:border-primary"
      />

      {filtered.length === 0 ? (
        <EmptyState title={t("studio.board.empty")} />
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2">{t("studio.board.col.id")}</th>
                <th className="px-3 py-2">{t("studio.board.col.project")}</th>
                <th className="px-3 py-2">{t("studio.datasets.col.scenario")}</th>
                <th className="px-3 py-2">{t("studio.datasets.col.domain")}</th>
                <th className="px-3 py-2 text-right">{t("studio.datasets.col.records")}</th>
                <th className="px-3 py-2 text-right">{t("studio.datasets.col.invalid")}</th>
                <th className="px-3 py-2">{t("studio.datasets.col.path")}</th>
                <th className="px-3 py-2">{t("studio.datasets.col.job")}</th>
                <th className="px-3 py-2 text-right">JSONL</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((artifact) => {
                const genJob = artifactToJob[artifact.id];
                const scenario = datasetScenario(artifact, genJob);
                const domain = scenarioToDomain[scenario] ?? "—";
                const projId = genJob?.project_id ?? "";
                return (
                  <tr key={artifact.id} className="border-b border-border/60 transition-colors hover:bg-[#161616]">
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => onDrillDataset(artifact.id)}
                        className="font-mono text-xs text-primary hover:underline"
                      >
                        {artifact.id}
                      </button>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {projId ? (
                        <span className="text-muted-foreground">{projectName(projId)}</span>
                      ) : (
                        <span className="text-[11px] text-muted-foreground/60">{t("studio.board.legacy")}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => onDrillScenario(scenario)}
                        className="text-xs text-[#3b82f6] hover:underline"
                      >
                        {scenario}
                      </button>
                    </td>
                    <td className="px-3 py-2">
                      {domain === "—" ? (
                        <span className="text-xs text-muted-foreground">—</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onDrillDomain(domain)}
                          className="text-xs text-[#3b82f6] hover:underline"
                        >
                          {domain}
                        </button>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right text-xs">{formatNumber(Number(artifact.meta?.records ?? 0), 0)}</td>
                    <td className="px-3 py-2 text-right text-xs">{formatNumber(Number(artifact.meta?.invalid_lines ?? 0), 0)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{artifact.path}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {genJob ? (
                        <Link href={`/studio/jobs/${genJob.id}`} className="text-primary hover:underline">
                          {genJob.id}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">{t("studio.datasets.col.noJob")}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <a className="text-xs text-primary hover:underline" href={api.exportUrl(artifact.id)}>JSONL</a>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Pager
        page={safePage}
        totalPages={totalPages}
        pageSize={pageSize}
        pageSizeOptions={[10, 20, 50, 100]}
        onPage={setPage}
        onPageSize={(size) => { setPageSize(size); setPage(1); }}
        labels={{
          prev: t("studio.board.prev"),
          next: t("studio.board.next"),
          pageOf: (p, tot) => t("studio.board.pageOf", { page: p, total: tot }),
          rowsPerPage: t("studio.datasets.rowsPerPage"),
        }}
      />
    </div>
  );
}

/** 提交作业的类型导航：把 8 个 kind 按数据轨的真实流程重排成流程图，
 *  必执行主干用实心蓝点 + 常规边框，可选步骤用虚线边框 + 空心点并标注喂给哪一步。 */
function SubmitFlow({ active, onSelect }: { active: string; onSelect: (kind: string) => void }) {
  const { t, lang } = useLang();
  const zh = lang === "zh";
  const arrow = <span className="text-muted-foreground">→</span>;

  const step = (node: FlowNode) => {
    const isActive = node.kind === active;
    return (
      <button
        key={node.kind}
        type="button"
        onClick={() => onSelect(node.kind)}
        title={node.note ? `→ ${node.note}` : undefined}
        className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs transition-colors ${
          isActive ? "bg-[#1e3a8a] font-medium text-[#3b82f6]" : "text-muted-foreground hover:bg-[#161616]"
        } ${node.required ? "" : "border border-dashed border-border"}`}
      >
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          node.required ? "bg-[#3b82f6]" : "border border-[#3b82f6]/50"
        }`} />
        {t(`console.data.kind.${node.kind}`)}
      </button>
    );
  };

  return (
    <div className="rounded-md border border-border bg-[#0f0f0f] p-3">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-[#3b82f6]" />{zh ? "必执行" : "Required"}</span>
        <span className="inline-flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full border border-[#3b82f6]/50" />{zh ? "可选" : "Optional"}</span>
        <span>{zh ? "训练前必须跑完实心的主干：计划 → 生产 → 划分 → 预检" : "Finish the solid spine before training: plan → produce → split → precheck"}</span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FLOW_PHASES.map((phase, i) => (
          <Fragment key={phase.caption.en}>
            {i > 0 && arrow}
            <div className="flex flex-col gap-1 rounded-md border border-border bg-[#111111] p-2">
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {zh ? phase.caption.zh : phase.caption.en}
              </span>
              <div className="flex flex-wrap gap-1.5">{phase.nodes.map(step)}</div>
            </div>
          </Fragment>
        ))}
        {arrow}
        <span
          className="rounded-md border border-border bg-[#111111] px-2 py-1 text-xs text-muted-foreground"
          title={zh ? "在「训练」页提交" : "submit on the Train page"}
        >
          {zh ? "训练" : "Train"}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
        <span className="text-muted-foreground">{zh ? "可选增强：" : "Add-ons:"}</span>
        {FLOW_AUX.map((node) => (
          <span key={node.kind} className="inline-flex items-center gap-1 rounded border border-dashed border-border px-1 py-0.5">
            {step(node)}
            <span className="text-muted-foreground">→ {node.note}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function SubmitPanel() {
  const { t, lang } = useLang();
  const [dataKind, setDataKind] = useState("generate");

  // 优先从后端 stage_param_specs 取 schema（可配置、可版本化）；失败/未播种时回退到内置 KINDS。
  // 用 kind 匹配来判定「已加载到当前 kind」，避免 kind 切换瞬间用到上一类的字段。
  const schema = usePoll(
    useCallback(() => api.stageParams(dataKind), [dataKind]),
    null as StageParams | null,
  );
  useEffect(() => { void schema.refresh(); }, [dataKind]); // kind 变了立刻重拉
  const usingApi = !!schema.value && schema.value.kind === dataKind && schema.value.fields.length > 0;
  const active = KINDS[dataKind];
  const fields: FieldSpec[] = usingApi
    ? (schema.value!.fields as FieldSpec[])
    : active.fields;
  // 默认值来自 schema.field.default（单一真相源）；回退到内置 KINDS 时才用 DEFAULTS。
  const initial = usingApi ? undefined : (DEFAULTS[dataKind] ?? {});

  return (
    <div className="space-y-4">
      <SubmitFlow active={dataKind} onSelect={setDataKind} />
      <p className="text-xs text-muted-foreground">
        {lang === "zh"
          ? "生成与划分必须串行：先跑 generate，再跑 split。"
          : "generate and split must run serially: generate first, then split."}
      </p>

      <JobStagePage
        key={`${dataKind}:${usingApi ? "api" : "fb"}`}
        kind={active.kind}
        title={t("studio.nav.datasets")}
        fields={fields}
        initial={initial}
        enableTemplates
        submitInFormColumn
        jobHref={(id) => `/studio/jobs/${id}`}
        hideTitle
      />
    </div>
  );
}

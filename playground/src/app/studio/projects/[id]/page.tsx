"use client";

import { Fragment, use, useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  type Artifact,
  type ArtifactVersion,
  type ArtifactVersionPage,
  type Bundle,
  type BundleDetail,
  type BundleMember,
  type Event,
  type Gate,
  type Job,
  type Lineage,
  type ProjectSummary,
  type Release,
  type Review,
  type ReviewQueueItem,
  type ReviewVerdict,
} from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { EmptyState, PageHead, Panel, StatusBadge } from "@/components/studio/primitives";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { latestJobPerStage } from "@/components/studio/project/selectors";

// 6 tab（收掉 overview，其内容并入常驻页头 ProjectMasthead，对齐样稿目标态）。
type Tab = "data" | "merge" | "review" | "trainings" | "results" | "lineage";

const TABS: { id: Tab; zh: string; en: string }[] = [
  { id: "data", zh: "数据", en: "Data" },
  { id: "merge", zh: "合成", en: "Merge" },
  { id: "review", zh: "标注", en: "Review" },
  { id: "trainings", zh: "训练", en: "Trainings" },
  { id: "results", zh: "结果", en: "Results" },
  { id: "lineage", zh: "血缘", en: "Lineage" },
];

export default function StudioProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { lang } = useLang();
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("data");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([
      api.project(id), api.jobs({ project: id }), api.projectArtifacts(id),
      api.bundles(id).catch(() => [] as Bundle[]),
    ])
      .then(([s, j, a, b]) => {
        if (!alive) return;
        setSummary(s);
        setJobs(j);
        setArtifacts(a);
        setBundles(b);
        setError(null);
      })
      .catch((e) => alive && setError(String((e as { message?: string })?.message ?? e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [id]);

  return (
    <div className="space-y-6">
      <PageHead
        title={summary?.name ?? id}
        subtitle={
          summary ? (
            <span className="font-mono text-xs">
              {summary.slug} · {lang === "zh" ? "场景" : "scenario"} {summary.scenario || "—"}
            </span>
          ) : undefined
        }
        actions={
          <Link href="/studio/projects" className="text-xs text-muted-foreground hover:text-foreground">
            ← {lang === "zh" ? "项目列表" : "All projects"}
          </Link>
        }
      />

      {error && (
        <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</div>
      )}

      {summary && !loading && (
        <ProjectMasthead summary={summary} jobs={jobs} bundles={bundles} lang={lang} />
      )}

      <div className="flex flex-wrap gap-2">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={
              "rounded border px-3 py-1.5 text-xs transition-colors " +
              (tab === item.id
                ? "border-primary bg-[#1e3a8a] text-[#3b82f6]"
                : "border-border bg-[#111111] text-muted-foreground hover:text-foreground")
            }
          >
            {lang === "zh" ? item.zh : item.en}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-xs text-muted-foreground">{lang === "zh" ? "加载中…" : "Loading…"}</div>
      ) : !summary ? (
        <EmptyState title={lang === "zh" ? "找不到该项目" : "Project not found"} />
      ) : tab === "data" ? (
        <DataTab artifacts={artifacts} lang={lang} />
      ) : tab === "merge" ? (
        <MergeTab projectId={id} summary={summary} artifacts={artifacts} lang={lang} />
      ) : tab === "review" ? (
        <ReviewTab projectId={id} summary={summary} lang={lang} />
      ) : tab === "trainings" ? (
        <TrainingsTab jobs={jobs} lang={lang} />
      ) : tab === "results" ? (
        <ResultsTab projectId={id} lang={lang} />
      ) : (
        <LineageTab projectId={id} lang={lang} />
      )}
    </div>
  );
}

/** 页头 F1–F4 取「最有代表性」的 bundle：已冻结 > 已物化 > 草稿 > 退役，同级取最新。 */
function pickHeadlineBundle(bundles: Bundle[]): Bundle | null {
  if (bundles.length === 0) return null;
  const rank = (b: Bundle) => (b.status === "frozen" ? 3 : b.status === "materialized" ? 2 : b.status === "retired" ? 0 : 1);
  return [...bundles].sort((a, b) => rank(b) - rank(a) || b.created_at.localeCompare(a.created_at))[0];
}

/** 常驻页头：本轮目标 + 状态/计数 + 各阶段最新作业 + freeze 门槛 + F1–F4 + 最近活动。
 *  收掉原 overview tab，把这些项目级信息提到所有 tab 之上（对齐样稿目标态）。 */
function ProjectMasthead({ summary, jobs, bundles, lang }:
  { summary: ProjectSummary; jobs: Job[]; bundles: Bundle[]; lang: string }) {
  const zh = lang === "zh";
  const latest = latestJobPerStage(jobs);
  const headline = pickHeadlineBundle(bundles);
  return (
    <div className="space-y-3">
      <div className="space-y-3 rounded-md border border-border bg-[#111111] p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{zh ? "本轮目标" : "Goal"}</div>
            <p className="mt-1 text-sm whitespace-pre-wrap">{summary.goal || (zh ? "（未填写）" : "(empty)")}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <StatusBadge status={summary.status} />
            <span className="rounded border border-border bg-[#0d0d0d] px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              {zh ? "作业" : "jobs"} {summary.jobs} · {zh ? "产物" : "artifacts"} {summary.artifacts}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {Object.keys(latest).length === 0 ? (
            <span className="text-xs text-muted-foreground">{zh ? "还没有作业" : "No jobs yet"}</span>
          ) : Object.entries(latest).map(([stage, job]) => (
            <div key={stage} className="flex items-center gap-2 rounded border border-border bg-[#0d0d0d] px-2 py-1 text-xs">
              <span className="font-mono text-muted-foreground">{stage}</span>
              <StatusBadge status={job.status} />
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-4 border-t border-border/60 pt-3 text-xs">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{zh ? "冻结门槛" : "Freeze gate"}</span>
          <span>{zh ? "最小记录" : "min records"}: <span className="font-mono text-foreground">{summary.freeze_min_records}</span></span>
          <span>{zh ? "最小复核比" : "min review ratio"}: <span className="font-mono text-foreground">{summary.freeze_min_review_ratio.toFixed(2)}</span></span>
          {headline && (
            <span className="text-muted-foreground">{zh ? "参考 bundle" : "ref bundle"}: <span className="font-mono text-foreground">{headline.name}</span> <BundleStatusBadge status={headline.status} /></span>
          )}
        </div>
      </div>

      <FreezeChecksPanel checks={headline?.freeze_checks ?? []} lang={lang} />

      <Panel title={zh ? "最近活动" : "Recent activity"}>
        <EventList events={summary.recent_events} lang={lang} />
      </Panel>
    </div>
  );
}

function EventList({ events, lang }: { events: Event[]; lang: string }) {
  const zh = lang === "zh";
  if (events.length === 0) return <EmptyState title={zh ? "暂无事件" : "No events"} />;
  return (
    <ul className="space-y-1">
      {events.map((e) => (
        <li key={e.id} className="flex gap-2 font-mono text-[11px] text-muted-foreground">
          <span>{e.ts.slice(11, 19)}</span>
          <span className="text-foreground/60">{e.stream}</span>
          <span className="truncate">{e.line}</span>
        </li>
      ))}
    </ul>
  );
}

function DataTab({ artifacts, lang }: { artifacts: Artifact[]; lang: string }) {
  const zh = lang === "zh";
  if (artifacts.length === 0) {
    return (
      <Panel title={zh ? "项目产物版本" : "Project artifact versions"}>
        <EmptyState title={zh ? "暂无产物" : "No artifacts"} />
      </Panel>
    );
  }
  return (
    <div className="space-y-4">
      {artifacts.map((a) => (
        <ArtifactVersions key={a.id} artifact={a} lang={lang} />
      ))}
    </div>
  );
}

/** 单个产物的版本表：seq × records × sha256 × integrity × 来源作业，点行展开预览 50 条。 */
function ArtifactVersions({ artifact, lang }: { artifact: Artifact; lang: string }) {
  const zh = lang === "zh";
  const [versions, setVersions] = useState<ArtifactVersion[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.artifactVersions(artifact.id)
      .then((v) => alive && setVersions(v))
      .catch(() => alive && setVersions([]));
    return () => {
      alive = false;
    };
  }, [artifact.id]);

  return (
    <Panel title={`${artifact.name} (${artifact.kind})`}>
      {versions === null ? (
        <div className="text-xs text-muted-foreground">{zh ? "加载中…" : "Loading…"}</div>
      ) : versions.length === 0 ? (
        <EmptyState title={zh ? "历史无版本" : "No versions registered"} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>seq</TableHead>
              <TableHead className="text-right">{zh ? "记录" : "records"}</TableHead>
              <TableHead className="text-right">{zh ? "字节" : "bytes"}</TableHead>
              <TableHead>sha256</TableHead>
              <TableHead>integrity</TableHead>
              <TableHead className="text-right">created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {versions.map((v) => (
              <Fragment key={v.id}>
                <TableRow className="cursor-pointer" onClick={() => setOpen(open === v.id ? null : v.id)}>
                  <TableCell className="font-mono text-xs">{v.seq}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{v.records ?? "—"}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{v.bytes ?? "—"}</TableCell>
                  <TableCell className="font-mono text-[11px] text-muted-foreground">{v.sha256.slice(0, 12)}</TableCell>
                  <TableCell><IntegrityBadge value={v.integrity} /></TableCell>
                  <TableCell className="text-right font-mono text-xs text-muted-foreground">{v.created_at.slice(0, 10)}</TableCell>
                </TableRow>
                {open === v.id && (
                  <TableRow>
                    <TableCell colSpan={6} className="bg-[#0d0d0d]">
                      <VersionPreview version={v} lang={lang} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
          </TableBody>
        </Table>
      )}
    </Panel>
  );
}

function IntegrityBadge({ value }: { value: ArtifactVersion["integrity"] }) {
  const tone =
    value === "ok" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
    : value === "drift" ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
    : "border-destructive/40 bg-destructive/10 text-destructive";
  return <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${tone}`}>{value}</span>;
}

/** 展开行的记录预览：分页拉 50 条，每行带指纹（与服务端 split_data 同一规范化）。 */
function VersionPreview({ version, lang }: { version: ArtifactVersion; lang: string }) {
  const zh = lang === "zh";
  const [page, setPage] = useState<ArtifactVersionPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.artifactVersionRecords(version.id, { offset: 0, limit: 50 })
      .then((p) => alive && setPage(p))
      .catch((e) => alive && setError(String((e as { message?: string })?.message ?? e)));
    return () => {
      alive = false;
    };
  }, [version.id]);

  if (error) return <div className="text-xs text-destructive">{error}</div>;
  if (!page) return <div className="text-xs text-muted-foreground">{zh ? "加载中…" : "Loading…"}</div>;
  if (page.records.length === 0)
    return <div className="text-xs text-muted-foreground">{zh ? "无可预览记录（非 JSONL 或文件缺失）" : "No previewable records"}</div>;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{zh ? `共 ${page.total} 条，显示前 ${page.records.length} 条` : `${page.total} records, showing first ${page.records.length}`}</span>
        <a href={api.artifactVersionExportUrl(version.id)} className="hover:text-foreground hover:underline">
          {zh ? "导出" : "Export"}
        </a>
      </div>
      <ul className="space-y-1">
        {page.records.map((r) => (
          <li key={r.line_no} className="flex gap-2 font-mono text-[11px]">
            <span className="w-10 shrink-0 text-muted-foreground">#{r.line_no}</span>
            <span className="text-muted-foreground/60">{r.fingerprint.slice(0, 10)}</span>
            <span className="truncate text-foreground/70">{JSON.stringify(r.record)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TrainingsTab({ jobs, lang }: { jobs: Job[]; lang: string }) {
  const zh = lang === "zh";
  const trainings = jobs.filter((j) => j.stage === "train");
  if (trainings.length === 0) {
    return (
      <Panel title={zh ? "训练作业" : "Training jobs"}>
        <EmptyState title={zh ? "还没有训练作业" : "No training jobs yet"} />
      </Panel>
    );
  }
  return (
    <Panel title={zh ? "训练作业" : "Training jobs"}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{zh ? "名称" : "title"}</TableHead>
            <TableHead>scenario</TableHead>
            <TableHead>{zh ? "状态" : "status"}</TableHead>
            <TableHead className="text-right">created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trainings.map((j) => (
            <TableRow key={j.id}>
              <TableCell className="text-sm">
                <Link href={`/studio/jobs/${j.id}`} className="hover:text-foreground hover:underline">{j.title || j.id}</Link>
              </TableCell>
              <TableCell className="font-mono text-xs">{j.scenario}</TableCell>
              <TableCell><StatusBadge status={j.status} /></TableCell>
              <TableCell className="text-right font-mono text-xs text-muted-foreground">{j.created_at.slice(0, 10)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Panel>
  );
}

function ResultsTab({ projectId, lang }: { projectId: string; lang: string }) {
  const zh = lang === "zh";
  const [releases, setReleases] = useState<Release[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.projectReleases(projectId)
      .then((rows) => alive && setReleases(rows))
      .catch((e) => alive && setError(String((e as { message?: string })?.message ?? e)));
    return () => {
      alive = false;
    };
  }, [projectId]);

  const num = (v: number | null | undefined, digits = 3) => (v == null ? "—" : v.toFixed(digits));

  if (error) {
    return (
      <Panel title={zh ? "结论" : "Results"}>
        <div className="text-xs text-destructive">{error}</div>
      </Panel>
    );
  }
  if (releases === null) {
    return (
      <Panel title={zh ? "结论" : "Results"}>
        <div className="text-xs text-muted-foreground">{zh ? "加载中…" : "Loading…"}</div>
      </Panel>
    );
  }
  if (releases.length === 0) {
    return (
      <Panel title={zh ? "结论" : "Results"}>
        <EmptyState
          title={zh ? "还没有落库的结论" : "No releases recorded yet"}
          hint={zh ? "评测/对比完成后在此登记一行结论（gates 服务端现算）" : "record a release after eval/compare; gates are computed server-side"}
        />
      </Panel>
    );
  }
  return (
    <Panel title={zh ? "结论（releases）" : "Results (releases)"}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{zh ? "结论" : "Release"}</TableHead>
            <TableHead>acc</TableHead>
            <TableHead>ECE</TableHead>
            <TableHead>Brier</TableHead>
            <TableHead>AURC</TableHead>
            <TableHead>{zh ? "覆盖" : "Coverage"}</TableHead>
            <TableHead>Δ</TableHead>
            <TableHead>Gates</TableHead>
            <TableHead>{zh ? "判定" : "Verdict"}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {releases.map((rel) => (
            <TableRow key={rel.id}>
              <TableCell className="font-medium">{rel.name}</TableCell>
              <TableCell className="font-mono">{num(rel.metrics.acc)}</TableCell>
              <TableCell className="font-mono">{num(rel.metrics.ece)}</TableCell>
              <TableCell className="font-mono">{num(rel.metrics.brier)}</TableCell>
              <TableCell className="font-mono">{num(rel.metrics.aurc)}</TableCell>
              <TableCell className="font-mono">{num(rel.metrics.coverage, 2)}</TableCell>
              <TableCell className="font-mono">{num(rel.metrics.delta, 4)}</TableCell>
              <TableCell><GateCell gates={rel.gates_snapshot} /></TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <ReleaseVerdictBadge verdict={rel.verdict} />
                  {rel.bundle_sha256 && (
                    <span className="font-mono text-[10px] text-muted-foreground">{rel.bundle_sha256.slice(0, 8)}</span>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Panel>
  );
}

function ReleaseVerdictBadge({ verdict }: { verdict: Release["verdict"] }) {
  const tone =
    verdict === "accepted" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
    : verdict === "rejected" ? "border-destructive/40 bg-destructive/10 text-destructive"
    : "border-amber-500/40 bg-amber-500/10 text-amber-400";
  return <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${tone}`}>{verdict}</span>;
}

function GateCell({ gates }: { gates: Gate[] }) {
  if (gates.length === 0) return <span className="text-[10px] text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {gates.map((g) => (
        <span
          key={g.id}
          title={g.detail}
          className={`rounded border px-1 font-mono text-[10px] ${
            g.ok ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                 : "border-destructive/40 bg-destructive/10 text-destructive"}`}
        >
          {g.id}
        </span>
      ))}
    </div>
  );
}

function LineageTab({ projectId, lang }: { projectId: string; lang: string }) {
  const zh = lang === "zh";
  const [data, setData] = useState<Lineage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.projectLineage(projectId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String((e as { message?: string })?.message ?? e)));
    return () => {
      alive = false;
    };
  }, [projectId]);

  if (error) {
    return <Panel title={zh ? "血缘" : "Lineage"}><div className="text-xs text-destructive">{error}</div></Panel>;
  }
  if (data === null) {
    return <Panel title={zh ? "血缘" : "Lineage"}><div className="text-xs text-muted-foreground">{zh ? "加载中…" : "Loading…"}</div></Panel>;
  }
  if (data.nodes.length === 0) {
    return <Panel title={zh ? "血缘" : "Lineage"}><EmptyState title={zh ? "暂无血缘节点" : "No lineage nodes"} /></Panel>;
  }
  return (
    <div className="space-y-4">
      <Panel title={zh ? `节点（${data.nodes.length}）` : `Nodes (${data.nodes.length})`}>
        <div className="flex flex-wrap gap-2">
          {data.nodes.map((n) => <NodeChip key={n.id} node={n} />)}
        </div>
      </Panel>
      <Panel title={zh ? `边（${data.edges.length}）` : `Edges (${data.edges.length})`}>
        {data.edges.length === 0 ? (
          <EmptyState title={zh ? "暂无血缘边" : "No lineage edges"} />
        ) : (
          <ul className="space-y-1">
            {data.edges.map((e, i) => (
              <li key={i} className="font-mono text-[11px] text-muted-foreground">
                <span className="text-foreground/80">{e.parent}</span> →{" "}
                <span className="text-foreground/80">{e.child}</span>{" "}
                <span className="rounded border border-border bg-[#111111] px-1 text-[10px]">{e.relation}</span>
                {e.job_id && <span className="ml-1 text-[10px]">job:{e.job_id.slice(0, 6)}</span>}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function NodeChip({ node }: { node: Lineage["nodes"][number] }) {
  const tone: Record<string, string> = {
    dataset: "border-sky-500/40 bg-sky-500/10 text-sky-400",
    bundle: "border-violet-500/40 bg-violet-500/10 text-violet-400",
    run: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
    eval: "border-amber-500/40 bg-amber-500/10 text-amber-400",
    comparison: "border-rose-500/40 bg-rose-500/10 text-rose-400",
    regression: "border-rose-500/40 bg-rose-500/10 text-rose-400",
    calibration: "border-teal-500/40 bg-teal-500/10 text-teal-400",
  };
  const cls = tone[node.kind] ?? "border-border bg-[#111111] text-muted-foreground";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${cls}`}>
      {node.id}{node.version != null ? ` ·v${node.version}` : ""}
    </span>
  );
}

// ---- merge tab（数据策展：bundle 合成 / 物化 / F1–F4 冻结，PR C）----

type MemberDraft = { version_id: string; op: "include" | "exclude" | "overlay"; ord: number };

function MergeTab({ projectId, summary, artifacts, lang }:
  { projectId: string; summary: ProjectSummary; artifacts: Artifact[]; lang: string }) {
  const zh = lang === "zh";
  const [bundles, setBundles] = useState<Bundle[] | null>(null);
  const [selected, setSelected] = useState<BundleDetail | null>(null);
  const [draft, setDraft] = useState<MemberDraft[]>([]);
  const [candidates, setCandidates] = useState<ArtifactVersion[]>([]);
  const [newName, setNewName] = useState("");
  const [addVersion, setAddVersion] = useState("");
  const [addOp, setAddOp] = useState<MemberDraft["op"]>("include");
  const [diffWith, setDiffWith] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.bundles(projectId).then((b) => alive && setBundles(b)).catch(() => alive && setBundles([]));
    return () => { alive = false; };
  }, [projectId]);

  // 候选版本：把项目每个产物的不可变版本拉平，供成员选择（bundle 成员 = version_id）。
  useEffect(() => {
    let alive = true;
    Promise.all(artifacts.map((a) => api.artifactVersions(a.id).catch(() => [] as ArtifactVersion[])))
      .then((pages) => alive && setCandidates(pages.flat()))
      .catch(() => alive && setCandidates([]));
    return () => { alive = false; };
  }, [artifacts]);

  async function reloadDetail(name: string) {
    const detail = await api.bundle(projectId, name);
    setSelected(detail);
    setDraft(detail.members.map((m) => ({ version_id: m.version_id, op: m.op, ord: m.ord })));
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null); setMessage(null);
    try { await fn(); } catch (e) { setError(String((e as { message?: string })?.message ?? e)); }
    finally { setBusy(false); }
  }

  const editable = selected?.status === "draft";
  const labelForVersion = (vid: string) => {
    const v = candidates.find((c) => c.id === vid);
    return v ? `${v.artifact_id} · seq ${v.seq} · ${v.records ?? "?"}` : vid;
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_1fr]">
      <Panel title={zh ? "Bundle 列表" : "Bundles"}>
        <div className="flex gap-2">
          <input value={newName} onChange={(e) => setNewName(e.target.value)}
            placeholder={zh ? "新 bundle 名（禁点号）" : "new bundle name"}
            className="min-w-0 flex-1 rounded border border-border bg-[#0d0d0d] px-2 py-1 text-xs" />
          <button type="button" disabled={busy || !newName.trim()}
            onClick={() => run(async () => {
              const created = await api.createBundle(projectId, { name: newName.trim() });
              setNewName("");
              setBundles(await api.bundles(projectId));
              await reloadDetail(created.name);
            })}
            className="rounded border border-border px-2 py-1 text-xs hover:text-foreground disabled:opacity-50">
            {zh ? "新建" : "Create"}
          </button>
        </div>
        <ul className="mt-3 space-y-1">
          {(bundles ?? []).map((b) => (
            <li key={b.id}>
              <button type="button" onClick={() => run(() => reloadDetail(b.name))}
                className={"flex w-full items-center justify-between rounded border px-2 py-1 text-xs " +
                  (selected?.id === b.id ? "border-primary/60 bg-[#1e3a8a]/30" : "border-border hover:text-foreground")}>
                <span className="font-mono">{b.name}</span>
                <BundleStatusBadge status={b.status} />
              </button>
            </li>
          ))}
          {bundles !== null && bundles.length === 0 && (
            <li className="text-xs text-muted-foreground">{zh ? "还没有 bundle" : "No bundles yet"}</li>
          )}
        </ul>
      </Panel>

      <div className="space-y-4">
        {error && <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</div>}
        {message && <div className="rounded border border-border bg-[#111111] px-3 py-2 text-xs text-muted-foreground">{message}</div>}
        {!selected ? (
          <Panel title={zh ? "选中一个 bundle" : "Select a bundle"}>
            <EmptyState title={zh ? "左侧选择或新建一个 bundle" : "Pick or create a bundle on the left"} />
          </Panel>
        ) : (
          <>
            <Panel title={<span className="font-mono">{selected.name}</span>}>
              <div className="flex flex-wrap items-center gap-4 text-xs">
                <span className="text-muted-foreground">status: <BundleStatusBadge status={selected.status} /></span>
                <span className="text-muted-foreground">records: <span className="font-mono text-foreground">{selected.records ?? "—"}</span></span>
                <span className="text-muted-foreground">sha256: <span className="font-mono text-foreground">{(selected.sha256 ?? "—").slice(0, 12)}</span></span>
                <span className="text-muted-foreground">review ratio: <span className="font-mono text-foreground">{(selected.review_ratio ?? 0).toFixed(3)}</span></span>
              </div>

              <div className="mt-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{zh ? "成员（按 ord）" : "Members (ordered)"}</span>
                  {editable && (
                    <span className="flex items-center gap-2">
                      <select value={addVersion} onChange={(e) => setAddVersion(e.target.value)}
                        className="rounded border border-border bg-[#0d0d0d] px-1 py-0.5 text-xs">
                        <option value="">{zh ? "选版本…" : "pick version…"}</option>
                        {candidates.map((c) => (
                          <option key={c.id} value={c.id}>{c.artifact_id} · seq {c.seq}</option>
                        ))}
                      </select>
                      <select value={addOp} onChange={(e) => setAddOp(e.target.value as MemberDraft["op"])}
                        className="rounded border border-border bg-[#0d0d0d] px-1 py-0.5 text-xs">
                        <option value="include">include</option>
                        <option value="exclude">exclude</option>
                        <option value="overlay">overlay</option>
                      </select>
                      <button type="button" disabled={!addVersion}
                        onClick={() => { if (addVersion) { setDraft([...draft, { version_id: addVersion, op: addOp, ord: draft.length }]); setAddVersion(""); } }}
                        className="rounded border border-border px-2 py-0.5 text-xs hover:text-foreground disabled:opacity-50">+ {zh ? "加成员" : "add"}</button>
                    </span>
                  )}
                </div>
                {draft.length === 0 ? (
                  <div className="text-xs text-muted-foreground">{zh ? "没有成员" : "No members"}</div>
                ) : (
                  <ul className="space-y-1">
                    {draft.map((m, i) => {
                      const stat = selected.members.find((s) => s.version_id === m.version_id);
                      return (
                        <li key={`${m.version_id}-${i}`} className="flex items-center gap-2 text-xs">
                          <span className="w-6 font-mono text-muted-foreground">{i}</span>
                          {editable ? (
                            <select value={m.op} onChange={(e) => setDraft(draft.map((x, xi) => xi === i ? { ...x, op: e.target.value as MemberDraft["op"] } : x))}
                              className="rounded border border-border bg-[#0d0d0d] px-1 py-0.5">
                              <option value="include">include</option>
                              <option value="exclude">exclude</option>
                              <option value="overlay">overlay</option>
                            </select>
                          ) : (
                            <span className="font-mono">{m.op}</span>
                          )}
                          <span className="min-w-0 flex-1 truncate font-mono" title={labelForVersion(m.version_id)}>{labelForVersion(m.version_id)}</span>
                          {stat && <MemberStats member={stat} />}
                          {editable && (
                            <>
                              <button type="button" disabled={i === 0}
                                onClick={() => setDraft(swap(draft, i, i - 1))}
                                className="rounded border border-border px-1.5 hover:text-foreground disabled:opacity-40">↑</button>
                              <button type="button" disabled={i === draft.length - 1}
                                onClick={() => setDraft(swap(draft, i, i + 1))}
                                className="rounded border border-border px-1.5 hover:text-foreground disabled:opacity-40">↓</button>
                              <button type="button" onClick={() => setDraft(draft.filter((_, xi) => xi !== i))}
                                className="rounded border border-destructive/40 px-1.5 text-destructive hover:text-foreground">×</button>
                            </>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {editable && (
                  <button type="button" disabled={busy}
                    onClick={() => run(async () => {
                      await api.setBundleMembers(projectId, selected.name,
                        draft.map((m, i) => ({ ...m, ord: i })));
                      await reloadDetail(selected.name);
                      setMessage(zh ? "成员已保存" : "Members saved");
                    })}
                    className="rounded border border-border px-3 py-1.5 text-xs hover:text-foreground disabled:opacity-50">{zh ? "保存成员" : "Save members"}</button>
                )}
                {(selected.status === "draft" || selected.status === "materialized") && (
                  <button type="button" disabled={busy}
                    onClick={() => run(async () => {
                      const { job_id } = await api.materializeBundle(projectId, selected.name);
                      setMessage(zh ? `物化作业已起：${job_id.slice(0, 8)}（稍后点刷新）` : `Materialize job ${job_id.slice(0, 8)} started (refresh later)`);
                    })}
                    className="rounded border border-primary/50 bg-[#1e3a8a]/30 px-3 py-1.5 text-xs text-[#3b82f6] disabled:opacity-50">{zh ? "物化" : "Materialize"}</button>
                )}
                {selected.status !== "frozen" && (
                  <button type="button" disabled={busy}
                    onClick={() => run(async () => {
                      try {
                        const res = await api.freezeBundle(projectId, selected.name);
                        await reloadDetail(selected.name);
                        setMessage(zh ? `已冻结${res.warnings.length ? `，${res.warnings.length} 条软告警` : ""}`
                                      : `Frozen${res.warnings.length ? `, ${res.warnings.length} warnings` : ""}`);
                        setBundles(await api.bundles(projectId));
                      } catch {
                        await reloadDetail(selected.name);   // F1/F4 硬拒：服务端已落 freeze_checks，重读展示红项
                      }
                    })}
                    className="rounded border border-border px-3 py-1.5 text-xs hover:text-foreground disabled:opacity-50">{zh ? "冻结" : "Freeze"}</button>
                )}
                <button type="button" disabled={busy}
                  onClick={() => run(() => reloadDetail(selected.name))}
                  className="rounded border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50">{zh ? "刷新" : "Refresh"}</button>
              </div>
            </Panel>

            <FreezePolicyPanel projectId={projectId} summary={summary} lang={lang}
              onBusy={setBusy} onError={setError} onMessage={setMessage} />
            <DiffPanel projectId={projectId} selected={selected} bundles={bundles ?? []} lang={lang}
              diffWith={diffWith} setDiffWith={setDiffWith} onBusy={setBusy} onError={setError} />
          </>
        )}
      </div>
    </div>
  );
}

function swap(list: MemberDraft[], a: number, b: number): MemberDraft[] {
  const out = [...list];
  [out[a], out[b]] = [out[b], out[a]];
  return out;
}

function BundleStatusBadge({ status }: { status: Bundle["status"] }) {
  const tone =
    status === "frozen" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
    : status === "materialized" ? "border-sky-500/40 bg-sky-500/10 text-sky-400"
    : status === "retired" ? "border-border bg-[#111111] text-muted-foreground"
    : "border-amber-500/40 bg-amber-500/10 text-amber-400";
  return <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${tone}`}>{status}</span>;
}

function MemberStats({ member }: { member: BundleMember }) {
  const reasons = Object.entries(member.drop_reasons ?? {})
    .filter(([, n]) => n).map(([k, n]) => `${k}:${n}`).join(" ");
  return (
    <span className="font-mono text-[11px] text-muted-foreground">
      {member.records_kept ?? "—"}/{member.records_in ?? "—"}{reasons ? ` (${reasons})` : ""}
    </span>
  );
}

function ReviewVerdictBadge({ verdict }: { verdict: ReviewVerdict }) {
  const tone =
    verdict === "accept" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
    : verdict === "drop" ? "border-destructive/40 bg-destructive/10 text-destructive"
    : verdict === "flag" ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
    : verdict === "relabel" ? "border-sky-500/40 bg-sky-500/10 text-sky-400"
    : "border-border bg-[#111111] text-muted-foreground";
  return <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${tone}`}>{verdict}</span>;
}

function ReviewTab({ projectId, summary, lang }:
  { projectId: string; summary: ProjectSummary; lang: string }) {
  const zh = lang === "zh";
  const [queue, setQueue] = useState<ReviewQueueItem[] | null>(null);
  const [reviews, setReviews] = useState<{ items: Review[]; total: number } | null>(null);
  const [seed, setSeed] = useState(42);
  const [includeDecided, setIncludeDecided] = useState(false);
  const [index, setIndex] = useState(0);
  const [note, setNote] = useState("");
  const [labels, setLabels] = useState("");
  const [importText, setImportText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const emptyScenario = !summary.scenario;

  async function load() {
    const [q, r] = await Promise.all([
      api.reviewQueue(projectId, { seed, include_decided: includeDecided ? 1 : 0 }),
      api.listReviews(projectId, { origin: "all" }),
    ]);
    setQueue(q.items); setReviews(r); setIndex(0);
  }

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.reviewQueue(projectId, { seed, include_decided: includeDecided ? 1 : 0 }),
      api.listReviews(projectId, { origin: "all" }),
    ])
      .then(([q, r]) => { if (alive) { setQueue(q.items); setReviews(r); setIndex(0); } })
      .catch((e) => alive && setError(String((e as { message?: string })?.message ?? e)));
    return () => { alive = false; };
  }, [projectId, seed, includeDecided]);

  async function decide(verdict: ReviewVerdict) {
    const item = queue?.[index];
    if (!item || emptyScenario) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const parsedLabels = labels.split(",").map((s) => s.trim()).filter(Boolean);
      await api.upsertReview(projectId, item.fingerprint,
        { verdict, note, labels: parsedLabels.length ? parsedLabels : undefined });
      setNote(""); setLabels("");
      await load();
      setMessage(zh ? "已记录决定" : "Decision recorded");
    } catch (e) {
      setError(String((e as { message?: string })?.message ?? e));
    } finally { setBusy(false); }
  }

  async function runImport() {
    const rows = importText.split("\n").map((l) => l.trim()).filter(Boolean)
      .map((l) => { try { return JSON.parse(l) as Record<string, unknown>; } catch { return null; } })
      .filter((x): x is Record<string, unknown> => x !== null);
    if (!rows.length) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const res = await api.importReviews(projectId, rows);
      setMessage(zh ? `导入 ${res.imported} 条，${res.unmatched.length} 条未匹配`
        : `imported ${res.imported}, unmatched ${res.unmatched.length}`);
      setImportText("");
      await load();
    } catch (e) {
      setError(String((e as { message?: string })?.message ?? e));
    } finally { setBusy(false); }
  }

  function onKey(e: React.KeyboardEvent) {
    if (busy || emptyScenario) return;
    const k = e.key.toLowerCase();
    if (k === "y" || k === "enter") { e.preventDefault(); void decide("accept"); }
    else if (k === "x") { void decide("drop"); }
    else if (k === "f") { void decide("flag"); }
    else if (k === "r") { void decide("relabel"); }
    else if (k === "arrowright") setIndex((i) => Math.min(i + 1, Math.max(0, (queue?.length ?? 1) - 1)));
    else if (k === "arrowleft") setIndex((i) => Math.max(i - 1, 0));
  }

  const current = queue?.[index] ?? null;
  const questions = (current?.record?.questions ?? {}) as Record<string, { type?: string; label?: unknown }>;

  return (
    <div className="space-y-4" tabIndex={0} onKeyDown={onKey}>
      {error && <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</div>}
      {message && <div className="rounded border border-border bg-[#111111] px-3 py-2 text-xs text-muted-foreground">{message}</div>}
      {emptyScenario && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
          {zh ? "项目未绑定场景，先补场景才能标注（决定作用域是场景）。" : "Project has no scenario; set one before labelling."}
        </div>
      )}

      <Panel title={zh ? "标注队列" : "Review queue"}>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-muted-foreground">{zh ? "已复核(含继承)" : "decided"}:
            <span className="ml-1 font-mono text-foreground">{reviews?.total ?? "—"}</span></span>
          <span className="text-muted-foreground">{zh ? "待标注" : "in queue"}:
            <span className="ml-1 font-mono text-foreground">{queue?.length ?? "—"}</span></span>
          <span className="text-muted-foreground">F3 min:
            <span className="ml-1 font-mono text-foreground">{summary.freeze_min_review_ratio.toFixed(2)}</span></span>
          <label className="flex items-center gap-1 text-muted-foreground">
            seed
            <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)}
              className="w-16 rounded border border-border bg-[#0d0d0d] px-1 py-0.5 font-mono" />
          </label>
          <label className="flex items-center gap-1 text-muted-foreground">
            <input type="checkbox" checked={includeDecided} onChange={(e) => setIncludeDecided(e.target.checked)} />
            {zh ? "含已决定" : "include decided"}
          </label>
          <button type="button" disabled={busy} onClick={() => { setBusy(true); void load().finally(() => setBusy(false)); }}
            className="rounded border border-border px-2 py-0.5 hover:text-foreground disabled:opacity-50">{zh ? "刷新" : "Reload"}</button>
          <span className="ml-auto text-[10px] text-muted-foreground">{zh ? "键位：y/Enter 接受 · r 重标 · x 丢弃 · f 标记 · ←→ 切换" : "keys: y/Enter accept · r relabel · x drop · f flag · ←→ nav"}</span>
        </div>

        <div className="mt-4">
          {!current ? (
            <EmptyState title={queue === null ? (zh ? "加载中…" : "Loading…") : (zh ? "队列为空" : "Queue empty")} />
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[11px] text-muted-foreground">{current.fingerprint.slice(0, 16)}…</span>
                <span className="text-[11px] text-muted-foreground">{index + 1} / {queue?.length ?? 0}</span>
                {current.existing_verdict && <span className="text-[11px] text-muted-foreground">已有: <ReviewVerdictBadge verdict={current.existing_verdict} /></span>}
              </div>
              <div className="max-h-40 overflow-auto rounded border border-border bg-[#0d0d0d] p-2 text-xs whitespace-pre-wrap">
                {String((current.record as { state?: string }).state ?? "—")}
              </div>
              <div className="space-y-1">
                {Object.entries(questions).map(([qid, q]) => (
                  <div key={qid} className="flex items-center gap-2 text-xs">
                    <span className="font-mono text-muted-foreground">{qid}</span>
                    <span className="text-foreground">{String(q.type ?? "?")} = {String(q.label ?? "—")}</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <input value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder={zh ? "备注（可选）" : "note (optional)"}
                  className="min-w-0 flex-1 rounded border border-border bg-[#0d0d0d] px-2 py-1 text-xs" />
                <input value={labels} onChange={(e) => setLabels(e.target.value)}
                  placeholder={zh ? "标签，逗号分隔" : "labels, comma-sep"}
                  className="w-40 rounded border border-border bg-[#0d0d0d] px-2 py-1 text-xs" />
              </div>
              <div className="flex flex-wrap gap-2">
                {(["accept", "relabel", "drop", "flag"] as ReviewVerdict[]).map((v) => (
                  <button key={v} type="button" disabled={busy || emptyScenario} onClick={() => void decide(v)}
                    className="rounded border border-border px-2 py-1 text-xs hover:text-foreground disabled:opacity-50">{v}</button>
                ))}
              </div>
            </div>
          )}
        </div>
      </Panel>

      <Panel title={zh ? "已有决定（含继承，标出来源轮）" : "Decided (incl. inherited)"}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>fingerprint</TableHead><TableHead>verdict</TableHead>
              <TableHead>{zh ? "来源" : "origin"}</TableHead><TableHead>labels</TableHead><TableHead>{zh ? "备注" : "note"}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(reviews?.items ?? []).map((rv) => (
              <TableRow key={rv.id}>
                <TableCell className="font-mono text-[11px]">{rv.fingerprint.slice(0, 12)}…</TableCell>
                <TableCell><ReviewVerdictBadge verdict={rv.verdict} /></TableCell>
                <TableCell className="font-mono text-[11px] text-muted-foreground">{rv.origin_project_slug || "—"}</TableCell>
                <TableCell className="text-[11px]">{(rv.labels ?? []).join(", ")}</TableCell>
                <TableCell className="text-[11px] text-muted-foreground">{rv.note}</TableCell>
              </TableRow>
            ))}
            {reviews !== null && reviews.items.length === 0 && (
              <TableRow><TableCell colSpan={5} className="text-xs text-muted-foreground">{zh ? "还没有标注" : "No reviews yet"}</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Panel>

      <Panel title={zh ? "导入 reviews.jsonl" : "Import reviews.jsonl"}>
        <textarea value={importText} onChange={(e) => setImportText(e.target.value)} rows={4}
          placeholder={zh ? "每行一条 JSON（带 fingerprint，或带 record_id 反查）" : "one JSON row per line (fingerprint, or record_id lookup)"}
          className="w-full rounded border border-border bg-[#0d0d0d] p-2 font-mono text-xs" />
        <button type="button" disabled={busy || !importText.trim() || emptyScenario}
          onClick={() => void runImport()}
          className="mt-2 rounded border border-border px-2 py-1 text-xs hover:text-foreground disabled:opacity-50">{zh ? "导入" : "Import"}</button>
      </Panel>
    </div>
  );
}

function FreezeChecksPanel({ checks, lang }: { checks: Gate[]; lang: string }) {
  const zh = lang === "zh";
  if (checks.length === 0) return null;
  return (
    <Panel title={zh ? "冻结判定 F1–F4" : "Freeze checks (F1–F4)"}>
      <ul className="space-y-1">
        {checks.map((c) => (
          <li key={c.id} className="flex items-start gap-2 text-xs">
            <span className={"mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full " + (c.ok ? "bg-emerald-500" : "bg-destructive")} />
            <span className="font-mono text-muted-foreground">{c.id}</span>
            <span className="flex-1">{c.detail}</span>
            <span className="font-mono text-[11px] text-muted-foreground">{c.actual} / {c.need}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function FreezePolicyPanel({ projectId, summary, lang, onBusy, onError, onMessage }:
  { projectId: string; summary: ProjectSummary; lang: string;
    onBusy: (b: boolean) => void; onError: (e: string | null) => void; onMessage: (m: string | null) => void }) {
  const zh = lang === "zh";
  const [minRecords, setMinRecords] = useState(String(summary.freeze_min_records));
  const [minRatio, setMinRatio] = useState(String(summary.freeze_min_review_ratio));
  return (
    <Panel title={zh ? "冻结门槛（不追溯已冻结）" : "Freeze policy (not retroactive)"}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="text-muted-foreground">{zh ? "最小记录" : "min records"}</label>
        <input value={minRecords} onChange={(e) => setMinRecords(e.target.value)}
          className="w-24 rounded border border-border bg-[#0d0d0d] px-2 py-1 font-mono" />
        <label className="text-muted-foreground">{zh ? "最小复核比" : "min review ratio"}</label>
        <input value={minRatio} onChange={(e) => setMinRatio(e.target.value)}
          className="w-24 rounded border border-border bg-[#0d0d0d] px-2 py-1 font-mono" />
        <button type="button"
          onClick={async () => {
            onBusy(true); onError(null);
            try {
              await api.setFreezePolicy(projectId, {
                freeze_min_records: Number(minRecords), freeze_min_review_ratio: Number(minRatio) });
              onMessage(zh ? "门槛已更新" : "Policy updated");
            } catch (e) { onError(String((e as { message?: string })?.message ?? e)); }
            finally { onBusy(false); }
          }}
          className="rounded border border-border px-3 py-1 text-xs hover:text-foreground">{zh ? "保存门槛" : "Save"}</button>
      </div>
    </Panel>
  );
}

function DiffPanel({ projectId, selected, bundles, lang, diffWith, setDiffWith, onBusy, onError }:
  { projectId: string; selected: BundleDetail; bundles: Bundle[]; lang: string;
    diffWith: string; setDiffWith: (s: string) => void;
    onBusy: (b: boolean) => void; onError: (e: string | null) => void }) {
  const zh = lang === "zh";
  const [result, setResult] = useState<{ only_left: number; only_right: number; common: number } | null>(null);
  const others = bundles.filter((b) => b.id !== selected.id);
  if (others.length === 0) return null;
  return (
    <Panel title={zh ? "与另一 bundle 按指纹比较" : "Diff by fingerprint"}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select value={diffWith} onChange={(e) => setDiffWith(e.target.value)}
          className="rounded border border-border bg-[#0d0d0d] px-2 py-1 font-mono">
          <option value="">{zh ? "选另一 bundle…" : "other bundle…"}</option>
          {others.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        <button type="button" disabled={!diffWith}
          onClick={async () => {
            onBusy(true); onError(null);
            try {
              const d = await api.bundleDiff(selected.id, diffWith);
              setResult({ only_left: d.only_left.length, only_right: d.only_right.length, common: d.common.length });
            } catch (e) { onError(String((e as { message?: string })?.message ?? e)); }
            finally { onBusy(false); }
          }}
          className="rounded border border-border px-3 py-1 hover:text-foreground disabled:opacity-50">{zh ? "比较" : "Diff"}</button>
        {result && (
          <span className="font-mono text-muted-foreground">
            only_left {result.only_left} · only_right {result.only_right} · common {result.common}
          </span>
        )}
      </div>
    </Panel>
  );
}

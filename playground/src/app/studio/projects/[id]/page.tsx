"use client";

import { Fragment, use, useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  type Artifact,
  type ArtifactVersion,
  type ArtifactVersionPage,
  type Event,
  type Job,
  type JobDetail,
  type ProjectSummary,
} from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { EmptyState, PageHead, Panel, StatusBadge } from "@/components/studio/primitives";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { latestJobPerStage } from "@/components/studio/project/selectors";

type Tab = "overview" | "data" | "trainings" | "results" | "lineage";

const TABS: { id: Tab; zh: string; en: string }[] = [
  { id: "overview", zh: "概览", en: "Overview" },
  { id: "data", zh: "数据", en: "Data" },
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([api.project(id), api.jobs({ project: id }), api.projectArtifacts(id)])
      .then(([s, j, a]) => {
        if (!alive) return;
        setSummary(s);
        setJobs(j);
        setArtifacts(a);
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
      ) : tab === "overview" ? (
        <OverviewTab summary={summary} jobs={jobs} lang={lang} />
      ) : tab === "data" ? (
        <DataTab artifacts={artifacts} lang={lang} />
      ) : tab === "trainings" ? (
        <TrainingsTab jobs={jobs} lang={lang} />
      ) : tab === "results" ? (
        <ResultsTab jobs={jobs} lang={lang} />
      ) : (
        <LineageTab artifacts={artifacts} lang={lang} />
      )}
    </div>
  );
}

function OverviewTab({ summary, jobs, lang }: { summary: ProjectSummary; jobs: Job[]; lang: string }) {
  const latest = latestJobPerStage(jobs);
  const zh = lang === "zh";
  return (
    <div className="space-y-4">
      <Panel title={zh ? "项目目标" : "Goal"}>
        <p className="text-sm whitespace-pre-wrap">{summary.goal || (zh ? "（未填写）" : "(empty)")}</p>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <div><dt className="text-muted-foreground">{zh ? "状态" : "status"}</dt><dd>{summary.status}</dd></div>
          <div><dt className="text-muted-foreground">{zh ? "作业数" : "jobs"}</dt><dd>{summary.jobs}</dd></div>
          <div><dt className="text-muted-foreground">{zh ? "产物数" : "artifacts"}</dt><dd>{summary.artifacts}</dd></div>
          <div><dt className="text-muted-foreground">{zh ? "冻结最小记录" : "freeze min records"}</dt><dd>{summary.freeze_min_records}</dd></div>
          <div><dt className="text-muted-foreground">{zh ? "冻结最小复核比" : "freeze min review ratio"}</dt><dd>{summary.freeze_min_review_ratio}</dd></div>
        </dl>
      </Panel>

      <Panel title={zh ? "各阶段最新作业" : "Latest job per stage"}>
        {Object.keys(latest).length === 0 ? (
          <EmptyState title={zh ? "还没有作业" : "No jobs yet"} />
        ) : (
          <div className="flex flex-wrap gap-4">
            {Object.entries(latest).map(([stage, job]) => (
              <div key={stage} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-muted-foreground">{stage}</span>
                <StatusBadge status={job.status} />
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title={zh ? "最近事件" : "Recent events"}>
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

function ResultsTab({ jobs, lang }: { jobs: Job[]; lang: string }) {
  const zh = lang === "zh";
  const done = jobs.filter((j) => j.stage === "train" && j.status === "succeeded");
  const [details, setDetails] = useState<Record<string, JobDetail | null>>({});

  useEffect(() => {
    const succeeded = jobs.filter((j) => j.stage === "train" && j.status === "succeeded");
    let alive = true;
    Promise.all(
      succeeded.map((j) => api.job(j.id).then((d) => [j.id, d] as const).catch(() => [j.id, null] as const)),
    ).then((pairs) => alive && setDetails(Object.fromEntries(pairs)));
    return () => {
      alive = false;
    };
  }, [jobs]);

  if (done.length === 0) {
    return (
      <Panel title={zh ? "结果" : "Results"}>
        <EmptyState title={zh ? "还没有成功的训练可读结果" : "No succeeded training reads yet"} />
      </Panel>
    );
  }
  return (
    <div className="space-y-4">
      {done.map((j) => {
        const detail = details[j.id];
        const last = detail?.metrics?.[detail.metrics.length - 1];
        return (
          <Panel key={j.id} title={<Link href={`/studio/jobs/${j.id}`} className="hover:underline">{j.title || j.id}</Link>}>
            {!detail ? (
              <div className="text-xs text-muted-foreground">{zh ? "加载中…" : "Loading…"}</div>
            ) : (
              <div className="flex flex-wrap gap-6 text-xs">
                <span className="text-muted-foreground">{zh ? "指标条数" : "metrics"}: <span className="text-foreground">{detail.metrics.length}</span></span>
                {last && (
                  <>
                    <span className="text-muted-foreground">loss: <span className="font-mono text-foreground">{last.loss.toFixed(4)}</span></span>
                    <span className="text-muted-foreground">kl: <span className="font-mono text-foreground">{last.kl.toFixed(4)}</span></span>
                    <span className="text-muted-foreground">step: <span className="font-mono text-foreground">{last.step}/{last.total}</span></span>
                  </>
                )}
                <span className="text-muted-foreground">{zh ? "产物" : "artifacts"}: <span className="text-foreground">{detail.artifacts.length}</span></span>
              </div>
            )}
          </Panel>
        );
      })}
    </div>
  );
}

function LineageTab({ artifacts, lang }: { artifacts: Artifact[]; lang: string }) {
  const zh = lang === "zh";
  const edges: { parent: string; child: string; relation: string }[] = [];
  for (const a of artifacts) {
    for (const e of a.lineage ?? []) edges.push(e);
  }
  return (
    <Panel title={zh ? "产物血缘" : "Artifact lineage"}>
      {edges.length === 0 ? (
        <EmptyState title={zh ? "暂无血缘边" : "No lineage edges"} hint={zh ? "血缘执行属于后续计划" : "lineage execution is a follow-on plan"} />
      ) : (
        <ul className="space-y-1">
          {edges.map((e, i) => (
            <li key={i} className="font-mono text-[11px] text-muted-foreground">
              <span className="text-foreground/70">{e.parent}</span> → <span className="text-foreground/70">{e.child}</span> ({e.relation})
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

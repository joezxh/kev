"use client";

import { useEffect, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { JobStagePage } from "@/components/console/JobStagePage";
import { useLang } from "@/lib/i18n";
import { api, type Gate, type Release } from "@/lib/console";
import { EmptyState, FilterChip, Panel } from "@/components/studio/primitives";
import { useProjects } from "@/components/studio/ProjectSwitcher";
import { useSelectedProject } from "@/lib/project-context";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

export default function StudioPublishPage() {
  const { t, lang } = useLang();
  return (
    <div className="space-y-8">
      <JobStagePage
        kind="publish"
        title={t("studio.nav.publish")}
        hideScenario
        initial={{ run: "runs/cv-8b-lora-v1/checkpoint", repo: "jaredpalmer/kev-0.8b", card: "docs/model-cards/kev-0.8b.md", private: "0", replace: "0" }}
        jobHref={(id) => `/studio/jobs/${id}`}
        fields={[
          { key: "run", label: "--run", hint: "checkpoint 目录，默认 runs/<name>/checkpoint" },
          { key: "repo", label: "--repo" },
          { key: "card", label: "--card", hint: lang === "zh" ? "模型卡 markdown 路径" : "model card markdown, e.g. docs/model-cards/kev-0.8b.md" },
          { key: "message", label: "--message" },
          { key: "private", kind: "select", label: "--private", options: [{ value: "0", label: "0" }, { value: "1", label: "1" }] },
          { key: "tag", label: "--tag" },
          { key: "revision", label: "--revision" },
          { key: "replace", kind: "select", label: "--replace", options: [{ value: "0", label: "0" }, { value: "1", label: "1" }] },
        ]}
      >
        <Alert>
          <AlertTitle>{t("studio.nav.publish")}</AlertTitle>
          <AlertDescription>{t("console.publish.hint")}</AlertDescription>
        </Alert>
      </JobStagePage>

      <ReleasesPanel lang={lang} />
    </div>
  );
}

/** 发布记录表（req 5 发布结论）：本项目走 api.projectReleases；全部项目用 N+1 汇总各项目 releases。
 *  表结构复用详情页 ResultsTab，但 verdict/gate/num 是详情页局部组件不可 import，故在此内联重实现。 */
function ReleasesPanel({ lang }: { lang: string }) {
  const zh = lang === "zh";
  const [projectId] = useSelectedProject();
  const { projects } = useProjects();
  const [scopeSel, setScopeSel] = useState<"current" | "all" | null>(null);
  const scope = scopeSel ?? (projectId ? "current" : "all");
  const [rows, setRows] = useState<Release[] | null>(null);

  useEffect(() => {
    let alive = true;
    // ids 为空时 Promise.all([]) 自然解析为 []，无需同步 setState（避开级联渲染）。
    const ids = scope === "current" && projectId ? [projectId] : projects.map((p) => p.id);
    Promise.all(ids.map((id) => api.projectReleases(id).catch(() => [] as Release[])))
      .then((groups) => {
        if (!alive) return;
        setRows(groups.flat().sort((a, b) => b.created_at.localeCompare(a.created_at)));
      });
    return () => {
      alive = false;
    };
  }, [scope, projectId, projects]);

  const projectName = (id: string) => projects.find((p) => p.id === id)?.name ?? id.slice(0, 6);
  const num = (v: number | null | undefined, digits = 3) => (v == null ? "—" : v.toFixed(digits));

  return (
    <div className="space-y-3">
      {projectId && (
        <div className="flex items-center gap-1">
          <FilterChip active={scope === "current"} onClick={() => setScopeSel("current")}>
            {zh ? "本项目" : "This project"}
          </FilterChip>
          <FilterChip active={scope === "all"} onClick={() => setScopeSel("all")}>
            {zh ? "全部项目" : "All projects"}
          </FilterChip>
        </div>
      )}

      <Panel
        title={zh ? "发布记录" : "Releases"}
        desc={zh ? "候选 / 接受 / 拒绝的发布结论，含指标与闸门快照" : "candidate / accepted / rejected releases with metrics and gate snapshots"}
      >
        {rows === null ? (
          <div className="text-xs text-muted-foreground">{zh ? "加载中…" : "Loading…"}</div>
        ) : rows.length === 0 ? (
          <EmptyState
            title={zh ? "还没有发布记录" : "No releases recorded yet"}
            hint={zh ? "评测/对比完成后在项目详情登记一行结论" : "record a release from the project detail page after eval/compare"}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{zh ? "发布" : "Release"}</TableHead>
                {scope === "all" && <TableHead>{zh ? "项目" : "project"}</TableHead>}
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
              {rows.map((rel) => (
                <TableRow key={rel.id}>
                  <TableCell className="font-medium">
                    {rel.name}
                    {rel.train_job_id && (
                      <div className="font-mono text-[10px] text-muted-foreground">job:{rel.train_job_id.slice(0, 6)}</div>
                    )}
                  </TableCell>
                  {scope === "all" && (
                    <TableCell className="text-xs text-muted-foreground">{projectName(rel.project_id)}</TableCell>
                  )}
                  <TableCell className="font-mono">{num(rel.metrics.acc)}</TableCell>
                  <TableCell className="font-mono">{num(rel.metrics.ece)}</TableCell>
                  <TableCell className="font-mono">{num(rel.metrics.brier)}</TableCell>
                  <TableCell className="font-mono">{num(rel.metrics.aurc)}</TableCell>
                  <TableCell className="font-mono">{num(rel.metrics.coverage, 2)}</TableCell>
                  <TableCell className="font-mono">{num(rel.metrics.delta, 4)}</TableCell>
                  <TableCell><GateCell gates={rel.gates_snapshot} /></TableCell>
                  <TableCell><ReleaseVerdictBadge verdict={rel.verdict} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>
    </div>
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

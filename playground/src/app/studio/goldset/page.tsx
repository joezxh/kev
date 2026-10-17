"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { JobStagePage } from "@/components/console/JobStagePage";
import { useLang } from "@/lib/i18n";
import { api, type Review, type ReviewVerdict } from "@/lib/console";
import { EmptyState, FilterChip, Panel } from "@/components/studio/primitives";
import { useProjects } from "@/components/studio/ProjectSwitcher";
import { useSelectedProject } from "@/lib/project-context";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const VERDICTS: ReviewVerdict[] = ["accept", "relabel", "edit", "drop", "flag"];

export default function StudioGoldsetPage() {
  const { t, lang } = useLang();
  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-lg font-semibold">{t("studio.goldset.title")}</h1>
        <Alert>
          <AlertTitle>{t("studio.goldset.subtitle")}</AlertTitle>
          <AlertDescription>
            {lang === "zh"
              ? "make_goldset.py audit 对比两份标注的分歧率，超阈值则非 0 退出。"
              : "make_goldset.py audit compares disagreement between two labellings; above threshold it exits non-zero."}
          </AlertDescription>
        </Alert>
      </section>

      <JobStagePage
        kind="goldset_audit"
        title={t("studio.nav.goldset")}
        hideScenario
        initial={{ a: "data/cv.a.jsonl", b: "data/cv.b.jsonl", out: "", threshold: "0.05" }}
        jobHref={(id) => `/studio/jobs/${id}`}
        fields={[
          { key: "a", label: "A", hint: lang === "zh" ? "第一份标注（如厂商甲）" : "first labelling (e.g. vendor A)" },
          { key: "b", label: "B", hint: lang === "zh" ? "第二份标注（如厂商乙）" : "second labelling (e.g. vendor B)" },
          { key: "out", label: "--out", hint: lang === "zh" ? "分歧记录输出（可空）" : "disagreement output (optional)" },
          { key: "threshold", label: "--threshold", hint: lang === "zh" ? "最差问题分歧率超此值则非 0 退出" : "worst-question disagreement above this exits non-zero" },
        ]}
      />

      <GoldsetPanel lang={lang} />
    </div>
  );
}

/** 金标集 / 复核列表（req 5 复核队列）：本项目走 api.listReviews；全部项目用 N+1 汇总。
 *  顶部给出 verdict 五态分布（D6），并提供「去复核队列」跳转详情页 review tab（键盘优先复核）。 */
function GoldsetPanel({ lang }: { lang: string }) {
  const zh = lang === "zh";
  const [projectId] = useSelectedProject();
  const { projects } = useProjects();
  const [scopeSel, setScopeSel] = useState<"current" | "all" | null>(null);
  const scope = scopeSel ?? (projectId ? "current" : "all");
  const [rows, setRows] = useState<Review[] | null>(null);

  useEffect(() => {
    let alive = true;
    // ids 为空时 Promise.all([]) 自然解析为 []，无需同步 setState（避开级联渲染）。
    const ids = scope === "current" && projectId ? [projectId] : projects.map((p) => p.id);
    Promise.all(ids.map((id) => api.listReviews(id).then((pg) => pg.items).catch(() => [] as Review[])))
      .then((groups) => {
        if (!alive) return;
        setRows(groups.flat().sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
      });
    return () => {
      alive = false;
    };
  }, [scope, projectId, projects]);

  const projectName = (id: string) => projects.find((p) => p.id === id)?.name ?? id.slice(0, 6);
  const counts = VERDICTS.map((v) => ({ v, n: (rows ?? []).filter((r) => r.verdict === v).length }));

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
        title={zh ? "金标集 / 复核" : "Goldset / reviews"}
        actions={
          projectId ? (
            <Link
              href={`/studio/projects/${projectId}?tab=review`}
              className="rounded border border-border bg-[#0d0d0d] px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
            >
              {zh ? "去复核队列 →" : "Open review queue →"}
            </Link>
          ) : undefined
        }
      >
        <div className="mb-3 flex flex-wrap gap-2">
          {counts.map(({ v, n }) => (
            <span key={v} className="flex items-center gap-1.5 rounded border border-border bg-[#0d0d0d] px-2 py-1 text-xs">
              <VerdictBadge verdict={v} />
              <span className="font-mono text-muted-foreground">{n}</span>
            </span>
          ))}
        </div>

        {rows === null ? (
          <div className="text-xs text-muted-foreground">{zh ? "加载中…" : "Loading…"}</div>
        ) : rows.length === 0 ? (
          <EmptyState
            title={zh ? "还没有复核记录" : "No reviews recorded yet"}
            hint={zh ? "在项目详情的标注 tab 完成复核后在此汇总" : "reviews appear here after you label them in the project's review tab"}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{zh ? "指纹" : "fingerprint"}</TableHead>
                <TableHead>scenario</TableHead>
                {scope === "all" && <TableHead>{zh ? "项目" : "project"}</TableHead>}
                <TableHead>{zh ? "判定" : "verdict"}</TableHead>
                <TableHead>{zh ? "标签" : "labels"}</TableHead>
                <TableHead>{zh ? "复核人" : "reviewer"}</TableHead>
                <TableHead className="text-right">{zh ? "更新" : "updated"}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-[11px] text-muted-foreground">{r.fingerprint.slice(0, 10)}</TableCell>
                  <TableCell className="font-mono text-xs">{r.scenario}</TableCell>
                  {scope === "all" && (
                    <TableCell className="text-xs text-muted-foreground">{projectName(r.origin_project_id)}</TableCell>
                  )}
                  <TableCell><VerdictBadge verdict={r.verdict} /></TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.labels.length ? r.labels.join(", ") : "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.reviewer || "—"}</TableCell>
                  <TableCell className="text-right font-mono text-xs text-muted-foreground">{r.updated_at.slice(0, 16).replace("T", " ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: ReviewVerdict }) {
  const tone: Record<ReviewVerdict, string> = {
    accept: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
    relabel: "border-amber-500/40 bg-amber-500/10 text-amber-400",
    edit: "border-sky-500/40 bg-sky-500/10 text-sky-400",
    drop: "border-destructive/40 bg-destructive/10 text-destructive",
    flag: "border-violet-500/40 bg-violet-500/10 text-violet-400",
  };
  return <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${tone[verdict]}`}>{verdict}</span>;
}

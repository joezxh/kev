"use client";

import Link from "next/link";
import { useCallback } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { GatePanel } from "@/components/console/GatePanel";
import { JobTable } from "@/components/console/JobTable";
import { usePoll } from "@/components/console/usePoll";

const STAGES = [
  { href: "/console/datasets", key: "console.nav.data", stage: "data" },
  { href: "/console/train", key: "console.nav.train", stage: "train" },
  { href: "/console/eval", key: "console.nav.eval", stage: "benchmark" },
  { href: "/console/images", key: "console.nav.image", stage: "image" },
  { href: "/console/deploy", key: "console.nav.deploy", stage: "deploy" },
] as const;

export default function OverviewPage() {
  const { t, lang } = useLang();
  const loadJobs = useCallback(() => api.jobs(), []);
  const loadArtifacts = useCallback(() => api.artifacts(), []);
  const loadGates = useCallback(() => api.gates("image", "critical-value"), []);
  const jobs = usePoll(loadJobs, []);
  const artifacts = usePoll(loadArtifacts, []);
  const gates = usePoll(loadGates, []);

  const backendDown = jobs.error !== null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold">{t("console.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("console.subtitle")}</p>
      </header>

      {backendDown && (
        <Alert variant="destructive">
          <AlertTitle>{lang === "zh" ? "编排服务不可达" : "Orchestrator unreachable"}</AlertTitle>
          <AlertDescription>
            <p>{jobs.error}</p>
            <p className="mt-1 font-mono text-xs">
              {lang === "zh"
                ? "在 WSL2 里启动它：uv run python -m kev.console（只绑 127.0.0.1:8790）"
                : "Start it inside WSL2: uv run python -m kev.console (binds 127.0.0.1:8790 only)"}
            </p>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-3 sm:grid-cols-5">
        {STAGES.map((item) => (
          <Link key={item.href} href={item.href}
                className="rounded-md border border-border p-3 transition-colors hover:bg-accent">
            <div className="text-sm font-medium">{t(item.key)}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {jobs.value.filter((job) => job.stage === item.stage).length}{" "}
              {lang === "zh" ? "个作业" : "jobs"}
            </div>
          </Link>
        ))}
      </div>

      <GatePanel gates={gates.value} />

      <section className="space-y-2">
        <h2 className="text-sm font-medium">{lang === "zh" ? "全部作业" : "All jobs"}</h2>
        <JobTable jobs={jobs.value} onChanged={() => window.location.reload()} />
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium">
          {lang === "zh" ? "产物与血缘" : "Artifacts and lineage"}
        </h2>
        {artifacts.value.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {lang === "zh" ? "还没有产物" : "No artifacts yet"}
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {artifacts.value.map((artifact) => (
              <li key={artifact.id} className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono text-xs">{artifact.id}</span>
                <span className="text-xs text-muted-foreground">{artifact.path}</span>
                {artifact.lineage?.map((edge) => (
                  <span key={`${edge.parent}-${edge.relation}`} className="text-xs text-muted-foreground">
                    ← {edge.relation} ← {edge.parent}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
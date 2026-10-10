"use client";

import { useCallback, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobStagePage } from "@/components/console/JobStagePage";
import { usePoll } from "@/components/console/usePoll";
import { EmptyState } from "@/components/studio/primitives";
import { JobBoardSection } from "@/components/studio/JobBoardSection";
import { StudioTabs } from "@/components/studio/StudioTabs";

const DEPLOY_TABS = [
  { href: "/studio/deploy", labelKey: "studio.tab.run" },
  { href: "/studio/deploy/canary", labelKey: "studio.tab.canary" },
  { href: "/studio/deploy/health", labelKey: "studio.tab.health" },
  { href: "/studio/deploy/metrics", labelKey: "studio.tab.metrics" },
];

export default function StudioDeployPage() {
  const { t, lang } = useLang();
  const [action, setAction] = useState<"deploy" | "smoke">("deploy");
  const loadEndpoints = useCallback(() => api.endpoints(), []);
  const loadCal = useCallback(() => api.artifacts("calibration"), []);
  const endpoints = usePoll(loadEndpoints, { endpoints: [] });
  const calibrations = usePoll(loadCal, []);
  const latestCal = calibrations.value[0];
  const temperature = latestCal ? String(latestCal.meta?.workload_temperature ?? "") : "";
  const calRun = latestCal ? String(latestCal.id).split(":")[1] ?? "" : "";

  return (
    <div className="space-y-8">
      <StudioTabs tabs={DEPLOY_TABS} />
      <Alert>
        <AlertTitle>{t("console.deploy.priorWarning")}</AlertTitle>
        <AlertDescription>
          {lang === "zh"
            ? "本页不提供任何「关闭人工确认」的开关 —— 医疗场景默认模型建议 + 人工确认。"
            : "This page offers no switch to disable the human check: medical use is model-advises, human-confirms by default."}
        </AlertDescription>
      </Alert>

      <div className="flex gap-1.5">
        {(["deploy", "smoke"] as const).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setAction(name)}
            className={`rounded-md px-2.5 py-1 font-mono text-xs transition-colors ${
              name === action ? "bg-[#1e3a8a] text-[#3b82f6]" : "text-muted-foreground hover:bg-[#161616]"
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      {action === "deploy" ? (
        <JobStagePage
          key={latestCal?.id ?? "no-calibration"}
          kind="deploy"
          gateStage="deploy"
          title={t("studio.nav.deploy")}
          initial={{ temperature }}
          fields={[
            { key: "temperature", label: "TEMPERATURE", hint: lang === "zh" ? `必填，来自 calibration.json${temperature ? `（已自动填入：${calRun} → ${temperature}）` : "；先跑 calibrate"}` : "Required, from calibration.json (pre-filled when available)" },
            { key: "run", label: "--run", hint: "留空则用 runs/<run_name>" },
            { key: "port", label: "--port", hint: lang === "zh" ? "默认 8008。双端点共存时换端口" : "Defaults to 8008" },
          ]}
        />
      ) : (
        <JobStagePage
          key="smoke"
          kind="smoke"
          title={t("console.deploy.smoke")}
          fields={[{ key: "base_url", label: "--base-url" }]}
          initial={{ base_url: "http://127.0.0.1:8008" }}
          submitLabel={t("console.deploy.smoke")}
        >
          <p className="text-sm text-muted-foreground">
            {lang === "zh"
              ? "5 个场景各 1 例。看 p 分布与 argmax，别只看分数。"
              : "One case per scenario. Read the distribution and argmax, not just the score."}
          </p>
        </JobStagePage>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-medium">{t("studio.deploy.endpoints")}</h2>
        {endpoints.value.endpoints.length === 0 ? (
          <EmptyState title={t("studio.deploy.noEndpoints")} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>id</TableHead>
                <TableHead>path</TableHead>
                <TableHead>port</TableHead>
                <TableHead className="text-right">status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {endpoints.value.endpoints.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-mono text-xs">{e.id}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{e.path}</TableCell>
                  <TableCell className="font-mono text-xs">{String(e.meta?.port ?? "—")}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">{String(e.meta?.status ?? "—")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      <JobBoardSection
        title={`${t("studio.nav.deploy")} · jobs`}
        kinds={["deploy", "smoke"]}
        hrefFor={(id) => `/studio/deploy/${id}`}
      />
    </div>
  );
}

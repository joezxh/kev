"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobStagePage } from "@/components/console/JobStagePage";
import { usePoll } from "@/components/console/usePoll";

export default function DeployPage() {
  const { t, lang } = useLang();
  const [action, setAction] = useState<"deploy" | "smoke">("deploy");
  const loadEndpoints = useCallback(() => api.endpoints(), []);
  const loadSmoke = useCallback(() => api.artifacts("smoke"), []);
  const endpoints = usePoll(loadEndpoints, { endpoints: [] });
  const smoke = usePoll(loadSmoke, []);
  // 温度自动带出（与 image 页同源）：最近一次 calibrate 的 workload_temperature。
  const loadCal = useCallback(() => api.artifacts("calibration"), []);
  const calibrations = usePoll(loadCal, []);
  const latestCal = calibrations.value[0];
  const temperature = latestCal ? String(latestCal.meta?.workload_temperature ?? "") : "";
  const calRun = latestCal ? String(latestCal.id).split(":")[1] ?? "" : "";

  return (
    <div className="space-y-6">
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
          <Button key={name} size="sm" variant={name === action ? "secondary" : "ghost"}
                  onClick={() => setAction(name)}>
            <span className="font-mono text-xs">{name}</span>
          </Button>
        ))}
      </div>

      {action === "deploy" ? (
        <JobStagePage
          key={latestCal?.id ?? "no-calibration"}
          kind="deploy"
          gateStage="deploy"
          title={t("console.nav.deploy")}
          initial={{ temperature }}
          fields={[
            { key: "temperature", label: "TEMPERATURE",
              hint: lang === "zh"
                ? `必填，来自 calibration.json${temperature ? `（已自动填入：${calRun} → ${temperature}）` : "；先跑 calibrate"}` 
                : "Required, from calibration.json (pre-filled from the latest calibrate when available)" },
            { key: "run", label: "--run", hint: "留空则用 runs/<run_name>" },
            { key: "port", label: "--port",
              hint: lang === "zh"
                ? "默认 8008。双端点共存时换端口，并同步改 playground 的 /kev rewrite"
                : "Defaults to 8008. Use another port to coexist with a running endpoint" },
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
              ? "5 个场景各 1 例。看 p 分布与 argmax，别只看分数：形状不对说明权重或字段名有问题。"
              : "One case per scenario. Read the distribution and argmax, not just the score: a wrong shape means the weights or field names are wrong."}
          </p>
        </JobStagePage>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium">{t("console.deploy.endpoints")}</h2>
        {endpoints.value.endpoints.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {lang === "zh" ? "还没有端点" : "No endpoints yet"}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>run</TableHead><TableHead>temperature</TableHead>
                <TableHead>url</TableHead>
                <TableHead className="text-right">{lang === "zh" ? "问答页" : "Q&A page"}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {endpoints.value.endpoints.map((artifact) => (
                <TableRow key={artifact.id}>
                  <TableCell className="font-mono text-xs">
                    {artifact.meta.modal
                      ? <span className="mr-1 rounded bg-secondary px-1 py-0.5 text-[10px]">Modal</span>
                      : null}
                    {String(artifact.meta.run ?? "—")}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {String(artifact.meta.temperature ?? "—")}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{artifact.path}</TableCell>
                  <TableCell className="text-right">
                    <Link className="text-xs underline" href="/">
                      {lang === "zh" ? "打开" : "Open"}
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <p className="text-xs text-muted-foreground">{t("console.deploy.modelAdvisory")}</p>
      </section>

      {smoke.value.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-medium">{t("console.deploy.smoke")}</h2>
          <ul className="space-y-1 font-mono text-xs text-muted-foreground">
            {smoke.value.map((artifact) => <li key={artifact.id}>{artifact.path}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
}
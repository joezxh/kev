"use client";

import { useCallback, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobStagePage, type FieldSpec } from "@/components/console/JobStagePage";
import { usePoll } from "@/components/console/usePoll";
import { deltaBadge, formatMetric, metricAt, objectAt } from "@/components/console/format";
import { MetricDeltaBar, type MetricPair } from "@/components/console/MetricDeltaBar";
import { ReliabilityDiagram, type TopBin } from "@/components/console/ReliabilityDiagram";
import { CoverageCurve, type SelectiveBin } from "@/components/console/CoverageCurve";

/**
 * 阶段 3 · 评测。
 *
 * G4「增益真实」只能由 baseline + benchmark + compare 三件套产出 —— kev.benchmark 的
 * report.json 里没有 bootstrap 键（它写的是 paired_flip），所以「跑一次 benchmark 就能
 * 判增益」是错的，UI 必须把三步串起来呈现。
 */
const KINDS: Record<string, { kind: string; fields: FieldSpec[] }> = {
  baseline: { kind: "baseline", fields: [
    { key: "baseline", label: "--run", hint: "零样本对照的 checkpoint" },
    { key: "data", label: "--data",
      hint: "数据目录前缀；默认 data/<scenario>（读 development.jsonl）。与 benchmark 必须同源" },
    { key: "device", kind: "select", label: "--device",
      options: ["cuda", "cpu", "mps"].map((v) => ({ value: v, label: v })) },
  ] },
  benchmark: { kind: "benchmark", fields: [
    { key: "run", label: "--run",
      hint: "要打分的 checkpoint 目录；留空用 runs/<run_name>。公开套件回归时用它分别打 candidate 与 baseline" },
    { key: "data", label: "--data",
      hint: "数据目录前缀；默认 data/<scenario>（读 development.jsonl）。蒸馏链路需与 split 的 data 对齐" },
    { key: "device", kind: "select", label: "--device",
      options: ["cuda", "cpu", "mps"].map((v) => ({ value: v, label: v })) },
    { key: "remote", label: "--remote", hint: "远程端点 URL；填了则不打本地 checkpoint" },
    { key: "remote_model", label: "--remote-model", hint: "默认 kev-latest" },
    { key: "remote_concurrency", label: "--remote-concurrency", hint: "默认 1" },
    { key: "suite", label: "--suite", hint: "冻结 suite（如 evals/v7/decision-v7）；填了则替代 --data —— 这是 G6 的证据来源" },
    { key: "split", label: "--split", hint: "development / calibration / train（suite 模式下生效）" },
    { key: "allow_test", kind: "select", label: "--allow-test",
      options: [{ value: "0", label: "0" }, { value: "1", label: "1" }],
      hint: "读锁定 test 分区" },
    { key: "date_facts", kind: "select", label: "--date_facts",
      options: [{ value: "0", label: "0" }, { value: "1", label: "1" }],
      hint: "打分前对 state 套 with_date_facts" },
    { key: "rotations", label: "--rotations", hint: "选项循环旋转平均次数，默认 1" },
  ] },
  compare: { kind: "compare", fields: [
    { key: "public", kind: "select", label: "public",
      options: [{ value: "0", label: "0（workload 增益，G4）" }, { value: "1", label: "1（公开套件回归，G6）" }],
      hint: "public=1 产出独立的 regression 产物，与 G4 的 comparison 互不覆盖" },
    { key: "candidate", label: "--candidate", hint: "留空用 runs/<run_name>-eval；公开套件对比时指向 candidate 在 suite 上的打分目录" },
    { key: "reference", label: "--reference", hint: "留空用 runs/<run_name>-baseline-eval" },
  ] },
  calibrate: { kind: "calibrate", fields: [] },
};

export default function EvalPage() {
  const { t, lang } = useLang();
  const [evalKind, setEvalKind] = useState("benchmark");
  const loadComparison = useCallback(() => api.artifacts("comparison"), []);
  const comparison = usePoll(loadComparison, []);
  const active = KINDS[evalKind];
  const latest = comparison.value[0];

  const low = latest ? metricAt(latest.meta, ["paired", "acc", "ci95", 0]) : undefined;
  const high = latest ? metricAt(latest.meta, ["paired", "acc", "ci95", 1]) : undefined;
  const badge = deltaBadge(low !== undefined && high !== undefined ? [low, high] : undefined);

  // 图表数据源：candidate 是微调后、reference 是 baseline，两者只在 compare 的产物里同时存在。
  // 单跑 benchmark 只有 candidate，图表会退化成空态提示而不是画半张图。
  const pairs: MetricPair[] = latest
    ? ["acc", "ece", "brier", "nll", "aurc", "confident_error_rate", "coverage_at_5pct_error"]
        .map((name) => ({
          name,
          reference: metricAt(latest.meta, ["clean", "reference", name]),
          candidate: metricAt(latest.meta, ["clean", "candidate", name]),
        }))
    : [];
  const topBins = objectAt(latest?.meta, ["clean", "candidate", "top_bins"]) as
    Record<string, TopBin> | undefined;
  const selective = objectAt(latest?.meta, ["clean", "candidate", "selective"]) as
    Record<string, SelectiveBin> | undefined;

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-lg font-semibold">{t("console.nav.eval")}</h1>
        <div className="flex flex-wrap gap-1.5">
          {Object.keys(KINDS).map((name) => (
            <button key={name} type="button" onClick={() => setEvalKind(name)}
                    className={`rounded-md px-2.5 py-1 font-mono text-xs transition-colors ${
                      name === evalKind ? "bg-secondary text-secondary-foreground" : "hover:bg-accent"}`}>
              {name}
            </button>
          ))}
        </div>
        <Alert>
          <AlertTitle>{lang === "zh" ? "顺序不能乱" : "The order matters"}</AlertTitle>
          <AlertDescription>
            {lang === "zh"
              ? "baseline 与 benchmark 必须用同一份 development.jsonl —— compare 要求两侧 suite_sha256 一致，而它是数据文件内容的哈希。配对 CI 只在 compare 的产物里。"
              : "baseline and benchmark must score the same development.jsonl: compare requires matching suite_sha256, which is the content hash of the data file. The paired CI exists only in compare's output."}
          </AlertDescription>
        </Alert>
      </section>

      <JobStagePage
        key={evalKind}
        kind={active.kind}
        gateStage="image"
        title={t("console.nav.eval")}
        fields={active.fields}
        initial={{ device: "cuda", baseline: "jaredpalmer/kev-0.8b" }}
      />

      <section className="space-y-3">
        <h2 className="text-sm font-medium">
          {lang === "zh" ? "配对 CI（G4 的判据）" : "Paired CI (what G4 reads)"}
        </h2>
        {!latest ? (
          <p className="text-sm text-muted-foreground">
            {lang === "zh" ? "还没有 compare 产物" : "No comparison artifact yet"}
          </p>
        ) : (
          <div className="space-y-2">
            <p className={badge.ok ? "text-sm text-emerald-600" : "text-sm text-destructive"}>
              {badge.label} — {badge.detail}
            </p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>metric</TableHead>
                  <TableHead>baseline</TableHead><TableHead>fine-tuned</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {["acc", "ece", "confident_error_rate", "coverage_at_5pct_error", "aurc"].map((name) => (
                  <TableRow key={name}>
                    <TableCell className="font-mono text-xs">{name}</TableCell>
                    <TableCell className="text-xs">
                      {formatMetric(metricAt(latest.meta, ["clean", "reference", name]))}
                    </TableCell>
                    <TableCell className="text-xs">
                      {formatMetric(metricAt(latest.meta, ["clean", "candidate", name]))}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="text-xs text-muted-foreground">{t("console.eval.overconfident")}</p>
          </div>
        )}
      </section>

      <section className="space-y-6">
        <h2 className="text-sm font-medium">
          {lang === "zh" ? "指标差与校准" : "Deltas and calibration"}
        </h2>
        <div className="space-y-1">
          <h3 className="text-xs text-muted-foreground">
            {lang === "zh" ? "微调 vs baseline" : "fine-tuned vs baseline"}
          </h3>
          <MetricDeltaBar pairs={pairs} />
        </div>
        <div className="space-y-1">
          <h3 className="text-xs text-muted-foreground">
            {lang === "zh" ? "高置信区间可靠性（过度自信）" : "Top-confidence reliability (overconfidence)"}
          </h3>
          <ReliabilityDiagram
            bins={topBins}
            ece={metricAt(latest?.meta, ["clean", "candidate", "ece"])}
          />
        </div>
        <div className="space-y-1">
          <h3 className="text-xs text-muted-foreground">
            {lang === "zh" ? "覆盖 vs 错误率" : "Coverage vs error rate"}
          </h3>
          <CoverageCurve
            selective={selective}
            coverageAt5Pct={metricAt(latest?.meta, ["clean", "candidate", "coverage_at_5pct_error"])}
            coverageAt1Pct={metricAt(latest?.meta, ["clean", "candidate", "coverage_at_1pct_error"])}
          />
        </div>
      </section>
    </div>
  );
}
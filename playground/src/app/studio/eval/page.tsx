"use client";

import { useCallback, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobStagePage, type FieldSpec } from "@/components/console/JobStagePage";
import { usePoll } from "@/components/console/usePoll";
import { deltaBadge, metricAt } from "@/components/console/format";
import { ComparisonTable } from "@/components/studio/ComparisonTable";
import { EmptyState, Panel, StatusBadge } from "@/components/studio/primitives";
import { JobBoardSection } from "@/components/studio/JobBoardSection";
import { StudioTabs } from "@/components/studio/StudioTabs";

const KINDS: Record<string, { kind: string; fields: FieldSpec[] }> = {
  baseline: { kind: "baseline", fields: [
    { key: "baseline", label: "--run", hint: "零样本对照的 checkpoint" },
    { key: "data", label: "--data", hint: "数据目录前缀；默认 data/<scenario>（读 development.jsonl）" },
    { key: "device", kind: "select", label: "--device", options: ["cuda", "cpu", "mps"].map((v) => ({ value: v, label: v })) },
  ] },
  benchmark: { kind: "benchmark", fields: [
    { key: "run", label: "--run", hint: "要打分的 checkpoint 目录；留空用 runs/<run_name>" },
    { key: "data", label: "--data", hint: "数据目录前缀；默认 data/<scenario>（读 development.jsonl）" },
    { key: "device", kind: "select", label: "--device", options: ["cuda", "cpu", "mps"].map((v) => ({ value: v, label: v })) },
    { key: "remote", label: "--remote", hint: "远程端点 URL；填了则不打本地 checkpoint" },
    { key: "remote_model", label: "--remote-model", hint: "默认 kev-latest" },
    { key: "remote_concurrency", label: "--remote-concurrency", hint: "默认 1" },
    { key: "suite", label: "--suite", hint: "冻结 suite（如 evals/v7/decision-v7）" },
    { key: "split", label: "--split", hint: "development / calibration / train" },
    { key: "allow_test", kind: "select", label: "--allow-test", options: [{ value: "0", label: "0" }, { value: "1", label: "1" }] },
    { key: "date_facts", kind: "select", label: "--date_facts", options: [{ value: "0", label: "0" }, { value: "1", label: "1" }] },
    { key: "rotations", label: "--rotations", hint: "选项循环旋转平均次数，默认 1" },
  ] },
  compare: { kind: "compare", fields: [
    { key: "public", kind: "select", label: "public", options: [{ value: "0", label: "0（workload 增益，G4）" }, { value: "1", label: "1（公开套件回归，G6）" }] },
    { key: "candidate", label: "--candidate", hint: "留空用 runs/<run_name>-eval" },
    { key: "reference", label: "--reference", hint: "留空用 runs/<run_name>-baseline-eval" },
  ] },
  calibrate: { kind: "calibrate", fields: [] },
};

const METRIC_NAMES = ["acc", "ece", "brier", "nll", "aurc", "confident_error_rate", "coverage_at_5pct_error"];

const EVAL_TABS = [
  { href: "/studio/eval", labelKey: "studio.tab.run" },
  { href: "/studio/eval/compare", labelKey: "studio.tab.compare" },
];

export default function StudioEvalPage() {
  const { t, lang } = useLang();
  const [evalKind, setEvalKind] = useState("benchmark");
  const loadComparison = useCallback(() => api.artifacts("comparison"), []);
  const comparison = usePoll(loadComparison, []);
  const active = KINDS[evalKind];
  const latest = comparison.value[0];

  const low = latest ? metricAt(latest.meta, ["paired", "acc", "ci95", 0]) : undefined;
  const high = latest ? metricAt(latest.meta, ["paired", "acc", "ci95", 1]) : undefined;
  const badge = deltaBadge(low !== undefined && high !== undefined ? [low, high] : undefined);

  const pairs = latest
    ? METRIC_NAMES.map((name) => ({
        name,
        reference: metricAt(latest.meta, ["clean", "reference", name]),
        candidate: metricAt(latest.meta, ["clean", "candidate", name]),
      }))
    : [];

  return (
    <div className="space-y-8">
      <StudioTabs tabs={EVAL_TABS} />
      <section className="space-y-3">
        <h1 className="text-lg font-semibold">{t("studio.nav.eval")}</h1>
        <div className="flex flex-wrap gap-1.5">
          {Object.keys(KINDS).map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setEvalKind(name)}
              className={`rounded-md px-2.5 py-1 font-mono text-xs transition-colors ${
                name === evalKind ? "bg-[#1e3a8a] text-[#3b82f6]" : "text-muted-foreground hover:bg-[#161616]"
              }`}
            >
              {name}
            </button>
          ))}
        </div>
        <Alert>
          <AlertTitle>{lang === "zh" ? "顺序不能乱" : "The order matters"}</AlertTitle>
          <AlertDescription>
            {lang === "zh"
              ? "baseline 与 benchmark 必须用同一份 development.jsonl —— compare 要求两侧 suite_sha256 一致。配对 CI 只在 compare 的产物里。"
              : "baseline and benchmark must score the same development.jsonl: compare requires matching suite_sha256. The paired CI exists only in compare's output."}
          </AlertDescription>
        </Alert>
      </section>

      <JobStagePage
        key={evalKind}
        kind={active.kind}
        gateStage="image"
        title={t("studio.nav.eval")}
        fields={active.fields}
      />

      <section className="space-y-3">
        <h2 className="text-sm font-medium">{t("studio.eval.report")}</h2>
        {!latest ? (
          <EmptyState title={t("studio.eval.noComparison")} />
        ) : (
          <Panel desc={latest.id}>
            <div className="mb-3 flex items-center gap-2">
              <StatusBadge status={badge.ok ? "succeeded" : "failed"} label={badge.label} />
              <span className="text-xs text-muted-foreground">{badge.detail}</span>
            </div>
            <ComparisonTable
              rows={pairs}
              metricLabel={t("studio.eval.metric")}
              candidateLabel={t("studio.eval.candidate")}
              referenceLabel={t("studio.eval.reference")}
            />
          </Panel>
        )}
      </section>

      <JobBoardSection
        title={`${t("studio.nav.eval")} · jobs`}
        kinds={["baseline", "benchmark", "compare", "calibrate"]}
        hrefFor={(id) => `/studio/eval/${id}`}
      />
    </div>
  );
}

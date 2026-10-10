"use client";

import { useMemo, useState } from "react";
import { useLang } from "@/lib/i18n";
import { ComparisonTable } from "@/components/studio/ComparisonTable";
import { StudioTabs } from "@/components/studio/StudioTabs";
import { PageHead, Panel, StatusBadge, Field, FormGrid } from "@/components/studio/primitives";
import { deltaBadge, metricAt } from "@/components/console/format";

const EVAL_TABS = [
  { href: "/studio/eval", labelKey: "studio.tab.run" },
  { href: "/studio/eval/compare", labelKey: "studio.tab.compare" },
];

const METRIC_NAMES = ["acc", "ece", "brier", "nll", "aurc", "confident_error_rate", "coverage_at_5pct_error"];
const RUNS = ["kev-4b-a2", "kev-4b-a1", "kev-9b-b", "kev-baseline", "kev-0.8b-smoke"];

// 样例对比产物（结构同 api.artifacts("comparison")[0].meta）
const SAMPLE = {
  id: "comparison:kev-4b-a2:kev-baseline",
  meta: {
    suite_sha256: "a1b2c3",
    clean: {
      reference: { acc: 0.812, ece: 0.061, brier: 0.142, nll: 0.512, aurc: 0.118, confident_error_rate: 0.034, coverage_at_5pct_error: 0.41 },
      candidate: { acc: 0.894, ece: 0.048, brier: 0.121, nll: 0.421, aurc: 0.091, confident_error_rate: 0.021, coverage_at_5pct_error: 0.49 },
    },
    paired: {
      acc: { ci95: [0.061, 0.114] },
      ece: { ci95: [-0.021, -0.005] },
    },
  },
};

export default function EvalComparePage() {
  const { t, lang } = useLang();
  const [candidate, setCandidate] = useState("kev-4b-a2");
  const [reference, setReference] = useState("kev-baseline");

  const latest = SAMPLE;
  const low = metricAt(latest.meta, ["paired", "acc", "ci95", 0]);
  const high = metricAt(latest.meta, ["paired", "acc", "ci95", 1]);
  const badge = deltaBadge(low !== undefined && high !== undefined ? [low, high] : undefined);

  const pairs = useMemo(
    () =>
      METRIC_NAMES.map((name) => ({
        name,
        reference: metricAt(latest.meta, ["clean", "reference", name]),
        candidate: metricAt(latest.meta, ["clean", "candidate", name]),
      })),
    [latest]
  );

  return (
    <div className="space-y-6">
      <StudioTabs tabs={EVAL_TABS} />
      <PageHead
        title={t("studio.tab.compare")}
        subtitle={lang === "zh" ? "配对对比两个 checkpoint 的评测产物（要求 suite_sha256 一致）。" : "Paired comparison of two checkpoints' eval artifacts (matching suite_sha256 required)."}
      />

      <Panel title={lang === "zh" ? "选择对比对象" : "Pick comparison targets"}>
        <FormGrid>
          <Field label="candidate">
            <select
              value={candidate}
              onChange={(e) => setCandidate(e.target.value)}
              className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary"
            >
              {RUNS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </Field>
          <Field label="reference">
            <select
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary"
            >
              {RUNS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </Field>
        </FormGrid>
      </Panel>

      <Panel desc={latest.id}>
        <div className="mb-3 flex items-center gap-2">
          <StatusBadge status={badge.ok ? "succeeded" : "failed"} label={badge.label} />
          <span className="text-xs text-muted-foreground">{badge.detail}</span>
        </div>
        <ComparisonTable
          rows={pairs}
          metricLabel={t("studio.eval.metric")}
          candidateLabel={candidate}
          referenceLabel={reference}
          withDelta
        />
      </Panel>
    </div>
  );
}

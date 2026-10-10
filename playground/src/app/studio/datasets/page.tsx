"use client";

import { useCallback, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type Artifact } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobStagePage, type FieldSpec } from "@/components/console/JobStagePage";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";
import { EmptyState } from "@/components/studio/primitives";
import { JobBoardSection } from "@/components/studio/JobBoardSection";
import { StudioTabs } from "@/components/studio/StudioTabs";
import Link from "next/link";

const DATASETS_TABS = [
  { href: "/studio/datasets", labelKey: "studio.tab.run" },
  { href: "/studio/datasets/label", labelKey: "studio.tab.label" },
];

const KINDS: Record<string, { kind: string; fields: FieldSpec[] }> = {
  plan_size: { kind: "plan_size", fields: [] },
  generate: { kind: "generate", fields: [
    { key: "n", label: "--n", hint: "787 = 5 个 spec 都是 4 问题/记录时的计划量" },
    { key: "seed", label: "--seed" },
  ] },
  distill: { kind: "distill", fields: [
    { key: "category", label: "--category" },
    { key: "provider_id", label: "provider", kind: "select", optionsUrl: "/console/api/distill-providers", hint: "蒸馏配置在「蒸馏配置」页创建" },
    { key: "examples", label: "--examples", hint: "可选：真实标注记录的 JSONL，作为 few-shot 范例" },
    { key: "n_examples", label: "--n-examples" },
    { key: "concurrency", label: "--concurrency" },
    { key: "n", label: "--n" },
    { key: "schedule", label: "--schedule", hint: "HH:MM（可选；守护模式下必填）" },
    { key: "state_dir", label: "--state-dir", hint: "进度状态目录（用量采集依据）" },
  ] },
  distill_daemon: { kind: "distill_daemon", fields: [
    { key: "category", label: "--category" },
    { key: "provider_id", label: "provider", kind: "select", optionsUrl: "/console/api/distill-providers", hint: "蒸馏配置在「蒸馏配置」页创建" },
    { key: "examples", label: "--examples" },
    { key: "n_examples", label: "--n-examples" },
    { key: "concurrency", label: "--concurrency" },
    { key: "n", label: "--n" },
    { key: "schedule", label: "--schedule", hint: "HH:MM；每天蒸馏到当日配额后睡到本地该时刻" },
    { key: "state_dir", label: "--state-dir" },
  ] },
  goldset: { kind: "goldset", fields: [
    { key: "n", label: "--n", hint: "150-250 是有用区间" },
    { key: "seed", label: "--seed" },
  ] },
  split: { kind: "split", fields: [
    { key: "calibration", label: "--calibration" },
    { key: "development", label: "--development" },
    { key: "seed", label: "--seed" },
    { key: "holdout", label: "--holdout", hint: "金标对半分进 calibration/development，永不进 train" },
  ] },
  precheck: { kind: "precheck", fields: [
    { key: "init_from", label: "--init-from", hint: "A1 用 kev-0.8b；A2/B 用裸基座的 tokenizer" },
    { key: "split", kind: "select", label: "--split", options: ["train", "calibration", "development"].map((v) => ({ value: v, label: v })) },
  ] },
  make_examples: { kind: "make_examples", fields: [
    { key: "data", label: "--data", hint: "已标注 JSONL，如 data/critical-value.jsonl" },
    { key: "n", label: "--n", hint: "范例条数，默认 8" },
    { key: "seed", label: "--seed" },
    { key: "out", label: "--out", hint: "默认 <data 同目录>/examples.jsonl" },
  ] },
};

export default function StudioDatasetsPage() {
  const { t, lang } = useLang();
  const [dataKind, setDataKind] = useState("generate");
  const load = useCallback(() => api.datasets(), []);
  const datasets = usePoll(load, []);
  const active = KINDS[dataKind];

  return (
    <div className="space-y-8">
      <StudioTabs tabs={DATASETS_TABS} />
      <section className="space-y-3">
        <h1 className="text-lg font-semibold">{t("studio.nav.datasets")}</h1>
        <div className="flex flex-wrap gap-1.5">
          {Object.keys(KINDS).map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setDataKind(name)}
              className={`rounded-md px-2.5 py-1 font-mono text-xs transition-colors ${
                name === dataKind ? "bg-[#1e3a8a] text-[#3b82f6]" : "text-muted-foreground hover:bg-[#161616]"
              }`}
            >
              {name}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          {lang === "zh"
            ? "生成与划分必须串行：先跑 generate，再跑 split。"
            : "generate and split must run serially: generate first, then split."}
        </p>
      </section>

      <JobStagePage
        key={dataKind}
        kind={active.kind}
        title={t("studio.nav.datasets")}
        fields={active.fields}
        initial={{ n: "787", seed: "0", calibration: "0.15", development: "0.15", model: "Ling-3.0-tiny", concurrency: "3", init_from: "jaredpalmer/kev-0.8b", split: "train" }}
      />

      <section className="space-y-2">
        <h2 className="text-sm font-medium">{t("studio.nav.datasets")}</h2>
        {datasets.value.length === 0 ? (
          <EmptyState title={lang === "zh" ? "还没有数据集" : "No datasets yet"} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>id</TableHead>
                <TableHead>path</TableHead>
                <TableHead className="text-right">{t("studio.datasets.records")}</TableHead>
                <TableHead className="text-right">{t("studio.datasets.invalid")}</TableHead>
                <TableHead className="text-right">{t("studio.datasets.export")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {datasets.value.map((artifact: Artifact) => (
                <TableRow key={artifact.id}>
                  <TableCell className="font-mono text-xs">
                    <Link href={`/studio/datasets/${encodeURIComponent(artifact.id)}`} className="hover:text-primary hover:underline">
                      {artifact.id}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{artifact.path}</TableCell>
                  <TableCell className="text-right text-xs">{formatNumber(artifact.meta.records as number, 0)}</TableCell>
                  <TableCell className="text-right text-xs">{formatNumber(artifact.meta.invalid_lines as number, 0)}</TableCell>
                  <TableCell className="text-right">
                    <a className="text-xs text-primary hover:underline" href={api.exportUrl(artifact.id)}>JSONL</a>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      <JobBoardSection
        title={`${t("studio.nav.datasets")} · jobs`}
        kinds={Object.keys(KINDS)}
        hrefFor={(id) => `/studio/jobs/${id}`}
      />
    </div>
  );
}

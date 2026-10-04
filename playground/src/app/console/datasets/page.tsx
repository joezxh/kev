"use client";

import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type Artifact } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobStagePage, type FieldSpec } from "@/components/console/JobStagePage";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";

/** 5 个场景 × 6 种数据作业，用一个 kind 切换器覆盖。 */
const KINDS: Record<string, { kind: string; fields: FieldSpec[] }> = {
  plan_size: { kind: "plan_size", fields: [] },
  generate: { kind: "generate", fields: [
    { key: "n", label: "--n", hint: "787 = 5 个 spec 都是 4 问题/记录时的计划量" },
    { key: "seed", label: "--seed" },
  ] },
  distill: { kind: "distill", fields: [
    { key: "category", label: "--category" },
    { key: "model", label: "--model" },
    { key: "base_url", label: "KEV_GEN_BASE_URL",
      hint: "凭据（KEV_GEN_API_KEYS）由编排服务进程环境注入，不在这里填" },
    { key: "concurrency", label: "--concurrency" },
    { key: "n", label: "--n" },
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
    { key: "split", kind: "select", label: "--split",
      options: ["train", "calibration", "development"].map((v) => ({ value: v, label: v })) },
  ] },
};

export default function DatasetsPage() {
  const { t, lang } = useLang();
  const [dataKind, setDataKind] = useState("generate");
  const load = useCallback(() => api.datasets(), []);
  const datasets = usePoll(load, []);

  const active = KINDS[dataKind];

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-lg font-semibold">{t("console.nav.data")}</h1>
        <div className="flex flex-wrap gap-1.5">
          {Object.keys(KINDS).map((name) => (
            <Button key={name} size="sm"
                    variant={name === dataKind ? "secondary" : "ghost"}
                    onClick={() => setDataKind(name)}>
              <span className="font-mono text-xs">{name}</span>
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          {lang === "zh"
            ? "生成与划分必须串行：先跑 generate，再跑 split。并行会让 split 读到还没写完的文件。"
            : "generate and split must run serially: generate first, then split. Running them in parallel makes split read a half-written file."}
        </p>
      </section>

      <JobStagePage
        key={dataKind}
        kind={active.kind}
        title={t("console.nav.data")}
        fields={active.fields}
        initial={{ n: "787", seed: "0", calibration: "0.15", development: "0.15",
                    model: "Ling-3.0-tiny", concurrency: "3", init_from: "jaredpalmer/kev-0.8b",
                    split: "train" }}
      />

      <section className="space-y-2">
        <h2 className="text-sm font-medium">{t("console.data.datasets")}</h2>
        {datasets.value.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {lang === "zh" ? "还没有数据集" : "No datasets yet"}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>id</TableHead><TableHead>path</TableHead>
                <TableHead>records</TableHead><TableHead>invalid</TableHead>
                <TableHead className="text-right">{t("console.data.export")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {datasets.value.map((artifact: Artifact) => (
                <TableRow key={artifact.id}>
                  <TableCell className="font-mono text-xs">{artifact.id}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{artifact.path}</TableCell>
                  <TableCell className="text-xs">
                    {formatNumber(artifact.meta.records as number, 0)}
                  </TableCell>
                  <TableCell className="text-xs">
                    {formatNumber(artifact.meta.invalid_lines as number, 0)}
                  </TableCell>
                  <TableCell className="text-right">
                    <a className="text-xs underline" href={api.exportUrl(artifact.id)}>
                      JSONL
                    </a>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {datasets.error && (
          <p className="text-xs text-destructive">{datasets.error}</p>
        )}
      </section>
    </div>
  );
}
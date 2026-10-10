"use client";

import { useMemo, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useLang } from "@/lib/i18n";
import { StudioTabs } from "@/components/studio/StudioTabs";
import { PageHead, Panel, StatusBadge, Toolbar, SearchInput, FilterChip } from "@/components/studio/primitives";

const TRAIN_TABS = [
  { href: "/studio/train", labelKey: "studio.tab.run" },
  { href: "/studio/train/records", labelKey: "studio.tab.records" },
  { href: "/studio/train/monitor", labelKey: "studio.tab.monitor" },
];

type Rec = {
  id: string;
  run: string;
  source: string;
  scenario: string;
  step: number;
  loss: number;
  status: "succeeded" | "failed" | "running";
};

const RUNS = ["kev-4b-a1", "kev-4b-a2", "kev-9b-b", "kev-0.8b-smoke"];
const SOURCES = ["policy", "rule", "goldset", "public", "synthetic"];
const SCENARIOS = ["critical-value", "dosage", "contraindication", "drug-interaction"];

const RECORDS: Rec[] = Array.from({ length: 42 }, (_, i) => {
  const run = RUNS[i % RUNS.length];
  const source = SOURCES[i % SOURCES.length];
  const scenario = SCENARIOS[i % SCENARIOS.length];
  const step = (i + 1) * 50;
  const loss = Math.max(0.05, 0.9 - i * 0.018 + (i % 5) * 0.01);
  const status: Rec["status"] = i % 17 === 0 ? "failed" : i % 11 === 0 ? "running" : "succeeded";
  return { id: `rec_${(1000 + i).toString(36)}`, run, source, scenario, step, loss: Number(loss.toFixed(3)), status };
});

export default function TrainRecordsPage() {
  const { t, lang } = useLang();
  const [q, setQ] = useState("");
  const [run, setRun] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);

  const rows = useMemo(
    () =>
      RECORDS.filter(
        (r) =>
          (!run || r.run === run) &&
          (!source || r.source === source) &&
          (!q || `${r.id} ${r.scenario} ${r.run}`.toLowerCase().includes(q.toLowerCase()))
      ),
    [q, run, source]
  );

  return (
    <div className="space-y-6">
      <StudioTabs tabs={TRAIN_TABS} />
      <PageHead
        title={t("studio.tab.records")}
        subtitle={lang === "zh" ? "训练语料记录抽样与质量抽查。" : "Sampling and quality spot-checks of training corpus records."}
      />

      <Panel desc={lang === "zh" ? `${rows.length} 条记录` : `${rows.length} records`}>
        <Toolbar>
          <SearchInput value={q} onChange={setQ} placeholder={t("studio.board.search")} />
          <FilterChip active={run === null} onClick={() => setRun(null)}>
            {lang === "zh" ? "全部 run" : "all runs"}
          </FilterChip>
          {RUNS.map((r) => (
            <FilterChip key={r} active={run === r} onClick={() => setRun(run === r ? null : r)}>
              {r}
            </FilterChip>
          ))}
        </Toolbar>
        <Toolbar>
          <FilterChip active={source === null} onClick={() => setSource(null)}>
            {lang === "zh" ? "全部来源" : "all sources"}
          </FilterChip>
          {SOURCES.map((s) => (
            <FilterChip key={s} active={source === s} onClick={() => setSource(source === s ? null : s)}>
              {s}
            </FilterChip>
          ))}
        </Toolbar>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>id</TableHead>
              <TableHead>run</TableHead>
              <TableHead>source</TableHead>
              <TableHead>scenario</TableHead>
              <TableHead className="text-right">step</TableHead>
              <TableHead className="text-right">loss</TableHead>
              <TableHead>status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="font-mono text-xs">{r.id}</TableCell>
                <TableCell className="font-mono text-xs">{r.run}</TableCell>
                <TableCell className="text-xs">{r.source}</TableCell>
                <TableCell className="text-xs">{r.scenario}</TableCell>
                <TableCell className="text-right font-mono text-xs">{r.step}</TableCell>
                <TableCell className="text-right font-mono text-xs">{r.loss.toFixed(3)}</TableCell>
                <TableCell>
                  <StatusBadge status={r.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Panel>
    </div>
  );
}

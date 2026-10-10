"use client";

import { useLang } from "@/lib/i18n";
import { StudioTabs } from "@/components/studio/StudioTabs";
import { PageHead, Panel, Kpi, Sparkline, StatusBadge } from "@/components/studio/primitives";

const TRAIN_TABS = [
  { href: "/studio/train", labelKey: "studio.tab.run" },
  { href: "/studio/train/records", labelKey: "studio.tab.records" },
  { href: "/studio/train/monitor", labelKey: "studio.tab.monitor" },
];

const lossCurve = [0.91, 0.84, 0.77, 0.71, 0.66, 0.61, 0.58, 0.55, 0.53, 0.51, 0.50, 0.49];
const gradNorm = [2.4, 1.9, 1.6, 1.4, 1.3, 1.2, 1.1, 1.05, 1.0, 0.98, 0.95, 0.93];

const RANKS = [
  { rank: 0, gpu: "H200", util: 97, mem: 121, temp: 64 },
  { rank: 1, gpu: "H200", util: 95, mem: 118, temp: 63 },
  { rank: 2, gpu: "H200", util: 96, mem: 120, temp: 65 },
  { rank: 3, gpu: "H200", util: 92, mem: 119, temp: 63 },
  { rank: 4, gpu: "H200", util: 88, mem: 117, temp: 62 },
  { rank: 5, gpu: "H200", util: 90, mem: 118, temp: 64 },
  { rank: 6, gpu: "H200", util: 94, mem: 121, temp: 66 },
  { rank: 7, gpu: "H200", util: 91, mem: 116, temp: 61 },
];

export default function TrainMonitorPage() {
  const { t, lang } = useLang();
  return (
    <div className="space-y-6">
      <StudioTabs tabs={TRAIN_TABS} />
      <PageHead
        title={t("studio.tab.monitor")}
        subtitle={lang === "zh" ? "训练资源监控（rank 级 GPU 利用率、显存、损失与梯度范数）。" : "Per-rank GPU utilisation, memory, loss and gradient norm."}
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label="throughput" value="7.6 rec/s">
          <Sparkline data={[6, 6.4, 6.9, 7.2, 7.4, 7.6]} color="#22c55e" />
        </Kpi>
        <Kpi label="gpu util" value="93%">
          <Sparkline data={[88, 90, 92, 93, 92, 93]} color="#3b82f6" />
        </Kpi>
        <Kpi label="loss" value="0.49" delta="−0.42" deltaUp>
          <Sparkline data={lossCurve} color="#3b82f6" />
        </Kpi>
        <Kpi label="grad norm" value="0.93" delta="−1.47" deltaUp>
          <Sparkline data={gradNorm} color="#f59e0b" />
        </Kpi>
      </div>

      <Panel title={lang === "zh" ? "rank 明细" : "Per-rank detail"} desc="8 × H200">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="py-2 pr-4 font-medium">rank</th>
                <th className="py-2 pr-4 font-medium">gpu</th>
                <th className="py-2 pr-4 text-right font-medium">util</th>
                <th className="py-2 pr-4 text-right font-medium">mem (GiB)</th>
                <th className="py-2 pr-4 text-right font-medium">temp</th>
                <th className="py-2 font-medium">status</th>
              </tr>
            </thead>
            <tbody>
              {RANKS.map((r) => (
                <tr key={r.rank} className="border-b border-border/60">
                  <td className="py-2 pr-4 font-mono">{r.rank}</td>
                  <td className="py-2 pr-4 font-mono">{r.gpu}</td>
                  <td className="py-2 pr-4 text-right font-mono">{r.util}%</td>
                  <td className="py-2 pr-4 text-right font-mono">{r.mem}</td>
                  <td className="py-2 pr-4 text-right font-mono">{r.temp}°C</td>
                  <td className="py-2">
                    <StatusBadge status="running" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">
          {lang === "zh"
            ? "数据为样例；真实指标来自 kev.full_ft 的 training_metrics.json（grad_norm、backbone_save_seconds、snapshots）。"
            : "Sample data; real metrics come from kev.full_ft training_metrics.json (grad_norm, backbone_save_seconds, snapshots)."}
        </p>
      </Panel>
    </div>
  );
}

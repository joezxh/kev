"use client";

import { useLang } from "@/lib/i18n";
import { StudioTabs } from "@/components/studio/StudioTabs";
import { PageHead, Panel, StatusBadge } from "@/components/studio/primitives";
import { Button as UiButton } from "@/components/ui/button";

const DEPLOY_TABS = [
  { href: "/studio/deploy", labelKey: "studio.tab.run" },
  { href: "/studio/deploy/canary", labelKey: "studio.tab.canary" },
  { href: "/studio/deploy/health", labelKey: "studio.tab.health" },
  { href: "/studio/deploy/metrics", labelKey: "studio.tab.metrics" },
];

const DEPLOYS = [
  { id: "kev-4b-a2", env: "prod", canary: 25, traffic: 25, status: "running", version: "v4b-a2@3f1c" },
  { id: "kev-4b-a2", env: "prod", canary: 100, traffic: 100, status: "succeeded", version: "v4b-a1@9a02" },
  { id: "kev-9b-b", env: "staging", canary: 10, traffic: 10, status: "running", version: "v9b-b@c771" },
  { id: "kev-0.8b-smoke", env: "staging", canary: 100, traffic: 100, status: "succeeded", version: "v08b@12de" },
];

export default function DeployCanaryPage() {
  const { t, lang } = useLang();
  return (
    <div className="space-y-6">
      <StudioTabs tabs={DEPLOY_TABS} />
      <PageHead
        title={t("studio.tab.canary")}
        subtitle={lang === "zh" ? "灰度放量、流量权重与一键回滚（医疗场景保留人工确认）。" : "Canary rollout, traffic weighting and one-click rollback (human confirm retained for medical)."}
      />

      <Panel desc={lang === "zh" ? "活动部署" : "Active deployments"}>
        <div className="space-y-3">
          {DEPLOYS.map((d, i) => (
            <div key={i} className="flex flex-wrap items-center gap-3 rounded border border-border bg-[#111111] p-3">
              <div className="min-w-[140px]">
                <div className="font-mono text-xs">{d.id}</div>
                <div className="text-[11px] text-muted-foreground">{d.version}</div>
              </div>
              <span className="rounded bg-[#1c1c1c] px-2 py-0.5 font-mono text-[11px] text-muted-foreground">{d.env}</span>
              <div className="flex-1">
                <div className="mb-1 flex justify-between text-[11px] text-muted-foreground">
                  <span>{lang === "zh" ? "灰度" : "canary"} {d.canary}%</span>
                  <span>{lang === "zh" ? "流量" : "traffic"} {d.traffic}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded bg-[#1c1c1c]">
                  <div className="h-full bg-[#3b82f6]" style={{ width: `${d.traffic}%` }} />
                </div>
              </div>
              <StatusBadge status={d.status} />
              <div className="flex gap-2">
                <UiButton size="xs" variant="outline" disabled={d.traffic >= 100}>
                  {lang === "zh" ? "放量" : "promote"}
                </UiButton>
                <UiButton size="xs" variant="destructive" disabled={d.traffic <= 10}>
                  {lang === "zh" ? "回滚" : "rollback"}
                </UiButton>
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">
          {lang === "zh" ? "样例数据；真实灰度由发布流水线驱动，本页仅作可视化与人工确认入口。" : "Sample data; real canary is driven by the publish pipeline, this page is visualization + human confirm."}
        </p>
      </Panel>
    </div>
  );
}

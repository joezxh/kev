"use client";

import { useEffect, useState } from "react";
import { api, type StageMeta } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { STAGE_INSIGHTS, STAGE_INSIGHT_GENERIC, type InsightItem, type InsightText } from "./strings";
import { Fold } from "./Fold";

// 阶段元数据是静态注册表，整个 SPA 会话只取一次（模块级缓存，所有阶段页共享）。
// 取不到就当没有：老后端没这条路由、或编排服务未起时，卡片退回纯前端映射，
// 绝不因为解析卡报错而阻塞提交。
let stagesPromise: Promise<Record<string, StageMeta>> | null = null;
function loadStages(): Promise<Record<string, StageMeta>> {
  if (!stagesPromise) {
    stagesPromise = api.stages().catch(() => ({}) as Record<string, StageMeta>);
  }
  return stagesPromise;
}

/**
 * 「提交作业」右栏顶部的只读解析卡：把当前 kind 讲清楚 —— 这一步在做什么、
 * 需要哪些入参、产出哪些产物，以及各产物的去向（被哪道闸门校验、被哪个下游
 * 消费、缺失的后果）。
 *
 * 真相源分两层：
 * - 结构事实（阶段名、StageSpec.outcome、gates.STAGE_GATES 的闸门归属）走只读
 *   接口 GET /console/api/stages，前端不许复制，否则后端一改就漂移；
 * - 描述性文案全在 strings.ts 的 STAGE_INSIGHTS（后端没有中英双语字段），
 *   其头注记录了每 kind 对应的 stages/*.py 与 artifacts.py 位置。
 * 未知 kind 退回 STAGE_INSIGHT_GENERIC，不报错。
 */
export function StageInsights({ kind }: { kind: string }) {
  const { lang, t } = useLang();
  const [meta, setMeta] = useState<StageMeta | null>(null);
  useEffect(() => {
    let cancelled = false;
    loadStages().then((stages) => {
      if (!cancelled) setMeta(stages[kind] ?? null);
    });
    return () => { cancelled = true; };
  }, [kind]);

  const insight = STAGE_INSIGHTS[kind] ?? STAGE_INSIGHT_GENERIC;
  const pick = (text: InsightText) => text[lang];

  return (
    <Fold title={t("console.insights.title")} summary={kind}>
      {/* 右栏是 lg:sticky：解析内容可能很高，卡片内部滚动才不会把命令预览和
          提交按钮顶出可视区；不想看时点标题折叠。 */}
      <div className="max-h-80 space-y-3 overflow-y-auto pr-1 text-xs leading-relaxed">
        <section className="space-y-1">
          <h3 className="font-medium text-muted-foreground">{t("console.insights.step")}</h3>
          <p>{pick(insight.summary)}</p>
          {meta && meta.gates.length > 0 && (
            <p className="text-muted-foreground">
              {t("console.insights.gates")}:{" "}
              <span className="font-mono text-[11px]">{meta.gates.join(" · ")}</span>
            </p>
          )}
          {meta?.outcome && (
            <p className="text-muted-foreground">
              {t("console.insights.outcome")}: {meta.outcome}
            </p>
          )}
        </section>
        <InsightList title={t("console.insights.inputs")} items={insight.inputs} pick={pick} />
        <InsightList title={t("console.insights.outputs")} items={insight.outputs} pick={pick} />
        <p className="text-[11px] text-muted-foreground">{t("console.insights.note")}</p>
      </div>
    </Fold>
  );
}

function InsightList({
  title, items, pick,
}: {
  title: string; items: InsightItem[]; pick: (text: InsightText) => string;
}) {
  return (
    <section className="space-y-1.5">
      <h3 className="font-medium text-muted-foreground">{title}</h3>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item.name}>
            <span className="font-mono text-[11px]">{item.name}</span>
            <p className="text-muted-foreground">{pick(item.text)}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

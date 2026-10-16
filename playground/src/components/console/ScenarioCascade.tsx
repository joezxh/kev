"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api, type ScenarioTree } from "@/lib/console";
import { useLang } from "@/lib/i18n";

/**
 * 域 → 场景 两级级联选择器。输出场景 slug；占位文案随语言切换。
 * 与 JobStagePage 的 run_name 联动由调用方在 onChange 里处理。
 */
export function ScenarioCascade({
  value, onChange,
}: {
  value: string;
  onChange: (slug: string) => void;
}) {
  const { lang, t } = useLang();
  const [tree, setTree] = useState<ScenarioTree[]>([]);

  useEffect(() => {
    api.scenarioDomains(lang).then(setTree).catch(() => setTree([]));
  }, [lang]);

  const allScenarios = useMemo(
    () => tree.flatMap((domain) =>
      domain.scenarios.map((scenario) => ({ ...scenario, domainSlug: domain.slug }))),
    [tree],
  );
  const current = allScenarios.find((scenario) => scenario.slug === value);
  const [domainSlug, setDomainSlug] = useState(current?.domainSlug ?? tree[0]?.slug ?? "");

  // 外部 value 变化（如重置表单）时同步高亮所属域
  useEffect(() => {
    if (current) setDomainSlug(current.domainSlug);
  }, [value, tree]); // eslint-disable-line react-hooks/exhaustive-deps

  const domainScenarios = tree.find((domain) => domain.slug === domainSlug)?.scenarios ?? [];
  // 场景名中英并列（label_zh【label_en】），与域下拉一致：场景标签多为英文术语，
  // 只给单语时中文界面里常认不出是哪一条。触发器宽度有限，title 兜住被截断的全文。
  const currentLabel = current ? `${current.label_zh}【${current.label_en}】` : "";

  return (
    <div className="flex gap-2">
      <Select value={domainSlug} onValueChange={(next) => {
        if (!next) return;
        setDomainSlug(next);
        const first = tree.find((domain) => domain.slug === next)?.scenarios[0];
        if (first) onChange(first.slug);
      }}>
        <SelectTrigger className="w-40">
          <SelectValue placeholder={t("console.cascade.domain")}>
            {(value: string) => {
              const d = tree.find((o) => o.slug === value);
              return d ? `${d.label_zh}[${d.label_en}]` : t("console.cascade.domain");
            }}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {tree.map((domain) => (
            <SelectItem key={domain.slug} value={domain.slug}>{domain.label_zh}[{domain.label_en}]</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={value} onValueChange={(next) => { if (next) onChange(next); }}>
        <SelectTrigger className="w-56" title={currentLabel}>
          <SelectValue placeholder={t("console.cascade.scenario")} />
        </SelectTrigger>
        <SelectContent>
          {domainScenarios.length === 0 ? (
            <SelectItem value="__none__" disabled>
              {t("console.cascade.scenarioPlaceholder")}
            </SelectItem>
          ) : (
            domainScenarios.map((scenario) => (
              <SelectItem key={scenario.slug} value={scenario.slug}>
                {scenario.label_zh}【{scenario.label_en}】
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>
    </div>
  );
}

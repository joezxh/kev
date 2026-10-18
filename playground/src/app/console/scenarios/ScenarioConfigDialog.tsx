"use client";
// 场景配置弹窗（任务 2/3 的快捷入口）：由场景行最右侧的「配置」/「YAML」按钮打开。
// 3 个 tab —— 结构化(SpecEditor) / 蒸馏 YAML(DistillYamlEditor，仅蒸馏场景) / 原始文本(JSON textarea)。
// 弹窗自持 spec 的载入与保存（api.scenarioSpec / saveScenarioSpec）；YAML tab 由 DistillYamlEditor 自行读写。
// 结构化与原始文本共用同一份 spec：对象为真相源，切 tab / 保存时做文本<->对象桥接（与 SpecEditor 内部同策略）。
// 保存成功回调 onSaved(slug)，页面据此在该场景正被选中时刷新右侧面板，避免两处状态漂移。
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { api, type Scenario } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { SpecEditor } from "./SpecEditor";
import { DistillYamlEditor } from "./DistillYamlEditor";

export type ConfigTab = "spec" | "yaml" | "raw";
// 按钮只以 spec / yaml 两个入口打开；raw 是弹窗内部 tab。
export type ConfigTarget = { scenario: Scenario; tab: "spec" | "yaml" };

type Spec = Record<string, unknown>;

function isDistillScenario(s: Scenario): boolean {
  return s.track === "distill" || s.track === "both" || !!s.distill_yaml;
}
function validateJson(raw: string): string | null {
  if (!raw.trim()) return null; // 空串视为合法（清空）
  try {
    JSON.parse(raw);
    return null;
  } catch (e) {
    return (e as Error).message;
  }
}

export function ScenarioConfigDialog({
  target, onClose, onSaved, contentClassName,
}: {
  target: ConfigTarget | null;
  onClose: () => void;
  onSaved?: (slug: string) => void;
  // studio 深色主题传 "dark"：DialogContent 走 body portal，落在 .studio 近黑调色板作用域外，
  // 需自带 dark 作用域才不至于黑字压黑底（同 JobFiles.tsx）；console 浅色页不传。
  contentClassName?: string;
}) {
  return (
    <Dialog open={!!target} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className={`max-h-[88vh] overflow-y-auto sm:max-w-4xl ${contentClassName ?? ""}`}>
        {target && (
          <ConfigBody
            key={target.scenario.slug}
            scenario={target.scenario}
            initialTab={target.tab === "yaml" && !isDistillScenario(target.scenario) ? "spec" : target.tab}
            onSaved={onSaved}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ConfigBody({
  scenario, initialTab, onSaved,
}: {
  scenario: Scenario;
  initialTab: ConfigTab;
  onSaved?: (slug: string) => void;
}) {
  const { t } = useLang();
  const slug = scenario.slug;
  const distill = isDistillScenario(scenario);
  const [tab, setTab] = useState<ConfigTab>(initialTab);
  const [obj, setObj] = useState<Spec>({});
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 载入 spec：只在异步回调（.then/.catch）里 setState，不在 effect 体同步 setState（lint set-state-in-effect）。
  // 初始 loading=true，拉取完成后置位；切场景由外层 key=slug 强制重挂载。
  useEffect(() => {
    let cancelled = false;
    api.scenarioSpec(slug)
      .then((res) => {
        if (cancelled) return;
        const content = res.content ?? "";
        setText(content);
        try {
          setObj(JSON.parse(content) as Spec);
        } catch {
          setObj({});
        }
        setDirty(false); setError(null); setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        toast.error(t("console.scenarios.specLoadFailed"));
        setText(""); setObj({}); setLoading(false);
      });
    return () => { cancelled = true; };
  }, [slug, t]);

  // 结构化编辑：对象为真相源，同步序列化文本 + dirty。
  const onSpecChange = (next: Spec) => {
    setObj(next); setText(JSON.stringify(next, null, 2)); setDirty(true); setError(null);
  };
  // 原始文本编辑：文本为真相源，实时校验（切 tab / 保存时再回填对象）。
  const onRawChange = (v: string) => {
    setText(v); setDirty(true);
    setError(validateJson(v) ? t("console.scenarios.specInvalid") : null);
  };

  // 切 tab：离开 raw 把文本解析回对象（非法则阻止切换），进入 raw 从对象重新序列化。
  const handleTab = (next: string | number | null) => {
    const key = String(next) as ConfigTab;
    if (key === tab) return;
    if (tab === "raw") {
      const txt = text.trim();
      if (txt) {
        try {
          setObj(JSON.parse(txt) as Spec);
        } catch {
          setError(t("console.scenarios.specInvalid"));
          return; // 原始文本非法：停在原 tab
        }
      } else {
        setObj({});
      }
    }
    if (key === "raw") { setText(JSON.stringify(obj, null, 2)); setError(null); }
    setTab(key);
  };

  const save = async () => {
    let content: string;
    if (tab === "raw") {
      if (validateJson(text)) {
        setError(t("console.scenarios.specInvalid"));
        toast.error(t("console.scenarios.specInvalid"));
        return;
      }
      content = text;
    } else {
      content = JSON.stringify(obj, null, 2);
    }
    setSaving(true);
    try {
      await api.saveScenarioSpec(slug, content);
      setText(content);
      try { setObj(JSON.parse(content) as Spec); } catch { /* 保存成功后对象以服务端为准，解析失败则保留当前 */ }
      setDirty(false);
      toast.success(t("console.scenarios.specSaved"));
      onSaved?.(slug);
    } catch (e) {
      toast.error((e as { message: string }).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <DialogHeader className="pr-8">
        <DialogTitle>{scenario.label} · {t("console.scenarios.configDialog.title")}</DialogTitle>
        <DialogDescription className="font-mono text-xs">
          {slug}{scenario.spec_path ? ` — ${scenario.spec_path}` : ""}
        </DialogDescription>
      </DialogHeader>

      <Tabs value={tab} onValueChange={handleTab}>
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="spec">{t("console.scenarios.configDialog.tab.spec")}</TabsTrigger>
          {distill && <TabsTrigger value="yaml">{t("console.scenarios.configDialog.tab.yaml")}</TabsTrigger>}
          <TabsTrigger value="raw">{t("console.scenarios.configDialog.tab.raw")}</TabsTrigger>
        </TabsList>

        <TabsContent value="spec" className="pt-1">
          {loading ? (
            <p className="py-10 text-center text-xs text-muted-foreground">{t("console.scenarios.configDialog.loading")}</p>
          ) : (
            <SpecEditor value={obj} onChange={onSpecChange} />
          )}
        </TabsContent>

        {distill && (
          <TabsContent value="yaml" className="pt-1">
            <DistillYamlEditor key={slug} slug={slug} specPath={scenario.spec_path} />
          </TabsContent>
        )}

        <TabsContent value="raw" className="pt-1">
          <Textarea
            className="min-h-[50vh] font-mono text-xs"
            value={text}
            onChange={(e) => onRawChange(e.target.value)}
            placeholder="{}"
            disabled={loading}
          />
        </TabsContent>
      </Tabs>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {/* YAML tab 的保存由 DistillYamlEditor 自带的「保存 YAML」按钮负责，这里只在 spec/raw tab 显示配置保存。 */}
      <DialogFooter className="items-center">
        {dirty && tab !== "yaml" && <span className="mr-auto text-xs text-amber-600">●</span>}
        {tab !== "yaml" && (
          <Button onClick={() => void save()} disabled={saving || loading}>{t("console.scenarios.specSave")}</Button>
        )}
      </DialogFooter>
    </>
  );
}

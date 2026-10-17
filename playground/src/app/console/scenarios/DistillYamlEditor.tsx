"use client";
// distill_yaml 可视化编辑器（任务 3）：加载 scenarios.distill_yaml_content（回退仓库文件），
// 以解析后的对象为真相源分区编辑，保存时 js-yaml dump + 重生成的标准头注释 -> PUT distill-yaml。
// 仅当场景处于 distill/both 轨（或存在 distill_yaml 路径）时由页面渲染。
// 结构化 <-> 原始 YAML 在「切 tab」时桥接；原始非法则阻止切换（与 SpecEditor 同策略）。
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { load as loadYaml, dump as dumpYaml } from "js-yaml";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { KeyValueEditor } from "./editors/KeyValueEditor";
import { RawPanel } from "./editors/RawPanel";

type Obj = Record<string, unknown>;
type StagePatch = { stage?: string; output?: string; params?: unknown };

// 已被专门分区覆盖的顶层键；其余归入「其它字段」。
const KNOWN_TOP = ["job_type", "backend", "dataset", "system_prompt", "pipeline", "resume"];
// EasyDistill 常见阶段（datalist 建议，仍允许自由文本）。
const STAGES = ["instruction_expansion", "generate", "judge", "filter", "build_sft"];
const DUMP_OPTS = { lineWidth: 120, noRefs: true };

function isObj(v: unknown): v is Obj {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function asObj(v: unknown): Obj {
  return isObj(v) ? v : {};
}
function str(v: unknown): string {
  if (typeof v === "string") return v;
  return v == null ? "" : String(v);
}
function numStr(v: unknown): string {
  return typeof v === "number" ? String(v) : "";
}
function toNum(text: string): number | null {
  return text.trim() === "" ? null : Number(text);
}
function validateYaml(text: string): string | null {
  if (!text.trim()) return null;
  try {
    loadYaml(text);
    return null;
  } catch (e) {
    return (e as Error).message;
  }
}
// 保存时重生成的标准头注释（往返不保留原注释，此处统一说明 env 变量与来源）。
function buildHeader(slug: string, specPath?: string): string {
  const lines = [
    `# ${slug} — EasyDistill 配置（控制台场景编辑器保存；注释为自动重生成，编辑往返不保留原注释）`,
  ];
  if (specPath) lines.push(`# spec 来源: ${specPath}`);
  lines.push(
    "# teacher backend 的 base_url / api_key 从环境变量读取（${KEV_GEN_BASE_URL} / ${KEV_GEN_API_KEY}），切勿写明文密钥。",
  );
  lines.push(`# 保存时间: ${new Date().toISOString()}`);
  return lines.map((l) => `${l}\n`).join("");
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1">
      <Label className="font-mono text-xs text-muted-foreground">{label}</Label>
      {children}
      {hint && <p className="text-[11px] leading-relaxed text-muted-foreground/80">{hint}</p>}
    </div>
  );
}

export function DistillYamlEditor({ slug, specPath }: { slug: string; specPath?: string }) {
  const { t } = useLang();
  const [obj, setObj] = useState<Obj>({});
  const [raw, setRaw] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("backend");

  // 取数只在 effect 里异步回写（.then/.catch），不在 effect 体同步 setState（lint 规则 set-state-in-effect）。
  // 初始 busy=true / loaded=false，拉取完成后在回调里置位。切场景时页面用 key=slug 强制重挂载，tab 由初始值复位。
  useEffect(() => {
    let cancelled = false;
    api.scenarioDistillYaml(slug)
      .then((res) => {
        if (cancelled) return;
        const text = res.content ?? "";
        if (!text.trim()) {
          setEmpty(true); setObj({}); setRaw("");
        } else {
          setEmpty(false);
          try {
            const parsed = loadYaml(text);
            setObj(isObj(parsed) ? parsed : {});
          } catch {
            setObj({});
          }
          setRaw(text);
        }
        setDirty(false); setError(null); setLoaded(true); setBusy(false);
      })
      .catch(() => {
        if (cancelled) return;
        toast.error(t("console.distillYaml.loadFailed"));
        setObj({}); setRaw(""); setLoaded(true); setBusy(false);
      });
    return () => { cancelled = true; };
  }, [slug, t]);

  const update = (next: Obj) => { setObj(next); setDirty(true); setError(null); };

  // 切 tab：离开 raw 解析回对象（非法则阻止），进入 raw 从对象重新序列化（不含头注释）。
  const handleTab = (next: string | number | null) => {
    const key = String(next);
    if (key === tab) return;
    if (tab === "raw") {
      if (!raw.trim()) { setObj({}); }
      else {
        try {
          const parsed = loadYaml(raw);
          setObj(isObj(parsed) ? parsed : {});
        } catch {
          setError(t("console.distillYaml.invalid"));
          return;
        }
      }
    }
    if (key === "raw") { setRaw(dumpYaml(obj, DUMP_OPTS)); setError(null); }
    setTab(key);
  };

  const save = async () => {
    let src = obj;
    if (tab === "raw") {
      try {
        const parsed = raw.trim() ? loadYaml(raw) : {};
        src = isObj(parsed) ? parsed : {};
      } catch {
        setError(t("console.distillYaml.invalid"));
        toast.error(t("console.distillYaml.invalid"));
        return;
      }
    }
    setError(null);
    const text = buildHeader(slug, specPath) + dumpYaml(src, DUMP_OPTS);
    setBusy(true);
    try {
      await api.saveScenarioDistillYaml(slug, text);
      setObj(src); setRaw(dumpYaml(src, DUMP_OPTS)); setDirty(false); setEmpty(false);
      toast.success(t("console.distillYaml.saved"));
    } catch (e) {
      toast.error((e as { message: string }).message);
    } finally {
      setBusy(false);
    }
  };

  // ---- backend ----
  const backend = asObj(obj.backend);
  const setB = (k: string, v: unknown) => update({ ...obj, backend: { ...backend, [k]: v } });
  // ---- dataset ----
  const dataset = asObj(obj.dataset);
  const setD = (k: string, v: unknown) => update({ ...obj, dataset: { ...dataset, [k]: v } });
  // ---- pipeline ----
  const pipeline = Array.isArray(obj.pipeline) ? (obj.pipeline as unknown[]) : [];
  const setPipeline = (p: unknown[]) => update({ ...obj, pipeline: p });
  const setStage = (i: number, patch: StagePatch) => {
    const n = pipeline.slice();
    n[i] = { ...asObj(pipeline[i]), ...patch };
    setPipeline(n);
  };
  const moveStage = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= pipeline.length) return;
    const n = pipeline.slice();
    const tmp = n[i]; n[i] = n[j]; n[j] = tmp;
    setPipeline(n);
  };
  const addStage = () => setPipeline([...pipeline, { stage: "generate", output: "" }]);
  const removeStage = (i: number) => setPipeline(pipeline.filter((_, j) => j !== i));
  // ---- 其它字段 ----
  const otherKeys = Object.keys(obj).filter((k) => !KNOWN_TOP.includes(k));
  const otherObj: Obj = {};
  for (const k of otherKeys) otherObj[k] = obj[k];
  const applyOther = (edited: Obj) => {
    const next: Obj = {};
    for (const [k, v] of Object.entries(obj)) {
      if (KNOWN_TOP.includes(k)) next[k] = v;
      else if (k in edited) next[k] = edited[k];
    }
    for (const [k, v] of Object.entries(edited)) if (!(k in next)) next[k] = v;
    update(next);
  };

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/30 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <Label className="text-sm font-medium">{t("console.distillYaml.title")}</Label>
          <p className="mt-0.5 max-w-2xl text-[11px] leading-relaxed text-muted-foreground">{t("console.distillYaml.subtitle")}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {dirty && <span className="text-xs text-amber-600">●</span>}
          <Button size="sm" onClick={() => void save()} disabled={busy || !loaded}>{t("console.distillYaml.save")}</Button>
        </div>
      </div>

      {empty && <p className="text-xs text-muted-foreground">{t("console.distillYaml.empty")}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex flex-wrap items-end gap-4">
        <Field label={t("console.distillYaml.jobType")}>
          <Input className="h-8 w-64 text-xs" value={str(obj.job_type)} onChange={(e) => update({ ...obj, job_type: e.target.value })} />
        </Field>
        <div className="flex items-center gap-2 pb-1.5">
          <Switch checked={obj.resume === true} onCheckedChange={(v) => update({ ...obj, resume: v })} />
          <Label className="font-mono text-xs text-muted-foreground">{t("console.distillYaml.resume")}</Label>
        </div>
      </div>

      <Tabs value={tab} onValueChange={handleTab}>
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="backend">{t("console.distillYaml.tab.backend")}</TabsTrigger>
          <TabsTrigger value="dataset">{t("console.distillYaml.tab.dataset")}</TabsTrigger>
          <TabsTrigger value="prompt">{t("console.distillYaml.tab.prompt")}</TabsTrigger>
          <TabsTrigger value="pipeline">{t("console.distillYaml.tab.pipeline")}</TabsTrigger>
          <TabsTrigger value="other">{t("console.distillYaml.tab.other")}</TabsTrigger>
          <TabsTrigger value="raw">{t("console.distillYaml.tab.raw")}</TabsTrigger>
        </TabsList>

        <TabsContent value="backend" className="space-y-3 pt-1">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="type"><Input className="text-xs" value={str(backend.type)} onChange={(e) => setB("type", e.target.value)} /></Field>
            <Field label="model"><Input className="text-xs" value={str(backend.model)} onChange={(e) => setB("model", e.target.value)} /></Field>
            <Field label="temperature"><Input type="number" step="0.1" className="text-xs" value={numStr(backend.temperature)} onChange={(e) => setB("temperature", toNum(e.target.value))} /></Field>
            <Field label="max_tokens"><Input type="number" className="text-xs" value={numStr(backend.max_tokens)} onChange={(e) => setB("max_tokens", toNum(e.target.value))} /></Field>
            <Field label="concurrency"><Input type="number" className="text-xs" value={numStr(backend.concurrency)} onChange={(e) => setB("concurrency", toNum(e.target.value))} /></Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="base_url"><Input className="text-xs opacity-70" readOnly value={str(backend.base_url ?? "${KEV_GEN_BASE_URL}")} /></Field>
            <Field label="api_key"><Input className="text-xs opacity-70" readOnly value={str(backend.api_key ?? "${KEV_GEN_API_KEY}")} /></Field>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">{t("console.distillYaml.envNote")}</p>
        </TabsContent>

        <TabsContent value="dataset" className="pt-1">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="instruction_key"><Input className="text-xs" value={str(dataset.instruction_key)} onChange={(e) => setD("instruction_key", e.target.value)} /></Field>
            <Field label="input_file"><Input className="text-xs" value={str(dataset.input_file)} onChange={(e) => setD("input_file", e.target.value)} /></Field>
            <Field label="output_dir"><Input className="text-xs" value={str(dataset.output_dir)} onChange={(e) => setD("output_dir", e.target.value)} /></Field>
          </div>
        </TabsContent>

        <TabsContent value="prompt" className="pt-1">
          <Textarea rows={10} className="text-xs" value={str(obj.system_prompt)} onChange={(e) => update({ ...obj, system_prompt: e.target.value })} />
        </TabsContent>

        <TabsContent value="pipeline" className="space-y-2 pt-1">
          <datalist id="distill-stages">
            {STAGES.map((s) => <option key={s} value={s} />)}
          </datalist>
          {pipeline.map((st, i) => {
            const s = asObj(st);
            return (
              <div key={i} className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
                <div className="flex items-center gap-1.5">
                  <span className="w-4 shrink-0 text-right font-mono text-[10px] text-muted-foreground">{i}</span>
                  <Input list="distill-stages" className="h-7 w-48 shrink-0 font-mono text-xs" placeholder={t("console.distillYaml.stage")}
                    value={str(s.stage)} onChange={(e) => setStage(i, { stage: e.target.value })} />
                  <Input className="h-7 flex-1 font-mono text-xs" placeholder={t("console.distillYaml.output")}
                    value={str(s.output)} onChange={(e) => setStage(i, { output: e.target.value })} />
                  <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs" disabled={i === 0} onClick={() => moveStage(i, -1)}>↑</Button>
                  <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs" disabled={i === pipeline.length - 1} onClick={() => moveStage(i, 1)}>↓</Button>
                  <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs text-muted-foreground" onClick={() => removeStage(i)}>{t("console.spec.kv.remove")}</Button>
                </div>
                <div className="space-y-1 pl-6">
                  <Label className="font-mono text-[11px] text-muted-foreground">{t("console.distillYaml.params")}</Label>
                  <KeyValueEditor value={s.params} onChange={(v) => setStage(i, { params: v })} />
                </div>
              </div>
            );
          })}
          <Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={addStage}>+ {t("console.distillYaml.addStage")}</Button>
        </TabsContent>

        <TabsContent value="other" className="space-y-2 pt-1">
          {otherKeys.length === 0 && <p className="text-xs text-muted-foreground">{t("console.spec.otherEmpty")}</p>}
          <KeyValueEditor value={otherObj} onChange={(v) => applyOther(asObj(v))} />
        </TabsContent>

        <TabsContent value="raw" className="pt-1">
          <RawPanel value={raw} onChange={setRaw} validate={validateYaml} rows={22} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

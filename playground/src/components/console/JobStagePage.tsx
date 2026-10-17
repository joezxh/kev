"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ApiError, api, type JobTemplate } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { useSelectedProject } from "@/lib/project-context";
import { ArgvPreview } from "./ArgvPreview";
import { GatePanel } from "./GatePanel";
import { ScenarioCascade } from "./ScenarioCascade";
import { StageInsights } from "./StageInsights";
import { usePoll } from "./usePoll";

export type FieldSpec = {
  key: string;
  label?: string;
  kind?: "text" | "number" | "select" | "checkbox" | "textarea";
  options?: { value: string; label: string }[];
  /** 选项从接口动态拉取（例如蒸馏配置列表），取代静态 options。 */
  optionsUrl?: string;
  hint?: string;
  /** 只在某些场景下出现（例如 snapshot_fractions 只对全参数有意义） */
  when?: (scenario: string, values: Record<string, string>) => boolean;
  /** 必填：提交前前端校验，空值标红；与后端 build 的 Invalid 对齐。 */
  required?: boolean;
  /** 默认值（字符串；与后端 build 默认对齐，作为单一真相源）。 */
  default?: string;
  /** 输入框占位提示。 */
  placeholder?: string;
  /** 可一键从某来源回填本字段（如 generate 的 --n 从 plan_size 产物读 total_records）。 */
  fillFrom?: string;
};

/**
 * 一个阶段页的骨架：左侧可编辑表单，右侧实时 argv 预览 + 闸门 + 提交。
 * （`submitInFormColumn` 把 run_name 与提交按钮收回左栏表单末尾，命令预览仍留在右栏。）
 *
 * 抽出它是因为 5 个阶段页形状完全一样，差异只在「有哪些字段」和「提交什么作业」。
 * 两条设计约定在这里落地：
 * - argv 永远可见（ArgvPreview），因为 runbook 的价值就在于命令可读、可审计。
 * - 闸门失败展开 GatePanel 且不跳走：那是配置问题不是运行失败，不该重试。
 */
export function JobStagePage({
  kind, title, gateStage, fields, initial, children, aside, submitLabel,
  hideScenario, jobHref, hideTitle, enableTemplates, submitInFormColumn,
}: {
  kind: string;
  title: string;
  gateStage?: string;
  fields: FieldSpec[];
  initial?: Record<string, string>;
  children?: React.ReactNode;
  aside?: React.ReactNode;
  submitLabel?: string;
  /** 不绑定场景的作业（publish / modal / goldset_audit）隐藏场景选择器。 */
  hideScenario?: boolean;
  /** 提交成功后的跳转目标；默认跳到 /console/jobs/<id>。studio 页传各自的 /studio/... 路由。 */
  jobHref?: (id: string) => string;
  /** 不渲染自带的 <h1>{title}</h1>（页面已有同级标题时避免重复）。 */
  hideTitle?: boolean;
  /** 启用「命名模板」工具条（保存/加载/删除），用于 studio 的提交作业页。 */
  enableTemplates?: boolean;
  /** run_name 项与提交按钮放在左栏表单末尾，而不是右栏预览之下（datasets 提交页用）。 */
  submitInFormColumn?: boolean;
}) {
  const router = useRouter();
  const { lang } = useLang();
  // /console 是唯一写入口，每个作业必须归属一个项目（D12/D14）；未选项目时禁止提交。
  const [projectId] = useSelectedProject();
  const [values, setValues] = useState<Record<string, string>>(() => {
    // 默认值优先级：schema.default（单一真相源）> 调用方 initial > 下拉首个选项 / 空串。
    // 既兼容其余 4 个阶段页（字段无 default、用 initial），也让 datasets 的默认值可配置。
    const base: Record<string, string> = { scenario: "critical-value", run_name: "cv-8b-lora-v1" };
    for (const f of fields) {
      const fallback = f.kind === "select" ? f.options?.[0]?.value ?? "" : "";
      base[f.key] = f.default ?? initial?.[f.key] ?? fallback;
    }
    for (const [k, v] of Object.entries(initial ?? {})) if (!(k in base)) base[k] = v;
    return base;
  });
  const [busy, setBusy] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [gateError, setGateError] = useState<ApiError | null>(null);
  const [dynamicOptions, setDynamicOptions] = useState<Record<string, { value: string; label: string }[]>>({});
  useEffect(() => {
    for (const f of fields) {
      if (f.optionsUrl && !(f.key in dynamicOptions)) {
        api.distillProviders().then((list) => {
          setDynamicOptions((prev) => ({
            ...prev,
            [f.key]: [
              { value: "", label: "（进程环境变量）" },
              ...list.map((p) => ({ value: p.id, label: `${p.name} · ${p.model}` })),
            ],
          }));
        }).catch(() => {});
      }
    }
    // dynamicOptions 仅作去重哨兵，故意不进依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields]);

  const loadGates = useCallback(
    () => (gateStage ? api.gates(gateStage, values.scenario) : Promise.resolve([])),
    [gateStage, values.scenario],
  );
  const gates = usePoll(loadGates, []);

  const params = Object.fromEntries(
    Object.entries(values).filter(([key, value]) =>
      key !== "scenario" && key !== "run_name" && value !== "" &&
      fields.some((f) => f.key === key) &&
      (fields.find((f) => f.key === key)?.when?.(values.scenario, values) ?? true)),
  );

  const set = (key: string, value: string) => {
    setValues((previous) => ({ ...previous, [key]: value }));
    setFieldErrors((previous) => {
      if (!(key in previous)) return previous;
      const next = { ...previous };
      delete next[key];
      return next;
    });
  };

  // ---- 命名模板（保存/加载/删除，仅 studio 提交作业页启用） -----------------
  const [templates, setTemplates] = useState<JobTemplate[]>([]);
  const [activeTemplateId, setActiveTemplateId] = useState<string | null>(null);
  const [newTplName, setNewTplName] = useState("");
  useEffect(() => {
    if (!enableTemplates) return;
    api.jobTemplates(kind).then(setTemplates).catch(() => setTemplates([]));
  }, [enableTemplates, kind]);

  const loadTemplate = (id: string) => {
    const tpl = templates.find((t) => t.id === id);
    if (!tpl) return;
    setValues((prev) => {
      const next = { ...prev };
      if (tpl.scenario) next.scenario = tpl.scenario;
      for (const [k, v] of Object.entries(tpl.params)) next[k] = v;
      return next;
    });
    setActiveTemplateId(id);
  };
  const saveTemplate = async () => {
    const name = newTplName.trim();
    if (!name) return;
    try {
      const created = await api.createJobTemplate({ kind, name, scenario: values.scenario, params });
      setNewTplName("");
      setActiveTemplateId(created.id);
      setTemplates((prev) => [created, ...prev]);
      toast.success(lang === "zh" ? "已保存模板" : "Template saved");
    } catch (e) { toast.error((e as ApiError).message); }
  };
  const deleteActive = async () => {
    if (!activeTemplateId) return;
    try {
      await api.deleteJobTemplate(activeTemplateId);
      setActiveTemplateId(null);
      setTemplates((prev) => prev.filter((t) => t.id !== activeTemplateId));
    } catch (e) { toast.error((e as ApiError).message); }
  };

  const submit = async () => {
    // 前端必填校验：与后端 build 的 Invalid 对齐，省一次无效往返（后端仍是最终防线）。
    const missing: Record<string, string> = {};
    for (const field of fields) {
      if (!field.required) continue;
      if (!(field.when?.(values.scenario, values) ?? true)) continue;
      if (!(values[field.key] ?? "").trim()) {
        missing[field.key] = lang === "zh" ? "此项必填" : "Required";
      }
    }
    if (Object.keys(missing).length > 0) {
      setFieldErrors(missing);
      return;
    }

    setBusy(true);
    setGateError(null);
    setFieldErrors({});
    try {
      const job = await api.submit({
        kind, scenario: values.scenario, run_name: values.run_name, params,
        project_id: projectId ?? "",
        ...(enableTemplates && activeTemplateId ? { template_id: activeTemplateId } : {}),
      });
      const goTo = jobHref ?? ((id: string) => `/console/jobs/${id}`);
      router.push(goTo(job.id));
    } catch (problem) {
      const apiError = problem as ApiError;
      // 闸门失败是配置问题：展开 GatePanel，不当作运行失败重试。
      if (apiError.detail?.kind === "gate") setGateError(apiError);
      // 表单校验失败（Invalid.field）：把后端红字标回对应输入框（附 hint）。
      // 只接「已渲染」的字段（fields 键或 run_name），其余退回 toast，避免错误被吞。
      else if (apiError.detail?.field &&
               (fields.some((f) => f.key === apiError.detail?.field) || apiError.detail.field === "run_name")) {
        setFieldErrors({ [apiError.detail.field]: apiError.detail.hint || apiError.detail.message });
      } else toast.error(apiError.message);
    } finally {
      setBusy(false);
    }
  };

  // run_name 项与提交按钮：两处共用同一份 JSX，默认在右栏，submitInFormColumn 时进左栏。
  const runNameField = (
    <div className="space-y-2">
      <Label htmlFor="f-run" className="font-mono text-xs">run_name</Label>
      <Input id="f-run" value={values.run_name}
             className={fieldErrors.run_name ? "border-[#ef4444]" : undefined}
             onChange={(event) => set("run_name", event.target.value)} />
      {fieldErrors.run_name ? (
        <p className="text-xs text-[#ef4444]">{fieldErrors.run_name}</p>
      ) : (
        <p className="text-xs text-muted-foreground">
          {lang === "zh"
            ? "只允许字母数字下划线连字符，尺寸写 8b 不写 0.8b（run_matrix.check_name 用 fullmatch）"
            : "Letters, digits, underscore and hyphen only; write 8b, never 0.8b (run_matrix.check_name uses fullmatch)"}
        </p>
      )}
    </div>
  );
  const submitButton = (
    <Button onClick={() => void submit()} disabled={busy || !projectId} className="w-full lg:w-auto">
      {busy ? (lang === "zh" ? "提交中…" : "Submitting…")
        : !projectId ? (lang === "zh" ? "先选项目" : "Select a project first")
        : submitLabel ?? (lang === "zh" ? "提交作业" : "Submit job")}
    </Button>
  );

  const formColumn = (
    <div className="space-y-4">
      {!hideScenario && (
        <div className="space-y-2">
          <Label htmlFor="f-scenario">{lang === "zh" ? "场景" : "Scenario"}</Label>
          <ScenarioCascade value={values.scenario} onChange={(slug) => {
            set("scenario", slug);
            set("run_name", `${slug}-8b-lora-v1`);
          }} />
        </div>
      )}

      {fields.filter((f) => f.when?.(values.scenario, values) ?? true).map((field) => (
        <div key={field.key} className="space-y-2">
          <Label htmlFor={`f-${field.key}`} className="font-mono text-xs">
            {field.label ?? field.key}
            {field.required && <span className="ml-0.5 text-[#ef4444]">*</span>}
          </Label>
          {field.kind === "select" ? (
            <Select value={values[field.key]} onValueChange={(v) => v !== null && set(field.key, v)}>
              <SelectTrigger id={`f-${field.key}`}
                             className={fieldErrors[field.key] ? "border-[#ef4444]" : undefined}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(field.optionsUrl ? dynamicOptions[field.key] ?? [] : field.options ?? []).map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Input id={`f-${field.key}`} value={values[field.key]}
                   placeholder={field.placeholder}
                   className={fieldErrors[field.key] ? "border-[#ef4444]" : undefined}
                   onChange={(event) => set(field.key, event.target.value)} />
          )}
          {field.fillFrom === "plan" && (
            <button
              type="button"
              onClick={async () => {
                try {
                  const plan = await api.plan(values.scenario);
                  set(field.key, String(plan.total_records));
                } catch (e) { toast.error((e as ApiError).message); }
              }}
              className="text-xs text-primary underline-offset-2 hover:underline"
            >
              {lang === "zh" ? "从计划读取" : "From plan"}
            </button>
          )}
          {fieldErrors[field.key] ? (
            <p className="text-xs text-[#ef4444]">{fieldErrors[field.key]}</p>
          ) : (
            field.hint && <p className="text-xs text-muted-foreground">{field.hint}</p>
          )}
        </div>
      ))}

      {submitInFormColumn && runNameField}
      {submitInFormColumn && submitButton}
    </div>
  );

  const grid = (
    <div className="grid gap-6 lg:grid-cols-2">
      {enableTemplates && (
        <div className="lg:col-span-2 flex flex-wrap items-center gap-2 rounded-md border border-border bg-[#0f0f0f] p-2 text-xs">
          <span className="text-muted-foreground">{lang === "zh" ? "模板" : "Template"}</span>
          <Select value={activeTemplateId ?? ""} onValueChange={(v) => v && loadTemplate(v)}>
            <SelectTrigger className="h-7 w-72 text-xs">
              <SelectValue placeholder={lang === "zh" ? "选择模板" : "Pick a template"} />
            </SelectTrigger>
            <SelectContent>
              {templates.map((tpl) => (
                <SelectItem key={tpl.id} value={tpl.id}>
                  {[tpl.name, tpl.kind, tpl.scenario].filter(Boolean).join(" · ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input
            value={newTplName}
            onChange={(e) => setNewTplName(e.target.value)}
            placeholder={lang === "zh" ? "新模板名" : "New template name"}
            className="h-7 w-40 rounded border border-border bg-[#111111] px-1.5 text-xs outline-none focus:border-primary"
          />
          <Button size="sm" variant="ghost" onClick={() => void saveTemplate()} disabled={!newTplName.trim()}>
            {lang === "zh" ? "另存为" : "Save as"}
          </Button>
          {activeTemplateId && (
            <Button size="sm" variant="ghost" onClick={() => void deleteActive()}>
              {lang === "zh" ? "删除" : "Delete"}
            </Button>
          )}
        </div>
      )}
      {formColumn}

      <div className="space-y-4 self-start lg:sticky lg:top-6">
        {/* 操作解析卡：右栏第一张卡，永远在命令预览之前，只读、默认展开、内部滚动。 */}
        <StageInsights kind={kind} />
        {!submitInFormColumn && runNameField}
        <ArgvPreview kind={kind} scenario={values.scenario}
                     runName={values.run_name} params={params} />
        {gateStage && <GatePanel gates={gates.value} />}
        {aside}
        {!submitInFormColumn && submitButton}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {!hideTitle && <h1 className="text-lg font-semibold">{title}</h1>}
      {children}

      {grid}

      {gateError && (
        <Alert variant="destructive">
          <AlertTitle>
            {lang === "zh" ? "被验收门槛拦下" : "Blocked by an acceptance gate"}
          </AlertTitle>
          <AlertDescription>
            <p>{gateError.message}</p>
            <GatePanel gates={gateError.gates()} />
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

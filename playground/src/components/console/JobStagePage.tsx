"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ApiError, api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { ArgvPreview } from "./ArgvPreview";
import { GatePanel } from "./GatePanel";
import { usePoll } from "./usePoll";

export type FieldSpec = {
  key: string;
  label?: string;
  kind?: "text" | "number" | "select";
  options?: { value: string; label: string }[];
  hint?: string;
  /** 只在某些场景下出现（例如 snapshot_fractions 只对全参数有意义） */
  when?: (scenario: string, values: Record<string, string>) => boolean;
};

/**
 * 一个阶段页的骨架：左侧可编辑表单，右侧实时 argv 预览 + 闸门 + 提交。
 *
 * 抽出它是因为 5 个阶段页形状完全一样，差异只在「有哪些字段」和「提交什么作业」。
 * 两条设计约定在这里落地：
 * - argv 永远可见（ArgvPreview），因为 runbook 的价值就在于命令可读、可审计。
 * - 闸门失败展开 GatePanel 且不跳走：那是配置问题不是运行失败，不该重试。
 */
export function JobStagePage({
  kind, title, gateStage, fields, initial, children, aside, submitLabel,
}: {
  kind: string;
  title: string;
  gateStage?: string;
  fields: FieldSpec[];
  initial?: Record<string, string>;
  children?: React.ReactNode;
  aside?: React.ReactNode;
  submitLabel?: string;
}) {
  const router = useRouter();
  const { lang } = useLang();
  const [values, setValues] = useState<Record<string, string>>(() => ({
    scenario: "critical-value",
    run_name: "cv-8b-lora-v1",
    ...Object.fromEntries(fields.map((f) => [f.key, f.kind === "select" ? f.options?.[0]?.value ?? "" : ""])),
    ...initial,
  }));
  const [busy, setBusy] = useState(false);
  const [gateError, setGateError] = useState<ApiError | null>(null);

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

  const set = (key: string, value: string) =>
    setValues((previous) => ({ ...previous, [key]: value }));

  const submit = async () => {
    setBusy(true);
    setGateError(null);
    try {
      const job = await api.submit({
        kind, scenario: values.scenario, run_name: values.run_name, params,
      });
      router.push(`/console/jobs/${job.id}`);
    } catch (problem) {
      const apiError = problem as ApiError;
      if (apiError.detail?.kind === "gate") setGateError(apiError);
      else toast.error(apiError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">{title}</h1>
      {children}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="f-scenario">{lang === "zh" ? "场景" : "Scenario"}</Label>
            <Select value={values.scenario} onValueChange={(value) => {
              if (value === null) return;      // base-ui 的 onValueChange 会给 null
              set("run_name", `${value}-8b-lora-v1`);
              set("run_name", `${value}-8b-lora-v1`);
            }}>
              <SelectTrigger id="f-scenario"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["critical-value", "triage", "medication-review", "nursing-quality",
                  "icd-coding"].map((name) => (
                  <SelectItem key={name} value={name}>{name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {fields.filter((f) => f.when?.(values.scenario, values) ?? true).map((field) => (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={`f-${field.key}`} className="font-mono text-xs">
                {field.label ?? field.key}
              </Label>
              {field.kind === "select" ? (
                <Select value={values[field.key]} onValueChange={(v) => v !== null && set(field.key, v)}>
                  <SelectTrigger id={`f-${field.key}`}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {field.options?.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input id={`f-${field.key}`} value={values[field.key]}
                       onChange={(event) => set(field.key, event.target.value)} />
              )}
              {field.hint && (
                <p className="text-xs text-muted-foreground">{field.hint}</p>
              )}
            </div>
          ))}

          <div className="space-y-2">
            <Label htmlFor="f-run" className="font-mono text-xs">run_name</Label>
            <Input id="f-run" value={values.run_name}
                   onChange={(event) => set("run_name", event.target.value)} />
            <p className="text-xs text-muted-foreground">
              {lang === "zh"
                ? "只允许字母数字下划线连字符，尺寸写 8b 不写 0.8b（run_matrix.check_name 用 fullmatch）"
                : "Letters, digits, underscore and hyphen only; write 8b, never 0.8b (run_matrix.check_name uses fullmatch)"}
            </p>
          </div>

          <Button onClick={() => void submit()} disabled={busy}>
            {busy ? (lang === "zh" ? "提交中…" : "Submitting…")
              : submitLabel ?? (lang === "zh" ? "提交作业" : "Submit job")}
          </Button>
        </div>

        <div className="space-y-4">
          <ArgvPreview kind={kind} scenario={values.scenario}
                       runName={values.run_name} params={params} />
          {gateStage && <GatePanel gates={gates.value} />}
          {aside}
        </div>
      </div>

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

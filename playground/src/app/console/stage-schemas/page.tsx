"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type StageParamField, type StageParamVersion, type StageParams } from "@/lib/console";
import { usePoll } from "@/components/console/usePoll";
import { useLang } from "@/lib/i18n";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";

// 由 DB 的 stage_param_specs 支撑的「提交作业」阶段类型（其余阶段表单在前端写死，不在本编辑器范围内）。
const KINDS = [
  "plan_size", "generate", "distill", "distill_daemon",
  "goldset", "split", "precheck", "make_examples",
];

const FIELD_KINDS: StageParamField["kind"][] = ["text", "number", "select", "checkbox", "textarea"];

function blankField(): StageParamField {
  return { key: "", label: "", kind: "text", required: false, default: "", hint: "" };
}

export default function StageSchemasPage() {
  const { lang } = useLang();
  const [selected, setSelected] = useState<string>(KINDS[1]); // generate
  const [draft, setDraft] = useState<StageParamField[]>([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  // 历史版本 / 回滚
  const [historyOpen, setHistoryOpen] = useState(false);
  const [versions, setVersions] = useState<StageParamVersion[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [confirmVersion, setConfirmVersion] = useState<number | null>(null);
  const [rollingBack, setRollingBack] = useState(false);

  // 大间隔：基本不自动轮询，避免误覆盖未保存的编辑；刷新靠切换种类 / 手动「重置」。
  const spec = usePoll(
    useCallback(() => api.stageParams(selected), [selected]),
    null as StageParams | null,
    3_600_000,
  );
  useEffect(() => {
    // 切换种类时收起历史，避免展示上一个 kind 的归档。
    setHistoryOpen(false);
    setVersions([]);
    setConfirmVersion(null);
    void spec.refresh();
  }, [selected]);

  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      setVersions(await api.stageParamVersions(selected));
    } catch (e) {
      toast.error((e as { message: string }).message);
      setVersions([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const doRollback = async (version: number) => {
    setRollingBack(true);
    setConfirmVersion(null);
    try {
      const saved = await api.rollbackStageParams(selected, version);
      setDraft(saved.fields.map((f) => ({ ...f })));
      setDirty(false);
      await spec.refresh();
      await loadHistory();
      toast.success(lang === "zh"
        ? `已回滚到历史版本 v${version}（现 v${saved.version}）`
        : `Rolled back to v${version} (now v${saved.version})`);
    } catch (e) {
      toast.error((e as { message: string }).message);
    } finally {
      setRollingBack(false);
    }
  };

  // 后端 schema 加载/变更时，用其字段重置草稿（重置=丢弃未保存编辑，符合按钮语义）。
  useEffect(() => {
    if (spec.value) {
      setDraft(spec.value.fields.map((f) => ({ ...f })));
      setDirty(false);
    }
  }, [spec.value]);

  const version = spec.value?.version ?? 0;
  const source = spec.value?.source ?? "default";

  const update = (next: StageParamField[]) => { setDraft(next); setDirty(true); };
  const setField = (i: number, patch: Partial<StageParamField>) =>
    update(draft.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const removeField = (i: number) => update(draft.filter((_, j) => j !== i));
  const addField = () => update([...draft, blankField()]);
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= draft.length) return;
    const next = [...draft];
    [next[i], next[j]] = [next[j], next[i]];
    update(next);
  };

  const save = async () => {
    const keys = draft.map((f) => f.key.trim());
    if (keys.some((k) => k === "")) {
      toast.error(lang === "zh" ? "字段 key 不能为空" : "Field key cannot be empty");
      return;
    }
    if (new Set(keys).size !== keys.length) {
      toast.error(lang === "zh" ? "字段 key 必须唯一" : "Field keys must be unique");
      return;
    }
    setSaving(true);
    try {
      const saved = await api.saveStageParams(selected, draft);
      setDraft(saved.fields.map((f) => ({ ...f })));
      setDirty(false);
      await spec.refresh();
      toast.success(lang === "zh"
        ? `已保存 ${selected}（v${saved.version}）`
        : `Saved ${selected} (v${saved.version})`);
    } catch (e) {
      toast.error((e as { message: string }).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">{lang === "zh" ? "作业表单配置" : "Stage schema"}</h1>
        <p className="text-xs text-muted-foreground">
          {lang === "zh"
            ? "编辑各作业类型「提交作业」表单的字段、默认值与必填项；保存到 stage_param_specs（版本化，旧版本进历史），前端据此动态渲染。"
            : "Edit the submit-form fields, defaults and required flags per stage kind; saved to stage_param_specs (versioned). The frontend renders from this."}
        </p>
      </div>

      <div className="flex gap-6">
        <div className="w-44 shrink-0 space-y-1">
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setSelected(k)}
              className={`w-full rounded-md px-3 py-2 text-left font-mono text-xs transition-colors ${
                k === selected ? "bg-[#1e3a8a] text-[#3b82f6]" : "text-muted-foreground hover:bg-[#161616]"
              }`}
            >
              {k}
            </button>
          ))}
        </div>

        <div className="min-w-0 flex-1 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="font-mono text-foreground">{selected}</span>
              <span>{lang === "zh" ? "来源" : "source"}: {source}</span>
              <span>v{version}</span>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => void spec.refresh()}>
                {lang === "zh" ? "重置" : "Reload"}
              </Button>
              <Button size="sm" onClick={() => void save()} disabled={!dirty || saving}>
                {saving ? (lang === "zh" ? "保存中…" : "Saving…") : (lang === "zh" ? "保存" : "Save")}
              </Button>
            </div>
          </div>

          {draft.map((f, i) => (
            <Card key={i} size="sm">
              <CardContent className="space-y-3 pt-3">
                <div className="flex items-start gap-3">
                  <div className="grid flex-1 grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs">{lang === "zh" ? "字段 key" : "key"}</Label>
                      <Input value={f.key} onChange={(e) => setField(i, { key: e.target.value })} placeholder="--n" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">{lang === "zh" ? "显示名" : "label"}</Label>
                      <Input value={f.label ?? ""} onChange={(e) => setField(i, { label: e.target.value })} placeholder="--n" />
                    </div>
                  </div>
                  <div className="flex flex-col gap-1">
                    <Button size="sm" variant="ghost" onClick={() => move(i, -1)} disabled={i === 0}>↑</Button>
                    <Button size="sm" variant="ghost" onClick={() => move(i, 1)} disabled={i === draft.length - 1}>↓</Button>
                    <Button size="sm" variant="ghost" onClick={() => removeField(i)}>{lang === "zh" ? "删" : "Del"}</Button>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">{lang === "zh" ? "控件" : "control"}</Label>
                    <Select
                      value={f.kind ?? "text"}
                      onValueChange={(v) => setField(i, { kind: v as StageParamField["kind"] })}
                    >
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {FIELD_KINDS.map((k) => (
                          <SelectItem key={k} value={k}>{k}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">default</Label>
                    <Input value={f.default ?? ""} onChange={(e) => setField(i, { default: e.target.value })} />
                  </div>
                  <div className="flex items-end gap-3 pb-1">
                    <label className="flex items-center gap-2 text-xs">
                      <Switch size="sm" checked={!!f.required} onCheckedChange={(c) => setField(i, { required: c })} />
                      {lang === "zh" ? "必填" : "required"}
                    </label>
                    <label className="flex items-center gap-2 text-xs">
                      <Switch
                        size="sm"
                        checked={f.fillFrom === "plan"}
                        onCheckedChange={(c) => setField(i, { fillFrom: c ? "plan" : undefined })}
                      />
                      {lang === "zh" ? "从计划读" : "from plan"}
                    </label>
                  </div>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">hint</Label>
                  <Textarea
                    value={f.hint ?? ""}
                    onChange={(e) => setField(i, { hint: e.target.value })}
                    rows={2}
                    className="text-xs"
                  />
                </div>

                {f.kind === "select" && (
                  <div className="space-y-2 rounded-md border border-border p-2">
                    <Label className="text-xs">{lang === "zh" ? "选项 (value=label)" : "options (value=label)"}</Label>
                    {(f.options ?? []).map((opt, oi) => (
                      <div key={oi} className="flex gap-2">
                        <Input
                          className="flex-1" value={opt.value} placeholder="value"
                          onChange={(e) => {
                            const opts = [...(f.options ?? [])];
                            opts[oi] = { ...opt, value: e.target.value };
                            setField(i, { options: opts });
                          }}
                        />
                        <Input
                          className="flex-1" value={opt.label} placeholder="label"
                          onChange={(e) => {
                            const opts = [...(f.options ?? [])];
                            opts[oi] = { ...opt, label: e.target.value };
                            setField(i, { options: opts });
                          }}
                        />
                        <Button
                          size="sm" variant="ghost"
                          onClick={() => {
                            const opts = (f.options ?? []).filter((_, j) => j !== oi);
                            setField(i, { options: opts });
                          }}
                        >×</Button>
                      </div>
                    ))}
                    <Button
                      size="sm" variant="ghost"
                      onClick={() => setField(i, { options: [...(f.options ?? []), { value: "", label: "" }] })}
                    >
                      {lang === "zh" ? "加选项" : "Add option"}
                    </Button>
                    <div className="space-y-1 pt-1">
                      <Label className="text-xs">optionsUrl</Label>
                      <Input
                        value={f.optionsUrl ?? ""}
                        placeholder="/console/api/distill-providers"
                        onChange={(e) => setField(i, { optionsUrl: e.target.value || undefined })}
                      />
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}

          <Button variant="outline" size="sm" onClick={addField}>
            + {lang === "zh" ? "新增字段" : "Add field"}
          </Button>
        </div>
      </div>

      {/* 历史版本与回滚 */}
      <div className="space-y-3 rounded-lg border border-border p-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">
            {lang === "zh" ? "历史版本" : "Version history"}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {lang === "zh" ? `${versions.length} 条（每次保存归档旧版）` : `${versions.length} archived`}
            </span>
          </div>
          <Button
            size="sm" variant="ghost"
            onClick={async () => {
              if (historyOpen) { setHistoryOpen(false); return; }
              await loadHistory();
              setHistoryOpen(true);
            }}
            disabled={loadingHistory}
          >
            {historyOpen ? (lang === "zh" ? "收起" : "Hide") : (lang === "zh" ? "查看历史" : "Show history")}
          </Button>
        </div>

        {historyOpen && (
          versions.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              {lang === "zh" ? "暂无历史版本（至少保存过一次后才有）" : "No archived versions yet."}
            </p>
          ) : (
            <div className="space-y-2">
              {versions.map((v) => (
                <div
                  key={v.id}
                  className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-xs"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-foreground">v{v.version}</span>
                    <span className="text-muted-foreground">{v.created_at}</span>
                    <span className="text-muted-foreground">{v.fields.length} fields</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {confirmVersion === v.version ? (
                      <>
                        <span className="text-muted-foreground">{lang === "zh" ? "确认回滚？" : "Confirm rollback?"}</span>
                        <Button
                          size="sm" variant="destructive"
                          onClick={() => void doRollback(v.version)}
                          disabled={rollingBack}
                        >
                          {lang === "zh" ? "确认" : "Confirm"}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirmVersion(null)}>
                          {lang === "zh" ? "取消" : "Cancel"}
                        </Button>
                      </>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => setConfirmVersion(v.version)}>
                        {lang === "zh" ? "回滚到此版本" : "Roll back"}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}

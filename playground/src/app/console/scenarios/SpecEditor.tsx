"use client";
// spec_json 结构化编辑器（任务 2）：以整个 spec 对象为单一真相源，按顶层键分 tab。
// - 基本信息：name/domain/state/guidance 文本域，variety 字符串数组，state_example 动态键值
// - 问题 questions：类数据表，每行 qid/type/instructions/criteria（按题型自适应），可增删改
// - generator/distill/routing/smoke_probe：各一个 tab，KeyValueEditor 结构化 + RawPanel 原始 JSON 兜底
// - 其它字段：未被上面覆盖的顶层键，用 KeyValueEditor
// - 原始 JSON：全量 spec 的 RawPanel，与结构化视图在「切 tab」时合并（非法则阻止切换）
// 组件本身不保存：编辑通过 onChange 冒泡给页面，页面沿用既有 saveScenarioSpec 通道（含历史/校验）。
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useLang } from "@/lib/i18n";
import { KeyValueEditor } from "./editors/KeyValueEditor";
import { StringListEditor } from "./editors/StringListEditor";
import { RawPanel } from "./editors/RawPanel";

type Spec = Record<string, unknown>;

// 已被专门 tab 覆盖的顶层键；其余归入「其它字段」。
const KNOWN_KEYS = [
  "name", "domain", "state", "state_example", "questions",
  "guidance", "variety", "generator", "distill", "routing", "smoke_probe",
];
const QUESTION_TYPES = ["choice", "noul", "score"];

function isObj(v: unknown): v is Spec {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function asObj(v: unknown): Spec {
  return isObj(v) ? v : {};
}
function text(v: unknown): string {
  if (typeof v === "string") return v;
  return v == null ? "" : JSON.stringify(v);
}
// 保持插入顺序地重命名对象键（用于问题 qid 改名）。
function renameKey(obj: Spec, oldKey: string, newKey: string): Spec {
  const out: Spec = {};
  for (const [k, v] of Object.entries(obj)) out[k === oldKey ? newKey : k] = v;
  return out;
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

// 表单 / 原始 JSON 的模式切换（用于对象型子字段）。
function ModeToggle({ mode, onMode }: { mode: "form" | "raw"; onMode: (m: "form" | "raw") => void }) {
  const { t } = useLang();
  const btn = (m: "form" | "raw", label: string) => (
    <Button
      variant={mode === m ? "default" : "outline"}
      size="sm"
      className="h-7 px-2 text-xs"
      onClick={() => onMode(m)}
    >
      {label}
    </Button>
  );
  return (
    <div className="flex items-center gap-1">
      {btn("form", t("console.spec.mode.form"))}
      {btn("raw", t("console.spec.mode.raw"))}
    </div>
  );
}

// 对象型子字段（generator/distill/routing/smoke_probe）：KeyValueEditor 结构化 + RawPanel 兜底。
// 切模式时做文本 <-> 对象桥接；原始非法则不切回表单（RawPanel 已实时提示）。
function ObjectFieldEditor({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const [mode, setMode] = useState<"form" | "raw">("form");
  const [raw, setRaw] = useState(() => JSON.stringify(asObj(value), null, 2));

  const switchMode = (next: "form" | "raw") => {
    if (next === mode) return;
    if (next === "form") {
      const txt = raw.trim();
      try {
        onChange(txt ? JSON.parse(txt) : {});
      } catch {
        return; // 非法则留在原始模式
      }
    } else {
      setRaw(JSON.stringify(asObj(value), null, 2));
    }
    setMode(next);
  };

  return (
    <div className="space-y-2">
      <ModeToggle mode={mode} onMode={switchMode} />
      {mode === "form" ? (
        <KeyValueEditor value={value} onChange={onChange} />
      ) : (
        <RawPanel value={raw} onChange={setRaw} validate={validateJson} />
      )}
    </div>
  );
}

// 判据编辑器：按题型自适应（choice=键值说明；noul=固定 true/false；score=字符串数组）。
function CriteriaEditor({ type, criteria, onChange }: { type: string; criteria: unknown; onChange: (c: unknown) => void }) {
  if (type === "noul") {
    const c = asObj(criteria);
    const set = (k: string, v: string) => onChange({ ...c, [k]: v });
    return (
      <div className="space-y-1">
        {(["true", "false"] as const).map((k) => (
          <div key={k} className="flex items-start gap-2">
            <span className="mt-1 w-10 shrink-0 font-mono text-[11px] text-muted-foreground">{k}</span>
            <Textarea
              rows={1}
              className="text-xs"
              value={typeof c[k] === "string" ? (c[k] as string) : ""}
              onChange={(e) => set(k, e.target.value)}
            />
          </div>
        ))}
      </div>
    );
  }
  if (type === "score") {
    return <StringListEditor value={Array.isArray(criteria) ? criteria : []} onChange={(v) => onChange(v)} />;
  }
  // choice / 默认：{选项 key: 中文说明}
  return <KeyValueEditor value={criteria} onChange={onChange} />;
}

type QuestionPatch = { type?: string; instructions?: string; criteria?: unknown };

// 单行问题（类数据表的一行）。用 index 作 React key，改名时不重挂载以保留输入焦点。
function QuestionRow({
  qid, q, onPatch, onRename, onRemove,
}: {
  qid: string; q: Spec;
  onPatch: (p: QuestionPatch) => void;
  onRename: (newQid: string) => void;
  onRemove: () => void;
}) {
  const { t } = useLang();
  const type = typeof q.type === "string" ? q.type : "choice";
  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <div className="flex items-center gap-2">
        <Input
          className="h-7 w-40 shrink-0 font-mono text-xs"
          value={qid}
          onChange={(e) => onRename(e.target.value)}
        />
        <Select value={type} onValueChange={(v) => v && onPatch({ type: v })}>
          <SelectTrigger className="h-7 w-44 shrink-0 text-xs">
            <SelectValue>
              {(val: string) => (QUESTION_TYPES.includes(val) ? t(`console.spec.type.${val}`) : val)}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {QUESTION_TYPES.map((ty) => (
              <SelectItem key={ty} value={ty}>{t(`console.spec.type.${ty}`)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="ghost" size="sm"
          className="ml-auto h-7 shrink-0 px-2 text-xs text-muted-foreground"
          onClick={onRemove}
        >
          {t("console.spec.kv.remove")}
        </Button>
      </div>
      <Textarea
        rows={2}
        className="text-xs"
        placeholder={t("console.spec.instructions")}
        value={typeof q.instructions === "string" ? q.instructions : ""}
        onChange={(e) => onPatch({ instructions: e.target.value })}
      />
      <div className="space-y-1">
        <Label className="font-mono text-[11px] text-muted-foreground">{t("console.spec.criteria")}</Label>
        <CriteriaEditor type={type} criteria={q.criteria} onChange={(c) => onPatch({ criteria: c })} />
      </div>
    </div>
  );
}

// 一行「标签 + 控件」的基本信息布局。
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="font-mono text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

export function SpecEditor({ value, onChange }: { value: Spec; onChange: (v: Spec) => void }) {
  const { t } = useLang();
  const [tab, setTab] = useState("basic");
  const [raw, setRaw] = useState(() => JSON.stringify(value, null, 2));

  // 切 tab 时桥接原始 JSON <-> 对象：离开 raw 合并回对象（非法则阻止切换），进入 raw 从对象重新序列化。
  const handleTab = (next: string | number | null) => {
    const key = String(next);
    if (key === tab) return;
    if (tab === "raw") {
      const txt = raw.trim();
      try {
        onChange(txt ? (JSON.parse(txt) as Spec) : {});
      } catch {
        return; // 原始 JSON 非法：停在原 tab，RawPanel 已提示
      }
    }
    if (key === "raw") setRaw(JSON.stringify(value, null, 2));
    setTab(key);
  };

  // ---- questions 类数据表操作 ----
  const questions = asObj(value.questions);
  const setQuestions = (q: Spec) => onChange({ ...value, questions: q });
  const patchQuestion = (qid: string, patch: QuestionPatch) =>
    setQuestions({ ...questions, [qid]: { ...asObj(questions[qid]), ...patch } });
  const addQuestion = () => {
    let id = "q1";
    let n = 1;
    while (id in questions) id = `q${++n}`;
    setQuestions({ ...questions, [id]: { type: "choice", instructions: "", criteria: {} } });
  };

  // ---- 其它字段：未覆盖的顶层键 ----
  const otherKeys = Object.keys(value).filter((k) => !KNOWN_KEYS.includes(k));
  const otherObj: Spec = {};
  for (const k of otherKeys) otherObj[k] = value[k];
  const applyOther = (edited: Spec) => {
    const next: Spec = {};
    for (const [k, v] of Object.entries(value)) {
      if (KNOWN_KEYS.includes(k)) next[k] = v;          // 已知键原样保留
      else if (k in edited) next[k] = edited[k];        // 其它键取编辑后的值
      // 否则：已被删除，跳过
    }
    for (const [k, v] of Object.entries(edited)) {
      if (!(k in next)) next[k] = v;                     // 新增的其它键
    }
    onChange(next);
  };

  const objTab = (key: "generator" | "distill" | "routing" | "smoke_probe") => (
    <ObjectFieldEditor value={value[key]} onChange={(v) => onChange({ ...value, [key]: v })} />
  );

  return (
    <Tabs value={tab} onValueChange={handleTab}>
      <TabsList className="h-auto flex-wrap">
        <TabsTrigger value="basic">{t("console.spec.tab.basic")}</TabsTrigger>
        <TabsTrigger value="questions">{t("console.spec.tab.questions")}</TabsTrigger>
        <TabsTrigger value="generator">{t("console.spec.tab.generator")}</TabsTrigger>
        <TabsTrigger value="distill">{t("console.spec.tab.distill")}</TabsTrigger>
        <TabsTrigger value="routing">{t("console.spec.tab.routing")}</TabsTrigger>
        <TabsTrigger value="smoke_probe">{t("console.spec.tab.smoke")}</TabsTrigger>
        <TabsTrigger value="other">{t("console.spec.tab.other")}</TabsTrigger>
        <TabsTrigger value="raw">{t("console.spec.tab.raw")}</TabsTrigger>
      </TabsList>

      <TabsContent value="basic" className="space-y-3 pt-1">
        <Row label={t("console.spec.name")}>
          <Input className="text-xs" value={text(value.name)} onChange={(e) => onChange({ ...value, name: e.target.value })} />
        </Row>
        <Row label={t("console.spec.domain")}>
          <Textarea rows={3} className="text-xs" value={text(value.domain)} onChange={(e) => onChange({ ...value, domain: e.target.value })} />
        </Row>
        <Row label={t("console.spec.state")}>
          <Textarea rows={3} className="text-xs" value={text(value.state)} onChange={(e) => onChange({ ...value, state: e.target.value })} />
        </Row>
        <Row label={t("console.spec.guidance")}>
          <Textarea rows={6} className="text-xs" value={text(value.guidance)} onChange={(e) => onChange({ ...value, guidance: e.target.value })} />
        </Row>
        <Row label={t("console.spec.variety")}>
          <StringListEditor value={value.variety} onChange={(v) => onChange({ ...value, variety: v })} />
        </Row>
        <Row label={t("console.spec.stateExample")}>
          <KeyValueEditor value={value.state_example} onChange={(v) => onChange({ ...value, state_example: v })} />
        </Row>
      </TabsContent>

      <TabsContent value="questions" className="space-y-2 pt-1">
        {Object.entries(questions).map(([qid, qv], idx) => (
          <QuestionRow
            key={idx}
            qid={qid}
            q={asObj(qv)}
            onPatch={(p) => patchQuestion(qid, p)}
            onRename={(newQid) => { if (newQid && newQid !== qid) setQuestions(renameKey(questions, qid, newQid)); }}
            onRemove={() => { const n = { ...questions }; delete n[qid]; setQuestions(n); }}
          />
        ))}
        <Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={addQuestion}>
          + {t("console.spec.addQuestion")}
        </Button>
      </TabsContent>

      <TabsContent value="generator" className="pt-1">{objTab("generator")}</TabsContent>
      <TabsContent value="distill" className="pt-1">{objTab("distill")}</TabsContent>
      <TabsContent value="routing" className="pt-1">{objTab("routing")}</TabsContent>
      <TabsContent value="smoke_probe" className="pt-1">{objTab("smoke_probe")}</TabsContent>

      <TabsContent value="other" className="space-y-2 pt-1">
        {otherKeys.length === 0 && (
          <p className="text-xs text-muted-foreground">{t("console.spec.otherEmpty")}</p>
        )}
        <KeyValueEditor value={otherObj} onChange={(v) => applyOther(asObj(v))} />
      </TabsContent>

      <TabsContent value="raw" className="pt-1">
        <RawPanel value={raw} onChange={setRaw} validate={validateJson} rows={24} />
      </TabsContent>
    </Tabs>
  );
}

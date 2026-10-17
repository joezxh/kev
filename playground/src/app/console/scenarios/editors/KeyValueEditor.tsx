"use client";
// 动态键值编辑器：把任意 JSON 值（对象 / 数组 / 标量）渲染成可增删改的友好表单。
// 关键字段之外的「不固定字段」用它兜底 —— 值类型自动推断，标量带类型下拉可改，
// 嵌套对象/数组递归展开。与 RawPanel 配合，保证任何结构都能编辑且不丢字段。
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useLang } from "@/lib/i18n";

type Kind = "string" | "number" | "boolean" | "null";

function kindOf(value: unknown): Kind {
  if (value === null || value === undefined) return "null";
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  return "string";
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseScalar(text: string, kind: Kind): unknown {
  switch (kind) {
    case "number": {
      const n = Number(text);
      return text.trim() !== "" && !Number.isNaN(n) ? n : 0;
    }
    case "boolean":
      return text === "true";
    case "null":
      return null;
    default:
      return text;
  }
}

function displayText(value: unknown, kind: Kind): string {
  if (kind === "null") return "";
  if (kind === "boolean") return value ? "true" : "false";
  if (value === null || value === undefined) return "";
  return String(value);
}

function renameKey(obj: Record<string, unknown>, oldKey: string, newKey: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    out[k === oldKey ? newKey : k] = v;
  }
  return out;
}

const inputCls = "h-7 font-mono text-xs";
const kindSelectCls =
  "h-7 shrink-0 rounded-md border border-border bg-background px-1 font-mono text-[11px] text-muted-foreground";

// 标量：类型下拉 + 文本框（本地 state 避免输入被 parse 抖动，prop 变化时重新同步）。
function ScalarEditor({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const [kind, setKind] = useState<Kind>(kindOf(value));
  const [text, setText] = useState(() => displayText(value, kindOf(value)));
  // 外部值真正变化时（切场景 / 原始 tab 同步）才重同步本地态。用 React 官方「渲染期调整状态」
  // 模式而非 effect 里 setState（lint 规则 set-state-in-effect 禁止后者）；标量按值相等比较，
  // 输入中间态（如 "1."）不改变父值，故不会被覆盖，避免数字输入抖动。
  const [lastValue, setLastValue] = useState(value);
  if (lastValue !== value) {
    setLastValue(value);
    const nextKind = kindOf(value);
    setKind(nextKind);
    setText(displayText(value, nextKind));
  }

  const commitKind = (next: Kind) => {
    setKind(next);
    const parsed = next === "boolean" ? false : parseScalar(text, next);
    setText(displayText(parsed, next));
    onChange(parsed);
  };

  return (
    <span className="flex flex-1 items-center gap-1">
      <select className={kindSelectCls} value={kind} onChange={(e) => commitKind(e.target.value as Kind)}>
        <option value="string">str</option>
        <option value="number">num</option>
        <option value="boolean">bool</option>
        <option value="null">null</option>
      </select>
      {kind === "boolean" ? (
        <select
          className={`${kindSelectCls} flex-1`}
          value={text}
          onChange={(e) => { setText(e.target.value); onChange(e.target.value === "true"); }}
        >
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      ) : kind === "null" ? (
        <Input className={inputCls} value="null" disabled />
      ) : (
        <Input
          className={inputCls}
          type={kind === "number" ? "number" : "text"}
          value={text}
          onChange={(e) => { setText(e.target.value); onChange(parseScalar(e.target.value, kind)); }}
        />
      )}
    </span>
  );
}

// 单个值的编辑器：按 JS 类型分派到对象 / 数组 / 标量。
function ValueEditor({ value, onChange, depth }: { value: unknown; onChange: (v: unknown) => void; depth: number }) {
  const { t } = useLang();
  if (Array.isArray(value)) {
    const items = value;
    return (
      <div className="w-full space-y-1 rounded-md border border-border/60 bg-muted/20 p-1.5">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-1">
            <span className="mt-1 w-5 shrink-0 text-right font-mono text-[10px] text-muted-foreground">{i}</span>
            <div className="flex flex-1 items-start gap-1">
              <ValueEditor depth={depth + 1} value={item}
                onChange={(v) => { const next = items.slice(); next[i] = v; onChange(next); }} />
            </div>
            <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs text-muted-foreground"
              onClick={() => onChange(items.filter((_, j) => j !== i))}>
              {t("console.spec.kv.remove")}
            </Button>
          </div>
        ))}
        <Button variant="outline" size="sm" className="h-7 px-2 text-xs"
          onClick={() => onChange([...items, ""])}>
          + {t("console.spec.kv.addItem")}
        </Button>
      </div>
    );
  }
  if (isPlainObject(value)) {
    const entries = Object.entries(value);
    return (
      <div className="w-full space-y-1 rounded-md border border-border/60 bg-muted/20 p-1.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-start gap-1">
            <Input
              className={`${inputCls} w-32 shrink-0`}
              value={k}
              onChange={(e) => onChange(renameKey(value, k, e.target.value))}
            />
            <div className="flex flex-1 items-start gap-1">
              <ValueEditor depth={depth + 1} value={v} onChange={(nv) => onChange({ ...value, [k]: nv })} />
            </div>
            <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs text-muted-foreground"
              onClick={() => { const next = { ...value }; delete next[k]; onChange(next); }}>
              {t("console.spec.kv.remove")}
            </Button>
          </div>
        ))}
        <AddFieldButton onAdd={(key) => onChange({ ...value, [key]: "" })} />
      </div>
    );
  }
  return <ScalarEditor value={value} onChange={onChange} />;
}

// 「新增字段」：内联输入键名后确认，避免用 prompt()。
function AddFieldButton({ onAdd }: { onAdd: (key: string) => void }) {
  const { t } = useLang();
  const [adding, setAdding] = useState(false);
  const [key, setKey] = useState("");
  if (!adding) {
    return (
      <Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => setAdding(true)}>
        + {t("console.spec.kv.add")}
      </Button>
    );
  }
  return (
    <span className="flex items-center gap-1">
      <Input className={`${inputCls} w-40`} placeholder={t("console.spec.kv.key")} value={key}
        onChange={(e) => setKey(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && key.trim()) { onAdd(key.trim()); setKey(""); setAdding(false); } }} />
      <Button size="sm" className="h-7 px-2 text-xs" disabled={!key.trim()}
        onClick={() => { onAdd(key.trim()); setKey(""); setAdding(false); }}>
        {t("console.spec.kv.add")}
      </Button>
      <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => { setKey(""); setAdding(false); }}>
        ×
      </Button>
    </span>
  );
}

// 对外入口：编辑一个对象（顶层必须是对象；非对象时包一层展示）。
export function KeyValueEditor({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const obj = isPlainObject(value) ? value : {};
  return <ValueEditor value={obj} onChange={onChange} depth={0} />;
}

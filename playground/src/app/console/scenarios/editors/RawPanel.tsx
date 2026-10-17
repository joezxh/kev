"use client";
// 原始文本编辑器 + 解析校验兜底。校验器由父组件注入（JSON 用 JSON.parse，YAML 用 js-yaml load），
// 组件本身不绑定任何解析库，保持无依赖可复用。校验失败时在下方红字提示，
// 父组件可据此阻止「切 tab / 保存」。
import { useMemo } from "react";
import { Textarea } from "@/components/ui/textarea";

export function RawPanel({
  value,
  onChange,
  validate,
  rows = 18,
  placeholder,
  className,
}: {
  value: string;
  onChange: (text: string) => void;
  validate?: (text: string) => string | null; // 返回错误信息或 null（合法）
  rows?: number;
  placeholder?: string;
  className?: string;
}) {
  const error = useMemo(() => (validate ? validate(value) : null), [validate, value]);
  return (
    <div className="space-y-1">
      <Textarea
        className={className ?? "min-h-72 font-mono text-xs"}
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

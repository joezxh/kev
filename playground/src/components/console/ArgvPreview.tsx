"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { renderArgv } from "./format";

/**
 * 每个作业表单右侧都必须显示将要执行的完整 argv（只读、可复制）。
 *
 * 理由来自 runbook 的价值结构：步骤给的是「目的 / 输入 / 命令 / 预期输出 / 验证」。
 * 藏起命令会让用户失去可审计性与可复现性，医疗场景下这是硬伤（spec §11.2）。
 */
export function ArgvPreview({ kind, scenario, runName, params, className }: {
  kind: string;
  scenario: string;
  runName: string;
  params: Record<string, unknown>;
  className?: string;
}) {
  const [argv, setArgv] = useState<string[] | null>(null);
  const [outcome, setOutcome] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { t } = useLang();
  const paramsKey = JSON.stringify(params);

  useEffect(() => {
    let cancelled = false;
    // 防抖：打字时不去打爆编排服务
    const timer = setTimeout(() => {
      api.preview({ kind, scenario, run_name: runName, params })
        .then((result) => {
          if (cancelled) return;
          setArgv(result.argv);
          setOutcome(result.outcome);
          setError(null);
        })
        .catch((problem: Error) => {
          if (cancelled) return;
          setError(problem.message);
          setArgv(null);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // params 是个对象字面量，引用每次渲染都变；用序列化后的字符串当依赖键，
    // 语义是「内容变了才重取」—— 这正是想要的。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, scenario, runName, paramsKey]);

  const text = argv ? renderArgv(argv) : "";

  return (
    <div className={className}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          {t("console.argv.preview")}
        </span>
        {argv && (
          <Button size="sm" variant="ghost" onClick={() => void navigator.clipboard.writeText(text)}>
            {t("console.argv.copy")}
          </Button>
        )}
      </div>
      <ScrollArea className="max-h-44 rounded-md border border-border bg-muted/40">
        <pre className="p-3 font-mono text-xs leading-relaxed break-all">
          {error ? <span className="text-destructive">{error}</span>
            : argv ? text : "…"}
        </pre>
      </ScrollArea>
      {outcome && !error && (
        <p className="mt-1.5 text-xs text-muted-foreground">{outcome}</p>
      )}
      <p className="mt-1.5 text-xs text-muted-foreground">{t("console.argv.hint")}</p>
    </div>
  );
}
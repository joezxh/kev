"use client";

import { useCallback, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";

type Question = { type?: string; options?: string[]; label?: number | string; target?: unknown };
type Record_ = { state?: Record<string, unknown>; questions?: Record<string, Question> };

/** 金标人工审校（runbook §七 7.4 项 7）：纯前端，无子进程。
 *  读入 goldset sample 产出的 jsonl，逐条改标签，导出可喂 split --holdout 的金标文件。 */
export default function GoldsetReviewPage() {
  const { t, lang } = useLang();
  const loadDatasets = useCallback(() => api.datasets(), []);
  const datasets = usePoll(loadDatasets, []);
  const goldSets = useMemo(
    () => datasets.value.filter((a) => a.id.includes("gold")),
    [datasets.value],
  );

  const [selected, setSelected] = useState("");
  const [records, setRecords] = useState<Record_[]>([]);
  const [cursor, setCursor] = useState(0);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!selected) return;
    setError("");
    try {
      const text = await (await fetch(api.exportUrl(selected))).text();
      const parsed = text.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
      setRecords(parsed);
      setCursor(0);
    } catch (e) {
      setError(String(e));
    }
  }, [selected]);

  const setLabel = (qid: string, value: string) => {
    setRecords((prev) => prev.map((r, i) => {
      if (i !== cursor) return r;
      const questions = { ...(r.questions ?? {}) };
      questions[qid] = { ...questions[qid], label: Number(value) };
      return { ...r, questions };
    }));
  };

  const exportHoldout = () => {
    const blob = new Blob([records.map((r) => JSON.stringify(r)).join("\n") + "\n"],
      { type: "application/x-ndjson" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selected.replace(/\W+/g, "_") || "gold"}-reviewed.jsonl`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const record = records[cursor];
  const questions = record?.questions ?? {};

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold">{t("console.goldset.reviewTitle")}</h1>
        <p className="text-sm text-muted-foreground">{t("console.goldset.reviewHint")}</p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-2">
          <Label htmlFor="f-gold">{lang === "zh" ? "金标文件" : "Gold file"}</Label>
          <Select value={selected} onValueChange={(v) => v !== null && setSelected(v)}>
            <SelectTrigger id="f-gold"><SelectValue placeholder="dataset:*.gold" /></SelectTrigger>
            <SelectContent>
              {goldSets.map((a) => (
                <SelectItem key={a.id} value={a.id}>{a.id}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={() => void load()} disabled={!selected}>
          {lang === "zh" ? "载入" : "Load"}
        </Button>
        <Button variant="secondary" onClick={exportHoldout} disabled={records.length === 0}>
          {t("console.goldset.exportHoldout")}
        </Button>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>

      {records.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{lang === "zh" ? "记录" : "Record"} {cursor + 1} / {records.length}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" disabled={cursor === 0}
                  onClick={() => setCursor((c) => c - 1)}>←</Button>
                <Button size="sm" variant="ghost" disabled={cursor === records.length - 1}
                  onClick={() => setCursor((c) => c + 1)}>→</Button>
              </div>
            </div>
            <pre className="max-h-72 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
              {JSON.stringify(record?.state ?? {}, null, 2)}
            </pre>
          </div>

          <div className="space-y-3">
            {Object.entries(questions).map(([qid, q]) => (
              <div key={qid} className="space-y-1 rounded-md border border-border p-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs">{qid}</span>
                  <span className="text-xs text-muted-foreground">{q.type}</span>
                </div>
                {q.options && (
                  <p className="text-xs text-muted-foreground">{q.options.join(" | ")}</p>
                )}
                <div className="flex items-center gap-2">
                  <Label className="font-mono text-xs">label</Label>
                  <Input className="w-24" value={String(q.label ?? "")}
                    onChange={(e) => setLabel(qid, e.target.value)} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

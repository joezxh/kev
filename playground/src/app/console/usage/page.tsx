"use client";
import { useCallback, useEffect, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardAction } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type UsageRow, type UsageDay, type DistillUsageRow, type DistillProvider, type DistillUsageTotal } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";
import { UsageChart } from "@/components/console/UsageChart";

const RANGES = [["7", "7d"], ["30", "30d"], ["", "all"]] as const;

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

// 当前页前后各 span 页的窗口，避免页数过多时点爆。
function pageWindow(cur: number, total: number, span = 2): number[] {
  const lo = Math.max(1, cur - span);
  const hi = Math.min(total, cur + span);
  const out: number[] = [];
  for (let i = lo; i <= hi; i++) out.push(i);
  return out;
}

export default function UsagePage() {
  const { t, lang } = useLang();
  const [tab, setTab] = useState<string>("kev");
  const [days, setDays] = useState<string>("7");
  const from = days ? isoDaysAgo(Number(days)) : undefined;
  const load = useCallback(() => api.usageSummary(from), [from]);
  const { value: rows } = usePoll<UsageRow[]>(load, []);
  const [open, setOpen] = useState<string | null>(null);
  const series = usePoll<UsageDay[]>(
    useCallback(() => (open ? api.usageTimeseries(open, from) : Promise.resolve([])), [open, from]),
    [],
  );

  // ---- Kev 核心接口用量：前端分页（usageSummary 返回全量，按 key 切片展示）----
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [jump, setJump] = useState("");
  const total = rows?.length ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const pageRows = (rows ?? []).slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => { setPage(1); }, [days]);
  function goPage(p: number) {
    const np = Math.min(Math.max(1, p), totalPages);
    setPage(np);
    setOpen(null);
  }
  function changePageSize(ps: number) {
    setPageSize(ps);
    setPage(1);
    setOpen(null);
  }
  function goJump() {
    const n = parseInt(jump, 10);
    if (!Number.isNaN(n)) { goPage(n); setJump(""); }
  }

  // ---- distill 第三方用量 ----
  const [provFilter, setProvFilter] = useState("");
  const [providers, setProviders] = useState<Pick<DistillProvider, "id" | "name">[]>([]);
  const [distill, setDistill] = useState<DistillUsageRow[]>([]);
  useEffect(() => {
    api.distillProviders().then(setProviders).catch(() => setProviders([]));
  }, []);
  useEffect(() => {
    api.distillUsage(provFilter || undefined, from).then(setDistill).catch(() => setDistill([]));
  }, [provFilter, days]);
  const provName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;

  // ---- 按日汇总 + 预算告警（P2-2）：预算存 localStorage，前端告警不进后端 ----
  const [totals, setTotals] = useState<DistillUsageTotal[]>([]);
  useEffect(() => {
    api.distillUsageTotals(from).then(setTotals).catch(() => setTotals([]));
  }, [days]);
  const [budget, setBudget] = useState<string>(
    () => (typeof window !== "undefined" ? window.localStorage.getItem("kev-distill-budget") ?? "" : ""));
  const today = new Date().toISOString().slice(0, 10);
  const todayTokens = totals.find((row) => row.day === today)?.tokens ?? 0;
  const budgetNum = Number(budget);
  const overBudget = budget !== "" && Number.isFinite(budgetNum) && budgetNum > 0 && todayTokens > budgetNum;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{t("console.usage.title")}</h1>
        <div className="flex gap-1">
          {RANGES.map(([d, label]) => (
            <Button key={label} size="sm" variant={d === days ? "secondary" : "ghost"}
                    onClick={() => setDays(d)}>{label}</Button>
          ))}
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="kev">{t("console.usage.kev")}</TabsTrigger>
          <TabsTrigger value="distill">{t("console.usage.distill")}</TabsTrigger>
        </TabsList>

        {/* ---- Kev 核心接口用量 ---- */}
        <TabsContent value="kev">
          <Card>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>prefix</TableHead><TableHead>{t("console.apikeys.name")}</TableHead>
                    <TableHead>{t("console.apikeys.calls")}</TableHead>
                    <TableHead>in/out tok</TableHead>
                    <TableHead>avg ms</TableHead><TableHead>p99 ms</TableHead>
                    <TableHead>{t("console.apikeys.lastUsed")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(pageRows).map((r) => (
                    <TableRow key={r.id} className="cursor-pointer" onClick={() => setOpen(open === r.id ? null : r.id)}>
                      <TableCell className="font-mono text-xs">{r.prefix}</TableCell>
                      <TableCell>{r.name}</TableCell>
                      <TableCell>{formatNumber(r.calls, 0)}</TableCell>
                      <TableCell className="text-xs">{formatNumber(r.input_tokens, 0)}/{formatNumber(r.output_tokens, 0)}</TableCell>
                      <TableCell className="text-xs">{r.avg_latency_ms == null ? "—" : formatNumber(r.avg_latency_ms, 1)}</TableCell>
                      <TableCell className="text-xs">{formatNumber(r.p99_latency_ms, 1)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{r.last_used ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {open && series.value && series.value.length > 0 && (
                <div className="mt-4">
                  <UsageChart days={series.value} />
                </div>
              )}

              {total > 0 && (
                <div className="mt-4 flex flex-col gap-3 border-t border-border pt-4">
                  <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                    <p className="text-muted-foreground">{t("console.apikeys.total", { n: total })} · {t("console.apikeys.pageOf", { page, total: totalPages })}</p>
                    <div className="flex items-center gap-1">
                      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => goPage(page - 1)}>{t("console.apikeys.prev")}</Button>
                      {pageWindow(page, totalPages).map((p) => (
                        <Button key={p} variant={p === page ? "default" : "outline"} size="sm" className="min-w-8" onClick={() => goPage(p)}>{p}</Button>
                      ))}
                      <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => goPage(page + 1)}>{t("console.apikeys.next")}</Button>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <span>{t("console.apikeys.pageSize")}</span>
                      <select
                        className="h-8 rounded-md border border-border bg-background px-2 text-xs"
                        value={pageSize}
                        onChange={(e) => changePageSize(Number(e.target.value))}
                      >
                        {PAGE_SIZE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
                      </select>
                    </div>
                    <div className="flex items-center gap-2">
                      <span>{t("console.apikeys.goTo")}</span>
                      <input
                        type="number"
                        min={1}
                        max={totalPages}
                        value={jump}
                        onChange={(e) => setJump(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") goJump(); }}
                        className="h-8 w-20 rounded-md border border-input bg-transparent px-2 text-xs outline-none focus-visible:border-ring"
                      />
                      <span>{t("console.apikeys.pageUnit")}</span>
                      <Button variant="outline" size="sm" onClick={goJump}>{t("console.apikeys.go")}</Button>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- 蒸馏第三方模型用量 ---- */}
        <TabsContent value="distill">
          <Card>
            <CardHeader>
              <CardTitle>{t("console.usage.distill")}</CardTitle>
              <CardAction>
                <div className="flex flex-wrap gap-1">
                  <Button size="sm" variant={provFilter === "" ? "secondary" : "ghost"} onClick={() => setProvFilter("")}>all</Button>
                  {providers.map((p) => (
                    <Button key={p.id} size="sm" variant={provFilter === p.id ? "secondary" : "ghost"}
                            onClick={() => setProvFilter(p.id)}>{p.name}</Button>
                  ))}
                </div>
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-6">
              <Table>
                <TableHeader>
                  <TableRow><TableHead>config</TableHead><TableHead>key</TableHead><TableHead>model</TableHead>
                    <TableHead>tokens</TableHead><TableHead>days</TableHead><TableHead>{t("console.distill.dailyLimit")}</TableHead></TableRow>
                </TableHeader>
                <TableBody>
                  {(distill ?? []).map((r, i) => (
                    <TableRow key={i}>
                      <TableCell>{r.provider_id ? provName(r.provider_id) : "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{r.key_hint}</TableCell>
                      <TableCell>{r.model}</TableCell>
                      <TableCell>{formatNumber(r.tokens, 0)}</TableCell>
                      <TableCell>{r.days}</TableCell>
                      <TableCell className="text-xs">
                        {formatNumber(r.tokens, 0)} / {formatNumber(r.daily_limit, 0)}
                        {r.daily_limit > 0 && r.tokens >= r.daily_limit &&
                          <span className="ml-1 text-destructive">⚠</span>}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <h3 className="text-sm font-medium">
                    {lang === "zh" ? "按日汇总" : "Daily totals"}
                  </h3>
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    {lang === "zh" ? "每日预算 (tokens)" : "Daily budget (tokens)"}
                    <input
                      type="number"
                      value={budget}
                      onChange={(e) => {
                        setBudget(e.target.value);
                        window.localStorage.setItem("kev-distill-budget", e.target.value);
                      }}
                      className="h-7 w-32 rounded-md border border-input bg-transparent px-2 text-xs outline-none focus-visible:border-ring"
                    />
                  </label>
                  <span className={`text-xs ${overBudget ? "font-medium text-destructive" : "text-muted-foreground"}`}>
                    {lang === "zh" ? "今日 " : "today "}
                    {formatNumber(todayTokens, 0)}
                    {overBudget && (lang === "zh" ? " — 已超预算 ⚠" : " — over budget ⚠")}
                  </span>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow><TableHead>day</TableHead><TableHead>tokens</TableHead></TableRow>
                  </TableHeader>
                  <TableBody>
                    {(totals ?? []).map((row) => (
                      <TableRow key={row.day}>
                        <TableCell className="font-mono text-xs">{row.day}</TableCell>
                        <TableCell className="text-xs">{formatNumber(row.tokens, 0)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10) + "T00:00:00";
}

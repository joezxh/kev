"use client";
import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type ApiKey } from "@/lib/console";
import { apikeyStore } from "@/lib/apikey-store";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";

type ApiKeyPage = { items: ApiKey[]; total: number; page: number; page_size: number };

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

export default function ApiKeysPage() {
  const { t } = useLang();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<{ prefix: string; key: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [jump, setJump] = useState("");
  const pageRef = useRef(page);
  const pageSizeRef = useRef(pageSize);

  // 翻页用 ref 同步，避免 usePoll 轮询/立即刷新取到旧页或旧每页大小。
  const load = useCallback(() => api.apikeys(pageRef.current, pageSizeRef.current), []);
  const { value: data, refresh } = usePoll<ApiKeyPage>(load, { items: [], total: 0, page: 1, page_size: DEFAULT_PAGE_SIZE });

  const total = data.total;
  const totalPages = Math.max(1, Math.ceil(total / data.page_size));

  function goPage(p: number) {
    const np = Math.min(Math.max(1, p), totalPages);
    pageRef.current = np;
    setPage(np);
    void refresh();
  }
  function changePageSize(ps: number) {
    pageSizeRef.current = ps;
    setPageSize(ps);
    pageRef.current = 1;
    setPage(1);
    void refresh();
  }
  function goJump() {
    const n = parseInt(jump, 10);
    if (!Number.isNaN(n)) {
      goPage(n);
      setJump("");
    }
  }

  async function onCreate() {
    setError(null);
    try {
      const row = await api.createApiKey(name || "key");
      setCreated({ prefix: row.prefix, key: row.key });
      apikeyStore.saveKey(row.id, row.prefix, row.key);   // id 只存本地
      setName("");
      refresh();
    } catch (e) { setError((e as Error).message); }
  }
  // 撤销 / 重新启用 切换：active -> 撤销；非 active -> 重新启用。
  async function onToggle(k: ApiKey) {
    setError(null);
    try {
      if (k.active) {
        await api.revokeApiKey(k.id);
        // 撤销不清除本浏览器的副本：明文只在创建时展示一次并存入本地，
        // 撤销服务端 key 不会让本地副本失效；保留它以便「撤销→重新启用」后仍能在本浏览器使用。
      } else {
        await api.reactivateApiKey(k.id);
      }
      refresh();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">{t("console.nav.apikeys")}</h1>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-2">
          <Label htmlFor="kname">{t("console.apikeys.name")}</Label>
          <Input id="kname" value={name} onChange={(e) => setName(e.target.value)} placeholder="playground" />
        </div>
        <Button onClick={() => void onCreate()}>{t("console.apikeys.create")}</Button>
      </div>
      {created && (
        <div className="rounded-md border border-dashed border-border p-3 text-sm">
          <p className="font-medium">{t("console.apikeys.shownOnce")}</p>
          <code className="block break-all rounded bg-muted p-2 text-xs">{created.key}</code>
          <p className="mt-1 text-xs text-muted-foreground">{t("console.apikeys.copyNow")}</p>
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>prefix</TableHead><TableHead>{t("console.apikeys.name")}</TableHead>
            <TableHead>{t("console.apikeys.status")}</TableHead>
            <TableHead>{t("console.apikeys.calls")}</TableHead>
            <TableHead>tokens</TableHead><TableHead>{t("console.apikeys.lastUsed")}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(data.items ?? []).map((k) => (
            <TableRow key={k.id}>
              <TableCell className="font-mono text-xs">{k.prefix}</TableCell>
              <TableCell>{k.name}</TableCell>
              <TableCell>
                {k.active
                  ? <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-600">{t("console.apikeys.active")}</span>
                  : <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-600">{t("console.apikeys.revoked")}</span>}
              </TableCell>
              <TableCell>{formatNumber(k.calls, 0)}</TableCell>
              <TableCell className="text-xs">{formatNumber(k.input_tokens + k.output_tokens, 0)}</TableCell>
              <TableCell className="text-xs text-muted-foreground">{k.last_used ?? "—"}</TableCell>
              <TableCell className="text-right">
                {k.active
                  ? <Button size="sm" variant="ghost" className="text-red-600 hover:text-red-700" onClick={() => void onToggle(k)}>{t("console.apikeys.revoke")}</Button>
                  : <Button size="sm" variant="ghost" className="text-emerald-600 hover:text-emerald-700" onClick={() => void onToggle(k)}>{t("console.apikeys.reactivate")}</Button>}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="flex flex-col gap-3 border-t border-border pt-4">
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
            <Input
              type="number"
              min={1}
              max={totalPages}
              value={jump}
              onChange={(e) => setJump(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") goJump(); }}
              className="h-8 w-20 text-xs"
            />
            <span>{t("console.apikeys.pageUnit")}</span>
            <Button variant="outline" size="sm" onClick={goJump}>{t("console.apikeys.go")}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

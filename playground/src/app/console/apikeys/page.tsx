"use client";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type ApiKey } from "@/lib/console";
import { apikeyStore } from "@/lib/apikey-store";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";

export default function ApiKeysPage() {
  const { t, lang } = useLang();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<{ prefix: string; key: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api.apikeys(), []);
  const { value: keys, refresh } = usePoll<ApiKey[]>(load, []);

  async function onCreate() {
    setError(null);
    try {
      const row = await api.createApiKey(name || "key");
      setCreated({ prefix: row.prefix, key: row.key });
      apikeyStore.saveKey(row.id, row.prefix, row.key);   // 明文只存本地
      setName("");
      refresh();
    } catch (e) { setError((e as Error).message); }
  }
  async function onRevoke(id: string) {
    setError(null);
    try {
      await api.revokeApiKey(id);
      apikeyStore.clearKey(id);
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
          {(keys ?? []).map((k) => (
            <TableRow key={k.id}>
              <TableCell className="font-mono text-xs">{k.prefix}</TableCell>
              <TableCell>{k.name}</TableCell>
              <TableCell>{k.active ? t("console.apikeys.active") : t("console.apikeys.revoked")}</TableCell>
              <TableCell>{formatNumber(k.calls, 0)}</TableCell>
              <TableCell className="text-xs">{formatNumber(k.input_tokens + k.output_tokens, 0)}</TableCell>
              <TableCell className="text-xs text-muted-foreground">{k.last_used ?? "—"}</TableCell>
              <TableCell className="text-right">
                {k.active && <Button size="sm" variant="ghost" onClick={() => void onRevoke(k.id)}>
                  {t("console.apikeys.revoke")}</Button>}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

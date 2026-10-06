"use client";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type DistillProvider } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";

export default function DistillProvidersPage() {
  const { t, lang } = useLang();
  const [form, setForm] = useState({ name: "", base_url: "https://api.openai.com/v1",
    model: "", daily_limit: "500000", keys: "" });
  const set = (k: keyof typeof form, v: string) => setForm((p) => ({ ...p, [k]: v }));
  const load = useCallback(() => api.distillProviders(), []);
  const { value: list, refresh } = usePoll<DistillProvider[]>(load, []);

  async function onCreate() {
    try {
      await api.createDistillProvider({ name: form.name || "provider", base_url: form.base_url,
        model: form.model, daily_limit: Number(form.daily_limit) || 500000,
        keys: form.keys.split("\n").map((s) => s.trim()).filter(Boolean) });
      toast.success(t("console.distill.created"));
      setForm({ ...form, name: "", model: "", keys: "" });
      refresh();
    } catch (e) { toast.error((e as Error).message); }
  }
  async function onDeactivate(id: string) { await api.deactivateDistillProvider(id); refresh(); }

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">{t("console.nav.distill")}</h1>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="dname" label={t("console.apikeys.name")} value={form.name} onChange={(v) => set("name", v)} />
        <Field id="dmodel" label="model" value={form.model} onChange={(v) => set("model", v)} />
        <Field id="durl" label="Base URL" value={form.base_url} onChange={(v) => set("base_url", v)} />
        <Field id="dlim" label={t("console.distill.dailyLimit")} value={form.daily_limit} onChange={(v) => set("daily_limit", v)} />
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="dkeys">{t("console.distill.keys")}</Label>
          <textarea id="dkeys" className="h-24 w-full rounded-md border border-border bg-background p-2 font-mono text-xs"
            value={form.keys} onChange={(e) => set("keys", e.target.value)}
            placeholder={"sk-... 每行一个"} />
        </div>
      </div>
      <Button onClick={() => void onCreate()}>{t("console.distill.create")}</Button>
      <Table>
        <TableHeader>
          <TableRow><TableHead>{t("console.apikeys.name")}</TableHead><TableHead>Base URL</TableHead>
            <TableHead>model</TableHead><TableHead>{t("console.distill.dailyLimit")}</TableHead>
            <TableHead>keys</TableHead><TableHead /></TableRow>
        </TableHeader>
        <TableBody>
          {(list ?? []).map((p) => (
            <TableRow key={p.id}>
              <TableCell>{p.name}</TableCell><TableCell className="font-mono text-xs">{p.base_url}</TableCell>
              <TableCell>{p.model}</TableCell><TableCell>{formatNumber(p.daily_limit, 0)}</TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">{(p.key_hints ?? []).join(" ")}</TableCell>
              <TableCell className="text-right">
                <Button size="sm" variant="ghost" onClick={() => void onDeactivate(p.id)}>
                  {t("console.distill.deactivate")}</Button></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Field({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

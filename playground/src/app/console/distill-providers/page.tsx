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
  const { t } = useLang();
  const [form, setForm] = useState({ name: "", base_url: "https://api.openai.com/v1",
    model: "", daily_limit: "500000", keys: "" });
  const [editingId, setEditingId] = useState<string | null>(null);
  const set = (k: keyof typeof form, v: string) => setForm((p) => ({ ...p, [k]: v }));
  const load = useCallback(() => api.distillProviders(), []);
  const { value: list, refresh } = usePoll<DistillProvider[]>(load, []);

  function startEdit(p: DistillProvider) {
    setEditingId(p.id);
    setForm({ name: p.name, base_url: p.base_url, model: p.model,
      daily_limit: String(p.daily_limit), keys: "" });
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }
  function cancelEdit() {
    setEditingId(null);
    setForm({ name: "", base_url: "https://api.openai.com/v1", model: "", daily_limit: "500000", keys: "" });
  }
  async function onSave() {
    const payload = { name: form.name || "provider", base_url: form.base_url,
      model: form.model, daily_limit: Number(form.daily_limit) || 500000,
      keys: form.keys.split("\n").map((s) => s.trim()).filter(Boolean) };
    try {
      if (editingId) {
        await api.updateDistillProvider(editingId, payload);
        toast.success(t("console.distill.created"));
      } else {
        await api.createDistillProvider(payload);
        toast.success(t("console.distill.created"));
      }
      cancelEdit();
      refresh();
    } catch (e) { toast.error((e as Error).message); }
  }
  async function onDeactivate(id: string) { await api.deactivateDistillProvider(id); refresh(); }

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">{t("console.nav.distill")}</h1>

      {/* 配置列表（上方） */}
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
                <div className="flex justify-end gap-1">
                  <Button size="sm" variant="ghost" onClick={() => startEdit(p)}>{t("console.distill.edit")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => void onDeactivate(p.id)}>
                    {t("console.distill.deactivate")}</Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* 新增 / 编辑表单（下方） */}
      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-medium">
          {editingId ? t("console.distill.edit") : t("console.distill.create")}
        </h2>
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
            {editingId && (
              <p className="text-xs text-muted-foreground">{t("console.distill.keepKeys")}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => void onSave()}>
            {editingId ? t("console.distill.save") : t("console.distill.create")}
          </Button>
          {editingId && (
            <Button variant="ghost" onClick={cancelEdit}>{t("console.common.cancel")}</Button>
          )}
        </div>
      </div>
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

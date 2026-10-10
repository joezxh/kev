"use client";

import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { api, type ApiKey } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { Drawer, EmptyState, Field, PageHead, Panel, StatusBadge } from "./primitives";

export function ApiKeysManager() {
  const { t } = useLang();
  const load = useCallback(() => api.apikeys(1, 50), []);
  const { value, refresh } = usePoll<{ items: ApiKey[]; total: number }>(load, { items: [], total: 0 });

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    try {
      const res = await api.createApiKey(name || "untitled");
      setNewKey(res.key);
      setName("");
      toast.success(t("studio.apikeys.createdToast"));
      void refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    await api.revokeApiKey(id);
    toast.success(t("studio.apikeys.revokedToast"));
    void refresh();
  };
  const reactivate = async (id: string) => {
    await api.reactivateApiKey(id);
    toast.success(t("studio.apikeys.reactivatedToast"));
    void refresh();
  };

  return (
    <div className="space-y-4">
      <PageHead
        title={t("studio.apikeys.title")}
        subtitle={t("studio.apikeys.subtitle")}
        actions={<Button size="sm" onClick={() => { setNewKey(null); setOpen(true); }}>+ {t("studio.apikeys.create")}</Button>}
      />

      {value.items.length === 0 ? (
        <EmptyState title={t("studio.apikeys.empty")} />
      ) : (
        <Panel>
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2">{t("studio.apikeys.name")}</th>
                <th className="px-3 py-2">{t("studio.apikeys.prefix")}</th>
                <th className="px-3 py-2 text-right">{t("studio.apikeys.calls")}</th>
                <th className="px-3 py-2 text-right">{t("studio.apikeys.tokens")}</th>
                <th className="px-3 py-2">{t("studio.apikeys.lastUsed")}</th>
                <th className="px-3 py-2">{t("studio.apikeys.created")}</th>
                <th className="px-3 py-2 text-right">{t("studio.apikeys.revoke")}</th>
              </tr>
            </thead>
            <tbody>
              {value.items.map((k) => (
                <tr key={k.id} className="border-b border-border/60 last:border-0">
                  <td className="px-3 py-2">{k.name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{k.prefix}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{k.calls}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{(k.input_tokens + k.output_tokens).toLocaleString()}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{k.last_used ? k.last_used.slice(0, 19) : "—"}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{k.created_at.slice(0, 19)}</td>
                  <td className="px-3 py-2 text-right">
                    {k.active ? (
                      <Button size="xs" variant="ghost" className="text-[#ef4444]" onClick={() => void revoke(k.id)}>{t("studio.apikeys.revoke")}</Button>
                    ) : (
                      <Button size="xs" variant="ghost" onClick={() => void reactivate(k.id)}>{t("studio.apikeys.reactivate")}</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={t("studio.apikeys.create")}
        footer={<Button size="sm" disabled={busy || !name} onClick={() => void create()}>{t("studio.apikeys.create")}</Button>}
      >
        {newKey ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">{t("studio.apikeys.createdToast")}</p>
            <Input readOnly value={newKey} className="bg-[#0a0a0a] font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
          </div>
        ) : (
          <Field label={t("studio.apikeys.name")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="bg-[#0a0a0a]" placeholder="prod-edge" />
          </Field>
        )}
      </Drawer>
    </div>
  );
}

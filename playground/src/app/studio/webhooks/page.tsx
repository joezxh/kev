"use client";

import { useEffect, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button as UiButton } from "@/components/ui/button";
import { useLang } from "@/lib/i18n";
import { api, type Webhook } from "@/lib/console";
import { useProjects, ProjectSwitcher } from "@/components/studio/ProjectSwitcher";
import { PageHead, Panel, Drawer, FormGrid, Field, EmptyState, StatusBadge } from "@/components/studio/primitives";

const EVENTS = ["job.started", "job.succeeded", "job.failed", "deploy.promoted", "invoice.issued"];

export default function StudioWebhooksPage() {
  const { t, lang } = useLang();
  const { projects } = useProjects();
  const [pid, setPid] = useState<string | null>(null);
  const [hooks, setHooks] = useState<Webhook[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Webhook | null>(null);
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [secret, setSecret] = useState("");
  const [active, setActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pinging, setPinging] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!pid && projects.length) setPid(projects[0].id);
  }, [projects, pid]);

  useEffect(() => {
    if (!pid) return;
    let alive = true;
    setLoading(true);
    api.webhooks(pid)
      .then((w) => alive && setHooks(w))
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [pid]);

  function openCreate() {
    setEditing(null);
    setUrl("");
    setEvents([]);
    setSecret("");
    setActive(true);
    setErr(null);
    setOpen(true);
  }
  function openEdit(w: Webhook) {
    setEditing(w);
    setUrl(w.url);
    setEvents(w.events);
    setSecret(w.secret);
    setActive(w.active);
    setErr(null);
    setOpen(true);
  }
  async function save() {
    if (!pid) return;
    setBusy(true);
    setErr(null);
    try {
      if (editing) {
        await api.updateWebhook(pid, editing.id, { url, events, secret, active });
      } else {
        await api.createWebhook(pid, { url, events, secret });
      }
      setHooks(await api.webhooks(pid));
      setOpen(false);
    } catch (e) {
      setErr(String((e as { message?: string })?.message ?? e));
    } finally {
      setBusy(false);
    }
  }
  async function toggleActive(w: Webhook) {
    if (!pid) return;
    await api.updateWebhook(pid, w.id, { active: !w.active });
    setHooks(await api.webhooks(pid));
  }
  async function ping(w: Webhook) {
    if (!pid) return;
    setPinging(w.id);
    try {
      await api.pingWebhook(pid, w.id);
      setHooks(await api.webhooks(pid));
    } finally {
      setPinging(null);
    }
  }
  async function remove(w: Webhook) {
    if (!pid) return;
    if (!confirm(`${lang === "zh" ? "删除 webhook" : "Delete webhook"} ${w.url}?`)) return;
    await api.deleteWebhook(pid, w.id);
    setHooks(await api.webhooks(pid));
  }
  function toggleEvent(ev: string) {
    setEvents((prev) => (prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev]));
  }

  return (
    <div className="space-y-6">
      <PageHead
        title={t("studio.nav.webhooks")}
        subtitle={lang === "zh" ? "订阅作业与发布事件，推送到外部系统。" : "Subscribe to job and deploy events to external systems."}
        actions={pid ? <UiButton variant="default" onClick={openCreate}>{t("studio.webhooks.new")}</UiButton> : null}
      />

      {pid && <ProjectSwitcher projectId={pid} onChange={setPid} projects={projects} />}

      <Panel desc={pid ? `${hooks.length} ${lang === "zh" ? "个 webhook" : "webhooks"}` : ""}>
        {!pid ? (
          <EmptyState title={lang === "zh" ? "请先在 Projects 创建项目。" : "Create a project under Projects first."} />
        ) : loading ? (
          <div className="text-xs text-muted-foreground">{lang === "zh" ? "加载中…" : "Loading…"}</div>
        ) : hooks.length === 0 ? (
          <EmptyState title={lang === "zh" ? "还没有 webhook，新建一个。" : "No webhooks yet; create one."} action={<UiButton variant="default" onClick={openCreate}>{t("studio.webhooks.new")}</UiButton>} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("studio.webhooks.url")}</TableHead>
                <TableHead>{t("studio.webhooks.events")}</TableHead>
                <TableHead>{t("studio.webhooks.active")}</TableHead>
                <TableHead>{t("studio.webhooks.last_status")}</TableHead>
                <TableHead className="text-right"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {hooks.map((w) => (
                <TableRow key={w.id}>
                  <TableCell className="max-w-[280px] truncate font-mono text-xs">{w.url}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {w.events.map((e) => (
                        <span key={e} className="rounded bg-[#1c1c1c] px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{e}</span>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <label className="flex items-center gap-2 text-xs">
                      <input type="checkbox" checked={w.active} onChange={() => toggleActive(w)} className="accent-[#3b82f6]" />
                      {w.active ? (lang === "zh" ? "启用" : "on") : (lang === "zh" ? "停用" : "off")}
                    </label>
                  </TableCell>
                  <TableCell>
                    {w.last_status == null ? (
                      <span className="text-xs text-muted-foreground">—</span>
                    ) : (
                      <StatusBadge status={w.last_status >= 200 && w.last_status < 300 ? "succeeded" : "failed"} label={String(w.last_status)} />
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <UiButton size="xs" variant="outline" onClick={() => ping(w)} disabled={pinging === w.id}>{pinging === w.id ? "…" : t("studio.webhooks.ping")}</UiButton>
                      <UiButton size="xs" variant="outline" onClick={() => openEdit(w)}>{lang === "zh" ? "编辑" : "edit"}</UiButton>
                      <UiButton size="xs" variant="destructive" onClick={() => remove(w)}>{lang === "zh" ? "删除" : "delete"}</UiButton>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? (lang === "zh" ? "编辑 webhook" : "Edit webhook") : t("studio.webhooks.new")}
        footer={
          <>
            <UiButton variant="outline" onClick={() => setOpen(false)}>{lang === "zh" ? "取消" : "cancel"}</UiButton>
            <UiButton variant="default" onClick={save} disabled={busy}>{busy ? "…" : lang === "zh" ? "保存" : "save"}</UiButton>
          </>
        }
      >
        <div className="space-y-4">
          {err && <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{err}</div>}
          <Field label={t("studio.webhooks.url")} full>
            <input value={url} onChange={(e) => setUrl(e.target.value)} className="w-full rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
          </Field>
          <Field label={t("studio.webhooks.events")} full>
            <div className="flex flex-wrap gap-1">
              {EVENTS.map((ev) => (
                <button
                  key={ev}
                  type="button"
                  onClick={() => toggleEvent(ev)}
                  className={`rounded border px-2 py-1 font-mono text-[11px] transition-colors ${events.includes(ev) ? "border-primary bg-[#1e3a8a]/40 text-foreground" : "border-border bg-[#111111] text-muted-foreground"}`}
                >
                  {ev}
                </button>
              ))}
            </div>
          </Field>
          <FormGrid>
            <Field label={t("studio.webhooks.secret")}>
              <input value={secret} onChange={(e) => setSecret(e.target.value)} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
            </Field>
            <Field label={t("studio.webhooks.active")}>
              <label className="flex items-center gap-2 pt-1.5 text-sm">
                <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-[#3b82f6]" />
                {active ? (lang === "zh" ? "启用" : "on") : (lang === "zh" ? "停用" : "off")}
              </label>
            </Field>
          </FormGrid>
        </div>
      </Drawer>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Button as UiButton } from "@/components/ui/button";
import { useLang } from "@/lib/i18n";
import { api, type Quota } from "@/lib/console";
import { useProjects, ProjectSwitcher } from "@/components/studio/ProjectSwitcher";
import { PageHead, Panel, Drawer, FormGrid, Field, Kpi, EmptyState } from "@/components/studio/primitives";

function pct(used: number, limit: number) {
  if (!limit) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

export default function StudioQuotaPage() {
  const { t, lang } = useLang();
  const { projects } = useProjects();
  const [pid, setPid] = useState<string | null>(null);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ training_hours_limit: 0, gpu_limit: 0, api_calls_limit: 0, storage_gb_limit: 0 });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!pid && projects.length) setPid(projects[0].id);
  }, [projects, pid]);

  useEffect(() => {
    if (!pid) return;
    let alive = true;
    setLoading(true);
    api.quota(pid)
      .then((q) => alive && setQuota(q))
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [pid]);

  function openEdit() {
    if (!quota) return;
    setForm({
      training_hours_limit: quota.training_hours_limit,
      gpu_limit: quota.gpu_limit,
      api_calls_limit: quota.api_calls_limit,
      storage_gb_limit: quota.storage_gb_limit,
    });
    setOpen(true);
  }
  async function save() {
    if (!pid) return;
    setBusy(true);
    try {
      await api.setQuota(pid, form);
      setQuota(await api.quota(pid));
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  const dims = quota
    ? [
        { key: "training", label: t("studio.quota.training_hours"), used: quota.training_hours_used, limit: quota.training_hours_limit, unit: "h" },
        { key: "gpu", label: t("studio.quota.gpu"), used: 0, limit: quota.gpu_limit, unit: "" },
        { key: "api", label: t("studio.quota.api_calls"), used: quota.api_calls_used, limit: quota.api_calls_limit, unit: "" },
        { key: "storage", label: t("studio.quota.storage"), used: quota.storage_gb_used, limit: quota.storage_gb_limit, unit: "GB" },
      ]
    : [];

  return (
    <div className="space-y-6">
      <PageHead
        title={t("studio.nav.quota")}
        subtitle={lang === "zh" ? "项目资源限额与使用量（训练时长 / GPU / API 调用 / 存储）。" : "Per-project resource limits and usage."}
        actions={quota ? <UiButton variant="default" onClick={openEdit}>{t("studio.quota.set")}</UiButton> : null}
      />

      {pid && <ProjectSwitcher projectId={pid} onChange={setPid} projects={projects} />}

      {!pid ? (
        <EmptyState title={lang === "zh" ? "请先在 Projects 创建项目。" : "Create a project under Projects first."} />
      ) : loading || !quota ? (
        <Panel><div className="text-xs text-muted-foreground">{lang === "zh" ? "加载中…" : "Loading…"}</div></Panel>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {dims.map((d) => (
            <Kpi key={d.key} label={d.label} value={`${d.used}${d.unit} / ${d.limit}${d.unit}`}>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-[#1c1c1c]">
                <div className={`h-full ${pct(d.used, d.limit) > 85 ? "bg-[#ef4444]" : "bg-[#3b82f6]"}`} style={{ width: `${pct(d.used, d.limit)}%` }} />
              </div>
            </Kpi>
          ))}
        </div>
      )}

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={t("studio.quota.set")}
        footer={
          <>
            <UiButton variant="outline" onClick={() => setOpen(false)}>{lang === "zh" ? "取消" : "cancel"}</UiButton>
            <UiButton variant="default" onClick={save} disabled={busy}>{busy ? "…" : lang === "zh" ? "保存" : "save"}</UiButton>
          </>
        }
      >
        <FormGrid>
          <Field label={`${t("studio.quota.training_hours")} (${t("studio.quota.limit")})`}>
            <input type="number" value={form.training_hours_limit} onChange={(e) => setForm({ ...form, training_hours_limit: Number(e.target.value) })} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
          </Field>
          <Field label={`${t("studio.quota.gpu")} (${t("studio.quota.limit")})`}>
            <input type="number" value={form.gpu_limit} onChange={(e) => setForm({ ...form, gpu_limit: Number(e.target.value) })} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
          </Field>
          <Field label={`${t("studio.quota.api_calls")} (${t("studio.quota.limit")})`}>
            <input type="number" value={form.api_calls_limit} onChange={(e) => setForm({ ...form, api_calls_limit: Number(e.target.value) })} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
          </Field>
          <Field label={`${t("studio.quota.storage")} GB (${t("studio.quota.limit")})`}>
            <input type="number" value={form.storage_gb_limit} onChange={(e) => setForm({ ...form, storage_gb_limit: Number(e.target.value) })} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
          </Field>
        </FormGrid>
      </Drawer>
    </div>
  );
}

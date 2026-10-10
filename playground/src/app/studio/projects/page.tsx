"use client";

import { useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button as UiButton } from "@/components/ui/button";
import { useLang } from "@/lib/i18n";
import { api, type Project } from "@/lib/console";
import { useProjects } from "@/components/studio/ProjectSwitcher";
import { PageHead, Panel, Drawer, FormGrid, Field, EmptyState } from "@/components/studio/primitives";

export default function StudioProjectsPage() {
  const { t, lang } = useLang();
  const { projects, loading, reload } = useProjects();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function openCreate() {
    setEditing(null);
    setSlug("");
    setName("");
    setDescription("");
    setErr(null);
    setOpen(true);
  }
  function openEdit(p: Project) {
    setEditing(p);
    setSlug(p.slug);
    setName(p.name);
    setDescription(p.description);
    setErr(null);
    setOpen(true);
  }
  async function save() {
    setBusy(true);
    setErr(null);
    try {
      if (editing) {
        await api.updateProject(editing.id, { slug, name, description });
      } else {
        await api.createProject({ slug, name, description });
      }
      setOpen(false);
      reload();
    } catch (e) {
      setErr(String((e as { message?: string })?.message ?? e));
    } finally {
      setBusy(false);
    }
  }
  async function remove(p: Project) {
    if (!confirm(`${lang === "zh" ? "删除项目" : "Delete project"} ${p.name}?`)) return;
    await api.deleteProject(p.id);
    reload();
  }

  return (
    <div className="space-y-6">
      <PageHead
        title={t("studio.nav.projects")}
        subtitle={lang === "zh" ? "项目（组织工作区）的创建与成员、配额、计费的根。" : "Projects are the root of members, quota and billing."}
        actions={<UiButton variant="default" onClick={openCreate}>{lang === "zh" ? "新建项目" : "New project"}</UiButton>}
      />

      <Panel desc={lang === "zh" ? `${projects.length} 个项目` : `${projects.length} projects`}>
        {loading ? (
          <div className="text-xs text-muted-foreground">{lang === "zh" ? "加载中…" : "Loading…"}</div>
        ) : projects.length === 0 ? (
          <EmptyState title={lang === "zh" ? "还没有项目，先创建一个。" : "No projects yet; create one."} action={<UiButton variant="default" onClick={openCreate}>{lang === "zh" ? "新建项目" : "New project"}</UiButton>} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>name</TableHead>
                <TableHead>slug</TableHead>
                <TableHead>{t("studio.projects.description")}</TableHead>
                <TableHead className="text-right">created</TableHead>
                <TableHead className="text-right"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="text-sm">{p.name}</TableCell>
                  <TableCell className="font-mono text-xs">{p.slug}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.description || "—"}</TableCell>
                  <TableCell className="text-right font-mono text-xs text-muted-foreground">{p.created_at.slice(0, 10)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <UiButton size="xs" variant="outline" onClick={() => openEdit(p)}>{lang === "zh" ? "编辑" : "edit"}</UiButton>
                      <UiButton size="xs" variant="destructive" onClick={() => remove(p)}>{lang === "zh" ? "删除" : "delete"}</UiButton>
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
        title={editing ? (lang === "zh" ? "编辑项目" : "Edit project") : (lang === "zh" ? "新建项目" : "New project")}
        footer={
          <>
            <UiButton variant="outline" onClick={() => setOpen(false)}>{lang === "zh" ? "取消" : "cancel"}</UiButton>
            <UiButton variant="default" onClick={save} disabled={busy}>{busy ? "…" : lang === "zh" ? "保存" : "save"}</UiButton>
          </>
        }
      >
        <div className="space-y-4">
          {err && <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{err}</div>}
          <FormGrid>
            <Field label="slug" hint={lang === "zh" ? "URL 友好的唯一标识" : "unique url-friendly id"}>
              <input value={slug} onChange={(e) => setSlug(e.target.value)} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
            </Field>
            <Field label="name">
              <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
            </Field>
          </FormGrid>
          <Field label={t("studio.projects.description")} full>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="w-full rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
          </Field>
        </div>
      </Drawer>
    </div>
  );
}

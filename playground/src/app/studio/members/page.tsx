"use client";

import { useEffect, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button as UiButton } from "@/components/ui/button";
import { useLang } from "@/lib/i18n";
import { api, type Member } from "@/lib/console";
import { useProjects, ProjectSwitcher } from "@/components/studio/ProjectSwitcher";
import { PageHead, Panel, Drawer, FormGrid, Field, EmptyState, StatusBadge } from "@/components/studio/primitives";

const ROLES: Member["role"][] = ["owner", "admin", "member", "viewer"];

export default function StudioMembersPage() {
  const { t, lang } = useLang();
  const { projects } = useProjects();
  const [pid, setPid] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Member["role"]>("member");
  const [status, setStatus] = useState<Member["status"]>("invited");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!pid && projects.length) setPid(projects[0].id);
  }, [projects, pid]);

  useEffect(() => {
    if (!pid) return;
    let alive = true;
    setLoading(true);
    api.members(pid)
      .then((m) => alive && setMembers(m))
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [pid]);

  function openInvite() {
    setEmail("");
    setName("");
    setRole("member");
    setStatus("invited");
    setErr(null);
    setOpen(true);
  }
  async function invite() {
    if (!pid) return;
    setBusy(true);
    setErr(null);
    try {
      await api.inviteMember(pid, { email, name, role, status });
      setOpen(false);
      const m = await api.members(pid);
      setMembers(m);
    } catch (e) {
      setErr(String((e as { message?: string })?.message ?? e));
    } finally {
      setBusy(false);
    }
  }
  async function changeRole(m: Member, r: Member["role"]) {
    if (!pid) return;
    await api.updateMember(pid, m.id, { role: r });
    setMembers(await api.members(pid));
  }
  async function remove(m: Member) {
    if (!pid) return;
    if (!confirm(`${lang === "zh" ? "移除成员" : "Remove member"} ${m.email}?`)) return;
    await api.removeMember(pid, m.id);
    setMembers(await api.members(pid));
  }

  return (
    <div className="space-y-6">
      <PageHead
        title={t("studio.nav.members")}
        subtitle={lang === "zh" ? "项目成员与角色（owner/admin/member/viewer）。" : "Project members and roles (owner/admin/member/viewer)."}
        actions={pid ? <UiButton variant="default" onClick={openInvite}>{t("studio.members.invite")}</UiButton> : null}
      />

      {pid && <ProjectSwitcher projectId={pid} onChange={setPid} projects={projects} />}

      <Panel desc={pid ? `${members.length} ${lang === "zh" ? "名成员" : "members"}` : ""}>
        {!pid ? (
          <EmptyState title={lang === "zh" ? "请先在 Projects 创建项目。" : "Create a project under Projects first."} />
        ) : loading ? (
          <div className="text-xs text-muted-foreground">{lang === "zh" ? "加载中…" : "Loading…"}</div>
        ) : members.length === 0 ? (
          <EmptyState title={lang === "zh" ? "还没有成员，邀请一个。" : "No members yet; invite one."} action={<UiButton variant="default" onClick={openInvite}>{t("studio.members.invite")}</UiButton>} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("studio.members.email")}</TableHead>
                <TableHead>{t("studio.members.name")}</TableHead>
                <TableHead>{t("studio.members.role")}</TableHead>
                <TableHead>{t("studio.members.status")}</TableHead>
                <TableHead className="text-right"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="text-sm">{m.email}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{m.name || "—"}</TableCell>
                  <TableCell>
                    <select
                      value={m.role}
                      onChange={(e) => changeRole(m, e.target.value as Member["role"])}
                      className="rounded border border-border bg-[#111111] px-2 py-1 text-xs outline-none focus:border-primary"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={m.status === "active" ? "succeeded" : "pending"} label={m.status} />
                  </TableCell>
                  <TableCell className="text-right">
                    <UiButton size="xs" variant="destructive" onClick={() => remove(m)}>{lang === "zh" ? "移除" : "remove"}</UiButton>
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
        title={t("studio.members.invite")}
        footer={
          <>
            <UiButton variant="outline" onClick={() => setOpen(false)}>{lang === "zh" ? "取消" : "cancel"}</UiButton>
            <UiButton variant="default" onClick={invite} disabled={busy}>{busy ? "…" : lang === "zh" ? "发送邀请" : "invite"}</UiButton>
          </>
        }
      >
        <div className="space-y-4">
          {err && <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{err}</div>}
          <FormGrid>
            <Field label={t("studio.members.email")} hint="name@example.com">
              <input value={email} onChange={(e) => setEmail(e.target.value)} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
            </Field>
            <Field label={t("studio.members.name")}>
              <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
            </Field>
            <Field label={t("studio.members.role")}>
              <select value={role} onChange={(e) => setRole(e.target.value as Member["role"])} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary">
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
            <Field label={t("studio.members.status")}>
              <select value={status} onChange={(e) => setStatus(e.target.value as Member["status"])} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary">
                <option value="invited">{lang === "zh" ? "待接受" : "invited"}</option>
                <option value="active">{lang === "zh" ? "已加入" : "active"}</option>
              </select>
            </Field>
          </FormGrid>
        </div>
      </Drawer>
    </div>
  );
}

"use client";

import { useCallback, useState } from "react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { api, type Scenario, type ScenarioDomain } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { TrackBadge } from "@/components/console/TrackBadge";
import { ScenarioConfigDialog, type ConfigTarget } from "@/app/console/scenarios/ScenarioConfigDialog";
import { Drawer, EmptyState, Field, PageHead, Panel } from "./primitives";

type DrawerState =
  | { kind: "domain"; mode: "create" }
  | { kind: "domain"; mode: "edit"; domain: ScenarioDomain }
  | { kind: "scenario"; mode: "create"; domain: ScenarioDomain }
  | { kind: "scenario"; mode: "edit"; domain: ScenarioDomain; scenario: Scenario }
  | null;

// 域 / 场景表单：模块级组件。此前定义在 DomainsManager 内部会触发 react-hooks/static-components——
// 父组件每次重渲染（切域 tab、usePoll 刷新）都会重建它们、丢失正在编辑的表单状态。
// t 各自走 useLang，busy 内聚为局部 state，只有 close/refresh 这类「操作父状态」的能力才由父传入。
function DomainForm({ d, close, refresh }: { d?: ScenarioDomain; close: () => void; refresh: () => void }) {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    slug: d?.slug ?? "",
    label_zh: d?.label_zh ?? "",
    label_en: d?.label_en ?? "",
    sort: String(d?.sort ?? 0),
  });
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async () => {
    setBusy(true);
    try {
      if (d) await api.updateDomain(d.id, { label_zh: form.label_zh, label_en: form.label_en, sort: Number(form.sort) });
      else await api.createDomain({ slug: form.slug, label_zh: form.label_zh, label_en: form.label_en, sort: Number(form.sort) });
      toast.success(t("studio.domains.saved"));
      close();
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-3">
      {!d && <Field label={t("studio.domains.slug")}><Input value={form.slug} onChange={(e) => set("slug", e.target.value)} className="bg-[#0a0a0a]" /></Field>}
      <Field label={t("studio.domains.labelZh")}><Input value={form.label_zh} onChange={(e) => set("label_zh", e.target.value)} className="bg-[#0a0a0a]" /></Field>
      <Field label={t("studio.domains.labelEn")}><Input value={form.label_en} onChange={(e) => set("label_en", e.target.value)} className="bg-[#0a0a0a]" /></Field>
      <Field label="sort"><Input value={form.sort} onChange={(e) => set("sort", e.target.value)} className="bg-[#0a0a0a]" /></Field>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={close}>{t("studio.domains.cancel")}</Button>
        <Button size="sm" disabled={busy} onClick={() => void submit()}>{t("studio.domains.save")}</Button>
      </div>
    </div>
  );
}

function ScenarioForm({ domain, s, close, refresh }: { domain: ScenarioDomain; s?: Scenario; close: () => void; refresh: () => void }) {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    slug: s?.slug ?? "",
    label_zh: s?.label_zh ?? "",
    label_en: s?.label_en ?? "",
    spec_path: s?.spec_path ?? "",
    category: s?.category ?? "",
    sort: String(s?.sort ?? 0),
  });
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async () => {
    setBusy(true);
    try {
      if (s) await api.updateScenario(s.id, { label_zh: form.label_zh, label_en: form.label_en, spec_path: form.spec_path, category: form.category, sort: Number(form.sort) });
      else await api.createScenario({ domain_id: domain.id, slug: form.slug, label_zh: form.label_zh, label_en: form.label_en, spec_path: form.spec_path, category: form.category, sort: Number(form.sort) });
      toast.success(t("studio.domains.saved"));
      close();
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-3">
      {!s && <Field label={t("studio.domains.slug")}><Input value={form.slug} onChange={(e) => set("slug", e.target.value)} className="bg-[#0a0a0a]" /></Field>}
      <Field label={t("studio.domains.labelZh")}><Input value={form.label_zh} onChange={(e) => set("label_zh", e.target.value)} className="bg-[#0a0a0a]" /></Field>
      <Field label={t("studio.domains.labelEn")}><Input value={form.label_en} onChange={(e) => set("label_en", e.target.value)} className="bg-[#0a0a0a]" /></Field>
      <Field label={t("studio.domains.specPath")}><Input value={form.spec_path} onChange={(e) => set("spec_path", e.target.value)} className="bg-[#0a0a0a]" /></Field>
      <Field label={t("studio.domains.category")}><Input value={form.category} onChange={(e) => set("category", e.target.value)} className="bg-[#0a0a0a]" /></Field>
      <Field label="sort"><Input value={form.sort} onChange={(e) => set("sort", e.target.value)} className="bg-[#0a0a0a]" /></Field>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={close}>{t("studio.domains.cancel")}</Button>
        <Button size="sm" disabled={busy} onClick={() => void submit()}>{t("studio.domains.save")}</Button>
      </div>
    </div>
  );
}

export function DomainsManager() {
  const { t, lang } = useLang();
  const load = useCallback(() => api.scenarioDomains(lang), [lang]);
  const { value: domains, refresh } = usePoll<ScenarioDomain[]>(load, []);

  const [drawer, setDrawer] = useState<DrawerState>(null);
  // 场景行「配置」按钮打开的三 tab 弹窗（结构化 / YAML / 原始文本）；null = 关闭。
  const [configTarget, setConfigTarget] = useState<ConfigTarget | null>(null);
  // 顶部域 tab 的选中项；null 或失效（如域被删）时回退到第一个域，故无需 effect 同步。
  const [activeDomainId, setActiveDomainId] = useState<string | null>(null);
  const activeDomain = domains.find((d) => d.id === activeDomainId) ?? domains[0] ?? null;

  const removeDomain = async (d: ScenarioDomain) => {
    if (!confirm(t("studio.domains.deleteConfirm"))) return;
    await api.deleteDomain(d.id);
    void refresh();
  };
  const removeScenario = async (s: Scenario) => {
    await api.deleteScenario(s.id);
    void refresh();
  };

  return (
    <div className="space-y-4">
      {/* 标题行：域名 + 副标题在左，「新建域」按钮挂 PageHead 的 actions 槽在右（同 projects 页）。
          此前按钮独占一行、与 page.tsx 里的 PageHead 分处两层；一并收进本组件后顶部更紧凑，
          且按钮能直接触达本组件的 drawer 状态，无需跨层通信。 */}
      <PageHead
        title={t("studio.domains.title")}
        subtitle={t("studio.domains.subtitle")}
        actions={
          <Button size="sm" onClick={() => setDrawer({ kind: "domain", mode: "create" })}>
            + {t("studio.domains.newDomain")}
          </Button>
        }
      />

      {domains.length === 0 ? (
        <EmptyState title={t("studio.domains.noScenarios")} />
      ) : (
        <>
          {/* 域 tab 条：标题为域名，右侧小字为场景数；横向可滚动，选中态用 primary 下划线。 */}
          <div className="flex gap-1 overflow-x-auto border-b border-border">
            {domains.map((d) => {
              const active = d.id === activeDomain?.id;
              return (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => setActiveDomainId(d.id)}
                  className={cn(
                    "shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-[13px] transition-colors",
                    active
                      ? "border-primary font-medium text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {lang === "zh" ? d.label_zh : d.label_en}
                  <span className={cn("ml-1.5 text-[11px]", active ? "text-primary" : "text-muted-foreground/70")}>
                    {d.scenarios.length}
                  </span>
                </button>
              );
            })}
          </div>

          {/* 选中域：域操作（编辑/新建场景/删除）+ 场景列表；域名已在 tab 标题显示，此处 desc 用 slug。 */}
          {activeDomain && (
            <Panel
              desc={activeDomain.slug}
              actions={
                <div className="flex gap-2">
                  <Button size="xs" variant="ghost" onClick={() => setDrawer({ kind: "domain", mode: "edit", domain: activeDomain })}>{t("studio.domains.edit")}</Button>
                  <Button size="xs" variant="ghost" onClick={() => setDrawer({ kind: "scenario", mode: "create", domain: activeDomain })}>+ {t("studio.domains.newScenario")}</Button>
                  <Button size="xs" variant="ghost" className="text-[#ef4444]" onClick={() => void removeDomain(activeDomain)}>{t("studio.domains.delete")}</Button>
                </div>
              }
            >
              {activeDomain.scenarios.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t("studio.domains.noScenarios")}</p>
              ) : (
                <table className="w-full border-collapse text-[13px]">
                  <tbody>
                    {activeDomain.scenarios.map((s) => (
                      <tr key={s.id} className="border-b border-border/60 last:border-0">
                        <td className="py-2 pr-3 align-top">
                          <div className="font-medium">{lang === "zh" ? s.label_zh : s.label_en}</div>
                          <div className="text-xs text-muted-foreground">{s.slug}{s.exists ? "" : " · missing"}</div>
                        </td>
                        <td className="py-2 pr-3 align-top">
                          <TrackBadge track={s.track} label={t("console.scenarios.track")} />
                        </td>
                        <td className="py-2 pr-3 align-top font-mono text-xs text-muted-foreground">{s.spec_path}</td>
                        <td className="py-2 pr-3 align-top text-xs text-muted-foreground">{s.category}</td>
                        <td className="py-2 text-right align-top">
                          <div className="flex justify-end gap-2">
                            <Button size="xs" variant="ghost" onClick={() => setConfigTarget({ scenario: s, tab: "spec" })}>{t("studio.domains.spec")}</Button>
                            <Button size="xs" variant="ghost" onClick={() => setDrawer({ kind: "scenario", mode: "edit", domain: activeDomain, scenario: s })}>{t("studio.domains.edit")}</Button>
                            <Button size="xs" variant="ghost" className="text-[#ef4444]" onClick={() => void removeScenario(s)}>{t("studio.domains.delete")}</Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          )}
        </>
      )}

      <Drawer open={!!drawer} onClose={() => setDrawer(null)} title={
        drawer?.kind === "domain" ? (drawer.mode === "create" ? t("studio.domains.newDomain") : t("studio.domains.edit")) :
        drawer?.kind === "scenario" ? (drawer.mode === "create" ? t("studio.domains.newScenario") : t("studio.domains.edit")) : ""
      }>
        {drawer?.kind === "domain" && <DomainForm d={drawer.mode === "edit" ? drawer.domain : undefined} close={() => setDrawer(null)} refresh={refresh} />}
        {drawer?.kind === "scenario" && <ScenarioForm domain={drawer.domain} s={drawer.mode === "edit" ? drawer.scenario : undefined} close={() => setDrawer(null)} refresh={refresh} />}
      </Drawer>

      {/* 场景配置弹窗（与 console「场景管理」页共用同一组件）：结构化 / 蒸馏 YAML / 原始文本 三 tab。
          studio 为深色主题，传 contentClassName="dark" 让 portal 内弹窗继承暗色变量（见 JobFiles.tsx）。 */}
      <ScenarioConfigDialog
        target={configTarget}
        onClose={() => setConfigTarget(null)}
        onSaved={() => void refresh()}
        contentClassName="dark"
      />
    </div>
  );
}

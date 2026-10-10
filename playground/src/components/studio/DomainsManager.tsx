"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { api, type Scenario, type ScenarioDomain } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { Drawer, EmptyState, Field, Panel } from "./primitives";

type DrawerState =
  | { kind: "domain"; mode: "create" }
  | { kind: "domain"; mode: "edit"; domain: ScenarioDomain }
  | { kind: "scenario"; mode: "create"; domain: ScenarioDomain }
  | { kind: "scenario"; mode: "edit"; domain: ScenarioDomain; scenario: Scenario }
  | { kind: "spec"; scenario: Scenario }
  | null;

export function DomainsManager() {
  const { t, lang } = useLang();
  const load = useCallback(() => api.scenarioDomains(lang), [lang]);
  const { value: domains, refresh } = usePoll<ScenarioDomain[]>(load, []);

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [busy, setBusy] = useState(false);
  const [spec, setSpec] = useState<string>("");
  const [specLoading, setSpecLoading] = useState(false);

  useEffect(() => {
    if (drawer?.kind === "spec") {
      setSpecLoading(true);
      api
        .scenarioSpec(drawer.scenario.slug)
        .then((s) => setSpec(s.content))
        .catch(() => setSpec(""))
        .finally(() => setSpecLoading(false));
    }
  }, [drawer]);

  const DomainForm = ({ d }: { d?: ScenarioDomain }) => {
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
        setDrawer(null);
        void refresh();
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
          <Button size="sm" variant="ghost" onClick={() => setDrawer(null)}>{t("studio.domains.cancel")}</Button>
          <Button size="sm" disabled={busy} onClick={() => void submit()}>{t("studio.domains.save")}</Button>
        </div>
      </div>
    );
  };

  const ScenarioForm = ({ domain, s }: { domain: ScenarioDomain; s?: Scenario }) => {
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
        setDrawer(null);
        void refresh();
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
          <Button size="sm" variant="ghost" onClick={() => setDrawer(null)}>{t("studio.domains.cancel")}</Button>
          <Button size="sm" disabled={busy} onClick={() => void submit()}>{t("studio.domains.save")}</Button>
        </div>
      </div>
    );
  };

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
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setDrawer({ kind: "domain", mode: "create" })}>
          + {t("studio.domains.newDomain")}
        </Button>
      </div>

      {domains.length === 0 ? (
        <EmptyState title={t("studio.domains.noScenarios")} />
      ) : (
        domains.map((domain) => (
          <Panel
            key={domain.id}
            title={lang === "zh" ? domain.label_zh : domain.label_en}
            desc={domain.slug}
            actions={
              <div className="flex gap-2">
                <Button size="xs" variant="ghost" onClick={() => setDrawer({ kind: "domain", mode: "edit", domain })}>{t("studio.domains.edit")}</Button>
                <Button size="xs" variant="ghost" onClick={() => setDrawer({ kind: "scenario", mode: "create", domain })}>+ {t("studio.domains.newScenario")}</Button>
                <Button size="xs" variant="ghost" className="text-[#ef4444]" onClick={() => void removeDomain(domain)}>{t("studio.domains.delete")}</Button>
              </div>
            }
          >
            {domain.scenarios.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("studio.domains.noScenarios")}</p>
            ) : (
              <table className="w-full border-collapse text-[13px]">
                <tbody>
                  {domain.scenarios.map((s) => (
                    <tr key={s.id} className="border-b border-border/60 last:border-0">
                      <td className="py-2 pr-3 align-top">
                        <div className="font-medium">{lang === "zh" ? s.label_zh : s.label_en}</div>
                        <div className="text-xs text-muted-foreground">{s.slug}{s.exists ? "" : " · missing"}</div>
                      </td>
                      <td className="py-2 pr-3 align-top font-mono text-xs text-muted-foreground">{s.spec_path}</td>
                      <td className="py-2 pr-3 align-top text-xs text-muted-foreground">{s.category}</td>
                      <td className="py-2 text-right align-top">
                        <div className="flex justify-end gap-2">
                          <Button size="xs" variant="ghost" onClick={() => setDrawer({ kind: "spec", scenario: s })}>{t("studio.domains.spec")}</Button>
                          <Button size="xs" variant="ghost" onClick={() => setDrawer({ kind: "scenario", mode: "edit", domain, scenario: s })}>{t("studio.domains.edit")}</Button>
                          <Button size="xs" variant="ghost" className="text-[#ef4444]" onClick={() => void removeScenario(s)}>{t("studio.domains.delete")}</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        ))
      )}

      <Drawer open={!!drawer && drawer.kind !== "spec"} onClose={() => setDrawer(null)} title={
        drawer?.kind === "domain" ? (drawer.mode === "create" ? t("studio.domains.newDomain") : t("studio.domains.edit")) :
        drawer?.kind === "scenario" ? (drawer.mode === "create" ? t("studio.domains.newScenario") : t("studio.domains.edit")) : ""
      }>
        {drawer?.kind === "domain" && <DomainForm d={drawer.mode === "edit" ? drawer.domain : undefined} />}
        {drawer?.kind === "scenario" && <ScenarioForm domain={drawer.domain} s={drawer.mode === "edit" ? drawer.scenario : undefined} />}
      </Drawer>

      <Drawer
        open={drawer?.kind === "spec"}
        onClose={() => setDrawer(null)}
        title={`${t("studio.domains.spec")} · ${drawer?.kind === "spec" ? drawer.scenario.slug : ""}`}
        footer={
          <Button size="sm" disabled={specLoading} onClick={async () => {
            if (drawer?.kind !== "spec") return;
            await api.saveScenarioSpec(drawer.scenario.slug, spec);
            toast.success(t("studio.domains.saved"));
            setDrawer(null);
          }}>{t("studio.domains.save")}</Button>
        }
      >
        {specLoading ? (
          <p className="text-sm text-muted-foreground">{t("console.jobs.loading")}</p>
        ) : (
          <Textarea value={spec} onChange={(e) => setSpec(e.target.value)} className="min-h-[360px] bg-[#0a0a0a] font-mono text-xs" />
        )}
      </Drawer>
    </div>
  );
}

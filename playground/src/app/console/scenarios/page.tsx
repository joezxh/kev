"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { LangToggle } from "@/components/lang-toggle";
import { api, type Scenario, type ScenarioTree } from "@/lib/console";
import { useLang } from "@/lib/i18n";

type Selection =
  | { type: "domain"; id: string }
  | { type: "scenario"; id: string; slug: string }
  | null;

type DomainDraft = { id: string; slug: string; label_zh: string; label_en: string; sort: number };
type ScenarioDraft = {
  id: string; domain_id: string; slug: string; label_zh: string; label_en: string;
  spec_path: string; category: string; sort: number;
};

const blankDomain: DomainDraft = { id: "__new__", slug: "", label_zh: "", label_en: "", sort: 0 };
const blankScenario = (domainId: string): ScenarioDraft => ({
  id: "__new__", domain_id: domainId, slug: "", label_zh: "", label_en: "",
  spec_path: "", category: "medical", sort: 0,
});

export default function ScenariosPage() {
  const { t, lang } = useLang();
  const [tree, setTree] = useState<ScenarioTree[]>([]);
  const [selected, setSelected] = useState<Selection>(null);
  const [domainDraft, setDomainDraft] = useState<DomainDraft>(blankDomain);
  const [scenarioDraft, setScenarioDraft] = useState<ScenarioDraft>(blankScenario(""));
  const [specContent, setSpecContent] = useState("");
  const [specDirty, setSpecDirty] = useState(false);
  const [specError, setSpecError] = useState<string | null>(null);
  const [specHistory, setSpecHistory] = useState<{ ts: string }[]>([]);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.scenarioDomains(lang).then(setTree).catch(() => toast.error(t("console.scenarios.specLoadFailed")));
  }, [lang, t]);
  useEffect(load, [load]);

  const domainOptions = useMemo(() => tree.map((d) => ({ slug: d.slug, label: d.label })), [tree]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return tree;
    return tree
      .map((d) => ({
        ...d,
        scenarios: d.scenarios.filter(
          (s) => s.slug.includes(q) || s.label_zh.toLowerCase().includes(q) || s.label_en.toLowerCase().includes(q)),
      }))
      .filter((d) => d.label_zh.toLowerCase().includes(q) || d.label_en.toLowerCase().includes(q) || d.scenarios.length > 0);
  }, [tree, search]);

  const selectDomain = (domain: ScenarioTree) => {
    setSelected({ type: "domain", id: domain.id });
    setDomainDraft({
      id: domain.id, slug: domain.slug, label_zh: domain.label_zh,
      label_en: domain.label_en, sort: domain.sort,
    });
    setSpecContent(""); setSpecDirty(false); setSpecError(null);
  };

  const selectScenario = (domainSlug: string, scenario: Scenario) => {
    setSelected({ type: "scenario", id: scenario.id, slug: scenario.slug });
    const domain = tree.find((d) => d.slug === domainSlug);
    setScenarioDraft({
      id: scenario.id, domain_id: domain?.id ?? "", slug: scenario.slug, label_zh: scenario.label_zh,
      label_en: scenario.label_en, spec_path: scenario.spec_path, category: scenario.category, sort: scenario.sort,
    });
    setBusy(true);
    api.scenarioSpec(scenario.slug)
      .then((res) => { setSpecContent(res.content); setSpecDirty(false); setSpecError(null); })
      .catch(() => { setSpecContent(""); setSpecError(t("console.scenarios.specLoadFailed")); })
      .finally(() => setBusy(false));
    api.specHistory(scenario.slug).then(setSpecHistory).catch(() => setSpecHistory([]));
  };

  const newDomain = () => {
    setSelected({ type: "domain", id: "__new__" });
    setDomainDraft(blankDomain);
    setSpecContent(""); setSpecDirty(false); setSpecError(null);
  };

  const newScenario = () => {
    if (tree.length === 0) { toast.error(t("console.scenarios.empty")); return; }
    setSelected({ type: "scenario", id: "__new__", slug: "" });
    setScenarioDraft(blankScenario(tree[0].id));
    setSpecContent(""); setSpecDirty(false); setSpecError(null);
  };

  const saveDomain = async () => {
    setBusy(true);
    try {
      if (domainDraft.id === "__new__") {
        const created = await api.createDomain({
          slug: domainDraft.slug, label_zh: domainDraft.label_zh, label_en: domainDraft.label_en, sort: domainDraft.sort,
        });
        setSelected({ type: "domain", id: created.id });
      } else {
        await api.updateDomain(domainDraft.id, {
          label_zh: domainDraft.label_zh, label_en: domainDraft.label_en, sort: domainDraft.sort,
        });
      }
      toast.success(t("console.scenarios.save"));
      load();
    } catch (e) {
      toast.error((e as { message: string }).message);
    } finally {
      setBusy(false);
    }
  };

  const saveScenario = async () => {
    setBusy(true);
    try {
      if (scenarioDraft.id === "__new__") {
        const created = await api.createScenario({
          domain_id: scenarioDraft.domain_id, slug: scenarioDraft.slug, label_zh: scenarioDraft.label_zh,
          label_en: scenarioDraft.label_en, spec_path: scenarioDraft.spec_path,
          category: scenarioDraft.category, sort: scenarioDraft.sort,
        });
        setSelected({ type: "scenario", id: created.id, slug: scenarioDraft.slug });
      } else {
        await api.updateScenario(scenarioDraft.id, {
          domain_id: scenarioDraft.domain_id, label_zh: scenarioDraft.label_zh, label_en: scenarioDraft.label_en,
          spec_path: scenarioDraft.spec_path, category: scenarioDraft.category, sort: scenarioDraft.sort,
        });
      }
      toast.success(t("console.scenarios.save"));
      load();
    } catch (e) {
      toast.error((e as { message: string }).message);
    } finally {
      setBusy(false);
    }
  };

  const removeDomain = async () => {
    if (selected?.type !== "domain" || domainDraft.id === "__new__") return;
    if (!confirm(t("console.scenarios.confirmDelete"))) return;
    await api.deleteDomain(domainDraft.id);
    setSelected(null); load();
  };

  const removeScenario = async () => {
    if (selected?.type !== "scenario" || scenarioDraft.id === "__new__") return;
    if (!confirm(t("console.scenarios.confirmDelete"))) return;
    await api.deleteScenario(scenarioDraft.id);
    setSelected(null); load();
  };

  const saveSpec = async () => {
    if (selected?.type !== "scenario") return;
    try {
      JSON.parse(specContent);
      setSpecError(null);
    } catch {
      setSpecError(t("console.scenarios.specInvalid"));
      toast.error(t("console.scenarios.specInvalid"));
      return;
    }
    setBusy(true);
    try {
      await api.saveScenarioSpec(selected.slug, specContent);
      setSpecDirty(false);
      toast.success(t("console.scenarios.specSaved"));
      api.specHistory(selected.slug).then(setSpecHistory).catch(() => setSpecHistory([]));
    } catch (e) {
      toast.error((e as { message: string }).message);
    } finally {
      setBusy(false);
    }
  };

  const loadHistoryVersion = async (ts: string) => {
    if (selected?.type !== "scenario" || !ts) return;
    setBusy(true);
    try {
      const res = await api.specHistoryVersion(selected.slug, ts);
      setSpecContent(res.content);
      setSpecDirty(true);   // 回滚内容需再点「保存配置」才会写回源文件
      setSpecError(null);
    } catch (e) {
      toast.error((e as { message: string }).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">{t("console.scenarios.title")}</h1>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t("console.scenarios.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <LangToggle />
          <Button size="sm" variant="outline" onClick={newDomain}>{t("console.scenarios.newDomain")}</Button>
          <Button size="sm" onClick={newScenario}>{t("console.scenarios.newScenario")}</Button>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        {/* 左：两级树 */}
        <aside className="space-y-3">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("console.scenarios.search")} />
          <div className="space-y-1 rounded-lg border border-border bg-card p-2">
            {filtered.length === 0 && (
              <p className="px-2 py-4 text-xs text-muted-foreground">{t("console.scenarios.empty")}</p>
            )}
            {filtered.map((domain) => (
              <div key={domain.id} className="rounded-md">
                <button
                  type="button"
                  onClick={() => selectDomain(domain)}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted ${
                    selected?.type === "domain" && selected.id === domain.id ? "bg-muted font-medium" : ""}`}
                >
                  <span className="text-xs text-muted-foreground">▾</span>
                  <span className="flex-1">{domain.label}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">{domain.slug}</span>
                </button>
                <div className="ml-4 border-l border-border pl-2">
                  {domain.scenarios.map((scenario) => (
                    <button
                      key={scenario.id}
                      type="button"
                      onClick={() => selectScenario(domain.slug, scenario)}
                      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted ${
                        selected?.type === "scenario" && selected.id === scenario.id ? "bg-muted font-medium" : ""}`}
                    >
                      <span className="flex-1">{scenario.label}</span>
                      <span className={`h-1.5 w-1.5 rounded-full ${scenario.exists ? "bg-emerald-500" : "bg-amber-500"}`}
                            title={scenario.exists ? t("console.scenarios.exists") : t("console.scenarios.missing")} />
                      <span className="font-mono text-[10px] text-muted-foreground">{scenario.slug}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </aside>

        {/* 右：编辑面板 */}
        <section className="space-y-4 rounded-lg border border-border bg-card p-5">
          {!selected && (
            <p className="text-sm text-muted-foreground">{t("console.scenarios.empty")}</p>
          )}

          {selected?.type === "domain" && (
            <>
              <h2 className="text-sm font-medium">{t("console.scenarios.newDomain")}</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("console.scenarios.slug")}>
                  <Input value={domainDraft.slug} onChange={(e) => setDomainDraft({ ...domainDraft, slug: e.target.value })} />
                </Field>
                <Field label={t("console.scenarios.sort")}>
                  <Input type="number" value={domainDraft.sort} onChange={(e) => setDomainDraft({ ...domainDraft, sort: Number(e.target.value) })} />
                </Field>
                <Field label={t("console.scenarios.labelZh")}>
                  <Input value={domainDraft.label_zh} onChange={(e) => setDomainDraft({ ...domainDraft, label_zh: e.target.value })} />
                </Field>
                <Field label={t("console.scenarios.labelEn")}>
                  <Input value={domainDraft.label_en} onChange={(e) => setDomainDraft({ ...domainDraft, label_en: e.target.value })} />
                </Field>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => void saveDomain()} disabled={busy}>{t("console.scenarios.save")}</Button>
                {domainDraft.id !== "__new__" && (
                  <Button variant="destructive" onClick={() => void removeDomain()}>{t("console.scenarios.delete")}</Button>
                )}
              </div>
            </>
          )}

          {selected?.type === "scenario" && (
            <>
              <h2 className="text-sm font-medium">{t("console.scenarios.newScenario")}</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("console.scenarios.domain")}>
                  <Select value={scenarioDraft.domain_id} onValueChange={(v) => v && setScenarioDraft({ ...scenarioDraft, domain_id: v })}>
                    <SelectTrigger><SelectValue placeholder={t("console.cascade.domain")} /></SelectTrigger>
                    <SelectContent>
                      {domainOptions.map((d) => <SelectItem key={d.slug} value={d.slug}>{d.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label={t("console.scenarios.slug")}>
                  <Input value={scenarioDraft.slug} onChange={(e) => setScenarioDraft({ ...scenarioDraft, slug: e.target.value })} />
                </Field>
                <Field label={t("console.scenarios.labelZh")}>
                  <Input value={scenarioDraft.label_zh} onChange={(e) => setScenarioDraft({ ...scenarioDraft, label_zh: e.target.value })} />
                </Field>
                <Field label={t("console.scenarios.labelEn")}>
                  <Input value={scenarioDraft.label_en} onChange={(e) => setScenarioDraft({ ...scenarioDraft, label_en: e.target.value })} />
                </Field>
                <Field label={t("console.scenarios.specPath")}>
                  <Input value={scenarioDraft.spec_path} onChange={(e) => setScenarioDraft({ ...scenarioDraft, spec_path: e.target.value })} />
                </Field>
                <Field label={t("console.scenarios.category")}>
                  <Input value={scenarioDraft.category} onChange={(e) => setScenarioDraft({ ...scenarioDraft, category: e.target.value })} />
                </Field>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium">{t("console.scenarios.specEditor")}</Label>
                  {specDirty && <span className="text-xs text-amber-600">●</span>}
                </div>
                <Textarea
                  className="min-h-72 font-mono text-xs"
                  value={specContent}
                  onChange={(e) => { setSpecContent(e.target.value); setSpecDirty(true); }}
                  placeholder="{}"
                />
                {specError && <p className="text-xs text-destructive">{specError}</p>}
                <div className="flex flex-wrap items-center gap-2">
                  <Button onClick={() => void saveScenario()} disabled={busy}>{t("console.scenarios.save")}</Button>
                  <Button onClick={() => void saveSpec()} disabled={busy || !specDirty} variant="outline">
                    {t("console.scenarios.specSave")}
                  </Button>
                  {specHistory.length > 0 && (
                    <Select value="" onValueChange={(v) => v && void loadHistoryVersion(v)}>
                      <SelectTrigger className="w-56">
                        <SelectValue placeholder={lang === "zh" ? "历史版本（覆盖当前编辑）" : "History (loads into editor)"} />
                      </SelectTrigger>
                      <SelectContent>
                        {specHistory.map((version) => (
                          <SelectItem key={version.ts} value={version.ts}>{version.ts}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  {scenarioDraft.id !== "__new__" && (
                    <Button variant="destructive" onClick={() => void removeScenario()}>{t("console.scenarios.delete")}</Button>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

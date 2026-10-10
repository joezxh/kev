"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api, PRESETS, type PermuteResponse, type Question, type SystemOneRequest, type SystemOneResponse } from "@/lib/kev";
import { useLang } from "@/lib/i18n";
import { AnswerCard } from "@/components/answer-card";
import { LangToggle } from "@/components/lang-toggle";
import { ApiKeyPicker } from "@/components/console/ApiKeyPicker";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

function parseState(s: string) {
  const t = s.trim();
  if (t.startsWith("{") || t.startsWith("[")) {
    try { return JSON.parse(t); } catch { /* treat as plain text */ }
  }
  return s;
}

type ModelInfo = { run: string; base: string } | { error: string } | null;

export function Playground() {
  const { lang, t } = useLang();
  const [presetIdx, setPresetIdx] = useState(0);
  const [stateText, setStateText] = useState(() => PRESETS[0].state[lang]);
  const [questionsText, setQuestionsText] = useState(() => PRESETS[0].questions[lang]);
  const [result, setResult] = useState<SystemOneResponse | null>(null);
  const [separate, setSeparate] = useState<SystemOneResponse | null>(null);
  const [permute, setPermute] = useState<{ question: string; data: PermuteResponse } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState<ModelInfo>(null);
  const [tab, setTab] = useState("answers");

  useEffect(() => {
    api.models().then((m) => setModel(m.models[0])).catch((e: Error) => setModel({ error: e.message }));
  }, []);

  // On language change, reload the current preset in the new language so the
  // submitted state/questions also switch (option keys stay identical).
  useEffect(() => { loadPreset(presetIdx); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [lang]);

  const parsed = useMemo<{ req?: SystemOneRequest; err?: string }>(() => {
    try {
      const questions = JSON.parse(questionsText) as Record<string, Question>;
      return { req: { state: parseState(stateText), model: "kev-latest", questions } };
    } catch (e) { return { err: (e as Error).message }; }
  }, [stateText, questionsText]);

  const choiceIds = useMemo(
    () => (parsed.req ? Object.entries(parsed.req.questions).filter(([, q]) => q.type === "choice" && Object.keys(q.criteria).length >= 2).map(([id]) => id) : []),
    [parsed.req],
  );

  function loadPreset(i: number) {
    const p = PRESETS[i];
    setPresetIdx(i);
    setStateText(p.state[lang]);
    setQuestionsText(p.questions[lang]);
    setResult(null); setSeparate(null); setPermute(null); setError(null); setTab("answers");
  }

  async function run<T>(label: string, fn: () => Promise<T>, done: (t: T) => void) {
    if (!parsed.req) return;
    setBusy(label); setError(null);
    try { done(await fn()); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  const onRun = () => run("run", () => api.systemOne(parsed.req!), (r) => { setResult(r); setSeparate(null); setPermute(null); setTab("answers"); });
  const onSeparate = () => run("separate", async () => ({ packed: await api.systemOne(parsed.req!), sep: await api.separate(parsed.req!) }), ({ packed, sep }) => { setResult(packed); setSeparate(sep); setTab("answers"); });
  const onPermute = (qid: string) => run("permute", () => api.permute(parsed.req!, qid, 6), (d) => { setPermute({ question: qid, data: d }); setTab("permute"); });

  const onRunRef = useRef(onRun);
  useEffect(() => { onRunRef.current = onRun; });   // latest handler for the global shortcut, without re-subscribing
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); onRunRef.current(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const maxDiff = useMemo(() => {
    if (!result || !separate) return null;
    let m = 0;
    for (const [id, a] of Object.entries(result.answers)) {
      const b = separate.answers[id];
      if (!b) continue;
      if (a.type === "noul" && b.type === "noul") m = Math.max(m, Math.abs(a.noul - b.noul));
      else if ("probabilities" in a && "probabilities" in b) for (const k of Object.keys(a.probabilities)) m = Math.max(m, Math.abs(a.probabilities[k] - (b.probabilities[k] ?? 0)));
    }
    return m;
  }, [result, separate]);

  const nQ = result ? Object.keys(result.answers).length : 0;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col px-6 pt-8 md:px-10">
      <header className="flex flex-nowrap items-center justify-between gap-x-4">
        <nav className="flex min-w-0 items-baseline gap-4 text-[15px]">
          <h1 className="font-medium tracking-tight">kev</h1>
          <Link href="/chess" className="text-muted-foreground hover:text-foreground">chess</Link>
          <Link href="/console" className="text-muted-foreground hover:text-foreground">{t("kev.nav.console")}</Link>
          <Link href={`/docs/${lang}`} className="text-muted-foreground hover:text-foreground">{lang === "zh" ? "kev文档" : "docs"}</Link>
        </nav>
        <div className="flex shrink-0 items-center gap-3">
          <LangToggle />
          <ApiKeyPicker />
        </div>
      </header>

      <div className="mt-10 max-w-2xl">
        <h2 className="text-2xl font-medium tracking-tight">{t("kev.tagline")}</h2>
        <p className="mt-2 text-[15px] leading-6 text-muted-foreground">{t("kev.intro")}</p>
      </div>

      <nav aria-label="Presets" className="mt-8 flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {PRESETS.map((p, i) => (
          <button key={i} type="button" onClick={() => loadPreset(i)} aria-current={i === presetIdx ? "true" : undefined}
            className={`border-b pb-0.5 transition-colors ${i === presetIdx ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {p.name[lang]}
          </button>
        ))}
      </nav>
      <p className="mt-2 max-w-2xl text-[13px] leading-5 text-muted-foreground">{PRESETS[presetIdx].blurb[lang]}</p>

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          <div className="flex flex-col gap-2">
            <Label htmlFor="state" className="text-[13px]">{t("kev.stateLabel")} <span className="font-normal text-muted-foreground">{t("kev.stateHint")}</span></Label>
            <Textarea id="state" value={stateText} onChange={(e) => setStateText(e.target.value)} className="min-h-28 rounded-md font-mono text-[13px] leading-5 shadow-none" />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="questions" className="text-[13px]">{t("kev.questionsLabel")} <span className="font-normal text-muted-foreground">{t("kev.questionsHint")}</span></Label>
            <Textarea id="questions" value={questionsText} onChange={(e) => setQuestionsText(e.target.value)} className="min-h-[28rem] rounded-md font-mono text-[13px] leading-5 shadow-none" aria-invalid={!!parsed.err} />
            {parsed.err && <p className="text-[13px] text-destructive">{parsed.err}</p>}
          </div>
        </div>

        <div className="flex min-w-0 flex-col">
          <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <TabsList variant="line" className="h-auto p-0">
                <TabsTrigger value="answers" className="px-0 text-sm">{t("kev.tab.answers")}</TabsTrigger>
                <TabsTrigger value="permute" disabled={!permute} className="px-0 text-sm">{t("kev.tab.permute")}</TabsTrigger>
                <TabsTrigger value="raw" disabled={!result} className="px-0 text-sm">{t("kev.tab.json")}</TabsTrigger>
              </TabsList>
              {result && (
                <p className="text-[13px] tabular-nums text-muted-foreground">
                  {result.latency_ms.toFixed(0)} ms · {result.usage.input_tokens} {t("kev.inputTokens")} · {nQ} {nQ === 1 ? t("kev.questionWord") : t("kev.questionsWord")}
                </p>
              )}
            </div>

            <TabsContent value="answers" className="mt-5">
              {!result && (
                <p className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">{t("kev.empty")}</p>
              )}
              {result && separate && (
                <p className="mb-3 rounded-md border border-border bg-muted/40 px-4 py-2.5 text-[13px] leading-5">
                  {t("kev.separate", { n: nQ, m1: result.latency_ms.toFixed(0), t1: result.usage.input_tokens, m2: separate.latency_ms.toFixed(0), t2: separate.usage.input_tokens, d: maxDiff != null ? maxDiff.toFixed(4) : "" })}
                  {maxDiff !== null && maxDiff < 0.011 ? " " + t("kev.separate.ok") : " " + t("kev.separate.bad")}
                </p>
              )}
              <div className="flex flex-col gap-2">
                {result && Object.entries(result.answers).map(([id, a]) => (
                  <AnswerCard key={id} id={id} question={parsed.req?.questions[id]} answer={a} compare={separate?.answers[id]} />
                ))}
              </div>
            </TabsContent>

            <TabsContent value="permute" className="mt-5">
              {permute && (
                <div className="rounded-lg border border-border bg-card p-5">
                  <p className="text-sm leading-6">
                    <span className="font-mono">{permute.question}</span> {t("kev.perm.underN", { n: permute.data.runs.length })}.{" "}
                    {permute.data.argmax_stable ? t("kev.perm.same") : t("kev.perm.changes")}
                  </p>
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-[13px]">
                      <caption className="sr-only">{t("kev.perm.caption")}</caption>
                      <thead>
                        <tr className="border-b border-border text-left text-muted-foreground">
                          <th scope="col" className="py-2 pr-4 font-normal">{t("kev.perm.order")}</th>
                          {Object.keys(permute.data.spread).map((k) => <th key={k} scope="col" className="py-2 pl-4 text-right font-mono font-normal">{k}</th>)}
                        </tr>
                      </thead>
                      <tbody className="tabular-nums">
                        {permute.data.runs.map((r, i) => (
                          <tr key={i} className="border-b border-border">
                            <th scope="row" className="py-2 pr-4 text-left font-normal text-muted-foreground" title={r.order.join(" → ")}>{r.order.map((o) => o.slice(0, 3)).join(" · ")}</th>
                            {Object.keys(permute.data.spread).map((k) => (
                              <td key={k} className={`py-2 pl-4 text-right ${r.choice === k ? "font-medium" : "text-muted-foreground"}`}>{r.probabilities[k].toFixed(2)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr>
                          <th scope="row" className="py-2 pr-4 text-left font-normal text-muted-foreground">{t("kev.perm.spread")}</th>
                          {Object.entries(permute.data.spread).map(([k, s]) => <td key={k} className={`py-2 pl-4 text-right tabular-nums ${s > 0.1 ? "font-medium" : "text-muted-foreground"}`}>{s.toFixed(2)}</td>)}
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                  <p className="mt-3 text-[13px] leading-5 text-muted-foreground">{t("kev.perm.foot")}</p>
                </div>
              )}
            </TabsContent>

            <TabsContent value="raw" className="mt-5">
              {result && (
                <div className="grid gap-4 xl:grid-cols-2">
                  <div className="rounded-lg border border-border bg-card p-5">
                    <p className="text-[13px] text-muted-foreground">{t("kev.raw.request")}</p>
                    <pre className="mt-2 max-h-[36rem] overflow-auto font-mono text-[12px] leading-5">{JSON.stringify(parsed.req, null, 2)}</pre>
                  </div>
                  <div className="rounded-lg border border-border bg-card p-5">
                    <p className="text-[13px] text-muted-foreground">{t("kev.raw.response")}</p>
                    <pre className="mt-2 max-h-[36rem] overflow-auto font-mono text-[12px] leading-5">{JSON.stringify(result, null, 2)}</pre>
                  </div>
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <div className="sticky bottom-0 z-10 mt-10 -mx-6 border-t border-border bg-background px-6 py-3 md:-mx-10 md:px-10">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={onRun} disabled={!parsed.req || !!busy} className="rounded-md">
              {busy === "run" ? t("kev.running") : t("kev.run")}
              <kbd className="ml-1 font-mono text-[11px] font-normal opacity-70">⌘↵</kbd>
            </Button>
            <Button variant="outline" onClick={onSeparate} disabled={!parsed.req || !!busy} className="rounded-md shadow-none" title={t("kev.packed.title")}>
              {busy === "separate" ? t("kev.comparing") : t("kev.packed")}
            </Button>
            {choiceIds.map((id) => (
              <Button key={id} variant="ghost" onClick={() => onPermute(id)} disabled={!!busy} className="rounded-md text-muted-foreground" title={t("kev.permute.title", { id })}>
                {busy === "permute" && permute?.question === id ? t("kev.permuting") : t("kev.permute")} <span className="font-mono">{id}</span>
              </Button>
            ))}
          </div>
          {/* kev 状态/调用问题统一在底部展示：后端不可用时红字，正常时灰字提示模型 */}
          {model === null && <p className="text-[13px] text-muted-foreground">{t("kev.connecting")}</p>}
          {model !== null && ("error" in model
            ? <p className="text-[13px] text-destructive">{t("kev.backendUnavailable", { error: model.error })}</p>
            : <p className="text-[13px] text-muted-foreground"><span className="font-mono">{model.base}</span> · <span className="font-mono">{model.run}</span></p>)}
          {error && <pre className="whitespace-pre-wrap text-[13px] text-destructive">{error}</pre>}
        </div>
      </div>
    </div>
  );
}

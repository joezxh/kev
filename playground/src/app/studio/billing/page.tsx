"use client";

import { useEffect, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button as UiButton } from "@/components/ui/button";
import { useLang } from "@/lib/i18n";
import { api, type Invoice } from "@/lib/console";
import { useProjects, ProjectSwitcher } from "@/components/studio/ProjectSwitcher";
import { PageHead, Panel, Drawer, FormGrid, Field, Kpi, EmptyState, StatusBadge } from "@/components/studio/primitives";

export default function StudioBillingPage() {
  const { t, lang } = useLang();
  const { projects } = useProjects();
  const [pid, setPid] = useState<string | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [period, setPeriod] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!pid && projects.length) setPid(projects[0].id);
  }, [projects, pid]);

  useEffect(() => {
    if (!pid) return;
    let alive = true;
    setLoading(true);
    api.invoices(pid)
      .then((i) => alive && setInvoices(i))
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [pid]);

  const openAmount = invoices.filter((i) => i.status === "open").reduce((s, i) => s + i.amount, 0);

  function openCreate() {
    setPeriod("");
    setAmount("");
    setCurrency("USD");
    setErr(null);
    setOpen(true);
  }
  async function create() {
    if (!pid) return;
    setBusy(true);
    setErr(null);
    try {
      await api.createInvoice(pid, { period, amount: Number(amount), currency });
      setInvoices(await api.invoices(pid));
      setOpen(false);
    } catch (e) {
      setErr(String((e as { message?: string })?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHead
        title={t("studio.nav.billing")}
        subtitle={lang === "zh" ? "计费周期、发票与应付余额。" : "Billing periods, invoices and outstanding balance."}
        actions={pid ? <UiButton variant="default" onClick={openCreate}>{lang === "zh" ? "记一笔发票" : "Record invoice"}</UiButton> : null}
      />

      {pid && <ProjectSwitcher projectId={pid} onChange={setPid} projects={projects} />}

      {!pid ? (
        <EmptyState title={lang === "zh" ? "请先在 Projects 创建项目。" : "Create a project under Projects first."} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi label={t("studio.billing.plan")} value={pid ? "Pro" : "—"} />
            <Kpi label={lang === "zh" ? "应付" : "Outstanding"} value={`$${openAmount.toFixed(2)}`} />
            <Kpi label={t("studio.billing.invoice")} value={String(invoices.length)} />
            <Kpi label={lang === "zh" ? "已付" : "Paid"} value={String(invoices.filter((i) => i.status === "paid").length)} />
          </div>

          <Panel desc={lang === "zh" ? `${invoices.length} 张发票` : `${invoices.length} invoices`}>
            {loading ? (
              <div className="text-xs text-muted-foreground">{lang === "zh" ? "加载中…" : "Loading…"}</div>
            ) : invoices.length === 0 ? (
              <EmptyState title={lang === "zh" ? "还没有发票。" : "No invoices yet."} action={<UiButton variant="default" onClick={openCreate}>{lang === "zh" ? "记一笔发票" : "Record invoice"}</UiButton>} />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studio.billing.period")}</TableHead>
                    <TableHead className="text-right">{t("studio.billing.amount")}</TableHead>
                    <TableHead>{t("studio.billing.currency")}</TableHead>
                    <TableHead>{t("studio.billing.status")}</TableHead>
                    <TableHead className="text-right">{t("studio.billing.due")}</TableHead>
                    <TableHead className="text-right">{t("studio.billing.issued")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoices.map((i) => (
                    <TableRow key={i.id}>
                      <TableCell className="font-mono text-xs">{i.period}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{i.amount.toFixed(2)}</TableCell>
                      <TableCell className="text-xs">{i.currency}</TableCell>
                      <TableCell>
                        <StatusBadge
                          status={i.status === "paid" ? "succeeded" : i.status === "void" ? "failed" : "pending"}
                          label={i.status}
                        />
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">{i.due_at ? i.due_at.slice(0, 10) : "—"}</TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">{i.issued_at.slice(0, 10)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Panel>
        </>
      )}

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={lang === "zh" ? "记一笔发票" : "Record invoice"}
        footer={
          <>
            <UiButton variant="outline" onClick={() => setOpen(false)}>{lang === "zh" ? "取消" : "cancel"}</UiButton>
            <UiButton variant="default" onClick={create} disabled={busy}>{busy ? "…" : lang === "zh" ? "保存" : "save"}</UiButton>
          </>
        }
      >
        <div className="space-y-4">
          {err && <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{err}</div>}
          <FormGrid>
            <Field label={`${t("studio.billing.period")} (2026-10)`}>
              <input value={period} onChange={(e) => setPeriod(e.target.value)} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
            </Field>
            <Field label={t("studio.billing.amount")}>
              <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary" />
            </Field>
            <Field label={t("studio.billing.currency")}>
              <select value={currency} onChange={(e) => setCurrency(e.target.value)} className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary">
                <option value="USD">USD</option>
                <option value="CNY">CNY</option>
                <option value="EUR">EUR</option>
              </select>
            </Field>
          </FormGrid>
        </div>
      </Drawer>
    </div>
  );
}

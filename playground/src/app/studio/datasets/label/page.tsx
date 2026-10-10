"use client";

import { useState } from "react";
import { useLang } from "@/lib/i18n";
import { StudioTabs } from "@/components/studio/StudioTabs";
import { PageHead, Panel, StatusBadge, Drawer } from "@/components/studio/primitives";
import { Button as UiButton } from "@/components/ui/button";

const DATASETS_TABS = [
  { href: "/studio/datasets", labelKey: "studio.tab.run" },
  { href: "/studio/datasets/label", labelKey: "studio.tab.label" },
];

type Item = {
  id: string;
  scenario: string;
  state: string;
  question: string;
  options: string[];
  status: "pending" | "labeled" | "flagged";
  choice?: number;
};

const ITEMS: Item[] = [
  {
    id: "lbl_01",
    scenario: "critical-value",
    state: "血钾 3.1 mmol/L，肌酐 180 µmol/L，服用螺内酯 25mg qd。",
    question: "是否需暂停螺内酯并补钾？",
    options: ["是，暂停并补钾", "否，继续观察", "下调剂量至 12.5mg", "转肾内科会诊"],
    status: "pending",
  },
  {
    id: "lbl_02",
    scenario: "dosage",
    state: "华法林 3mg qd，INR 2.8，拟加用胺碘酮。",
    question: "胺碘酮联用下华法林应如何调整？",
    options: ["维持 3mg", "减至 1.5mg 并监测", "增至 4.5mg", "停用华法林"],
    status: "labeled",
    choice: 1,
  },
  {
    id: "lbl_03",
    scenario: "contraindication",
    state: "青霉素过敏史，社区获得性肺炎，需抗感染。",
    question: "首选抗感染方案？",
    options: ["阿莫西林", "莫西沙星", "头孢曲松", "阿奇霉素"],
    status: "flagged",
  },
  {
    id: "lbl_04",
    scenario: "drug-interaction",
    state: "辛伐他汀 40mg，新加用维拉帕米。",
    question: "该联用的主要风险与处理？",
    options: ["横纹肌溶解，辛伐他汀降至 10mg", "出血风险，无需调整", "QT 延长，停维拉帕米", "无显著相互作用"],
    status: "pending",
  },
];

export default function DatasetsLabelPage() {
  const { t, lang } = useLang();
  const [items, setItems] = useState(ITEM_MAP());
  const [openId, setOpenId] = useState<string | null>(null);
  const [choice, setChoice] = useState<number | undefined>(undefined);

  const open = items.find((i) => i.id === openId);
  const done = items.filter((i) => i.status !== "pending").length;
  const pct = Math.round((done / items.length) * 100);

  function openItem(id: string) {
    const it = items.find((i) => i.id === id);
    setChoice(it?.choice);
    setOpenId(id);
  }
  function save(status: "labeled" | "flagged") {
    if (openId == null) return;
    setItems((prev) => prev.map((i) => (i.id === openId ? { ...i, status, choice } : i)));
    setOpenId(null);
  }

  return (
    <div className="space-y-6">
      <StudioTabs tabs={DATASETS_TABS} />
      <PageHead
        title={t("studio.tab.label")}
        subtitle={lang === "zh" ? "人工标注与质检队列（医疗场景保留人工确认）。" : "Human labelling and QA queue (human confirm retained for medical)."}
      />

      <Panel desc={lang === "zh" ? `${done}/${items.length} 已处理` : `${done}/${items.length} done`}>
        <div className="mb-3 h-1.5 w-full overflow-hidden rounded bg-[#1c1c1c]">
          <div className="h-full bg-[#22c55e]" style={{ width: `${pct}%` }} />
        </div>
        <div className="space-y-2">
          {items.map((i) => (
            <button
              key={i.id}
              type="button"
              onClick={() => openItem(i.id)}
              className="flex w-full items-center gap-3 rounded border border-border bg-[#111111] p-3 text-left transition-colors hover:border-primary"
            >
              <span className="font-mono text-xs text-muted-foreground">{i.id}</span>
              <span className="rounded bg-[#1c1c1c] px-2 py-0.5 font-mono text-[11px] text-muted-foreground">{i.scenario}</span>
              <span className="flex-1 truncate text-xs">{i.state}</span>
              <StatusBadge
                status={i.status === "labeled" ? "succeeded" : i.status === "flagged" ? "failed" : "pending"}
                label={lang === "zh" ? (i.status === "labeled" ? "已标" : i.status === "flagged" ? "存疑" : "待标") : i.status}
              />
            </button>
          ))}
        </div>
      </Panel>

      <Drawer
        open={open !== undefined}
        onClose={() => setOpenId(null)}
        title={open?.id}
        subtitle={open?.scenario}
        footer={
          <>
            <UiButton variant="outline" onClick={() => save("flagged")}>
              {lang === "zh" ? "存疑" : "flag"}
            </UiButton>
            <UiButton variant="default" onClick={() => save("labeled")}>
              {lang === "zh" ? "保存" : "save"}
            </UiButton>
          </>
        }
      >
        {open && (
          <div className="space-y-4">
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">state</div>
              <p className="rounded border border-border bg-[#0a0a0a] p-3 text-sm">{open.state}</p>
            </div>
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">question</div>
              <p className="text-sm">{open.question}</p>
            </div>
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">options</div>
              <div className="space-y-2">
                {open.options.map((opt, idx) => (
                  <label
                    key={idx}
                    className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm transition-colors ${
                      choice === idx ? "border-primary bg-[#1e3a8a]/40" : "border-border bg-[#111111]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="choice"
                      checked={choice === idx}
                      onChange={() => setChoice(idx)}
                      className="accent-[#3b82f6]"
                    />
                    {opt}
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}

function ITEM_MAP() {
  return ITEMS.map((i) => ({ ...i }));
}

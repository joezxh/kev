"use client";

import Link from "next/link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { JobStagePage } from "@/components/console/JobStagePage";
import { useLang } from "@/lib/i18n";

export default function StudioGoldsetPage() {
  const { t, lang } = useLang();
  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-lg font-semibold">{t("studio.goldset.title")}</h1>
        <Alert>
          <AlertTitle>{t("studio.goldset.subtitle")}</AlertTitle>
          <AlertDescription>
            {lang === "zh"
              ? "make_goldset.py audit 对比两份标注的分歧率，超阈值则非 0 退出。"
              : "make_goldset.py audit compares disagreement between two labellings; above threshold it exits non-zero."}
          </AlertDescription>
        </Alert>
      </section>

      <JobStagePage
        kind="goldset_audit"
        title={t("studio.nav.goldset")}
        hideScenario
        initial={{ a: "data/cv.a.jsonl", b: "data/cv.b.jsonl", out: "", threshold: "0.05" }}
        fields={[
          { key: "a", label: "A", hint: lang === "zh" ? "第一份标注（如厂商甲）" : "first labelling (e.g. vendor A)" },
          { key: "b", label: "B", hint: lang === "zh" ? "第二份标注（如厂商乙）" : "second labelling (e.g. vendor B)" },
          { key: "out", label: "--out", hint: lang === "zh" ? "分歧记录输出（可空）" : "disagreement output (optional)" },
          { key: "threshold", label: "--threshold", hint: lang === "zh" ? "最差问题分歧率超此值则非 0 退出" : "worst-question disagreement above this exits non-zero" },
        ]}
      >
        <div>
          <Link href="/console/goldset/review">
            <Button variant="secondary" size="sm">{t("studio.goldset.review")}</Button>
          </Link>
        </div>
      </JobStagePage>
    </div>
  );
}

"use client";

import Link from "next/link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { JobStagePage } from "@/components/console/JobStagePage";
import { useLang } from "@/lib/i18n";

/** 金标集：分歧审计（make_goldset.py audit）。无场景概念，隐藏场景选择器。 */
export default function GoldsetPage() {
  const { t, lang } = useLang();

  return (
    <JobStagePage
      kind="goldset_audit"
      title={t("console.nav.goldset")}
      hideScenario
      initial={{ a: "data/cv.a.jsonl", b: "data/cv.b.jsonl", out: "", threshold: "0.05" }}
      fields={[
        { key: "a", label: "A", hint: lang === "zh" ? "第一份标注（如厂商甲）" : "first labelling (e.g. vendor A)" },
        { key: "b", label: "B", hint: lang === "zh" ? "第二份标注（如厂商乙）" : "second labelling (e.g. vendor B)" },
        { key: "out", label: "--out", hint: lang === "zh" ? "分歧记录输出（可空）" : "disagreement output (optional)" },
        { key: "threshold", label: "--threshold", hint: lang === "zh" ? "最差问题分歧率超此值则非 0 退出" : "worst-question disagreement above this exits non-zero" },
      ]}
    >
      <Alert>
        <AlertTitle>{t("console.nav.goldset")}</AlertTitle>
        <AlertDescription>{t("console.goldset.auditHint")}</AlertDescription>
      </Alert>
      <div>
        <Link href="/console/goldset/review">
          <Button variant="secondary" size="sm">{t("console.goldset.openReview")}</Button>
        </Link>
      </div>
    </JobStagePage>
  );
}

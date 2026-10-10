"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { JobStagePage } from "@/components/console/JobStagePage";
import { useLang } from "@/lib/i18n";

export default function StudioPublishPage() {
  const { t, lang } = useLang();
  return (
    <div className="space-y-8">
      <JobStagePage
        kind="publish"
        title={t("studio.nav.publish")}
        hideScenario
        initial={{ run: "runs/cv-8b-lora-v1/checkpoint", repo: "jaredpalmer/kev-0.8b", card: "docs/model-cards/kev-0.8b.md", private: "0", replace: "0" }}
        fields={[
          { key: "run", label: "--run", hint: "checkpoint 目录，默认 runs/<name>/checkpoint" },
          { key: "repo", label: "--repo" },
          { key: "card", label: "--card", hint: lang === "zh" ? "模型卡 markdown 路径" : "model card markdown, e.g. docs/model-cards/kev-0.8b.md" },
          { key: "message", label: "--message" },
          { key: "private", kind: "select", label: "--private", options: [{ value: "0", label: "0" }, { value: "1", label: "1" }] },
          { key: "tag", label: "--tag" },
          { key: "revision", label: "--revision" },
          { key: "replace", kind: "select", label: "--replace", options: [{ value: "0", label: "0" }, { value: "1", label: "1" }] },
        ]}
      >
        <Alert>
          <AlertTitle>{t("studio.nav.publish")}</AlertTitle>
          <AlertDescription>{t("console.publish.hint")}</AlertDescription>
        </Alert>
      </JobStagePage>
    </div>
  );
}

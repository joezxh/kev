"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { JobStagePage } from "@/components/console/JobStagePage";
import { useLang } from "@/lib/i18n";

/** 阶段 7 · Modal 部署（modal deploy kev_modal.py）。无场景概念，隐藏场景选择器。 */
export default function ModalPage() {
  const { t, lang } = useLang();

  return (
    <JobStagePage
      kind="modal"
      title={t("console.nav.modal")}
      hideScenario
      initial={{ run: "cv-8b-lora-v1", gpu: "L4", app_name: "kev-finetune", ref: "" }}
      fields={[
        { key: "run", label: "KEV_SERVE_RUN", hint: "本地 runs/<name> 或 Hub id（如 jaredpalmer/kev-4b）" },
        { key: "gpu", label: "KEV_SERVE_GPU", hint: "H100 / L40S / L4 / A100" },
        { key: "app_name", label: "KEV_APP_NAME" },
        { key: "ref", label: "KEV_REF", hint: lang === "zh" ? "commit 钉（可空）" : "commit pin (optional)" },
      ]}
    >
      <Alert>
        <AlertTitle>{t("console.nav.modal")}</AlertTitle>
        <AlertDescription>{t("console.modal.hint")}</AlertDescription>
      </Alert>
    </JobStagePage>
  );
}

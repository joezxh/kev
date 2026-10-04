"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { JobStagePage } from "@/components/console/JobStagePage";
import { useLang } from "@/lib/i18n";

/**
 * 阶段 2 · SFT 训练。
 *
 * 方式的默认值来自 /console/api/config（服务端单一来源），前端不硬编码 ——
 * icd-coding 只支持 4B 轨，而那是 run_matrix.FOUR_B_ONLY 决定的。
 */
export default function TrainPage() {
  const { t, lang } = useLang();

  return (
    <JobStagePage
      kind="train"
      gateStage="train"
      title={t("console.nav.train")}
      initial={{ method: "a1" }}
      fields={[
        { key: "method", kind: "select", label: "method",
          options: [
            { value: "a1", label: t("console.method.a1") },
            { value: "a2", label: t("console.method.a2") },
            { value: "b", label: t("console.method.b") },
          ] },
        { key: "lr", label: "--lr", hint: lang === "zh" ? "0.8B 是 4e-5、4B 是 2e-5（各自沿用 init 的参数）" : "4e-5 for 0.8B, 2e-5 for 4B (each inherits its init's)" },
        { key: "lora", label: "--lora" },
        { key: "lora_targets", kind: "select", label: "--lora_targets",
          options: ["all", "dense", "attn", "qv"].map((v) => ({ value: v, label: v })) },
        { key: "replay", label: "--replay", hint: lang === "zh" ? "混入公开 decision-v7 记录防遗忘" : "mix in public decision-v7 records to avoid forgetting" },
        { key: "epochs", label: "--epochs" },
        { key: "batch", label: "--batch" },
        { key: "accum", label: "--accum" },
        { key: "head_dim", label: "--head_dim" },
        { key: "checkpointing", kind: "select", label: "--checkpointing",
          options: [{ value: "0", label: "0" }, { value: "1", label: "1" }] },
        { key: "max_steps", label: "--max_steps",
          when: (_s, v) => v.method === "b",
          hint: lang === "zh" ? "写快照时必填：kev.budget.MAX_SNAPSHOTS = 8，且快照永不删除" : "required for snapshots: MAX_SNAPSHOTS = 8 and they are never deleted" },
        { key: "snapshot_fractions", label: "--snapshot_fractions",
          when: (_s, v) => v.method === "b" && v.max_steps !== "" },
      ]}
    >
      <Alert>
        <AlertTitle>{t("console.train.risk08b")}</AlertTitle>
        <AlertDescription>{t("console.train.risk08bBody")}</AlertDescription>
      </Alert>
    </JobStagePage>
  );
}
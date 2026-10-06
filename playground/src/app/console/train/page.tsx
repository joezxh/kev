"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { JobStagePage, type FieldSpec } from "@/components/console/JobStagePage";
import { useLang } from "@/lib/i18n";

/**
 * 阶段 2 · SFT 训练。
 *
 * 方式的默认值来自 /console/api/config（服务端单一来源），前端不硬编码 ——
 * icd-coding 只支持 4B 轨，而那是 run_matrix.FOUR_B_ONLY 决定的。
 * 训练高级开关（runbook §七 7.4 项 3）全部在此暴露，参数名下划线、与 kev/train.py 一致。
 */
const ADVANCED: FieldSpec[] = [
  { key: "anchor", label: "--anchor", hint: "锚定正例 json（state 列表路径）" },
  { key: "anchor_w", label: "--anchor_w", hint: "锚定权重，>0 才生效" },
  { key: "anchor_sources", label: "--anchor_sources", hint: "csv 来源" },
  { key: "perm_kl", label: "--perm_kl", hint: "排列 KL 系数" },
  { key: "perm_frac", label: "--perm_frac", hint: "默认 0.3" },
  { key: "ord_w", label: "--ord_w", hint: "排序损失权重" },
  { key: "label_smoothing", label: "--label_smoothing" },
  { key: "brier_w", label: "--brier_w" },
  { key: "focal_gamma", label: "--focal_gamma" },
  { key: "p_none", label: "--p_none", hint: "默认 0.1" },
  { key: "p_none_distract", label: "--p_none_distract", hint: "默认 0.12" },
  { key: "p_none_pair", label: "--p_none_pair" },
  { key: "none_pair_max_state", label: "--none_pair_max_state" },
  { key: "synthetic_repeat", label: "--synthetic_repeat", hint: "默认 1" },
  { key: "public_frac", label: "--public_frac", hint: "默认 1.0" },
  { key: "train_sources", label: "--train_sources", hint: "csv 训练源" },
  { key: "holdout", label: "--holdout", hint: "金标 holdout jsonl 路径，不进 train" },
  { key: "special_embeddings", label: "--special_embeddings", hint: "0/1" },
  { key: "option_isolation", label: "--option_isolation", hint: "0/1" },
  { key: "shared_prefix", label: "--shared_prefix", hint: "0/1" },
  { key: "snapshot_every_steps", label: "--snapshot_every_steps" },
];

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
        ...ADVANCED,
      ]}
    >
      <Alert>
        <AlertTitle>{t("console.train.risk08b")}</AlertTitle>
        <AlertDescription>{t("console.train.risk08bBody")}</AlertDescription>
      </Alert>
    </JobStagePage>
  );
}

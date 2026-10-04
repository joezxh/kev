<p align="center">
  <a href="./runbook-train.md"><img alt="详细中文" src="https://img.shields.io/badge/%E8%AF%A6%E7%BB%86%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./README.md"><img alt="主方案" src="https://img.shields.io/badge/%E4%B8%BB%E6%96%B9%E6%A1%88-blue?style=for-the-badge"></a>
</p>

# 医疗微调执行手册 · 英文版（速查）

[← 主方案](./README.md) · [数据格式](./data-format.md) · [生成器说明](./generators/README.md) · **完整版见 [runbook-train.md](./runbook-train.md)**

本文件是 `runbook-train.md` 的**精简引用版**：每步只给「目的 + 命令 + 判读要点」，踩坑与背景以详细版为准。命令均在本仓库根目录执行（PowerShell 用 `python`、bash 用 `python3`）。

---

## 〇、两种微调方式（一句话）

| 方式 | 开关 | 输出 | 适用 |
| --- | --- | --- | --- |
| A1 LoRA 热启动（推荐） | `--init_from jaredpalmer/kev-0.8b --lora 16` | `adapter_model.safetensors`+`head.pt` | 几百~几千条医疗数据 |
| A2 LoRA 裸基座 | `--base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e --lora 16` | 同上 | 完全自己塑形 |
| B 全参数 | `--full_ft 1 --weights_dtype bf16` | `model*.safetensors`+`head.pt` | 数千~数万条、有 24GB+ 单卡 |

> Kev 是「只输出校准概率、不生成文本」的决策模型；训练目标本质就是 SFT（对选项边界做 log-loss），**DPO 不适用**。

---

## 步骤 0 · 测两条基线（双尺寸）

```bash
uv run python -m kev.benchmark --run jaredpalmer/kev-0.8b --data data/cv/development.jsonl --out runs/base-8b --device cuda
uv run python -m kev.benchmark --run jaredpalmer/kev-4b  --data data/cv/development.jsonl --out runs/base-4b  --device cuda
```
**判读**：取 `development.calibrated.acc` 作为 `plan_size --baseline-acc` 输入。

## 步骤 1 · 算记录数

```bash
python skills/kev-finetune/scripts/plan_size.py docs/medical/specs/<name>.json --baseline-acc 0.75
```
**判读**：每场景 4 问 → `generate at least 787 records`（train 551 + cal 118 + dev 118）。

## 步骤 2 · 生成数据（★6 大类 / 多 key / 每日调度）

**程序化（阈值表零漂移，危急值等）**：
```bash
python docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0
```

**LLM 蒸馏（6 大类任选其一，用 `--category`）**：

| `--category` | 中文 | spec |
| --- | --- | --- |
| `nursing_quality` | 医院护理质量管控 | `nursing-quality.json` |
| `record_summary` | 住院病历现病史与病程记录摘要核对 | `record-summary.json` |
| `medication_review` | 门诊与住院处方审核 | `medication-review.json` |
| `icd_coding` | 住院病案编码与 DRG/DIP 审核 | `icd-coding.json` |
| `initial_assessment` | 门诊与急诊的初诊评估 | `diagnosis.json` |
| `report_review` | 医院检验科与影像科报告复核 | `critical-value.json` |
| `triage`（额外） | 门诊与互联网医院导诊分诊 | `triage.json` |

```bash
export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1
# 单 key
export KEV_GEN_API_KEY=sk-studio-****
python skills/kev-finetune/scripts/generate_data.py --category triage \
  --n 787 --batch 10 --concurrency 3 --model Ling-3.0-tiny --out data/cv/triage.jsonl
# 多 key：每把每天 50w token，额度用尽自动轮换；用量落在 .distill/usage_<日期>.json（跨进程续算）
export KEV_GEN_API_KEYS="sk-...1,sk-...2,sk-...3"     # 或 --keys-file .distill_keys.txt
python skills/kev-finetune/scripts/generate_data.py --category medication_review \
  --n 787 --model Ling-3.0-tiny --daily-limit 500000
# 每天蒸馏一部分：脚本守护 --schedule HH:MM，或交系统定时任务（cron / 任务计划程序）每天触发一次普通调用
python skills/kev-finetune/scripts/generate_data.py --category triage --n 787 --model Ling-3.0-tiny --schedule 03:00
```
**判读**：`stopped short of --n` 或 `rejected` 高 → `guidance` 太模糊（先 `--dry-run` 看提示词）。
**百灵 token 效率**：`Ling-3.0-flash`≈1828 tok/条（≈273 条/天·单 key）；`Ling-3.0-tiny`（关推理）≈301 tok/条（≈1658 条/天·单 key，提升 ≈6.1×）。多 key 线性叠加。

## 步骤 3 · 抽金标 + 人工审校

```bash
python docs/medical/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl --seed 0
```
**判读**：金标 ≥150 条；临床/药学按 `guidance` 逐条核对，**只用于最后一次终评**。

## 步骤 4 · 划分（串行，勿与生成并行）

```bash
python skills/kev-finetune/scripts/split_data.py data/cv.jsonl --out data/cv --holdout data/cv.gold.jsonl
# 每类独立：split_data.py data/cv/<cat>.jsonl --out data/cv/<cat>
```
**判读**：`states with conflicting labels dropped` 非 0 → 标注规则自相矛盾，回改 `guidance`。

## 步骤 5 · token 超限预检（中文必做）

```bash
uv run python -c "from kev.model import load_tokenizer, training_context, fits, materialize; from kev.data import load_records
tok=load_tokenizer('jaredpalmer/kev-0.8b'); recs=load_records('data/cv/train.jsonl')
print('over_limit', sum(1 for r in recs if not fits(materialize(r), tok, **training_context(384))))"
```
**判读**：`over_limit` 非 0 → 缩短 state；不要用 `STATE_CHARS_WARN=1400`（英文口径）。

## 步骤 6 · 训练配置（三方式开关）

| 开关 | A1 | A2 | B |
| --- | --- | --- | --- |
| `--init_from`/`--base` | `jaredpalmer/kev-0.8b` | `Qwen/Qwen3.5-0.8B-Base`(@`9a45d25e`) | 同上 |
| `--lora` | `16` | `16` | 忽略 |
| `--full_ft` | `0` | `0` | `1` |
| `--weights_dtype` | `fp32` | `fp32` | `bf16` |

## 步骤 7 · 启动训练

```bash
uv run python -m kev.train --data data/cv/train.jsonl --init_from jaredpalmer/kev-0.8b \
  --lora 16 --lr 4e-5 --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda --replay 2000 --out runs/cv-8b-lora-v1
```
**判读**：`trainable params` LoRA 为数百万；`loss` 随 step 降；打印 `dropped N of M` 非 0 → 回步骤 5。CPU 仅冒烟，真实训练用 GPU。

## 步骤 8 · 监控
看 `<out>/training_metrics.json`（`wall_seconds`/`grad_norm`/`records_seen`）；`max` 梯度范数远超均值 → 异常。

## 步骤 9 · 评估

```bash
uv run python -m kev.benchmark --run runs/cv-8b-lora-v1 --data data/cv/development.jsonl --out runs/cv-8b-lora-v1-eval --device cuda
```
**判读**：`bootstrap.acc.ci95` **排除 0** 才显著；`regression` >2 点 → 降 `--lr` 减半、保留 `--replay`。

## 步骤 10 · 温度拟合

```bash
uv run python -m kev.calibrate --rows runs/cv-8b-lora-v1-eval/rows.json --out runs/cv-8b-lora-v1-eval/calibration.json
```
**判读**：把 `workload_temperature` 作为服务温度；线上真实先验 ≠ 均衡训练先验，上线前重标定切点。

## 步骤 11 · 导出

```bash
uv run python -m kev.publish --run runs/cv-8b-lora-v1 --repo jaredpalmer/kev-0.8b --card docs/model-cards/kev-0.8b.md --private
```

## 步骤 12 · 部署

```bash
KEV_APP_NAME=kev-cv-8b KEV_SERVE_RUN=cv-8b-lora-v1 modal deploy skills/kev-finetune/scripts/kev_modal.py
# 或本地：uv run python -m kev.serve --run runs/cv-8b-lora-v1 --port 8008
```

---

## 排错清单（速查）

| 症状 | 处置 |
| --- | --- |
| `No module named 'resource'`/`'fcntl'` | 原生 Windows 跑训练报错；真实训练放 Linux/WSL2 |
| `OSError: couldn't connect to huggingface.co` | `export HF_ENDPOINT=https://hf-mirror.com` |
| `warning: labels [...] under 5%` | 调生成器配额，别加 `--n` |
| `states with conflicting labels dropped` 非 0 | `guidance` 自相矛盾，回改 |
| 训练器 `dropped N of M records` | 超 token 上限，步骤 5 实测缩短 state |
| `non-finite training loss` | 降 `--lr`，查数据 |
| `regression` > 2 点 | 降 `--lr` 减半、保留 `--replay 2000`、不加 epoch |
| 蒸馏 `stopped short of --n` | `guidance` 模糊，先 `--dry-run` |
| `[budget] all keys hit daily limit` / 退出码 2 | 当日多 key 额度用尽；等次日或加 key/调 `--daily-limit` |
| 蒸馏数据不进质量 | 先脱敏，或 `KEV_GEN_BASE_URL` 指向本地 Ollama |

---

## 交付物清单（速查）

见 [runbook-train.md §六](./runbook-train.md#六交付物清单)：规则合成数据（train/cal/dev 三分区）、0.8B Kev 微调模型（规划）、基座权重（镜像可达）；LLM 蒸馏按 `--category` 落到 `data/cv/<spec名>.jsonl`，多 key 每日 50w + 调度实现「每天蒸馏一部分」。

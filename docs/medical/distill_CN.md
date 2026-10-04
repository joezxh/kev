<p align="center">
  <a href="./distill_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./distill.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 医疗蒸馏层操作手册

[← 返回主方案](./README.md) · [蒸馏层总览](./distill/README.md) · [方案文档](../sft-distill_CN.md)

逐条命令、预期输出、判读要点、失败处置。方案与设计见[双语方案文档](../sft-distill_CN.md)。

```bash
D=docs/medical/distill
```

---

## 步骤 0 · 一次性准备

```powershell
$env:KEV_GEN_API_KEY = "..."                                # 百灵 API key
$env:KEV_GEN_BASE_URL = "https://<官方 base URL>/v1"        # 以 developer.ant-ling.com 为准
```

**预期**：无输出。
**判读**：base URL 与模型 id **必须**从官方文档确认。第三方博客（2026-02）称 `api.tbox.cn/api/llm/v1`，
未经交叉验证；模型族每 1–2 个月换代（最新为 Ling-3.0-flash），不要硬编码。
**失败处置**：若合规评估不通过，改用已开源的 `Ling-3.0-flash` 自建 vLLM，把 base URL 指向 `localhost`。

---

## 步骤 1 · 生成种子（零 token）

```bash
python3 $D/make_seeds.py --all --n 500 --out-dir data/seeds
```

**预期**：五行，每行打印种子数与 state 数，末行提示 `next: easydistill --config ...`。

**判读**：
- 每个场景的 seeds 与 states **行数必须相等**（脚本会断言）
- `knowledge-qa` 显示「Kev 轨: 无」是**正确的** —— Kev 只在预声明选项集上出概率，做不了开放式问答
- 种子 `instruction` 只陈述事实，**不含任何标签线索**

**失败处置**：
- `planned targets could not be realized` → 换 `--seed` 重跑；大批量出现则检查规则表与配额是否自洽
- `no spec at ...` → 该场景的 spec 不在 `docs/medical/specs/`

---

## 步骤 2 · 蒸馏（唯一花 token 的一步）

```bash
easydistill --config $D/configs/inquiry.yaml
```

**预期**：五个阶段依次落盘，最终产出 `data/sft/inquiry/inquiry.sft.jsonl`。

**判读 —— 每阶段后都要看行数**，尤其 `filter`：

| 阶段 | 行数应约为 | 若异常 |
| --- | --- | --- |
| `expanded` | 种子数 × `num_per_seed`（3） | 偏低说明扩充阶段产出被拒 |
| `generated` | ≈ expanded | 偏低说明 429 或生成失败，重跑（`resume: true` 会续） |
| `judged` | ≈ generated | — |
| `filtered` | **judged 的 50–80%** | **掉到 <30% 说明 judge 阈值与 spec 不匹配**，先放宽 `pass_score` |
| `*.sft.jsonl` | = filtered | — |

**失败处置**：
- `429` → 降 `backend.concurrency`（当前 2）并退避重试
- `401/403` → key 无效或未绑定
- `404` → model id 不存在，**去官方模型文档页重新确认**

⚠️ **按场景串行跑，不要并发跑多个场景** —— 云端并发上限低，并发只会换来 429。

---

## 步骤 3 · 转换 Kev 记录（零 token）

```bash
python3 $D/seed_to_kev.py --scenario inquiry \
  --seed-file data/seeds/inquiry.seed.jsonl \
  --state-file data/seeds/inquiry.state.jsonl \
  --out data/inquiry.jsonl
```

**预期**：

```text
500 records -> data/inquiry.jsonl (spec triage, seed 0)
distinct states: 500 (0 duplicate states)
  department: emergency=65 (13%), cardiology=39 (8%), ...
```

**判读**：与直接跑 `gen_triage.py` 的分布应基本一致 —— 标签源相同，差异只来自种子采样。
**失败处置**：
- `N seed ids have no state row` → 两个文件不同步，重跑步骤 1
- `labels [...] are not questions of spec` → 场景与 spec 名错配

---

## 步骤 4 · 教师/规则对账（只报告，不改标签）

```bash
python3 $D/seed_to_kev.py --scenario inquiry --from-sft data/sft/inquiry/inquiry.sft.jsonl \
  --report data/inquiry.reconcile.json
```

**预期**：`teacher/rule agreement: N/M = NN%`，外加分歧最多的 `(question, rule label)` 列表。

**判读**：这是**教师与规则引擎的边界一致率**，不是模型准确率。
- 高（>80%）→ 教师与规则看到同一条决策边界
- 低 → 分歧记录应优先进入人工审校

**失败处置**：SFT 文件没有 `id` 列时会跳过逐条对账并提示 —— 此时应在 EasyDistill 侧保留种子 `id`，
否则无法定位分歧记录。

---

## 步骤 5 · 量级与预算闸门

```bash
python3 $D/check_volume.py --scenario inquiry --records data/inquiry.jsonl --expect 500 \
  --from-sft data/sft/inquiry/inquiry.sft.jsonl --budget 8000000
```

**预期**：分布明细 + token 账 + `OK: 分布与预算断言全部通过`。

```text
== token 账
  Kev 轨: 0 LLM token（标签与 state 均来自规则引擎，不经 LLM）
  inquiry.sft.jsonl: 617,000 tokens over 500 rows (1,234/row, usage seen on 500 rows)
```

**判读 —— `1,234/row` 是本手册最有价值的一个数字**：它用**实测**替换了方案文档里
「每条约 1,000 tokens」的估算。拿到它之后，用它重算 Tier B/C 预算，再去谈付费额度。
**失败处置**：exit 1 时看 `FAILED` 列表逐条处理；`--expect` 不符是种子数问题，
`<5%` 或 `never labelled` 是规则表或配额问题，token 超限是量级问题。

---

## 排错清单

| 症状 | 原因 | 处置 |
| --- | --- | --- |
| `invalid run name` 相关 | 与蒸馏层无关，是 `train` 的命名规则 | 见 `runbook.md`；尺寸标识写 `8b`/`4b`，不写 `0.8b` |
| `429` | 云端并发/速率上限 | 降 `backend.concurrency`（当前 2），退避重试；`resume: true` 会续跑 |
| `404` on model | model id 不存在 | 模型族每 1–2 月换代，去官方模型文档页重新确认 |
| `401/403` | key 无效或未绑定账户 | 重新申请；确认账户已完成实名认证 |
| `filtered` 行数骤降 | judge 阈值与 spec 不匹配 | 放宽 `pass_score`；**不要**靠重跑碰运气 |
| `filtered` 为空 | 阈值过严或教师输出格式不符 | 先用 `--dry-run` 类比检查单条输出，再调阈值 |
| 对账跳过、提示无 `id` | SFT 文件缺 `id` 列 | 在 EasyDistill 侧保留种子 `id`，否则无法定位分歧 |
| 对账一致率极低 | 教师与规则边界不一致 | **不要**改标签；把分歧记录送人工审校，并检查 `guidance` |
| `N seed ids have no state row` | 双文件不同步 | 重跑 `make_seeds.py`，两文件必须同序同长 |
| `labels [...] under 5%` | 标签分布没配平 | 调生成器的 share 类参数，**不要**靠加量 |
| `never labelled` | 某选项从未作为正确答案出现 | 检查规则表/配额，让每个选项都有机会被选中 |
| `data/seeds/...` 提示已被 git 跟踪 | `.gitignore` 未生效 | 确认 `.gitignore` 含 `data/`（本仓库已加），用 `git check-ignore` 验证 |
| 成人携带儿科关键词 | `gen_triage.py` 词表缺陷（实测 6.8%） | **蒸馏前必修**，见方案文档 §13；需单独授权改上游生成器 |



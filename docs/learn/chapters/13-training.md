# 13. 训练框架实操

> 《Kev 基础知识系统学习指南》· 第三部分 应用篇
>
> **本部分目标**：把前十二个概念变成能跑的命令。每个模块先看入口与产物长什么样，再看“哪个旋钮真正改变结果”。
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](12-frozen-suites.md) · [下一章 →](14-serving.md)

---


### 13.1 概念定义

训练就是三件事：**把 record 变成 loss** → **把 loss 装进一个付得起显存的计划** → **把产物写成可加载的 checkpoint**。
[kev/train.py](../../../kev/train.py) 就按这三段组织（损失：47-96 行；数据与计划：104-388 行；入口与产物：390 行起）。

| 维度 | 选项 | 哪个旋钮 |
|---|---|---|
| 数据入口 | ① `--suite evals/v7/decision-v7`（只用其训练分区）② `--data x.jsonl`（自己的标注行）③ 都不给 → `--n_per_source N` 从公开源现场造（smoke 路径）；`--data + --suite --replay N` = 增量微调不忘本 | `--suite / --data / --n_per_source / --replay / --train_sources / --holdout` |
| 权重模式 | LoRA（默认）或全权重 `--full_ft 1 --weights_dtype bf16`（MasterAdamW fp32 masters；torchrun 下 FSDP2 分片） | `--full_ft / --lora / --lora_targets / --init_from` |
| 一次 forward 的形状 | packed（仅注意力基座）/ rows（hybrid 必然）/ shared prefix（`--shared_prefix`，行形式的最省版本） | `--shared_prefix / --row_budget / --length_sort / --pass_tokens_max` |
| 损失 | 硬标签 CE / 软目标 CE / +RPS / 三个互斥修正项 / 置换 KL / 锚定 KL | `--ord_w / --label_smoothing\|--brier_w\|--focal_gamma / --perm_kl / --anchor_w` |

### 13.2 原理讲解

**(1) 逐题损失怎么拼。** `question_loss(z, q, dev, ord_w, label_smoothing, brier_w, focal_gamma)`：

- `q["target"]` 存在（蒸馏 / 教师分布）→ `-(t · log_softmax(z)).sum()`，**三个硬标签修正项自动失效**（它们只作用于硬 CE）；
- 否则 `F.cross_entropy`，可选 `+ brier_w·‖p - onehot‖²` 或 focal 重加权 `(1 - e^{-loss})^γ · loss`；
  `label_smoothing / brier_w / focal_gamma` **三个只能选一个**，同时给两个直接 `ValueError`；
- `qtype == "score"` 且 `ord_w > 0` → 加归一化 RPS `mean((p.cumsum()[:-1] - observed_cdf)²)`。这是 `--ord_w` 让 Score 题“有序”的全部秘密。

⚠ 三个修正项默认 0，**且没有一个出现在任何发布配方里**（round 3 校准筛查的产物，不是产品特性）。

**(2) 两个“形状不变量”损失。** 它们不推高准确率，只堵两条捷路：

- **置换 KL**（`--perm_kl`，抽 `--perm_frac` 比例的 record）：`permuted_copy` 只对 **K ≥ 3 的 choice** 重排选项
  （noul 与 2 选项题重排无意义，`perms[q] = None`）；`permutation_kl` 算两个顺序下的**对称 KL**，同一预测换序后严格为 0。
- **锚定 KL**（`--anchor <json> --anchor_w`）：`KL(teacher ‖ student)`，teacher 是**冻结基座的零样本答案**（`kev.anchors` 生成）。
  关键细节：选项集合与 teacher 不一致（比如插了 none）时 **返回 `None` 跳过**，不猜。

**(3) 增强与混比**（真正改变行为的几个小数）：`--p_none / --p_none_distract / --p_distract` 往 record 里添/删 none 与干扰项；
`--p_none_pair` 额外产出 none-present / none-absent 最小对（训“该拒就拒”）；`--none_pair_max_state N` 只让短 state 配对
（round 21 的教训：一对就是三份 state，长文档上直接把 GPU 撞爆）；`--synthetic_repeat` 过采样三个生成源
（`SYNTHETIC_SOURCES = legacy_policy / compositional / contrastive`）；`--public_frac` 决定性抽稀公开源。

**(4) 计划：字符预算 vs token 预算。** `microbatch_plan` 把一个 optimizer step 的 record 切成 micro-batch；
`pass_tokens(shapes, shared)` 回答“一次 forward 吃多少 padded token”：行形式 = `行数 × 最长行`（state 每题重算一份），
共享前缀 = `record 数 × 最长 state + 分支个数 × 最长分支`（state 只算一次）。实测
`(1000,[120,140,130]) + (900,[110,105])`：行形式 **5,700**，共享前缀 **2,700**。`--length_sort 1` 用
`balanced_runs(items, n, cost)` 把一步的 record 切成“等长且成本平衡”的 n 个连续段（对上限二分，必要时对半拆最贵段）；
`--pass_tokens_max N` 把计划从**字符**改成**精确 token 形状**（`plan_shapes`）：round 21 用字符计划在到 62 步就 OOM
——一个 PII state 把 16 个 state 的 padding 顶到 5,877 token，一个 98.7k-token 的 pass 被按字符同槽位的 33-50k 兄弟平价看待。
`--row_budget N`（单 GPU）直接限定每次 forward/backward 的 padded token，装不下的 record 按问题拆（27B 单卡 H200 需要 8192）。

**(5) 产物长什么样。** 一个 LoRA run 的 `<out>` 目录（实测 `runs/smoke-mirror`）：

```text
adapter_config.json  adapter_model.safetensors          # PEFT 增量权重（基座本身永不写盘）
head.pt  tokenizer.json  tokenizer_config.json          # 指针头 + 含 5 个分隔 token 的 tokenizer
training_config.json  training_metrics.json             # 完整 args 与本次 run 的运行时统计
```

`head.pt` 的键（实测）：`args / suite_sha256 / init_source / base / base_revision / head（q、k 的 weight+bias）/ lora / head_dim /
option_isolation / special_embeddings / weights_dtype / temperature / holdout / weights`。
**第 9 章说的“出厂温度”就住在 `head.pt["temperature"]`**；`weights` 是 `"lora"` 还是 `"full"` 决定了加载路径。
`training_metrics.json` 里最有用的三个：`rejected_records` / `truncated_records`（多少数据装不下）、
`grad_norm[{epoch, steps, mean, max, clipped_steps}]`（剪辑前的梯度范数）、`step_seconds`（节奏曲线）。
全权重 run 还会写 `<out>/resume`（fp32 masters + moments + scheduler + RNG + 数据位置）与 `<out>-snapshots/step-0000389/checkpoint`。

**(6) 发布配方（背下来，因为所有对比都仍它）。**

```bash
# 4B / 9B
uv run python -m kev.train --suite evals/v7/decision-v7 --base Qwen/Qwen3.5-4B-Base --base_revision <sha> \
    --epochs 2 --lr 5e-5 --batch 4 --accum 2 --dtype bf16 --checkpointing 1 --p_none_pair 0.25 --device cuda --out runs/kev-4b
# 0.8B 只改两个数：--lr 1e-4 --batch 8
# smoke（~1 分钟）：uv run python -m kev.train --n_per_source 40 --accum 4 --out runs/smoke
```

```html
<div style="font-family:monospace;background:#0d1117;color:#c9d1d9;padding:18px;border-radius:8px;overflow-x:auto">
<style>
@keyframes tflow { 0%{left:0;opacity:0} 6%{opacity:1} 46%{opacity:1} 54%{left:100%;opacity:0} 100%{left:100%;opacity:0} }
.tf{position:relative;padding:16px 0}
.tf-d{position:absolute;top:50%;margin-top:-6px;width:12px;height:12px;border-radius:50%;background:#3fb950;
  box-shadow:0 0 8px #3fb950;animation:tflow 3.8s linear infinite}
.tf-d.b{animation-delay:1.27s;background:#58a6ff;box-shadow:0 0 8px #58a6ff}
.tf-d.c{animation-delay:2.54s;background:#f0883e;box-shadow:0 0 8px #f0883e}
.tf-l{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:4px 8px;margin:0 4px;font-size:12px}
.tf-l b{color:#3fb950}
.tf-x{font-size:11px;color:#8b949e;margin-top:6px}
</style>
<div class="tf">
  <span class="tf-d"></span><span class="tf-d b"></span><span class="tf-d c"></span>
  <span class="tf-l">suite / data 的 <b>train 分区</b></span>→
  <span class="tf-l"><b>增强</b>（none / distract / none_pair / perm）</span>→
  <span class="tf-l">编成 <b>Variant</b>（带 permuted 兄弟）</span>→
  <span class="tf-l">计划：<b>length_sort / pass_tokens_max / row_budget</b></span>→
  <span class="tf-l">一次 <b>forward</b>（packed | rows | shared_prefix）</span>→
  <span class="tf-l">PointerHead → <b>逐题 loss</b></span>→
  <span class="tf-l">CE(+RPS) + <b>perm_kl</b> + <b>anchor</b></span>→
  <span class="tf-l">accum 个 micro-batch → <b>optimizer step</b></span>→
  <span class="tf-l"><b>adapter + head.pt + metrics</b></span>
</div>
<div class="tf-x">每步只累梯度、每 accum 步才更新；<code>training_metrics.json</code> 里的 <code>clipped_steps</code> 就是这条管道上“梯度到底多大”的实录。</div>
</div>
```

### 13.3 示例代码

> 依赖：🟢 前两个块只需 `torch + kev.train` 的纯函数，**不下载基座、不需 GPU**（均已实测）。

```python
# ▶ 损失装配：四种分支 + 两个形状不变量损失
import random, torch
from kev.train import anchor_loss, permuted_copy, permutation_kl, question_loss

dev = torch.device("cpu")
z = torch.tensor([2.0, 0.5, -1.0])
print("硬标签 CE :", round(float(question_loss(z, {"qtype": "choice", "label": 0}, dev, 0.0)), 5))
print("软目标 CE :", round(float(question_loss(z, {"qtype": "choice", "label": 0, "target": [0.7, 0.2, 0.1]}, dev, 0.0)), 5))
print("score CE :", round(float(question_loss(z, {"qtype": "score", "label": 2}, dev, 0.0)), 5),
      "| +RPS:", round(float(question_loss(z, {"qtype": "score", "label": 2}, dev, 1.0)), 5))
try:
    question_loss(z, {"qtype": "choice", "label": 0}, dev, 0.0, label_smoothing=0.1, brier_w=0.1)
except ValueError as e:
    print("修正项互斥 →", e)

rec = {"state": "S", "questions": [{"qtype": "choice", "options": ["a", "b", "c"], "label": 0},
                                   {"qtype": "noul", "options": ["no", "yes"], "label": 1}]}
perm_rec, perms = permuted_copy(rec, random.Random(0))
print("重排后选项:", [q["options"] for q in perm_rec["questions"]], "| perms:", perms, "（noul 不参与）")
z1 = torch.tensor([2.0, 0.5, -1.0])
z2 = torch.tensor([2.0, -1.0, 0.5])                 # 同一预测在新顺序下的位置（perms[0] = [0, 2, 1]）
print("同一预测的 perm_kl:", round(float(permutation_kl(z1, z2, perms[0], dev)), 10))    # → 0.0
print("真改了顺序的 perm_kl:", round(float(permutation_kl(z1, torch.tensor([0.5, 2.0, -1.0]), perms[0], dev)), 5))

q = {"qtype": "choice", "label": 0, "keys": ["a", "b", "c"]}
print("锚定 KL:", round(float(anchor_loss(z1, q, {"a": .8, "b": .1, "c": .1}, dev)), 5),
      "| 选项集不等时：", anchor_loss(z1, {**q, "keys": [*q["keys"], "none_of_these"]}, {"a": .8, "b": .1, "c": .1}, dev))
```

```python
# ▶ 预算与长度平衡：一次 pass 吃多少 token，length_sort 在干什么
from kev.train import balanced_runs, pass_tokens

shapes = [(1000, [120, 140, 130]), (900, [110, 105])]        # (state token, 每题分支 token)
print("行形式 pass_tokens  :", pass_tokens(shapes, shared=False))   # → 5700（5 行 × 最长行 1140）
print("共享前缀 pass_tokens:", pass_tokens(shapes, shared=True))    # → 2700（state 只算一次）
print("→ 这就是 --shared_prefix 在长 state 多问题上的全部优势")

items = list(range(1, 9))                                    # 8 条 record 的“成本”
print("不排序直接切三段:", [items[i:i + 3] for i in (0, 3, 6)])
print("balanced_runs   :", balanced_runs(items, 3, sum))     # 连续段，最贵的那段尽量便宜
```

```python
# ▶ 跑一个 smoke（~1 分钟，会下载默认基座），然后读它的产物
# ▶ 🟡 需网络；🟢 不需 GPU：--device cpu 就能跑完
#    uv run python -m kev.train --n_per_source 40 --accum 4 --out runs/smoke --device cpu
import json
from pathlib import Path
import torch

out = Path("runs/smoke")
print("目录内容:", sorted(p.name for p in out.iterdir()))
head = torch.load(out / "head.pt", map_location="cpu", weights_only=False)
print("出厂温度 head.pt['temperature'] =", head["temperature"], "| weights =", head["weights"])
print("基座:", head["base"], "| lora r =", head["lora"], "| head_dim =", head["head_dim"])
print("head 参数:", list(head["head"]))
m = json.loads((out / "training_metrics.json").read_text(encoding="utf-8"))
for k in ("wall_seconds", "records_seen", "requested_records", "rejected_records", "truncated_records",
          "optimizer_steps", "forward_tokens", "grad_norm", "weights", "device", "dtype"):
    print(f"  {k:20s} {m.get(k)}")
cfg = json.loads((out / "training_config.json").read_text(encoding="utf-8"))
print("完整 args 回写在 training_config.json：", len(cfg["args"]), "个旋钮")
```

### 13.4 常见陷阱

- **同时给两个损失修正项**：`question_loss` 直接报错——这是护栏，不是 bug。
- **对 noul / 2 选项题指望 `--perm_kl`**：`permuted_copy` 不重排它们（`perms` 里是 `None`），这个损失只作用于 K ≥ 3 的 choice。
- **以为 anchor 会对“加了 none 的题”说话**：不会，选项集不等时 `anchor_loss` 返回 `None` 跳过。
- **同时跑两个训练进程**：`AGENTS.md` 明写“Only one training process at a time”——两个在 MPS 上会互相拖慢 ~10×。
- **`--dtype bf16` 当成“权重也是 bf16”**：`--dtype` 是 autocast，`--weights_dtype` 才是冻结基座权重的 dtype（35B-A3B 的 fused MoE experts 强制 bf16）。
- **混用互斥的计划旋钮**：`--row_budget` 不能与 `--perm_kl` / `--anchor_w` 同用；`--pass_tokens_max` 需要 `--length_sort 1` 且不能与 `--row_budget` / `--perm_kl` 同用；两者都要求 hybrid 基座走行形式。
- **改了基座不记 revision**：`--base_revision` 必须钉住（套件 manifest 没钉这个基座时由你钉），否则 provenance 不可复现。
- **在 CPU/MPS 上试 `--full_ft`**：全权重路径为多卡与 H200 尺寸而设（需 torch >= 2.8）；入门阶段先拿 LoRA smoke 跑通管道。

**关键结论**：训练框架里真正难的部分不是优化器，而是**计划**：一条 record 会派生出多少变体、一次 pass 到底吃多少 token、
一步能付得起多少。把 `pass_tokens` / `plan_shapes` / `row_passes` 这三个函数读懂，`--length_sort` / `--pass_tokens_max` /
`--row_budget` 就不再是一堆陌生开关，而是三种互相排斥的预算语言。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](12-frozen-suites.md) · [下一章 →](14-serving.md)

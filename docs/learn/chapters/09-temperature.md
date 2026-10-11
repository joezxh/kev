# 9. 温度校准（temperature scaling）

> 《Kev 基础知识系统学习指南》· 第二部分 进阶篇
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](08-row-form.md) · [下一章 →](10-metrics.md)

---


### 9.1 概念定义

- **温度 T**：`p = softmax(z / T)`。**单调变换 logits，argmax 不变 → accuracy 不变，但 NLL / ECE / Brier / AURC 全变**。
- **拟合目标**：在网格 `0.25 .. 4` 上找使**平均 NLL 最小**的 T。`fit_temperature(rows, aggregation="macro", points=81)`；
  发布 checkpoint 与工作负载拟合用 `TEMPERATURE_FIT = {"aggregation": "micro", "points": 121}`（121 点格）。
  `macro` 每题权重相等（按 task 归一），`micro` 每题同权。
- **三个 T 的名字**（新手最容易混淆）：

| 名称 | 是什么 | 存在哪 |
|---|---|---|
| `shipped` | checkpoint 出厂自带的温度 | `head.pt["temperature"]`，`read_meta(...).temperature` |
| `workload` | 在**某批工作数据**上重新拟合的 T | `kev.calibrate` 的报告、rounds 的 `temperature` pool |
| `raw` | T=1，即未校准 | `KEV_TEMPERATURE=1` / `LoadOptions(temperature=1.0)` |

### 9.2 原理讲解：四臂对照与"in-sample 乐观"

[`kev/calibrate.py:workload_report()`](../../../kev/calibrate.py) 只报告不改模型，比较四臂：
`raw` / `shipped` / `workload`（同一批行内样本拟合）/ `workload_oof`（**组间不相交**的 out-of-fold）。
关键在最后一臂：[`grouped_folds()`](../../../kev/metrics.py) 按 `(source, group)` 分折，同一 record 的兄弟问题
与变体**永不跨折**；每折的温度在其余折拟合，只用于本折评分。这才能回答"拟合本身有没有泄漏"。

> **为什么必跟这一臂？历史事故（AGENTS.md / rounds.py docstring）**：round 19 把 SFT arm 的温度拟合在
> `sft-v1` 的开发行上——那是训练数据源的留出**条目（items）**，同分布。结果 T=0.955、breadth-v1 ECE 0.059（看起来很好）；
> round 20 改用留出**数据集（datasets）**的池，同一个 checkpoint 得到 0.0085。两者差近 7 倍，而前者是自欺。

由此固化下来的护栏：

- `kev/rounds.py:POOL_REQUIRED_FROM = 21`：从第 21 轮起，**任何受温度影响的判据（除 accuracy 外）没注册 `temperature` 池，`validate`/`launch` 直接拒绝这一轮**；
  ≤ 20 的已记录轮只告警，以保证它们的 spec 仍然验证得通。
- `kev.rounds.pool_conflicts(pooled, training)`：拒绝池与任何 arm 的训练数据共用（池化套件是 arm 的训练套件/其 manifest 命名的组件/plan 的 data 套件；
  池了 arm 训过的 source；读了任何可训语料的 `calibration`/`development` 分区）。
- 每个 arm 的读数记 `temperature_source`（池及其问题数，或它自己的开发行及套件），父节点记 `parent_temperature_source`；
  表格在 arm 被训练语料的行服务时打 `!!!`。`SHIPPED_TOLERANCE = 0.05`：父节点被服务的 T 与它 shipped 的 T 差过 0.05 就警告（仅报告）。
- 拟合需要 **raw logits**：`fit_temperature` 对 `inference_temperature != 1.0` 的行直接报错；`raw_row()` 负正回归（`z = logits × T`）。
  所以 `kev.calibrate` 拒绝没有记录 `logits` 与 `inference_temperature` 的行（**远程端点的预测就是这类行**）。

<div style="font-family:monospace;background:#0d1117;color:#c9d1d9;padding:18px;border-radius:8px;overflow-x:auto">
<style>
@keyframes ktmp { 0%{left:0;opacity:0} 10%{opacity:1} 86%{opacity:1} 100%{left:520px;opacity:0} }
.tp{position:relative;height:74px;padding:18px 0}
.tp-p{position:absolute;top:32px;width:11px;height:11px;border-radius:50%;background:#f0883e;
  box-shadow:0 0 9px #f0883e;animation:ktmp 3.4s linear infinite}
.tp-p.b{animation-delay:1.7s;background:#d2a8ff;box-shadow:0 0 9px #d2a8ff}
.tp-l{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:4px 8px;margin:0 3px;font-size:12px}
.tp-l b{color:#f0883e}
.tp-x{color:#f85149;font-size:12px}
</style>
<div class="tp">
  <span class="tp-p"></span><span class="tp-p b"></span>
  <span class="tp-l">development 行（<b>非训练语料</b>）</span>→
  <span class="tp-l">raw_row → <b>z</b></span>→
  <span class="tp-l">121 点网格上扫 <b>mean NLL</b></span>→
  <span class="tp-l">argmin → <b>T</b></span>→
  <span class="tp-l">写 head.pt / 记 <b>temperature_source</b></span>→
  <span class="tp-l">OOF 复验（<b>组间不相交</b>）</span>
</div>
<div class="tp-x">✗ 被拒绝的回路：拟合行来自 arm 的训练语料（pool_conflicts / POOL_REQUIRED_FROM）</div>
</div>

### 9.3 示例代码

> 依赖：🟢 纯 numpy + `kev.metrics`，不需要 checkpoint 与 GPU。我们**人造一个过度自信的系统**。

```python
# ▶ 拟合温度：它只改形状，不改判定
import numpy as np
from kev.metrics import TEMPERATURE_FIT, ece, fit_temperature, metrics, raw_row, scored_rows, tempered_row

rng = np.random.default_rng(0)
def make_rows(n, scale, acc_rate):
    rows = []
    for i in range(n):
        y = int(rng.random() < acc_rate)                      # 真实答案
        z = np.array([-1.5, 1.5]) * (1 if y else -1) * scale  # scale 越大越自信
        z = z + rng.normal(0, 0.6, 2)
        p = np.exp(z - z.max()); p = p / p.sum()
        rows.append({"id": f"r{i}", "group": f"r{i}", "question": "q", "source": "synth", "task": "synth",
                     "type": "choice", "variant": "clean", "keys": ["a", "b"], "label": int(p.argmax()),
                     "p": p.tolist(), "logits": z.tolist(), "inference_temperature": 1.0})
    return rows

# 造一批"准确率 0.78、但自信到 0.95"的行（label 由 p 定，故意先造一个错位的版本）
rows = make_rows(400, scale=2.5, acc_rate=0.78)
for r in rows:
    if rng.random() < 0.22:                                   # 把 22% 的行翻到错的一侧：模型过自信
        r["label"] = 1 - r["label"]

raw = metrics(scored_rows(rows))
T = fit_temperature(rows, **TEMPERATURE_FIT)
fit = metrics([tempered_row(r, T) for r in scored_rows(rows)])
print(f"T = {T:.3f}（过自信 → T > 1）")
print("acc 不变:", round(raw["acc"], 4) == round(fit["acc"], 4))
print(f"ECE {raw['ece']:.4f} → {fit['ece']:.4f}   Brier {raw['brier']:.4f} → {fit['brier']:.4f}   NLL {raw['nll']:.4f} → {fit['nll']:.4f}")
print("mean_conf", round(raw["mean_conf"], 3), "→", round(fit["mean_conf"], 3), "| confidence_bias", round(raw["confidence_bias"], 3), "→", round(fit["confidence_bias"], 3))
```

```python
# ▶ in-sample 乐观：同一批行内样本拟合 vs 组间不相交的 out-of-fold
from kev.metrics import out_of_fold_rows, metrics, scored_rows, fit_temperature

oof_rows, fold_Ts = out_of_fold_rows(scored_rows(rows), folds=5, seed=0, **TEMPERATURE_FIT)
in, out = metrics(scored_rows(rows)), metrics(oof_rows)
print("in-sample 拟合后的 ECE:", round(in["ece"], 4), "| OOF 的 ECE:", round(out["ece"], 4))
print("每折温度:", [round(t, 3) for t in fold_Ts])   # 折与折之间会飘——这就是 rounds 记 temperature_ci 的理由
# kev.cross_validated_temperature(rows) 把上面这一切包成一个报告，并给出 raw / oof / delta 的 95% 区间（是否分离）
```

### 9.4 常见陷阱

- **`KEV_TEMPERATURE=1` 以为"更保守"**：它返回的是 **raw** 概率，不是更保守的校准概率；对比数字前先确认两边都是 served-vs-served。
- **用远程端点的 rows 拟合温度**：远程行没 logits，`kev.calibrate` 会拒（拟合相对的是服务侧概率，不是 checkpoint 的 raw logits）。
- **拿 accuracy 当"温度相同时才可比"的指标**：accuracy 对温度天然不变；变的永远是 Brier/ECE/NLL/AURC/coverage。
- **以为 T 能救回错的 top-1**：单调变换不改序；校准只修"置信度与频率对不上"，不修"答错"。

**关键结论**：温度是 Kev 唯一的"推理期旋钮"，也是**最容易产生幻觉的变量**。判断一个校准数字是否可信，只问一句：
它拟合在哪些行上？——`temperature_source` 字段就是这句问语的机器可读版本。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](08-row-form.md) · [下一章 →](10-metrics.md)

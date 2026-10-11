# 11. 统计比较：record-clustered paired bootstrap

> 《Kev 基础知识系统学习指南》· 第二部分 进阶篇
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](10-metrics.md) · [下一章 →](12-frozen-suites.md)

---


### 11.1 概念定义

> **record-clustered paired bootstrap = 把"同一原始 record 产生的所有行"当作一个不可拆分的抽样单位，同配对地重抽样，
> 每次重抽样里把目标统计量整体重算一遍，取 2.5% / 97.5% 分位数作为 95% 区间。**

三个关键词各对应一个必须处理的真实问题：

| 关键词 | 解决什么问题 | 仓库里的实现 |
|---|---|---|
| **paired** | 两个 checkpoint 读的是同一批题，题难度是共同方差源；配对后只留"模型差异" | `paired_bootstrap(candidate, reference, ...)` 要求两边的 `(id, question)` 集合完全相等 |
| **record-clustered** | 一个 record 的兄弟题/none 变体高度相关，当独立样本会虚增 n、区间假装很窄 | `_source_groups()` + `cluster_resamples()`：单位是 `(source, group)` |
| **percentile / full statistic** | `ece / aurc / coverage_at_*` 不是均值，不能对子集均值再组合 | 每次重抽样里 `statistic(indices, data)` 整体重算 |

📖 [`kev/metrics.py:paired_bootstrap()`](../../../kev/metrics.py)，上层入口是
[`kev.compare`](../../../kev/compare.py)（两个结果目录）与 [`kev/rounds.py:paired()`](../../../kev/rounds.py)（rounds 的注册读法）。

### 11.2 原理讲解：逐行拆开这个函数

**(1) 配对索引与拒绝条件。** 先把两侧各过 `scored_rows()`，建 `(id, question) -> row` 的索引，然后四道检查（碰任何一道直接报错）：

- `duplicate paired example`：同一 `(id, question)` 出现两次（devtools 的 CodeReviewer 就有这种重复 id，见第 12 章）；
- `paired comparison requires identical complete clean examples`：两侧键集合不相等（一侧漏读了题）；
- `paired comparison labels or option order differ`：`keys` 或 `label` 不一致（选项顺序变了 = 不同题）；
- `paired comparison group or task metadata differ`：`source / group / task / type` 任一不同（分组变了不能配对）。

**(2) 重抽样单位。** `_source_groups(rows)` 返回 `{source: [每个 (source, group) 的下标数组]}`；`cluster_resamples()` 在**每个 source 内部**
有放回地抽整个 cluster（`size = len(grouped)`），然后拼接。所以：同 record 的兄弟题与变体永远同进同出，
而 source 之间是按层拉齐（每个 source 自己的 cluster 数不变）。`unit` 字段就把这句话写进了结果：
`"source-stratified original record; sibling questions stay together"`。

**(3) micro vs macro。** `aggregation="micro"`：一次重抽样里 candidate - reference 算一个差；
`"macro"`：先按 `task` 拆，每个 task 内部算差，再对 task 取均值（题量不均衡时 macro 不让大赛题主导）。
默认参数是 `macro`，但 **rounds 的注册读法固定用 `micro`**（`kev.rounds.paired`）。

**(4) 返回形状。**

```json
{"micro_nll_delta": -0.041, "ci95": [-0.062, -0.019], "samples": 1000,
 "groups": 1487, "aggregation": "micro", "unit": "...", "method": "paired cluster percentile bootstrap; full statistic recomputed in each resample"}
```

键名是 `f"{aggregation}_{metric}_delta"`；`groups` 是 cluster 总数（**真正的样本量不是行数，而是这个数**）。
判读只问一句：`ci95` 是否跨 0。

**(5) 两个上层入口的差异（容易记错）。**

- `kev.compare --candidate <dir> --reference <dir> --out <file>`：**要求两侧 `report.json` 的 `suite_sha256` 完全相等**
  （否则 `comparison requires matching frozen-suite hashes`），默认 `samples=1000`、`aggregation=macro`，只测 `nll / acc / brier`；
  额外产出 `nll_floor_sensitivity`（在 `1e-3 / 1e-6 / 1e-9` 三个下限下重算 macro NLL：没 logits 的行 NLL 依赖下限）与
  `none_of_the_above` 诊断（`none_present / none_absent` 各自的 `mean_p_none`、`p_none_above_half`，**无观测时是 `None` 而不是 0**）。
- `kev.rounds.paired(candidate, reference, metric)`：`SAMPLES = 2000`（round 5 以来的注册值）、`seed = 0`、`micro`，
  只返 `{"delta", "ci95"}`。rounds 的判据（criterion）读的就是这两个数，例如 `long.ece_16k_plus.candidate <= 0.05` 与配对下界。

**(6) 另一件同样重抽样纪律的事：折。** `grouped_folds()` 也按 `(source, group)` 分折（同一 record 永不跨折），
并在每个 source 内 round-robin，保证每一折都看到每个 source。`out_of_fold_rows` / `cross_validated_temperature`（第 9 章）就建在它上面；
后者返 `separated`（配对 delta 的 95% 区间是否排除 0），这是"OOF 重写到底有没有真提升"的同一个判读语法。

<div style="font-family:monospace;background:#0d1117;color:#c9d1d9;padding:18px;border-radius:8px;overflow-x:auto">
<style>
@keyframes clu { 0%{transform:translateX(0);opacity:0} 10%{opacity:1} 40%{transform:translateX(150px)}
  60%{transform:translateX(150px)} 90%{opacity:1} 100%{transform:translateX(300px);opacity:0} }
@keyframes bad { 0%,100%{opacity:.25} 45%{opacity:1;box-shadow:0 0 10px #f85149} }
.cw{position:relative;height:150px;margin:10px 0}
.cr{position:absolute;height:16px;border-radius:4px;font-size:11px;line-height:16px;padding:0 6px;white-space:nowrap;color:#0d1117}
.cg1{background:#3fb950}.cg2{background:#58a6ff}.cg3{background:#d2a8ff}.cg4{background:#f0883e}
.cb{animation:clu 4.2s linear infinite}
.ci{animation:bad 2.1s ease-in-out infinite;border:1px dashed #f85149;background:transparent!important;color:#f85149}
.cl{font-size:11px;color:#8b949e}
</style>
<div style="font-size:12px;color:#58a6ff">▍上：以 (source, group) 为整块被重抽样（正确）——同 record 的兄弟题与变体同进同出</div>
<div class="cw">
  <span class="cr cg1 cb" style="top:6px;width:120px">rec-A · q1</span>
  <span class="cr cg1 cb" style="top:26px;width:150px;animation-delay:.05s">rec-A · q2</span>
  <span class="cr cg1 cb" style="top:46px;width:170px;animation-delay:.1s">rec-A · none_present</span>
  <span class="cr cg2 cb" style="top:72px;width:110px;animation-delay:.6s">rec-B · q1</span>
  <span class="cr cg2 cb" style="top:92px;width:130px;animation-delay:.65s">rec-B · q1</span>
  <span class="cr cg3 cb" style="top:118px;width:120px;animation-delay:1.3s">rec-C · q1</span>
</div>
<div style="font-size:12px;color:#58a6ff">▍下：行当独立样本（错误）——抽中一个变体却丢掉它的兄弟，n 虚增、区间假窄</div>
<div class="cw" style="height:60px">
  <span class="cr cg1 ci" style="top:8px;width:120px">rec-A · q1</span>
  <span class="cr" style="top:8px;left:170px;width:120px;background:#161b22;border:1px solid #30363d;color:#8b949e">rec-A · q2 漏</span>
  <span class="cr cg2 ci" style="top:32px;width:150px;animation-delay:.4s">rec-B · q1（重复两次）</span>
  <span class="cr" style="top:32px;left:350px;width:170px;background:#161b22;border:1px solid #30363d;color:#8b949e">rec-A · none_* 漏</span>
</div>
<div class="cl">一次重抽样 → 整批行重算 ece/aurc/coverage（非线性）或取均值（加性）→ 2000 个 delta → 取 2.5%/97.5% 分位</div>
</div>

### 11.3 示例代码

> 依赖：🟢 纯 numpy + `kev.metrics`，不需要 GPU。自己造一份"有聚类结构"的配对数据，看清楚不聚类会错多少。

```python
# ▶ 聚类 vs 独立：同一份数据，两种抽样单位算出的区间宽度完全不同（已实测跑通）
import numpy as np
from kev.metrics import cluster_resamples, paired_bootstrap, scored_rows

rng = np.random.default_rng(0)
N_REC, N_Q = 240, 3
labels = rng.integers(0, 2, N_REC)                    # 每个 record 的金标，两侧共用（配对前提）

def build(p_hit):
    """一个 record 只抽一次“对不对”，它的 3 道兄弟题以完全相关（组内相关 = 1）。"""
    rows = []
    for r in range(N_REC):
        ok = rng.random() < p_hit
        y = int(labels[r])
        for q in range(N_Q):
            z = np.array([1.4, -1.4]) if ok else np.array([-1.4, 1.4])
            z = z if y == 0 else z[::-1]                # 把“对”的一侧对齐到金标
            z = z + rng.normal(0, .1, 2)
            p = np.exp(z - z.max()); p = p / p.sum()
            rows.append({"id": f"rec{r}", "group": f"rec{r}", "question": f"q{q}", "source": "synth",
                         "task": "synth", "type": "choice", "variant": "clean", "keys": ["a", "b"],
                         "label": y, "p": p.tolist(), "logits": z.tolist(), "inference_temperature": 1.0})
    return rows

cand, refs = build(0.80), build(0.55)
res = paired_bootstrap(cand, refs, samples=2000, seed=0, metric="acc", aggregation="micro")
print("delta", round(res["micro_acc_delta"], 4), "| ci95", [round(v, 4) for v in res["ci95"]])
print("groups（真正的样本量）", res["groups"], "| 行数", len(cand), "| unit", res["unit"])
# → delta 0.2333  ci95 [0.1542, 0.3083]  groups 240  rows 720

# 把它当独立样本算（错法）：同一个均差的 95% 半宽会小得多
d = np.array([float(np.argmax(r["p"]) == r["label"]) for r in cand]) - \
    np.array([float(np.argmax(r["p"]) == r["label"]) for r in refs])
iid_half = d.std(ddof=1) / np.sqrt(len(d)) * 1.96
clu = np.array([d[drawn].mean() for drawn in cluster_resamples(scored_rows(cand), 2000, 0)])
clu_half = (np.quantile(clu, .975) - np.quantile(clu, .025)) / 2
print(f"iid 半宽 {iid_half:.4f}  vs  聚类半宽 {clu_half:.4f}（宽了 {clu_half / iid_half:.2f}×）")
# → 实测 iid 0.0450 vs 聚类 0.0751：把 720 行当独立样本，直接把区间算窄 40%

# 非线性指标：ece 在每次重抽样里整体重算，方法字段就把这句话写进了结果
ece = paired_bootstrap(cand, refs, samples=2000, seed=0, metric="ece", aggregation="micro")
print("ece delta", round(ece["micro_ece_delta"], 4), "ci95", [round(v, 4) for v in ece["ci95"]], "|", ece["method"])
# → ece delta -0.2338  ci95 [-0.3092, -0.1545]

# macro vs micro：同一批数据，两个名字不同、值也不同（键名里带聚合名就是为了防混用）
mac = paired_bootstrap(cand, refs, samples=500, seed=0, metric="nll", aggregation="macro")
print("macro_nll_delta", round(mac["macro_nll_delta"], 4))
```

```python
# ▶ 配对比较的四道拒绝条件：亲眼看它什么时候报错
missing = [r for r in cand if r["question"] != "q2"]              # 一侧漏读：键集合不等
flipped = [{**r, "label": 1 - r["label"]} for r in refs]          # 金标不一致
newmeta = [{**r, "group": r["group"] + "x"} for r in refs]        # 聚类元数据不一致
for name, other in (("漏行", missing), ("金标不同", flipped), ("group 不同", newmeta)):
    try:
        paired_bootstrap(cand, other, samples=8, metric="acc")
        print(name, "→ 没报错")
    except ValueError as e:
        print(f"{name} → {e}")
# 漏行 → paired comparison requires identical complete clean examples
# 金标不同 → paired comparison labels or option order differ
# group 不同 → paired comparison group or task metadata differ
```

```python
# ▶ 真数据：kev.compare 要求两侧 report.json 的 suite_sha256 相等（否则直接拒绝，这是护栏不是 bug）
# ▶ 🟢 纯 CPU、不下载任何 checkpoint：先跑下面这条命令写出 runs/compare-demo.json
#    uv run python -m kev.compare --candidate runs/breadth-v1-kev-27b --reference runs/breadth-v1-kev-4b \\
#        --out runs/compare-demo.json
import json
from pathlib import Path

diff = json.loads(Path("runs/compare-demo.json").read_text(encoding="utf-8"))
print("suite_sha256（两侧必须相等）:", diff["suite_sha256"][:16])
for metric, block in diff["paired"].items():                      # 默认只测 nll / acc / brier
    key = f"{block['aggregation']}_{metric}_delta"
    lo, hi = block["ci95"]
    print(f"  {key} = {block[key]:+.4f}  ci95 [{lo:+.4f}, {hi:+.4f}]  "
          f"samples={block['samples']}  groups={block['groups']}")
print("NLL 下限敏感性（没 logits 的行依赖它）:", diff["nll_floor_sensitivity"])
print("none 诊断:", json.dumps(diff["none_of_the_above"]["candidate"], ensure_ascii=False))
# 实测（breadth-v1，27B vs 4B）：macro_nll_delta -0.1125 ci [-0.1323, -0.0917]，
#                  macro_acc_delta +0.0450 ci [+0.0296, +0.0613]，groups 1924（不是行数 3075）
```

### 11.4 常见陷阱

- **拿 `n`（行数）当样本量**：有效样本量是 `groups`。一个 144 个 record、每题 500 行的面板，区间宽度由 144 个聚类决定。
- **以为 `samples` 越大越准**：`samples` 只控制 Monte-Carlo 噪声，不控制数据本身的量；rounds 定在 2000 已足够稳定。**固定 `seed=0` 是为了可复现**，不是随便选的。
- **micro / macro 混用**：`kev.compare` 默认 macro，`kev.rounds.paired` 强制 micro。两者键名不同（`macro_nll_delta` ≠ `micro_nll_delta`），不允许直接横向比较。
- **区间跨 0 就写"没差异"**：它只表示"这个量、这个样本量下分不出"；先看 `groups` 够不够，再看能不能换一个更敏感的非线性指标。
- **不同 `suite_sha256` 强行比**：`kev.compare` 直接拒绝，是对的。套件变了就不是配对比较。
- **对 ece 的区间对称性有期待**：ece 非负，candidate 与 reference 都很准时区间会右偏。

**关键结论**：本仓库里"两个 checkpoint 谁更好"只允许三种说法：同一冻结套件（`suite_sha256` 相等）、
同一温度口径（`served_at` / `temperature_source` 对齐）、**以 `(source, group)` 为单位的配对 bootstrap 区间不跨 0**。
其余都是噪声。rounds 的 criterion 就按这三条写，所以读 spec 时看到 `paired` / `ci95` / `pool` 就知道它们在堵哪个漏洞。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](10-metrics.md) · [下一章 →](12-frozen-suites.md)

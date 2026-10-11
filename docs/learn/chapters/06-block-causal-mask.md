# 6. block-causal mask 与分支隔离

> 《Kev 基础知识系统学习指南》· 第二部分 进阶篇
>
> **本部分目标**：掌握 Kev 特有的六个概念——分支隔离、指针读出、行形式、温度、指标族、聚类 bootstrap、冻结套件。 读完才能读懂 `shared_prefix` / `fused_qwen35` / `rounds` 这些“看起来过度设计”的代码为什么必须存在。
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](05-record.md) · [下一章 →](07-pointer-head.md)

---


### 6.1 概念定义

`encode()` 给每个 token 打一个**段号 `seg`**：state 段是 `0`，第 k 个问题分支是 `k`。
[`branch_mask()`](../../../kev/model.py) 的规则一行写完：

> `attend(i, j) ⇔ j ≤ i 且（seg[j] == 0 或 seg[j] == seg[i]）`

即：**因果（不看未来）+ 只能看共享 state 或自己那条分支**。三个配套字段：

| 字段 | 含义 |
|---|---|
| `seg` | 段号（分支隔离的依据） |
| `pos` | position ids：分支从 state 末尾续排（RoPE 按 position，不按数组下标） |
| `opt` | 每个 token 属于其分支内第几个选项：`OPT_NONE(-1)` 结构/指令、`0..K-1` 选项 span、`OPT_DECIDE(-2)` |

`branch_mask_batch(segs, device, dtype, opts=None, length=None)` 返回**加性掩码 `[B,1,L,L]`**（右填充到最长序列）。

### 6.2 原理讲解：填充与 `-inf` 的两个细节

1. **padded key 对所有 query 屏蔽**；**padded query 行保留对角线**——否则整行都被屏蔽，softmax 出 NaN。
2. 用 `torch.finfo(dtype).min` 而不是 `-inf`：`-inf` 参与后续减/乘会变成 NaN，`finfo.min` 保证 softmax 两侧都有限。
3. `option_isolation=True` 时 `opts` 也进掩码：选项 token 的 key 只对**同选项**的 query 开放，`<decide>` 看全分支——于是逐选项表示与 `<decide>` 的注意力天然排列不变（仅 attention-only 骨干可用，见第 8 章）。

```
（seg 视图，✓=可读，·=被掩码；行= query i，列= key j）
            state(0)   分支1(1)   分支2(2)
  state      ✓✓✓        ···        ···      ← state 之间因果，看不见任何分支
  分支1      ✓✓✓        ✓··        ···      ← 分支1 读 state + 自己（因果）
  分支2      ✓✓✓        ···        ✓··
```

<div style="font-family:monospace;background:#0d1117;color:#c9d1d9;padding:18px;border-radius:8px;overflow-x:auto">
<style>
@keyframes kmb { 0%{transform:translateX(0);opacity:0} 15%{opacity:1} 85%{opacity:1} 100%{transform:translateX(330px);opacity:0} }
.km{position:relative;height:120px;margin-top:8px}
.km-row{position:absolute;left:0;width:110px;padding:6px 8px;border-radius:6px;font-size:12px;text-align:center}
.km-a{top:8px;background:#1e3a5f;border:1px solid #2f5a8f}
.km-b{top:52px;background:#2d4a2b;border:1px solid #3f7a3b}
.km-c{top:96px;background:#4a2d4a;border:1px solid #7a3f7a}
.km-track{position:absolute;left:126px;top:0;height:100%;width:360px;border-left:1px dashed #30363d}
.km-p{position:absolute;top:24px;width:10px;height:10px;border-radius:50%;background:#3fb950;
  box-shadow:0 0 8px #3fb950;animation:kmb 2.4s linear infinite}
.km-p.b{top:68px;background:#f0883e;box-shadow:0 0 8px #f0883e;animation-delay:1.2s}
.km-x{position:absolute;right:12px;top:44px;color:#f85149;font-size:13px}
.km-lbl{position:absolute;left:132px;font-size:11px;color:#8b949e}
</style>
<div class="km">
  <div class="km-row km-a">&lt;state&gt; s1 s2 s3<br/>seg=0</div>
  <div class="km-row km-b">q1 分支 &lt;decide&gt;<br/>seg=1</div>
  <div class="km-row km-c">q2 分支 &lt;decide&gt;<br/>seg=2</div>
  <div class="km-track">
    <span class="km-lbl" style="top:6px">↓ 两条分支并行地读同一个 state（一次前向）</span>
    <span class="km-p"></span><span class="km-p b"></span>
    <span class="km-x">兄弟分支 ✕ 互不可见</span>
  </div>
</div>
<div style="color:#8b949e;font-size:12px">绿色/橙色粒子 = 分支的注意力请求；它们能穿过左边界读 state，永远到不了另一条分支</div>
</div>

📖 `kev/model.py:encode()`、`branch_mask()`、`branch_mask_batch()`、`OPT_NONE/OPT_DECIDE`。
测试对照：`tests/test_unit.py`（"option1 never sees option0"那段断言）、`tests/test_model.py::test_rows_match_packed`。

### 6.3 示例代码

```python
# ▶ 🟢 纯 torch：自己实现块因果掩码，直观理解"加性掩码 + 段号"
import torch

def block_causal(seg):
    """seg: list[int]，0=state，k=问题分支。-> [L,L] bool（True=允许 attend）"""
    L = len(seg)
    ok = torch.zeros(L, L, dtype=torch.bool)
    for i in range(L):                      # 因果：只看 j <= i
        for j in range(i + 1):
            if seg[j] == 0 or seg[j] == seg[i]:
                ok[i, j] = True
    return ok

seg = [0, 0, 0,               # state
       1, 1, 1,               # 问题1：指令 + 一个选项
       2, 2]                  # 问题2
m = block_causal(seg)
print(m.int())
# 分支1（行 3-5）能看 state 三列 + 自己那一段，看不到行 6-7；反之亦然
```

```python
# ▶ 🟢 用 Kev 的实现（只需 torch + kev，不需要 tokenizer）
from kev.model import branch_mask_batch

m = branch_mask_batch([seg], "cpu")          # [1,1,L,L] 加性掩码：0=允许，finfo.min=屏蔽
allowed = m[0, 0] == 0
print("兄弟分支是否互通:", bool(allowed[3, 6] or allowed[6, 3]))   # → False
print("分支能否读 state:", bool(allowed[3, 0] and allowed[6, 2]))  # → True
print("对角线是否自留(含填充位):", bool(allowed.diagonal().all()))   # → True，防整行被掩空
```

```python
# ▶ 🟢 隔离性实验：把问题1的选项文字改掉，问题2的 logits 必须逐 bit 不变
#    （这正是 report.json 里 `isolation` 读数在真实 checkpoint 上做的事）
import torch
from kev.model import encode, load_tokenizer

tok = load_tokenizer("Qwen/Qwen2.5-0.5B")
base = {"state": "客户被重复扣款", "questions": [
    {"instr": "归口？", "options": ["账务", "物流"], "label": 0},
    {"instr": "负面？", "options": ["否", "是"], "label": 1}]}
moved = {"state": base["state"], "questions": [base["questions"][0],
         {**base["questions"][1], "instr": "这是一条完全不同的问题"}]}
e1, e2 = encode(tok, base, strict=False), encode(tok, moved, strict=False)
# 只比较第二段之后的 seg/pos 结构：分支互不依赖，改动不外溢
print("分支数不变:", max(e1["seg"]) == max(e2["seg"]), "| state 段长度不变:", e1["seg"].count(0) == e2["seg"].count(0))
```

### 6.4 与 Kev 的对应 / 陷阱

| 你可能以为 | 实际 |
|---|---|
| packed 掩码天然排列不变 | 默认 packing 下选项 2 能看选项 1；排列不变要 `option_isolation=True`（且它只让**表示**不变，README Limitations 仍提醒：真实 checkpoint 的选项顺序可能改变答案） |
| 掩码是 `bool` 矩阵 | HF 侧要**加性浮点**掩码：`branch_mask_batch` 输出 `0 / finfo.min`，dtype 跟随骨干 |
| 分支隔离 = 参数隔离 | 只是注意力可见性隔离；权重完全共享，所以一次前向能并行 Q 个问题 |
| 混合骨干也能跑 packed | **不能**，见第 8 章；`DecisionModel.__init__` 会拒绝 `hybrid + option_isolation` |

**关键结论**：block-causal mask 是 Kev 的"一次前向、多问不串味"的全部机制；它的正确性由两条独立检验守住：
`permutation`（换序稳不稳，进 `report.json`）与 `isolation`（分支互不影响，`kev.experiment:mechanism_checks()`
用 `ISOLATION_PROBE` 探兄弟问题会不会泄入，阈值 `GATES["isolation_tolerance"] = 0.001`）。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](05-record.md) · [下一章 →](07-pointer-head.md)

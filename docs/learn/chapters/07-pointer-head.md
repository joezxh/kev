# 7. PointerHead：prefill-only 的指针读出

> 《Kev 基础知识系统学习指南》· 第二部分 进阶篇
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](06-block-causal-mask.md) · [下一章 →](08-row-form.md)

---


### 7.1 概念定义

[`PointerHead`](../../../kev/model.py) 是模型唯一的"输出层"，只有两个线性投影：

\[ z_k \;=\; \frac{1}{\sqrt{dp}}\; \big(W_k\,h^{opt}_k\big)^{\top}\big(W_q\,h^{decide}\big), \qquad p = \mathrm{softmax}(z / T) \]

- `h_decide`：`<decide>` token 的隐向量 → query（"现在要决定了"）；
- `h_opts[k]`：第 k 个选项**结束标记 `</opt>`** 的隐向量 → key（"第 k 个选项是这个样子"）；
- `dp`：指针维度，`head_dim`（默认 256，`--head_dim` 128/256/512/1024 是可调架构旋钮）；
- `T`：**校准温度**，只在 `eval` 且 `T != 1.0` 时参与除法；训练永远看 `T=1`。

> 为什么读 `</opt>` 而不是 `<decide>` 去预测下一个词？因为"选项"是变长的任意文本，词表里没有它的一席之地；
> 而 `</opt>` 的位置隐向量已经"读完整个选项并知道它结束了"——这正是指针式打分需要的 key。**这也是 `<opt>/</opt>` 边界 token 必须存在、且必须不可伪造的原因**（第 3 章）。

### 7.2 原理讲解

三个 API 面：

| 方法 | 场景 | 形状 |
|---|---|---|
| `forward(h_decide, h_opts)` | 单题（训练、单记录库路径） | `[d] , [K,d] -> [K]` |
| `many(h_decide, h_opts, owner)` | 服务批量：一次算完所有问题的所有选项 | `[Q,d] , [ΣK,d], [ΣK] -> [ΣK]` |
| `temperature` 属性 | checkpoint 自带（`head.pt["temperature"]`）；`--temperature`/`KEV_TEMPERATURE` 可覆盖 | float |

读出位置由 `encode()` 交付，模型不算索引：`enc["decide_idx"]`（每题 `<decide>` 的下标）与 `enc["opt_idx"]`（每题各 `</opt>` 的下标），
`DecisionModel._readout()` 就是 `zip(decide_idx, opt_idx)` 后逐题调用 head。

<div style="font-family:monospace;background:#0d1117;color:#c9d1d9;padding:18px;border-radius:8px;overflow-x:auto">
<style>
@keyframes kph { 0%{left:0;opacity:0} 12%{opacity:1} 80%{opacity:1} 100%{left:270px;opacity:0} }
.ph{position:relative;height:118px}
.ph-side{position:absolute;top:0;left:0;font-size:12px;line-height:1.9}
.ph-box{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:3px 8px}
.ph-box b{color:#58a6ff}.ph-box i{color:#3fb950;font-style:normal}
.ph-lane{position:absolute;left:0;right:0;height:22px}
.ph-p{position:absolute;top:6px;width:10px;height:10px;border-radius:50%;background:#58a6ff;
  box-shadow:0 0 8px #58a6ff;animation:kph 2.6s linear infinite}
.ph-p.o1{background:#3fb950;box-shadow:0 0 8px #3fb950;animation-delay:.6s}
.ph-p.o2{background:#f0883e;box-shadow:0 0 8px #f0883e;animation-delay:1.3s}
.ph-p.o3{background:#d2a8ff;box-shadow:0 0 8px #d2a8ff;animation-delay:1.9s}
.ph-grid{position:absolute;right:0;top:0;width:200px;font-size:11px;color:#8b949e;text-align:center}
.ph-dot{position:absolute;right:88px;top:46px;width:14px;height:14px;border-radius:50%;
  background:#e3b341;box-shadow:0 0 12px #e3b341}
</style>
<div class="ph">
  <div class="ph-side">
    <span class="ph-box"><b>&lt;decide&gt;</b> h_decide → W_q</span><br/>
    <span class="ph-box"><i>&lt;/opt&gt;</i> h_opt[0] → W_k</span><br/>
    <span class="ph-box"><i>&lt;/opt&gt;</i> h_opt[1] → W_k</span><br/>
    <span class="ph-box"><i>&lt;/opt&gt;</i> h_opt[2] → W_k</span>
  </div>
  <span class="ph-p"></span><span class="ph-p o1"></span><span class="ph-p o2"></span><span class="ph-p o3"></span>
  <span class="ph-dot"></span>
  <div class="ph-grid">
    q·kᵀ/√dp → z[3]<br/>
    ↓ ÷T (仅 eval)<br/>
    softmax → p[3]
  </div>
</div>
<div style="color:#8b949e;font-size:12px">四条粒子（1 个 query + 3 个 key）汇聚到中心点积；训练时没有 ÷T 那一步</div>
</div>

### 7.3 示例代码

```python
# ▶ 🟢 直接操作 head：温度改形状、不改 argmax（与 tests/test_unit.py 的断言同构）
import torch
from kev.model import PointerHead

torch.manual_seed(0)
head = PointerHead(d=32, dp=8)
h_decide, h_opts = torch.randn(32), torch.randn(3, 32)

head.train(); z_train = head(h_decide, h_opts)          # 训练：永远 raw
head.eval();  z_raw = head(h_decide, h_opts)            # eval, T=1 → 依然 raw
head.temperature = 2.0
z_warm = head(h_decide, h_opts)                         # eval, T=2 → z/2

print("训练路径不受温度影响:", torch.allclose(z_train, z_raw))                 # → True
print("校准只是除以 T:", torch.allclose(z_warm, z_raw / 2.0))                   # → True
print("argmax 不变:", z_warm.argmax() == z_raw.argmax())                        # → True
```

```python
# ▶ 🟢 三题型如何共用一个头：读 api.to_answers 的映射
import torch
from kev.api import to_answers

probs = [[0.15, 0.85],                                   # noul：keys=[false,true]
         [0.6, 0.25, 0.15],                              # choice：keys=criteria 名
         [0.05, 0.1, 0.2, 0.55, 0.1]]                    # score：keys="0".."4"
meta = [{"id": "urgent", "type": "noul", "keys": ["false", "true"]},
        {"id": "team", "type": "choice", "keys": ["billing", "shipping", "refund"]},
        {"id": "risk", "type": "score", "keys": [str(i) for i in range(5)],
         "legend": {str(i): c for i, c in enumerate(["很低", "低", "中", "高", "很高"])}}]
for qid, ans in to_answers(probs, meta).items():
    print(qid, ans)
# urgent  → {'type':'noul','noul':0.85}                        ← p(true)
# team    → {'choice':'billing','confidence':0.4, ...}          ← argmax + (p_max-1/K)/(1-1/K)
# risk    → {'score':2.95, 'legend':{...}, ...}                 ← 期望等级 Σ i·p[i]
```

### 7.4 常见陷阱

- **给训练也设温度**：`PointerHead.forward` 里 `self.training` 优先，设了也不生效；但如果你在 `train` 模式外手工拟合温度再拿去训练，`head.pt` 里的 T 就失去意义。纪律：**训练恒 T=1，温度只在拟合与推理出现**。
- **以为 `head` 跟骨干同 dtype**：骨干可以是 bf16，`hidden_batch` 出来立刻 `.float()`，head 常驻 fp32。
- **`dp` 改小图省事**：`head_dim` 是容量旋钮（`CHOICES` 里 128/256/512/1024），改了就不是同一个 checkpoint——`--init_from` 会拒绝尺寸不匹配。
- **忘记 `opt_idx` 指向 `</opt>`**：调试"某选项概率恒定"时，先看 `enc["opt_idx"][k]` 的长度是否等于选项数，最常见的错因是选项文本里出现了被转义的结构 token（第 3 章）。

**关键结论**：Kev 的"模型本体"只有三件东西——`encode`（形状）、`branch_mask`（可见性）、`PointerHead`（读出）。
把这三件读懂，任何 checkpoint 的输出都能手工复现到 logits 级。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](06-block-causal-mask.md) · [下一章 →](08-row-form.md)

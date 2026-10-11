# 2. Transformer 与因果语言模型最小集

> 《Kev 基础知识系统学习指南》· 第一部分 入门篇
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](01-positioning.md) · [下一章 →](03-tokenizer.md)

---


### 2.1 概念定义

- **因果语言模型（causal LM）**：每个 token 只能注意它**之前**的 token（含自身），由因果掩码保证。
- **prefill vs decode**：一次前向算完整个 prompt 叫 prefill；逐 token 生成叫 decode。
  Kev 只要 prefill——因此加载骨干时用 `AutoModel` 拿隐状态、**丢掉 LM head**。
- **additive 4D mask**：HuggingFace 允许传入形状 `[B, 1, L, L]` 的浮点掩码，**加到**注意力分数上；
  不允许的位置填一个极小值（如 `finfo.min`，不是 `-inf`，保证 softmax 有限）。
- **position ids 可自定义**：RoPE 按 position 编码而非数组下标，Kev 用这一点实现选项排列不变（第 6 章）。

### 2.2 原理讲解

注意力公式中，掩码作用在 `QKᵀ/√d` 之后、softmax 之前：

\[ \text{Attn}(Q,K) = \text{softmax}\!\Big(\frac{QK^\top}{\sqrt{d}} + M\Big)V \]

普通因果 LM 的 `M` 是标准下三角；Kev 的 `M` 是**块因果**（block-causal）：
`允许 attend(i,j) ⇔ j ≤ i 且 seg[j]==0 或 seg[j]==seg[i]`（state 段共享、问题分支各自隔离）——这正是第 6 章的内容。

📖 `kev/model.py:branch_mask_batch()`；HF 侧：`transformers` 的 `attention_mask`/`position_ids` 参数文档。

### 2.3 示例代码：手写一个 additive 因果掩码

```python
# ▶ 不依赖 Kev 包，纯 torch：直观理解 [1,1,L,L] additive mask
import torch, torch.nn.functional as F

L, d = 5, 8
torch.manual_seed(0)
Q, K, V = (torch.randn(1, L, d) for _ in range(3))

neg = torch.finfo(torch.float32).min
# 标准因果掩码：j <= i
causal = torch.triu(torch.full((L, L), neg), diagonal=1)          # [L,L]
attn = F.softmax(Q @ K.transpose(-2, -1) / d**0.5 + causal, dim=-1)
out = attn @ V
print("第 0 行能看几个 token？", (attn[0, 0] > neg / 2).sum().item())   # → 1
print("第 4 行能看几个 token？", (attn[0, 4] > neg / 2).sum().item())   # → 5
```

```python
# ▶ 用 transformers 验证：自定义 4D mask 与 position_ids 都会被尊重
import torch
from transformers import AutoModel, AutoTokenizer

tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B")
lm = AutoModel.from_pretrained("Qwen/Qwen2.5-0.5B")   # 只要隐状态，不要 LM head
ids = tok("state text here", return_tensors="pt")
L = ids.input_ids.shape[1]
neg = torch.finfo(torch.float32).min
mask = torch.triu(torch.full((1, 1, L, L), neg), diagonal=1)   # 下三角因果
h = lm(**ids, attention_mask=mask).last_hidden_state
print(h.shape)   # [1, L, 896] —— prefill 一次完成，无解码
```

### 2.4 与 Kev 的对应

| 你刚学的 | Kev 里的位置 |
|---|---|
| additive 4D mask | `branch_mask_batch()` 返回 `[B,1,L,L]`，padded 行保留对角线（防整行 -inf） |
| 去 LM head | `DecisionModel.__init__` 只取 `.model` 的 `last_hidden_state` |
| position ids | `encode()` 的 `pos` 字段，选项隔离时各选项共享同一位置区间 |
| KV cache（prefill 复用） | 服务侧 `kev/serve.py:PrefixCache`：state 前缀只算一次，分支续算 |

**关键结论**：只要会手写 `[1,1,L,L]` additive mask 并理解"position 是语义声明不是下标"，
你就具备了读懂 Kev 掩码代码的全部数学前置。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](01-positioning.md) · [下一章 →](03-tokenizer.md)

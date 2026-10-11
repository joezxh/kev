# 4. 概率与损失基础：softmax、交叉熵、KL

> 《Kev 基础知识系统学习指南》· 第一部分 入门篇
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](03-tokenizer.md) · [下一章 →](05-record.md)

---


### 4.1 概念定义

| 概念 | 定义 | 在 Kev 中 |
|---|---|---|
| logits | 未归一化分数 z | PointerHead 输出 K 维 |
| softmax | \(p_i = e^{z_i}/\sum_j e^{z_j}\) | 概率来源 |
| 交叉熵 / NLL | \(-\log p_{y}\)（真实类 y） | **训练主损失**（选项上的 log loss） |
| KL 散度 | \(D_{KL}(p\Vert q)=\sum_i p_i\log\frac{p_i}{q_i}\) | `--perm_kl`（置换 KL）、`--anchor`（向冻结基座拉近） |
| label smoothing | 把 one-hot 软化为 ε 混合 | round-3 校准筛选实验项，**未进发布配方** |

### 4.2 原理讲解

Kev 与普通 LLM 训练的最大差异：**损失不在全部 token 上**，只在每题选项分布上算 log loss。
一个 packed 序列里有 Q 个问题，就产生 Q 个独立的小交叉熵，平均即可。
soft target（teacher 分布）与 KL 只出现在两个可选分支：permutation KL（让"选项换个顺序"的分布一致）
和 anchor KL（防止微调把基座的常识冲掉）。

📖 `kev/train.py:question_loss()` / `anchor_loss()`。

### 4.3 示例代码

```python
# ▶ 纯 torch：从 logits 到训练损失的最小可运行样例
import torch, torch.nn.functional as F

z = torch.tensor([2.0, 0.5, -1.0])            # PointerHead 的 3 选项 logits
p = F.softmax(z, dim=-1)
print(p, p.sum())                              # 概率，和为 1

y = torch.tensor(0)
nll = F.cross_entropy(z[None], y[None])        # 训练主损失 = -log p[y]
print("NLL =", nll.item())                     # = -log softmax(z)[0]

# 温度缩放：除以 T 不改 argmax，但改概率形状（第 9 章的主角）
p_T = F.softmax(z / 2.0, dim=-1)               # T=2：更平
print("argmax 不变:", p.argmax().item() == p_T.argmax().item())
print("更接近均匀分布:", p_T.std().item() < p.std().item())

# KL：permutation KL 的骨架——同一题、两种选项顺序，分布应对齐
z_perm = z[[2, 0, 1]]                          # 选项重排后的 logits
kl = F.kl_div(F.log_softmax(z_perm, -1), F.softmax(z, -1),
              reduction="batchmean", log_target=False)
print("permutation KL =", kl.item())           # 训练时把它最小化
```

### 4.4 与 Kev 的对应

- 训练时**永远 T=1**（`kev/model.py:PointerHead` 注释），保证拟合出的温度有意义。
- `--ord_w`（Score 题）用的是 ranked probability score：对有序等级的累积分布算损失，
  普通交叉熵不知道"等级 2 离等级 5 比离等级 3 更远"。
- label smoothing / Brier 损失 / focal loss 都在 round-3 筛过（`--label_smoothing/--brier_w/--focal_gamma`），
  **没有任何一个进发布配方**——新手不要指望它们提升指标。

**关键结论**：Kev 的训练 = "在选项边界上算 CE，可选加置换 KL 与 anchor KL"。
没有 token 级 next-token loss，这是它与 SFT 的本质区别。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](03-tokenizer.md) · [下一章 →](05-record.md)

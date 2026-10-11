# 8. 行形式（row form）与混合骨干（hybrid backbone）：整个仓库复杂度的根源

> 《Kev 基础知识系统学习指南》· 第二部分 进阶篇
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](07-pointer-head.md) · [下一章 →](09-temperature.md)

---


### 8.1 概念定义

| 术语 | 定义 |
|---|---|
| **attention-only 骨干** | 每层都是标准自注意力（如 Qwen2.5）：尊重任意 4D 掩码 → 可以跑 **packed 形式**（一条序列一次前向） |
| **hybrid 骨干** | 含 **Gated DeltaNet 线性注意力**层的基座（Qwen3.5 / Qwen3.8）：`is_hybrid(config)` 看 `config.layer_types` 里有没有 `linear_attention` |
| **递归状态** | DeltaNet 层不存 K/V，而是维护 `conv_states`（短卷积窗口）+ `recurrent_states`（循环矩阵）；它们是**按顺序递推**的，无法实现"跳过兄弟分支"这种任意可见性 |
| **row form（行形式）** | 每个问题一条独立的因果行：`state tokens + 该题分支 tokens`；行间天然隔离，代价是 state 被重算 Q 次 |
| **`ROW_PASS_TOKENS = 16384`** | 一次推理 pass 容纳的 token 预算；也是 attention-only 从 packed 改行形式的阈值（packed 的掩码是 L×L，随问题数无界增长） |

选路只有一行（`DecisionModel.rows_form`）：`return self.hybrid or any(len(e["ids"]) > ROW_PASS_TOKENS for e in encs)`。

### 8.2 原理讲解：为什么行形式是**等价**而不是退化

[`rows_of()`](../../../kev/model.py) 的 docstring 把论证写完：

> *"Feeding state + rows[k] as one causal row is equivalent to the packed block-causal form for that question, on any
> architecture: the row contains exactly the tokens question k may attend to, in the same positions."*

即：行里恰好只装了"允许被看见"的 token，位置 `pos` 也从 state 末尾接着排——那标准因果掩码就已经是块因果掩码。
两条路径在 fp32 噪声内一致，由 `tests/test_model.py::test_rows_match_packed` 守住。

代价是算力：`forward_rows_batch` 不带缓存时每行都重算 state（`Q × state tokens`）——训练能接受，服务不行。于是有了三个补救：

1. **服务侧 prefix cache**（[`kev/serve.py:PrefixCache`](../../../kev/serve.py)）：把 state 的前缀（注意力 K/V + DeltaNet 的 conv/recurrent 状态）按 `(state token ids, option_isolation)` 缓存，
   命中后只跑"分支行"。`_rows_hidden(rows, cache, prefix_len)` 会**复制一份 cache**再跑（`copy.copy` 逐层，递归状态 `.copy()`），
   保证调用方的 prefix 不被写脏、下个同 state 的请求还能用；OOM 时直接**丢掉整个缓存重试一次**（缓存只省时间，不决定答案）。
2. **训练侧 `shared_prefix`**（[`kev/shared_prefix.py:branch_hidden()`](../../../kev/shared_prefix.py)）：梯度也在内的"state 只跑一次"，行形式的数学，packed 的成本（`--shared_prefix`，`--full_ft` 默认开）。
3. **长 state 走 flash 因果核**：微批里的 state 无需 padding 时，直接用 SDPA 的因果 flash kernel（不具化 64k×64k 掩码）；
   实测同一个 64k 步：带显式掩码 **150 s** 并填满 GPU，flash 路径 **44 s**（`runs/sft-probe/lc-27b-8xh200-mask-ab`）。

`prefix_min_tokens` 回答"多短的 state 不值得缓存"：hybrid 与 MLX 为 **0**（不缓存就每题重算），
attention-only 在 MPS 上为 **384**（低于它，纯分支 pass 并不比一次 packed pass 快）。

<div style="font-family:monospace;background:#0d1117;color:#c9d1d9;padding:18px;border-radius:8px;overflow-x:auto">
<style>
@keyframes krow { 0%{width:0;opacity:.25} 55%{opacity:1} 100%{width:100%;opacity:1} }
.kc{margin:6px 0}
.kc-l{font-size:12px;color:#8b949e}
.kc-b{height:12px;border-radius:3px;margin:3px 0;width:0;animation:krow 2.8s ease-out infinite}
.st{background:#1e3a5f;border:1px solid #2f5a8f}
.br{background:#2d4a2b;border:1px solid #3f7a3b;margin-left:0}
.kc-h{font-size:12px;color:#58a6ff;margin-top:10px}
</style>
<div style="display:flex;gap:24px;flex-wrap:wrap">
  <div style="flex:1;min-width:260px">
    <div class="kc-h">✗ 无缓存的行形式：state 被算 3 次</div>
    <div class="kc"><div class="kc-b st"></div><div class="kc-b br" style="animation-delay:.15s"></div>
      <div class="kc-b st" style="animation-delay:.3s"></div><div class="kc-b br" style="animation-delay:.45s"></div>
      <div class="kc-b st" style="animation-delay:.6s"></div><div class="kc-b br" style="animation-delay:.75s"></div></div>
    <div class="kc-l">3 条行 = 3 ×（state + 分支）</div>
  </div>
  <div style="flex:1;min-width:260px">
    <div class="kc-h">✓ prefix cache：state 算 1 次，命中后只跑分支</div>
    <div class="kc"><div class="kc-b st" style="animation:none;width:100%"></div>
      <div class="kc-b br" style="width:30%"></div><div class="kc-b br" style="width:26%;animation-delay:.4s"></div>
      <div class="kc-b br" style="width:34%;animation-delay:.8s"></div></div>
    <div class="kc-l">蓝色 = 缓存的 state 前缀；绿色 = 后续三次分支 pass</div>
  </div>
</div>
</div>

📖 `kev/model.py:is_hybrid()`、`rows_of()`、`rows_per_pass()`、`DecisionModel.rows_form/_rows_hidden/forward_rows_batch`；
`kev/shared_prefix.py`、`kev/serve.py:PrefixCache`；`kev/mlx_model.py`（Metal 上的同一套行+前缀逻辑）。

### 8.3 示例代码

```python
# ▶ 🟢 行拆分的结构（不需要任何下载，直接拿第 6 章那批 seg 造一个假 enc）
from kev.model import rows_per_pass, ROW_PASS_TOKENS

# rows_per_pass 回答：一次 forward 能塞几条行？每行都带着缓存 state，所以 prefix 要计入成本
short_state = [[0] * 30] * 5
print(rows_per_pass(short_state, prefix_len=270))       # → 16384 // 300 = 54：普通请求一次全跑完
long_state = [[0] * 20] * 64
print(rows_per_pass(long_state, prefix_len=4802))       # → 3：长 state 只能几份缓存拷贝一次
print(rows_per_pass([[0] * 8192], prefix_len=8192))     # → 1：最长的一条行也必须能跑
```

```python
# ▶ 🟡 看 packed enc 拆成的行（与第 5 章同一条 record）
from kev.model import encode, rows_of

rec = {"state": {"doc": "服务超时上升，数据库连接池耗尽"},
       "questions": [{"instr": "根因？", "options": ["连接池", "网络"], "label": 0},
                     {"instr": "是否需升级？", "options": ["否", "是"], "label": 1}]}
enc = encode(tok, rec, max_state=64, max_branch=256)
state_ids, state_pos, rows = rows_of(enc)
print("state 长度:", len(state_ids), "| 行数(= 问题数):", len(rows))
for i, r in enumerate(rows):
    print(f"行{i}: 分支 {len(r['ids'])} token、decide 在分支内 {r['decide']}、选项 {len(r['opts'])} 个")
# 真正的完整行 = state_ids + r["ids"]；r["decide"]/r["opts"] 是**分支内**的下标，加 len(state_ids) 才是行内下标
```

```powershell
# ▶ 亲眼看到两条路径等价（需 CPU 就能跑的小模型 fixture）
uv run pytest tests/test_model.py -k "rows_match_packed or shared_prefix_matches_rows or prefix_cache_matches_full_pass"
```

### 8.4 常见陷阱

- **在 hybrid 上要求 packed**：`DecisionModel.__init__` 直接拒绝 `hybrid + option_isolation`；行形式里没有块因果掩码可用。
- **以为 `option_isolation` 在 hybrid 上"退化成普通 packing"**：不是，是**不可用**（它需要掩码能力）。
- **缓存当正确性依赖**：`PrefixCache` 只影响速度；OOM 丢缓存重跑就是拿这条当公理写的。
- **`DeltaNet` 的数学细节想一次看懂**：入门阶段不需要。只需记住一句："它是递归的，不认任意掩码"。`fused_qwen35.py`、`fla` 的 Triton kernel、`cuda_graphs.py` 都归入"遇到再学"。

**关键结论**：hybrid 基座 → 行形式 → 于是需要前缀复用 → 于是有 `PrefixCache`/`shared_prefix`/flash 无掩码路径/`rows_per_pass` 预算。
这条因果链是仓库里"看起来过度设计"的代码的唯一存合理山；读懂它就不会误删"看似冗余"的分支。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](07-pointer-head.md) · [下一章 →](09-temperature.md)

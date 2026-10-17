# Kev 算子名单与架构解析

本文分五部分：**一**讲清「算子」这个概念本身，**二**解析 Kev 算子层的架构与数据流，**三**给出合并为单张表的完整算子名单（覆盖到符号级，并链到源码行），**四**把这份名单与常见生成式 LLM 及兄弟系统 Jev 逐算子对照，**五**小结。

> 一句话定位：Kev 是一个 **prefill-only 的决策模型**——因果 LM 骨干 + LoRA，跑一次前向（不逐 token 生成文本），用块因果掩码把共享 state 前缀与各问题分支隔开，最后通过一个**指针读出（pointer readout）**在选项边界 token 上打分。因此它的「算子」不是 NLP 生成栈里那套采样/解码算子，而是**掩码、指针打分、融合线性注意力核、CUDA Graph 与执行层后端**。

---

## 一、什么是「算子」（概念）

「算子」（operator / kernel）指**一次不可再分的张量计算单元**：给定输入张量，执行一段固定的数学运算，产出输出张量。在不同抽象层级上，同一个词指代不同粒度的东西：

| 抽象层级 | 含义 | 典型形态 | 谁定义 |
|---|---|---|---|
| 数学/逻辑算子 | 一个语义操作（softmax、交叉熵、KL 散度、注意力） | 框架里的函数 | 框架或业务代码 |
| 融合算子（fused op） | 把一串逻辑操作合并成**一次** GPU 启动，减少中间张量与 launch 开销 | Triton / CUDA kernel | 手写或第三方库（此处为 `fla`） |
| 硬件 kernel | GPU/加速器上真正执行的线程块 | SASS / PTX、Metal | 编译器 + 驱动 |
| 执行层算子 | 决定「用哪个 kernel、以什么 shape、能否重放」的调度件 | SDPA 后端选择、CUDA Graph 捕获 | 运行时包装 |

在 PyTorch 语境里，`nn.Module.forward` / `F.*` 是逻辑算子；一个 `.cuda` 上真正跑的是若干 kernel；**一次 forward 可能发起上千个 kernel launch**——这正是 Kev 用 CUDA Graph「把一次 pass 捕获成一张图、一次调用重放」要解决的问题（见第三节 `cuda_graphs`）。

**Kev 的特殊性**决定了它的算子清单与常见 LLM 不同：

- 它**不生成文本**，所以没有 `sample` / `top-k` / `logits processor` / KV decode-step 那套解码算子；骨干只取 `last_hidden_state`（`AutoModel ... .model`，无 vocab head）。
- 它的输出是**选项上的概率分布**，由一个自定义的指针读出算子产生，而不是语言模型的下一 token 分布。
- 骨干是 **Qwen3.5 混合架构**（`full_attention` 层 + `linear_attention`/Gated DeltaNet 层交替），DeltaNet 层的因果卷积与分块 delta 规则是它最重、也最需要融合优化的算子。

### 1.1 先补一个前提：张量（tensor）是什么

上面的定义里反复出现「张量」，这里先把它说清。一句话：**张量 = 形状固定的多维数字数组**——先规定它嵌套几层（`shape`），再往里填数（每个数有一个类型 `dtype`）。数嵌套层数，就是它的「阶」：

| 阶 | 别名 | 直观样子 | 例子 |
|---|---|---|---|
| 0 阶 | 标量 | 一个数 | 温度 `36.5` |
| 1 阶 | 向量 | 一排数 | 一行 Excel |
| 2 阶 | 矩阵 | 一张表格 | 灰度图的像素（高×宽） |
| 3 阶 | —— | 一摞表格 | 彩色图（高×宽×RGB 三通道） |

再往上是 4 阶、5 阶……本质不变，只是套娃层数更多。**模型层与层之间流动的东西全是张量**。在 Kev 里：一批问题的 token id 是 2 阶张量 `(batch, seq)`，模型内部的隐藏状态是 3 阶张量 `(batch, seq, hidden_dim)`。

### 1.2 范例：ReLU —— 给定输入、固定运算、产出输出

回到本节开头那句话「给定输入张量 → 执行一段固定的数学运算 → 产出输出张量」。最便宜的算子是 **ReLU**，规则只有一个：负数变 0，正数不动，即 `max(0, x)`。

- **输入张量**：`[3, -1, 2, 0]`（shape `(4,)`）
- **固定的数学运算**：对每个元素做 `max(0, x)`
- **输出张量**：`[3, 0, 2, 0]`（还是 shape `(4,)`）

`-1` 被夹成 `0`，其余原样通过。整个过程在 GPU 上是**一次** kernel 启动完成的。

### 1.3 「不可再分」是什么意思

「不可再分」不是说数学上不能再拆，而是说它是**一次性的、整体的一个执行单元**。用 `y = 2x + 1` 对比最清楚：

- **拆成两个算子**：先「× 2」得到中间张量、写回显存，再「+ 1」把中间张量读回来算 → **2 次 GPU 启动 + 1 个中间张量**（多一次显存往返）。
- **融合成一个算子**：把乘和加熔进一个 kernel 一次做完 → **1 次启动、0 个中间张量**，中间结果根本不出芯片。

融合之后的这一步，才是定义里说的「不可再分的单元」。Kev 的 `fused_qwen35.py` 里那些融合 kernel（RMSNorm+Linear、SwiGLU）就是这种工程做法。

### 1.4 稍复杂一点：矩阵乘法（GEMM）

真实 LLM 里最重的算子就是**矩阵乘法**（GEMM）：注意力的 `QKᵀ`、加权求和、FFN、各种投影全是它。规则只有一句：**C 的第 i 行 j 列 = A 的第 i 行 · B 的第 j 列**（点积：对应位置相乘，再全部加起来）。最小例子，A 是 2×3、B 是 3×2，得到 C 是 2×2：

```
A = [ 1  2  3 ]    B = [  7   8 ]    C = A·B = [  58   64 ]
    [ 4  5  6 ]        [  9  10 ]              [ 139  154 ]
                       [ 11  12 ]
```

以 `C[0][0]` 为例：`1×7 + 2×9 + 3×11 = 58`。四个格子各做一次点积，但在 GPU 上是**一个 GEMM kernel** 一次算完——它「吃两个输入张量、吐一个输出张量」，仍然是一个不可再分的算子。

> 以上 1.1–1.4 对应演示页 [`docs/tensor-operator-demo.html`](file:///d:/projects/github/kev/docs/tensor-operator-demo.html) 第 1–4 节：HTML 版可逐格动画播放（张量阶数分层、ReLU 逐元素夹取、拆两个 vs 融合一个的 kernel 计数对比、矩阵乘法逐格高亮「行·列」）。

---

## 二、Kev 算子层的架构

Kev 没有手写 CUDA/C++ kernel。它的算子层由**三个来源**构成：

| 来源 | 说明 | 主要落点 |
|---|---|---|
| ① 自定义 PyTorch 前向算子 | 块因果掩码、指针读出、state-prefix 复用、共享前缀训练前向 | `model.py`、`shared_prefix.py` |
| ② 第三方 Triton 融合核的接管 | flash-linear-attention（`fla`）的因果卷积、分块门控 delta、融合 norm/SwiGLU；`fused_qwen35` 原地重写骨干层前向去用它们 | `fused_qwen35.py` |
| ③ 执行层算子 | CUDA Graph 捕获/重放、SDPA 后端选择、fused AdamW master 优化器、MLX Metal kernel | `cuda_graphs.py`、`predictors.py`、`full_ft.py`、`mlx_model.py` |

### 2.1 分层视图

| 层 | 职责 | 代表算子 | 代码 |
|---|---|---|---|
| 编码层 | record → token/段/位置/选项索引 | `encode`、`user_tokens`、`rows_of` | `model.py` |
| 掩码层 | 块因果（含 option isolation） | `branch_mask` / `branch_mask_batch` | `model.py` |
| 骨干层（attention） | 标准多头注意力 + RoPE | `attention_forward`（融合）/ SDPA 后端 | `fused_qwen35.py`、`predictors.py` |
| 骨干层（DeltaNet） | 短因果卷积 + 分块门控 delta 规则 | `causal_conv1d`、`chunk_gated_delta_rule`、`deltanet_forward` | `fused_qwen35.py` |
| 归一/激活层 | RMSNorm（零中心）、SwiGLU、sigmoid 门 | `rms_norm`、`rms_norm_gated`、`swiglu`、`sigmoidglu` | `fused_qwen35.py` |
| 读出层 | 指针打分 + 温度校准 | `PointerHead.forward`/`many`、`_readout_many` | `model.py` |
| 缓存/前缀层 | state KV/conv/recurrent 前缀只跑一次并复用 | `prefix`/`probs_and_prefix`/`probs_with_prefix`、`Prefix`、`BufferKV`、`set_linear` | `model.py`、`shared_prefix.py`、`cuda_graphs.py` |
| 执行层 | shape 分桶、图捕获/重放、后端选择、优化器 | `bucket`/`length_groups`、`CudaGraphs.states`/`rows`、`long_row_kernels`、`MasterAdamW` | `cuda_graphs.py`、`predictors.py`、`full_ft.py` |
| 训练目标层 | 交叉熵及校准/锚定/置换变体 | `question_loss`、`anchor_loss`、`permuted_copy` | `train.py` |

### 2.2 一次打分的数据流

```
record (state + questions + options)
  └─ encode ──► ids / seg / pos / opt  (+ decide_idx, opt_idx 读出偏移)
        ├─ 注意力-only 骨干：packed + branch_mask_batch  [块因果掩码]
        └─ 混合骨干（Qwen3.5）：rows_of → 逐问因果行，state 作前缀缓存复用
              每层：full_attention → attention_forward  ｜ linear_attention → deltanet_forward
                    (qkv 单 GEMM + SDPA)                  (causal_conv1d + chunk_gated_delta_rule)
                    rms_norm / swiglu / sigmoidglu         rms_norm_gated
        ──► last_hidden_state[<decide> 位置 与 </opt> 边界位置]
              └─ PointerHead.forward / many  z = (k(h_opts) · q(h_decide)) · scale
                    └─(eval)÷ temperature─► softmax ─► 选项概率
```

关键不变量：**分支 token 永不跨问题互相注意，state 也看不到分支**（块因果 + 掩码保证），所以「state 跑一次、分支续跑」与「每问各自整行重跑」**逐 fp32 位等价**（`tests/test_model.py::test_rows_match_packed`）——这是 state-prefix 缓存复用与 `shared_prefix` 训练正确性的根。

### 2.3 三条执行路径与各自的算子集合

| 路径 | dtype / kernel | 用的算子 | 备注 |
|---|---|---|---|
| 训练（`train.py`） | fp32 精确；混合骨干可选 `--shared_prefix` | `shared_prefix.*` + fla Triton（可微）+ `full_ft.MasterAdamW` + `train.question_loss` | 融合核仅 serving；训练走 reference/可微路径 |
| 评测（`predictors.LocalPredictor`） | fp32-exact（禁 TF32/融合 SDPA） | SDPA 后端 `long_row_kernels`；CUDA 上混合骨干 DeltaNet 仍落 fla Triton（TF32 点积） | 长行 > `ROW_PASS_TOKENS` 走 `kernels: efficient` |
| 上线服务（`serve.py`） | bf16 + `fuse()` + CUDA Graph | `fused_qwen35.*` + `cuda_graphs.*` + `PointerHead.many` | 默认开融合核与图；`KEV_FUSED=0`/`KEV_CUDA_GRAPHS=0` 可关 |

### 2.4 可复现契约：`kernel_environment`

一次读出的 logits 不止依赖 kev 代码与 checkpoint，还依赖**它跑在哪套 kernel 上**（包版本、GPU、骨干 dtype、attention 实现、被 `fused_qwen35` 替换的 DeltaNet forward、conv 与 delta rule 的实际绑定）。`predictors.kernel_environment` 把这套指纹写进 `report.json` 的 `environment`；**两次读取只有在 kernel 集与 kev commit 都一致时才可逐位配对**。（背景：#125 的 `causal-conv1d` kernel 变更曾在无代码改动下把 Kev-27B v1 的 p 移动最多 0.06。）

---

## 三、算子完整名单（单表）

下表把全部算子合并为一张表，用「功能域」列区分。功能域与代码文件对应：`核心模型`= `model.py`；`融合 Triton serving`= `fused_qwen35.py`；`共享前缀训练`= `shared_prefix.py`；`CUDA Graph`= `cuda_graphs.py`；`Attention 后端/kernel 环境`= `predictors.py`；`全权重优化器`= `full_ft.py`；`MLX 后端`= `mlx_model.py`；`训练目标`= `train.py`。

| 功能域 | 算子 | 位置 | 说明 |
|---|---|---|---|
| 核心模型 | `encode` | [model.py#L87-L127](file:///d:/projects/github/kev/kev/model.py#L87-L127) | 把一条 record 打包为 `[<state>… <q> instr <opt> o </opt>… <decide>]`，产出 ids/seg/pos/opt 与读出偏移；`option_isolation` 时每个选项成独立子分支 |
| 核心模型 | `user_tokens` | [model.py#L78-L81](file:///d:/projects/github/kev/kev/model.py#L78-L81) | 对调用方文本分词，把 `<\|name\|>` 改写为 `<¦name¦>`，使选项边界 token 不可伪造 |
| 核心模型 | `branch_mask` / `branch_mask_batch` | [model.py#L154-L185](file:///d:/projects/github/kev/kev/model.py#L154-L185) | **块因果掩码算子**：`attend(i,j) iff j≤i 且 (seg[j]==0 或 seg[j]==seg[i])`，返回加性 `[B,1,L,L]`；含 option-isolation 与 pad 处理 |
| 核心模型 | `rows_of` | [model.py#L188-L202](file:///d:/projects/github/kev/kev/model.py#L188-L202) | 把 packed 编码拆成 state + 每问的因果行（与 packed 块因果等价） |
| 核心模型 | `PointerHead.forward` | [model.py#L205-L218](file:///d:/projects/github/kev/kev/model.py#L205-L218) | **指针读出算子（核心原语）**：`z = (k(h_opts) @ q(h_decide)) * scale`，对选项边界 token 打分而非生成文本；eval 模式下除以 `temperature` 做校准 |
| 核心模型 | `PointerHead.many` | [model.py#L220-L223](file:///d:/projects/github/kev/kev/model.py#L220-L223) | 一次算多问的指针读出（serving 批处理），一次 pass 代替逐问 |
| 核心模型 | `_readout_many` | [model.py#L494-L505](file:///d:/projects/github/kev/kev/model.py#L494-L505) | 从挑出的 hidden states 以固定 kernel 数 + 单次 device sync 算多问概率 |
| 核心模型 | `prefix` / `probs_and_prefix` / `probs_with_prefix` | [model.py#L416-L462](file:///d:/projects/github/kev/kev/model.py#L416-L462) | **state-prefix KV 缓存复用**：state 只跑一次，问题分支从缓存继续；exact by construction |
| 核心模型 | `rows_per_pass` | [model.py#L41-L47](file:///d:/projects/github/kev/kev/model.py#L41-L47) | 计算一次推理 pass 能塞多少因果行（按 token 预算），约束显存 |
| 融合 Triton serving | `causal_conv1d` (fla) | [fused_qwen35.py#L26](file:///d:/projects/github/kev/kev/fused_qwen35.py#L26) · 调用 [#L72](file:///d:/projects/github/kev/kev/fused_qwen35.py#L72) | fla 的 Triton 因果卷积，从缓存的 conv state 起步（不做拼接） |
| 融合 Triton serving | `chunk_gated_delta_rule` (fla) | [fused_qwen35.py#L29](file:///d:/projects/github/kev/kev/fused_qwen35.py#L29) · 调用 [#L75-L78](file:///d:/projects/github/kev/kev/fused_qwen35.py#L75-L78) | 分块门控 delta 规则，核内计算 gate(`-exp(A_log)*softplus`)、beta sigmoid、q/k L2 norm，key head 复用 |
| 融合 Triton serving | `rms_norm_gated` (fla) | [fused_qwen35.py#L27](file:///d:/projects/github/kev/kev/fused_qwen35.py#L27) · 调用 [#L84](file:///d:/projects/github/kev/kev/fused_qwen35.py#L84) | 融合门控 RMSNorm（DeltaNet 输出） |
| 融合 Triton serving | `rms_norm` (fla) | [fused_qwen35.py#L28](file:///d:/projects/github/kev/kev/fused_qwen35.py#L28) | 融合 RMSNorm（零中心 norm 用 `1+w` fp32，第二个兼加残差） |
| 融合 Triton serving | `swiglu` / `sigmoidglu` (fla) | [fused_qwen35.py#L25](file:///d:/projects/github/kev/kev/fused_qwen35.py#L25) · [#L100](file:///d:/projects/github/kev/kev/fused_qwen35.py#L100), [#L105](file:///d:/projects/github/kev/kev/fused_qwen35.py#L105) | 融合 SwiGLU（MLP）与 sigmoid 输出门（attention） |
| 融合 Triton serving | `deltanet_forward` | [fused_qwen35.py#L62-L85](file:///d:/projects/github/kev/kev/fused_qwen35.py#L62-L85) | 替换 `Qwen3_5GatedDeltaNet.forward`：单次 q/k/v/z/b/a 投影 GEMM + 上述融合核 |
| 融合 Triton serving | `attention_forward` | [fused_qwen35.py#L88-L100](file:///d:/projects/github/kev/kev/fused_qwen35.py#L88-L100) | 替换 `Qwen3_5Attention.forward`：单 GEMM qkv、融合 q/k RMSNorm、融合 sigmoid 门 |
| 融合 Triton serving | `mlp_forward` | [fused_qwen35.py#L103-L105](file:///d:/projects/github/kev/kev/fused_qwen35.py#L103-L105) | 替换 MLP：gate+up 单 GEMM + 融合 SwiGLU |
| 融合 Triton serving | `decoder_forward` | [fused_qwen35.py#L108-L118](file:///d:/projects/github/kev/kev/fused_qwen35.py#L108-L118) | 替换 decoder 层：两个零中心 RMSNorm 走融合核，post-norm 兼加残差 |
| 融合 Triton serving | `_concat` | [fused_qwen35.py#L56-L59](file:///d:/projects/github/kev/kev/fused_qwen35.py#L56-L59) | 把多个无 bias 同输入投影合并成一份权重（一次 GEMM） |
| 融合 Triton serving | `_FixedNB` / `_fix_nb` | [fused_qwen35.py#L34-L50](file:///d:/projects/github/kev/kev/fused_qwen35.py#L34-L50) | 给 fla 的 4 个 Triton 核（`causal_conv1d_fwd_kernel`、`layer_norm_gated_fwd_kernel`、`l2norm_fwd_kernel`、`layer_norm_fwd_kernel`）钉住 `NB=1`，避免每个新 batch shape 重编译/autotune |
| 融合 Triton serving | `fuse` | [fused_qwen35.py#L121-L155](file:///d:/projects/github/kev/kev/fused_qwen35.py#L121-L155) | 原地重写整个 Qwen3.5 backbone 用融合核；要求 `fla==0.5.2`，不支持 MoE 层 |
| 共享前缀训练 | `Prefix` | [shared_prefix.py#L30-L69](file:///d:/projects/github/kev/kev/shared_prefix.py#L30-L69) | 函数式的逐层 state 缓存（attention K/V、DeltaNet conv 窗口 + recurrent state），不改写原地，让 autograd 能穿过；`branch()` 按 branch 行 gather |
| 共享前缀训练 | `_masks` | [shared_prefix.py#L72-L76](file:///d:/projects/github/kev/kev/shared_prefix.py#L72-L76) | eager 用加性 float 掩码、SDPA 用 boolean |
| 共享前缀训练 | `branch_hidden` | [shared_prefix.py#L79-L96](file:///d:/projects/github/kev/kev/shared_prefix.py#L79-L96) | 左 pad state、右 pad branch，得到每问最终 hidden states 供指针头读出 |
| 共享前缀训练 | `_forward` / `_step` | [shared_prefix.py#L99-L132](file:///d:/projects/github/kev/kev/shared_prefix.py#L99-L132) | decoder stack 的 state pass + branch pass 合一步；无 pad 的 state 走 SDPA causal flash（不传掩码），gradient checkpointing 整步重算 |
| CUDA Graph | `bucket` / `pow2` / `count_bucket` | [cuda_graphs.py#L59-L73](file:///d:/projects/github/kev/kev/cuda_graphs.py#L59-L73) | shape 分桶（padding 规划） |
| CUDA Graph | `length_groups` | [cuda_graphs.py#L76-L90](file:///d:/projects/github/kev/kev/cuda_graphs.py#L76-L90) | DP 求最省 token 的分组成 padded pass |
| CUDA Graph | `BufferKV` | [cuda_graphs.py#L113-L126](file:///d:/projects/github/kev/kev/cuda_graphs.py#L113-L126) | 预分配 `[N,heads,T,dim]` 缓冲上的 attention KV cache（写入代替 concat） |
| CUDA Graph | `set_linear` | [cuda_graphs.py#L129-L134](file:///d:/projects/github/kev/kev/cuda_graphs.py#L129-L134) | 把 DeltaNet cache 层指向 conv/recurrent state 张量 |
| CUDA Graph | `CudaGraphs.states` | [cuda_graphs.py#L301-L330](file:///d:/projects/github/kev/kev/cuda_graphs.py#L301-L330) | state pass 图：多 state 同跑，左 pad，结果写入 bank |
| CUDA Graph | `CudaGraphs.rows` / `_row_pass` | [cuda_graphs.py#L340-L375](file:///d:/projects/github/kev/kev/cuda_graphs.py#L340-L375) | row pass 图：每问行从 bank gather 其 state 后续跑 |
| CUDA Graph | `capture_pending` / `_replay` | [cuda_graphs.py#L206-L254](file:///d:/projects/github/kev/kev/cuda_graphs.py#L206-L254) | 侧流 warm-up + 捕获；捕获失败永久退回 eager |
| Attention 后端/kernel 环境 | `long_row_kernels` | [predictors.py#L37-L56](file:///d:/projects/github/kev/kev/predictors.py#L37-L56) | 长行 attention 后端上下文：SDPA 的 **flash / memory-efficient / math** 三后端；fp32 未 pad state 走 memory-efficient（cutlass `OpMultiplyAddFastF32`，fp32 精度） |
| Attention 后端/kernel 环境 | `DELTANET_KERNELS` | [predictors.py#L34](file:///d:/projects/github/kev/kev/predictors.py#L34) | transformers GatedDeltaNet 的两个 prefill hook：`causal_conv1d_fn`、`torch_chunk_gated_delta_rule` |
| Attention 后端/kernel 环境 | `bound_implementation` / `kernel_environment` | [predictors.py#L59-L90](file:///d:/projects/github/kev/kev/predictors.py#L59-L90) | 记录一次 logits 读取依赖的 kernel 集（包版本、GPU、dtype、attention 实现、被 `fused_qwen35` 替换的 DeltaNet forward、conv 与 delta rule 绑定），写入 `report.json` |
| 全权重优化器 | `MasterAdamW` | [full_ft.py#L63+](file:///d:/projects/github/kev/kev/full_ft.py#L63) | fp32 master + moments 的 AdamW（内部用 torch fused `adamw`，见 [#L35](file:///d:/projects/github/kev/kev/full_ft.py#L35)）；单 GPU 时 master 在 host 内存，torchrun 下 FSDP2 分片到 GPU |
| 全权重优化器 | `_clip_scale` | [full_ft.py#L84-L93](file:///d:/projects/github/kev/kev/full_ft.py#L84-L93) | 按全局梯度 L2 范数做 gradient clipping（分片跨 rank 求和，非有限即拒 step） |
| 全权重优化器 | `_fetch` / `_put` | [full_ft.py#L95-L113](file:///d:/projects/github/kev/kev/full_ft.py#L95-L113) | pinned 双槽异步流水：逐 tensor 下载梯度→CPU 更新→上传 bf16(master) |
| MLX 后端 | `MLXDecisionModel._hidden` / `_logits` | [mlx_model.py#L149-L164](file:///d:/projects/github/kev/kev/mlx_model.py#L149) | MLX 前向 + 指针读出（与 torch 端 parity 测于 `tests/test_mlx.py`），走 mlx-lm 的 Metal kernel |
| MLX 后端 | `merge_lora` | [mlx_model.py#L97](file:///d:/projects/github/kev/kev/mlx_model.py#L97) | LoRA 合并进骨干（与 `fused_qwen35.fuse` 的合并边界一致） |
| 训练目标 | `question_loss` | [train.py#L61-L80](file:///d:/projects/github/kev/kev/train.py#L61-L80) | 交叉熵 / soft-target CE，可选叠加 `brier_w`（Brier）、`focal_gamma`（focal）、`label_smoothing`，及 Score 题型的 ranked probability score（`ord_w`）；三者互斥 |
| 训练目标 | `anchor_loss` | [train.py#L84](file:///d:/projects/github/kev/kev/train.py#L84) | 向冻结基座零样本分布的 `KL(teacher‖student)`（锚定） |
| 训练目标 | `permuted_copy` | [train.py#L49](file:///d:/projects/github/kev/kev/train.py#L49) | 选项重排（permutation KL 的数据侧） |

---

## 四、与常见 LLM / Jev 对照

第三节列的是「Kev 有什么算子」，本节反过来问「同一个生成式 LLM 推理栈里的算子，Kev 有没有、被什么替代、对应哪个指标、开销落在计算还是访存」，并并列参照兄弟系统 Jev。三个维度合在一张表里：**存在性与替代**（常见 LLM / Kev / Jev 各一列）、**产出指标**、**计算·访存开销**。

一句话结论：**Kev 是 prefill-only 决策模型**，砍掉了整个「词表投影 + 采样解码 + 自回归循环」，用一个**指针读出**顶上；**Jev 是完整生成式决策系统**，保留全套解码算子——但它在本仓库是 **API 黑盒**（经 Vercel AI Gateway，由 `kev.jev` 打分），算子内部不可见，其指标是端到端的 JevBench 决策准确率而非逐 kernel，故 Jev 列一律标注为「黑盒推断」。

图例：✅ 与常见 LLM 一致 · ❌ Kev 砍掉 · 🔁 Kev 用自定义或融合算子替代。

| 算子（逻辑） | 常见生成式 LLM | Kev（✅/❌/） | Jev（黑盒推断） | 对应评测指标 | 计算 / 访存开销 |
|---|---|---|---|---|---|
| Embedding | 查表 token→向量 | ✅ 有（骨干自带，非自定义） | ✅ 有（骨干） | — | 访存（查表） |
| RMSNorm / LayerNorm | 每层归一 | 🔁 融合 `rms_norm` / `rms_norm_gated`（`fused_qwen35`） | ✅ 有（内部） | — | 访存 bound（已并入残差） |
| Linear / GEMM | 大量投影 + FFN | 🔁 单 GEMM 投影 `_concat` / `attention_forward` / `mlp_forward` | ✅ 大量 GEMM | 间接（决定 hidden 质量→accuracy） | 计算 bound，FLOPs 主体 2·m·n·k |
| RoPE 位置编码 | 有 | ✅ 有（`attention_forward` 内） | ✅ 有 | — | 轻，逐元素 |
| 注意力 Attention | 标准因果 `softmax(QKᵀ/√d)V` | 🔁 full_attention 层 SDPA + **块因果掩码** `branch_mask`；linear 层 DeltaNet `causal_conv1d` + `chunk_gated_delta_rule` | ✅ 标准注意力（黑盒） | isolation、permutation（掩码/隔离保证） | O(L²·d) 计算；flash 省显存 |
| 激活 SwiGLU / GeGLU | 有 | 🔁 融合 `swiglu` / `sigmoidglu` | ✅ 有 | — | 访存，已融合 |
| LM Head（词表投影） | hidden→vocab logits | ❌ 无——不加载 vocab head，取 `last_hidden_state` | ✅ 有（生成文本） | — | 大 GEMM（×vocab） |
| 采样 sample / top-k / top-p | 逐 token 生成 | ❌ 无解码采样；temperature 只做概率校准（`PointerHead` eval 除以 T） | ✅ 有（自回归生成） | Kev 侧→ECE（校准）；Jev 侧→生成质量 | 每步一次 launch |
| 输出读出 Readout | argmax / next-token | 🔁 **指针读出** `PointerHead.forward`/`many`：在选项边界 token 打分→softmax→选项概率 | ✅ 文本 / 决策输出 | accuracy、NLL、ECE、Brier、AURC、coverage | 极小（几个选项 token 的点积） |
| KV Cache | 自回归解码缓存，随 L 增长 | 🔁 `BufferKV` + **state-prefix 复用** `prefix`/`probs_and_prefix`（prefill 复用，非解码缓存） | ✅ 标准解码 KV cache | 正确性不变量（逐 fp32 位等价），不改指标 | 访存/显存，随 L 线性 |
| 自回归解码步 | 循环 N 次生成 | ❌ 无——prefill-only，一次前向 | ✅ 有 | — | Kev 省掉整个解码循环 |
| 训练损失 CE | next-token 交叉熵 | 🔁 `question_loss`（选项 CE / soft-target，可叠 `brier_w`/`focal`/`label_smoothing`/`ord_w`）+ `anchor_loss`（KL 锚定）+ `permuted_copy`（置换 KL） | 未知（黑盒） | 直接塑造 accuracy/ECE/Brier/RPS | 训练期 |
| 执行层 CUDA Graph | 可选（推理框架） | 🔁 `cuda_graphs`：`bucket`/`length_groups`/`CudaGraphs.states`/`rows`，把一次 pass 捕获成图重放 | 未知 | 不改数值（bf16 噪声级重结合） | 省 launch 开销 |

> 指标名取自 `kev.benchmark` 写出的 `report.json`（accuracy / ECE / Brier / NLL / coverage / AURC / permutation / isolation）。符号级定义与源码行链接见第三节。

---

## 五、小结

Kev 的「算子」本质是三类：

1. **自定义前向原语**（`model.py`）——块因果掩码 + 指针读出 + state-prefix 复用，这是它的研究贡献所在；
2. **对 flash-linear-attention Triton 融合核的接管**（`fused_qwen35.py`）——因果卷积、分块门控 delta、融合 norm/SwiGLU，`shared_prefix.py` 复用同批核但走可微分路径；
3. **执行层算子**——`cuda_graphs` 图捕获/重放、`predictors` SDPA 后端选择、`full_ft` fused AdamW master 优化器、`mlx_model` 的 Metal kernel。

贯穿三者的是同一条 **state → questions → probabilities** 单指针原语，以及 `kernel_environment` 对「一次读取跑在哪套 kernel 上」的可复现契约：融合与图路径相对 reference 只允许 bf16 噪声级的重结合差异，评测路径坚持 fp32-exact。

# 附录 A. 术语表

> 《Kev 基础知识系统学习指南》· 第四部分 路径与总结
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](18-cheatsheet.md) · [下一章 →](appendix-b-examples.md)

---


检索用：每条给出**英文原名（与代码里一致）→ 中文 → 一句定义 → 主要出现章**。定义一律以代码行为为准，不是行业惯例。

### A.1 数据与编码

| 英文（代码里） | 中文 | 定义 | 章 |
|---|---|---|---|
| record | 记录 | Kev 的唯一数据单元：一个 `state` + 1..N 个 `questions`，共享同一 state | 5 |
| state | 状态 | 被决策的事实文本（策略、上下文、文档）；一条 record 只有一份 | 5 |
| question / branch | 问题 / 分支 | 挂在同一 state 上的一条指令 + 一组选项；不生成文本 | 5 |
| variant | 变体 | 同一题的不同读数形式：`clean` / `none_absent` / `none_present` / `permuted` | 5, 15 |
| option boundary token | 选项边界 token | 每个选项前的不可伪造标记 token；`PointerHead` 只读这些位置 | 3, 7 |
| `<state>` | state 起始标记 | 编码时前缀的子串，**计入 state token 数**（长度预算与分桶都用它） | 3, 10 |
| encode() | 编码 | record → token/mask/位置信息的唯一入口（`kev/model.py`） | 3, 5 |
| none pair | 空选项对 | 训练增广：同一题造“正确项缺席”与“正确项在场”两兄弟行，迫使模型读 state | 5, 13 |

### A.2 架构与计算形式

| 英文 | 中文 | 定义 | 章 |
|---|---|---|---|
| block-causal mask | 块因果掩码 | state 全可见，题与题互不可见（段号 + 加性掩码） | 6 |
| option isolation | 选项隔离 | 把“其他题/其他选项”逐位隔开的开关（`--option_isolation`）；隔离是门控项 | 6, 13, 15 |
| row form | 行形式 | 每题一行（state 重复 N 次）；形式最直白，成本最高 | 8 |
| packed form | 打包形式 | 一 record 一次前向，靠 mask 隔离；与行形式在可验证的精度上等价 | 8 |
| shared prefix | 共享前缀 | state 只算一遍，题分支从它续上（递归状态、卷积状态与注意力 K/V 全携带） | 8, 13 |
| hybrid backbone | 混合骨干 | 注意力层 + 线性递归（GatedDeltaNet）混排的基座；决定哪些路径可用 | 8 |
| prefill-only | 仅前向 | 一次前向算完全部 token，**不做自回归生成** | 1, 7 |
| PointerHead | 指针头 | 在边界 token 的隐状态上做读出；`--head_dim` 是它的宽度 | 7 |
| TF32 | TF32 矩阵乘 | GPU 上的低精度 matmul；评估路径关掉它（它会搬 ~1e-3 的概率） | 15 |
| `ROW_PASS_TOKENS` | 长行规则阈值 | 一行超 16,384 token 则改走 flash/efficient kernel，预测带 `kernels: efficient` | 14 |

### A.3 概率与校准

| 英文 | 中文 | 定义 | 章 |
|---|---|---|---|
| temperature scaling | 温度校准 | 单参数 \(T\) 只改分布尖锐度，**不改 argmax** | 9 |
| inference_temperature | 服务温度 | 行里存的 logits 已是这个温度下的（反解 raw：乘回去） | 9, 15 |
| ECE | 期望校准误差 | 10 个置信箱的 \(\lvert acc_b - conf_b \rvert\) 加权；可正负抵消 | 10 |
| Brier | Brier 分 | 每行对选项求和的均方误差，**不除 \(K\)** | 10 |
| NLL | 负对数似然 | 有 logits 时 `logsumexp(z) − z_y`；否则带 1e-9 floor | 10 |
| choice_confidence | 选项置信度 | \((p_{max} - 1/K)/(1 - 1/K)\) | 10, 14 |
| score_confidence | 等级置信度 | \(\max(0, 1 - \mathbb{E}\lvert level - mode \rvert / D)\) | 10, 14 |
| coverage_at_error | 误差预算下的覆盖率 | 经验曲线上误差≤预算的最大接受占比；**不是部署保证** | 10 |
| AURC | 风险-覆盖率下面积 | 右阶梯、整组进出的曲线下面积 | 10 |
| calibration by length | 分长度校准 | 按 state token 分桶的 acc/ECE/Brier/自信错；rounds 面板可 `by_length` | 10, 16 |

### A.4 统计与评估

| 英文 | 中文 | 定义 | 章 |
|---|---|---|---|
| record-clustered paired bootstrap | 按 record 聚簇的配对重抽样 | 同 record 的兄弟行同进同出；2,000 次、seed 0、micro | 11 |
| CI / 下界判据 | 区间 / 判据 | 比较看差值区间，不是看均值点；判据常写“下界 ≥ 阈值” | 11, 16 |
| objective | 目标分 | \(-\operatorname{mean}_{task}(nll)\)；单个数排序用，不是准确率 | 15 |
| permutation gate | 序门控 | 选项顺序重排后的 `mean_max_delta` 与 `flip_rate` | 15 |
| mechanism_checks | 机理检查 | packed / solo / with_sibling 三次前向对比（前 8 条 clean）；隔离与打包的直证 | 15 |
| GATES | 门控集 | `experiment.py` 的八项（含 `isolation_tolerance` 0.001）；不过就不是候选 | 15 |
| kernel_environment | 内核环境 | 读数依赖的内核集合（版本/GPU/dtype/attention/forward 绑定）；比较前先对这块 | 15 |
| metric_policy | 指标口径版本 | `report.json` 里逐条写明分母、floor、整组规则的那块（v2） | 15 |

### A.5 数据纪律与流水线

| 英文 | 中文 | 定义 | 章 |
|---|---|---|---|
| frozen suite / manifest | 冻结套件 / 清单 | `evals/<ver>/<suite>/` + 逐分区 sha256；套件不可变 | 12 |
| partition | 分区 | train / calibration / development / test；四者用途不可互串 | 12 |
| suite_sha256 | 套件哈希 | `digest(manifest)`；配对比较两侧必须相等 | 12, 15 |
| eval-only suite | 仅评测套件 | breadth-v1 / longdoc-v1 / tasksource-heldout-v1 等；**永不进训练 corpus** | 12 |
| locked test | 锁定的测试分区 | 只能用 `--allow-test` 读，且一个 checkpoint 只能读一次 | 12 |
| REMOVED_SUITES | 已移除套件 | 4 个因“不适合当门控”而移除的套件；读了会带理由报错 | 12 |
| admission / ContextOverflow | 准入 / 上下文溢出 | state 65,536、单行 73,728；超 → 422，不静默截断 | 14 |
| PrefixCache | 前缀缓存 | state 前缀的 LRU；size/min_tokens/max_tokens 三条边界 | 14 |
| study / plan / trial | 研究 / 计划 / 试验 | 一轮里的一组配置；trial 是一个具体 checkpoint 配方 | 16 |
| arm / parent | 臂 / 父臂 | 一次比较的两边：候选与基准（臂可以是 checkpoint，无 trial） | 16 |
| read tag / panel | 读数标签 / 面板 | 一个标签对应一个套件；面板把多个读数归成一个比较集 | 16 |
| temperature pool | 温度池 | 把多个读数的行汇起来拟合一个 T；必须与训练数据不相交 | 16 |
| criteria / rank / candidates | 判据 / 排序 / 候选 | 判据在配对区间上求值；候选可以一个都没有，这是常态 | 16 |
| confirm stage | 确认阶段 | 分阶段的终审（如 locked）；无人会话**从不** confirm | 16 |
| resume point / snapshot | 续跑点 / 快照 | 前者含优化器状态，后者是可加载 bf16 checkpoint；最多 8 个，写了不删 | 13 |
| LoRA / full fine-tune | 低秩适配 / 全权重 | `--lora` 与 `--full_ft 1`；两条路径的预算与内存语言完全不同 | 13 |
| anchor | 锚定损失 | KL 向冻结基座的零样本答案（`--anchor_w`）；发布配方里不用 | 13 |
| WiSE-FT interpolation | 权重插值 | 两个同基座 checkpoint 的线性混合（rounds 里的“checkpoint 臂”） | 16 |

---

[⌂ 目录与架构图](../index.html) · [← 上一章](18-cheatsheet.md) · [下一章 →](appendix-b-examples.md)

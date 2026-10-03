---
language: en
license: apache-2.0
library_name: peft
base_model: Qwen/Qwen2.5-0.5B
pipeline_tag: text-classification
tags:
  - decision-model
  - calibration
  - lora
  - multiple-choice
  - typesafe
  - prototype
datasets:
  - legacy-datasets/banking77
  - google/boolq
  - fancyzhx/ag_news
  - nyu-mll/multi_nli
  - SetFit/sst5
  - Yelp/yelp_review_full
metrics:
  - accuracy
  - expected_calibration_error
  - nll
model-index:
  - name: Kev-0.5B
    results:
      - task: { type: text-classification, name: typed decision (choice / noul / score) }
        dataset: { type: mixed, name: "held-out split of the six training sources (1,350 questions)" }
        metrics:
          - { type: accuracy, value: 0.799 }
          - { type: expected_calibration_error, value: 0.065, name: "ECE (10 bins)" }
          - { type: expected_calibration_error, value: 0.031, name: "ECE after temperature scaling (T=1.47)" }
---

<p align="center">
  <a href="./kev-0.5b_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./kev-0.5b.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>


# Kev-0.5B — 原型（已被取代）

Kev-0.5B 是一个**决策模型**。它接收一篇文档（即 *state*，状态）和一组带类型的问题，并在一次前向传播中为每个问题返回一个概率分布。它不生成文本。

它是一个 LoRA 适配器加上一个小型指针头（pointer head），建立在 `Qwen/Qwen2.5-0.5B` 之上。它复现了 Archer Hume 在 [*Jev's Architecture Unmasked*](https://archerhume.com/posts/jevs-architecture-unmasked) 一文中推断出的 Jev（TypeSafe 系统）架构，并服务于 TypeSafe 公开接口 `/v1/systemone` 的 API 契约。

该检查点是**最初的原始原型**，于 2026 年 9 月在一台笔记本电脑上训练完成，用以证明该机制可行。它已被 [Kev-0.8B](kev-0.8b.md)、[Kev-4B](kev-4b.md) 和 [Kev-9B](kev-9b.md) 取代——后者使用 Qwen3.5 基座、冻结并做校验和（checksummed）的测试套件，以及通过约 110 次受控试验找到的训练配方；在相同的域外样本（transfer-v4 dev）上，本模型得分为 0.561，而它们分别为 0.643 / 0.794 / 0.812.620 / 0.790 / 0.796。它保留在 Hub 上仅供参考与复现使用；其他任何用途请使用当前的模型家族。

- Hub：[jaredpalmer/kev-0.5b](https://huggingface.co/jaredpalmer/kev-0.5b)（标签 `v0.1`）
- 代码、训练配方、评估与演示：[github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)
- 权重：[GitHub release `v0.1.0`](https://github.com/jaredpalmer/kev/releases/tag/v0.1.0)，`kev-0.5b.tar.gz`（38 MB；LoRA 适配器 `adapter_model.safetensors`、头 `head.pt`、tokenizer 文件、`eval.json`、训练日志）。SHA-256 `15639f79…6e12f8`，完整摘要见附属文件 `.sha256`。解压至 `runs/kev/`。权重不提交到 git。

## 模型详情

| | |
|---|---|
| 开发者 | Jared Palmer，与 Devin（Cognition）合作 |
| 模型类型 | 因果 transformer，仅预填充（prefill-only），块因果分支掩码（block-causal branch mask），指针读出（pointer readout） |
| 基座模型 | `Qwen/Qwen2.5-0.5B`（4.94 亿参数，冻结） |
| 适配器 | LoRA rank 16，alpha 32，dropout 0.05，作用于 `q_proj k_proj v_proj o_proj gate_proj up_proj down_proj`（全部 24 层） |
| 头 | 两个线性映射 `896 → 256`（query 来自 `<decide>`，key 来自每个 `</opt>`），缩放点积，对选项做 softmax |
| 可训练参数 | 930 万（LoRA 880 万 + 头 46 万），占主干网络的 1.9% |
| 精度 | fp32（在 Apple MPS 上训练与推理） |
| 训练所用上下文 | 状态 token ≤ 384，每个问题分支 token ≤ 1,024 |
| 推理允许的上下文 | 每个分支 8,192（主干网络支持 32k） |
| 问题类型 | `noul`（是/否）、`choice`（2–255 个选项）、`score`（2–255 个有序等级） |
| 语言 | 英语 |
| 许可证 | 适配器与头为 Apache-2.0。基座模型采用 Qwen 许可证（Qwen2.5-0.5B 为 Apache-2.0）。数据集各自带有其许可证。 |
| 版本 | Kev-0.5B v0.1，训练于 2026-09-17 |

## 预期用途

**预期用途。** 关于决策模型的研究：直接概率读出的校准、共享状态 / 隔离问题的注意力、选项顺序敏感性，以及与 TypeSafe 的 System One 契约在 API 层面的兼容性。本地演示与教学。

**非预期用途。** 任何影响人的生产决策：审核、反欺诈、信贷、招聘、医疗或法律路由。该模型的知识受限于 0.5B 的主干网络，其校准仅在训练分布上得到验证，而在不熟悉任务上的输出尚未经过测量。

## 模型的使用方式

输入是一段打包好的 token 序列：

```
<state> …state…  <q> instr <opt> o1 </opt> <opt> o2 </opt> … <decide>  <q> … <decide>  …
```

- 注意力掩码让某个问题 token 只能看到状态和它自己的分支。问题之间互相不可见。
- 每个分支在状态之后重新启动 position id。
- 对于每个问题，头将每个 `</opt>` 的隐藏状态与 `<decide>` 的隐藏状态打分，并应用 softmax。
- 应用层代码将概率分布转换为 API 答案：Choice 对应 `choice`/`confidence`，Noul 对应 `p(yes)`，Score 对应期望等级。

保留的 token 为现有的 Qwen 特殊 token（`<|fim_prefix|>`、`<|fim_middle|>`、`<|box_start|>`、`<|box_end|>`、`<|fim_suffix|>`）。用户输入会经过净化处理，使其无法产生这些 token。

使用 `python -m kev.serve --run runs/kev` 启动服务并调用 `POST /v1/systemone`，或使用 `typesafe-sdk` 并将 `base_url="http://127.0.0.1:8009"`。

## 训练数据

六个公开数据集，转换为 TypeSafe 形态的请求，并使用与服务时相同的代码路径（`api.to_record()`）渲染。每个数据源从标准 **train** 切分中采样 1,500 条记录，得到 9,000 条记录与 13,500 个问题（4,500 个 Choice、6,000 个 Noul、3,000 个 Score）。

| 数据源 | 切分 | 转换为 | 备注 |
|---|---|---|---|
| Banking77 | train | Choice，K = 77 | 意图名作为选项键；模板化描述，50% 为 `null` |
| BoolQ | train | Noul | 段落作为状态；40% 带 `true`/`false` 判据 |
| AG News | train | Choice K = 4 + 2 Noul | 派生的是非问题与主题问题打包在一起 |
| MNLI | train | Choice K = 3 | 前提作为状态，假设写入指令 |
| SST-5 | train | Score，5 个等级 | |
| Yelp Review Full | train | Score 5 等级 + Noul | 文本截断至 220 词；`recommend` = 星级 ≥ 4 |

在转换时应用的渲染变化：约 30% 的 `null` 选项描述、约 10% 的结构化 `{"what": …}` 描述、约 15% 的结构化 `{"question", "focus"}` 指令、约 32% 的状态被包装为对象或数组（`{"document"}`、`{"ticket": {"channel","body"}}`、`[{"role","content"}]`）。

在编码前对每条记录应用一次增强：打乱选项顺序；以 0.10 的概率将正确选项替换为 `other: None of the above`；以 0.15 的概率加入一个无关干扰项选项。

没有使用 LLM 生成的数据。除原始数据集外没有人工标注。

## 训练过程

| | |
|---|---|
| 目标函数 | 对选项的交叉熵，在一条记录内的各问题间取平均 |
| 优化器 | AdamW，lr 2e-4，weight decay 0.01，OneCycle 调度（10% 预热） |
| 批次 | 每步 1 条记录，梯度累积 8，梯度裁剪 1.0 |
| 轮数 | 2（2,250 个优化器步） |
| 硬件 | Apple M5，32 GB 统一内存，PyTorch 2.8 MPS 后端 |
| 实际耗时 | 约 1 小时 45 分（每条记录约 0.29 秒） |
| 随机种子 | 0 |
| 最终训练损失 | 0.27 |

该检查点早于 `kev/train.py` 中现已作为默认的两项损失项：面向 Score 的有序项（`--ord_w`）和面向 Choice 的排列一致性 KL（`--perm_kl`）。要精确复现该检查点：

```bash
uv run python -m kev.train --n_per_source 1500 --epochs 2 --accum 8 --perm_kl 0 --ord_w 0 --out runs/kev
```

注意，增强现在是在每个 epoch 重新应用，而非在编码时固定，因此重新运行不会逐位一致。

## 评估

相同的六个数据源留出 **test / validation** 切分，每数据源 150 条记录，共 1,350 个问题，种子 1。完整结果见 `runs/kev/eval.json`。

### 准确率与校准

| 数据源 | K | 零样本基座 | 零样本 Instruct | **Kev-0.5B** |
|---|---|---|---|---|
| | | acc / ECE | acc / ECE | acc / ECE / NLL |
| banking77 | 77 | – | – | 0.860 / 0.057 / 0.56 |
| agnews | 4 | 0.813 / 0.069 | 0.787 / 0.160 | 0.940 / 0.028 / 0.22 |
| agnews yes/no | 2 | 0.780 / 0.103 | 0.853 / 0.062 | 0.960 / 0.017 / 0.10 |
| boolq | 2 | 0.427 / 0.274 | 0.607 / 0.084 | 0.753 / 0.136 / 0.63 |
| mnli | 3 | 0.460 / 0.225 | 0.433 / 0.390 | 0.747 / 0.100 / 0.63 |
| sst5 | 5 | 0.373 / 0.083 | 0.447 / 0.344 | 0.533 / 0.121 / 1.17（MAE 0.59 个等级） |
| yelp | 5 | 0.313 / 0.043 | 0.353 / 0.078 | 0.553 / 0.118 / 0.95（MAE 0.54 个等级） |
| yelp yes/no | 2 | 0.833 / 0.129 | 0.833 / 0.066 | 0.887 / 0.084 / 0.33 |
| **all** | | | | **0.799 / 0.065** |

基线：`Qwen/Qwen2.5-0.5B`（原始）与 `Qwen/Qwen2.5-0.5B-Instruct`（chat 模板），使用相同的渲染文本，对选项字母 A–H 的下一 token 逻辑值（logits）；K = 77 时未运行。ECE 使用对最高概率的 10 个等宽分箱。

### 温度缩放

在偶数索引记录上拟合，在奇数索引记录上测试：`T = 1.47`。留出 NLL 0.505 → 0.481，ECE 0.057 → **0.031**。该模型在缩放前存在轻微过度自信。

### 机制测试

| 测试 | 结果 |
|---|---|
| 隔离性（密钥位于兄弟问题中 / 缺失 / 位于状态中） | p = 0.03 / 0.03 / **0.99** |
| 打包 vs 分开，最大绝对概率差 | 3.7e-6（打包快 2.0×，每个请求约 2.7 个问题） |
| 排列，4 种顺序，Choice K ≥ 3 | argmax 翻转 7.4%；p(correct) 的平均极差 0.065，p90 为 0.25 |
| IIA，追加一个无关选项 | 前 2 名的平均 \|Δ log-odds\| = 0.13，p90 为 0.34 |
| 边界伪造，选项文本带虚假分隔符 | 选项数量不变；被伪造选项 p ≤ 0.09 |

## 局限性

- **仅限分布内。** 以上所有数字均来自训练数据集的留出切分。该检查点的域外泛化尚未测量。
- **主干网络小。** 5 亿参数。在 TypeSafe 文档的结构化判据示例中，模型选择了 `return_policy`，而 Jev 选择的是 `return_status`。阅读理解（BoolQ 0.75、MNLI 0.75）远低于当前最优水平。
- **任务覆盖面窄。** 六个数据集和约十个指令模板。代码、表格、多轮对话、算术以及多步条件均未经训练。
- **顺序敏感性仍然存在。** 在选项重排下，argmax 翻转率为 7%，概率的 p90 极差为 0.25。靠近决策边界的阈值可能会改变动作。
- **Score 置信度**由服务代码计算，而非检查点。在本卡片撰写时其公式为 `1 − E|level − mode| / (L − 1)`；现已改为 `max(0, 1 − E|level − mode| / D)`，其中 D 为等级上均匀分布的平均绝对偏差，如 TypeSafe 的参考适配器（`system-one-adapter` 0.2.1）所示。
- **校准不是保证。** 在这些数据源上温度缩放后的 ECE 0.03，对新工作流的校准情况毫无说明。正确的评分规则只提供正确的*激励*；它们并不能消除对结果数据的需求。
- **继承自** Qwen2.5-0.5B 与数据集的局限性，包括它们的标签噪声、人口统计学偏差（如 Yelp、银行意图）以及仅支持英语。

## 偏差、风险与建议

训练集带有其来源的偏差：以美国为中心的新闻类别、英语银行术语、餐厅评论以及众包 NLI 标签。模型会反映这些偏差。

直接的概率输出看起来很权威。来自该模型的 `confidence: 0.92` 是关于其对三个选项自身分布的统计量，而非已验证的正确概率。在没有先在你自己的标注结果上测量校准之前，不要据此设置阈值用于重大决定。

问题隔离特性是一项真正的安全特性（一个问题的文本无法操纵另一个问题的答案），并已得到验证。针对五个保留 token 的分隔符伪造防护也已得到验证。其他通过状态文本的提示注入（prompt-injection）途径尚未研究。

## 环境影响

一次训练运行：在单台 Apple M5 笔记本 SoC 上约 1.75 小时，功率约 30–40 W，即约 0.06 kWh。评估与冒烟运行增加相近的用量。这个量很小。

## 引用

```bibtex
@software{kev2026,
  title  = {kev: a laptop-scale reconstruction of a Jev-style decision model},
  author = {Palmer, Jared},
  year   = {2026},
  url    = {https://github.com/jaredpalmer/kev}
}

@misc{hume2026jev,
  title  = {Jev's Architecture Unmasked},
  author = {Hume, Archer},
  year   = {2026},
  url    = {https://archerhume.com/posts/jevs-architecture-unmasked}
}
```

## 联系方式

在 [github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev/issues) 提交 issue。

<p align="center">
  <a href="./README_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./README.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# kev-finetune

在你的自己的问题上微调一个开放的 Jev 风格决策模型，得到校准概率，并把它作为一个 TypeSafe System One 端点来服务。你的机器上不需要 GPU；一切都在 Modal 上、通过六个短脚本运行。

`SKILL.md` 是本页面对 agent 友好的版本。用以下命令把它安装到你的编码 agent 中：

```bash
npx skills add jaredpalmer/kev@kev-finetune
```

然后说「fine-tune Kev on my support tickets（在我的支持工单上微调 Kev）」。该 agent 会面试你、找到你的代码已经在问的问题、生成数据、训练、把数字展示给你、部署并清理。本页其余部分是人类使用的同一份配方。

## What you need（你需要什么）

- Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)；为 [Modal](https://modal.com) 账户执行一次 `uvx modal setup`（在 H100 上训练一次 Kev-4B 大约花费 $1；在 L4 上服务会缩放到零）。
- 可选：一个 OpenAI 兼容的 API key，用于生成训练数据（用 gpt-4.1-mini 大约每 1000 条记录 $0.25）。

## The recipe（配方）

1. **描述决策**，写在 `workload.json` 中：输入，以及 System One 形状的问题（`noul` 是非/否、`choice` 是具名选项、`score` 是有序等级）。从 `assets/workload.example.json` 开始。如果你的代码已经在调用 Jev / TypeSafe，用 `python3 scripts/extract_workload.py path/to/repo --out workload.json` 从调用点起草它。
2. **确定数据集大小**：`python3 scripts/plan_size.py workload.json` 会告诉你要多少条记录才能让相对于已发布模型的可测量 +5 点提升（大约每记录三个问题需要 1000 条）。
3. **获取带标签的记录**（见 `references/data-generation.md`）：
   - 从你已有的数据：`python3 scripts/convert_data.py workload.json tickets.csv --state body --label team=dept --out data/x.real.jsonl`
   - 从 LLM：`KEV_GEN_API_KEY=... python3 scripts/generate_data.py workload.json --n 1000 --out data/x.jsonl --examples data/x.real.jsonl`
4. **划分**：`python3 scripts/split_data.py data/x.jsonl --out data/x [--holdout data/x.real.jsonl]`。
5. **训练 + 校准 + 打分**：`modal run scripts/kev_modal.py::train --data data/x --name x-v1 --init-from jaredpalmer/kev-4b`。打印 baseline 对比 fine-tuned、原始对比校准；写入 `runs/x-v1/result.json` 和 `errors.jsonl`。
6. **部署**：`KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=x-v1 modal deploy scripts/kev_modal.py`，然后把你的 TypeSafe 客户端的 `base_url` 指向打印出来的 URL（`references/deploy.md`）。
7. **拆除（Tear down）**：`modal run scripts/kev_modal.py::teardown --everything --yes`。

在 3 和 5 之间迭代：读 `errors.jsonl`，收紧 spec 中的标注规则，加记录，作为 `x-v2` 重新训练，`modal run scripts/kev_modal.py::compare --a x-v2 --b x-v1`。`references/hill-climbing.md` 解释了每一个数字。

## Why fine-tune at all（到底为什么要微调）

已发布的 Kev checkpoint 已经能零样本地回答这些问题，而且 `train` 会为你给那个 baseline 打分。微调在一个特定工作负载上增加的是 (a) 在你的 label 上的 accuracy，以及 (b) 为你的数据拟合的一个 temperature，这样你用作阈值的置信度名副其实。在示例工作负载上（`assets/workload.example.json`：支持工单、三个问题、1050 条生成记录、在 H100 上 15 分钟）Kev-4B 的 accuracy 从 67.7% 提升到 73.6%（提升的 95% CI 为 +2.3 到 +9.7 点），Brier 从 0.402 降到 0.330，并且从在 5% 误差预算下自动化 34% 的决策提升到 48%，而在公开评估数据上没有变化。用 400 条记录时同样的提升落在噪声之内，这正是配方先把数据集定好的原因。一个托管的模型无法为你的数据重新校准；这就是全部论据。

## Layout（布局）

```
SKILL.md                      agent 指令（phases、interview、gotchas）
scripts/extract_workload.py   在一个代码库中找 Jev/TypeSafe 调用和带标签的文件；起草 spec
scripts/convert_data.py       CSV/JSONL 带标签 -> Kev 记录
scripts/generate_data.py      spec -> 通过 OpenAI 兼容模型得到带标签的记录
scripts/plan_size.py          一次显著比较需要多少记录；从 result.json 事后计算
scripts/split_data.py         验证 + 按状态划分（可选的真实留出）
scripts/kev_modal.py          Modal app：validate、train、evaluate、compare、pull、publish、teardown、Serve
references/                   data-format、data-generation、hill-climbing、deploy
assets/workload.example.json  一份可复制的完整 spec
```

这些脚本是标准库 Python（外加 `modal`），并且故意写得短：当你的用例不合适时，去编辑它们。

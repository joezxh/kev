<p align="center">
  <a href="./README_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./README.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# Kev

你可以自己训练并运行的小型 Jev 式决策模型。

<p>
  <a href="https://github.com/jaredpalmer/kev/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/jaredpalmer/kev/ci.yml?style=for-the-badge&labelColor=000000" height="28"></a>
  <a href="https://huggingface.co/collections/jaredpalmer/kev-6aad9d0ea49f2589665e07cd"><img alt="Weights: Kev-0.8B · 4B · 9B · 27B" src="https://img.shields.io/badge/WEIGHTS-0.8B%20%C2%B7%204B%20%C2%B7%209B%20%C2%B7%2027B-0a0a0a.svg?style=for-the-badge&labelColor=000000" height="28"></a>
  <a href="https://huggingface.co/spaces/jaredpalmer/kev"><img alt="Demo on Hugging Face Spaces" src="https://img.shields.io/badge/DEMO-HF%20Spaces-0a0a0a.svg?style=for-the-badge&labelColor=000000" height="28"></a>
  <a href="https://huggingface.co/datasets/jaredpalmer/kev-suites"><img alt="Frozen eval suites" src="https://img.shields.io/badge/EVAL%20SUITES-frozen-0a0a0a.svg?style=for-the-badge&labelColor=000000" height="28"></a>
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-0a0a0a.svg?style=for-the-badge&labelColor=000000" height="28"></a>
</p>

Kev 是一系列基于 Qwen3.5 和 Qwen3.8 构建的小型决策模型，架构来源于 [Jev's Architecture Unmasked](https://archerhume.com/posts/jevs-architecture-unmasked) 一文的描述。你可以使用预训练权重，也可以训练自己的模型。其 API 与 TypeSafe 的 [System One](https://docs.typesafe.ai/api) 一致，因此你可以把他们的 Python SDK 指向你本地的服务器。

## Highlights（亮点）

- 在一次请求中同时提出是/否（`noul`）、多选（`choice`）和评分（`score`）问题。这些问题共用同一段文本，但彼此之间无法读取对方。
- 默认提供经过校准的概率：每个 checkpoint 都附带一个拟合好的温度（temperature）。
- 可直接替代 Jev：TypeSafe 的 Python SDK 无需改动即可对接 Kev 服务器。
- 四个规格，作为 Kev 1.0 统一发布：从能在笔记本电脑上运行的 0.8B，到为单张数据中心 GPU 准备的 27B。
- 支持最长 65,536 个 token 的文档，可在 CUDA 上运行，也可通过 MLX 在 Apple Silicon 上运行。每个模型卡都会说明文档长度达到多少时准确率开始下降。
- 可在你自己的标注样本上进行微调。一个编码代理（coding-agent）skill 可在 Modal 上跑完整个循环，从寻找你的问题到提供最终服务。
- 一条命令即可部署你自己的 HTTPS 端点。空闲时自动缩容到零。
- 先在浏览器里试用：[huggingface.co/spaces/jaredpalmer/kev](https://huggingface.co/spaces/jaredpalmer/kev)。

## Models（模型）

从 Kev-4B 开始。如果你有更大的 GPU，可以升级到 Kev-9B；如果你有一张 80 GB 的 GPU 并想要最准确的 Kev，就升级到 Kev-27B。当体积比准确率更重要时，使用 Kev-0.8B。

| Model | Base（基础模型，含许可证） | Runs on: CUDA | Runs on: Mac（MLX） | Validated context（已验证上下文） | Held-out datasets: index（留出数据集指数） | Card（模型卡） |
|---|---|---|---|---|---|---|
| [Kev-0.8B](https://huggingface.co/jaredpalmer/kev-0.8b) | Qwen3.5-0.8B-Base（Apache-2.0） | L4，任意 4 GB GPU | 任意 Apple Silicon Mac；实测至 65k tokens | 8,192 | 23.3 | [Details](docs/model-cards/kev-0.8b.md) |
| [Kev-4B](https://huggingface.co/jaredpalmer/kev-4b) | Qwen3.5-4B-Base（Apache-2.0） | L40S，H100 | 32 GB Mac；实测至 65k tokens | 8,192 | 38.0 | [Details](docs/model-cards/kev-4b.md) |
| [Kev-9B](https://huggingface.co/jaredpalmer/kev-9b) | Qwen3.5-9B-Base（Apache-2.0） | L40S，H100 | 32 GB 或更大 Mac（预期，未实测） | 8,192 | 41.0 | [Details](docs/model-cards/kev-9b.md) |
| [Kev-27B](https://huggingface.co/jaredpalmer/kev-27b) | Qwen3.8-27B，post-trained（Apache-2.0） | B200，H200，H100 80 GB | 96–128 GB Mac（预期，未实测） | 65,536 | **52.3** | [Details](docs/model-cards/kev-27b.md) |
| Jev | Hosted（托管） | TypeSafe 的 API | – | – | 54.0 | – |

"Held-out datasets"（留出数据集）是社区 Decision Index 的机会校正（chance-corrected）指数，在 `breadth-v1` 的测试切分上打分：五个领域共 14 个公开数据集，没有任何 Kev 在训练时见过。 "Validated context"（已验证上下文）指一段文档在保证真实合同（CUAD）上的准确率保持在同模型 8k tokens 准确率 3 个百分点以内（取 95% 下界）时的最长 token 数；每个模型卡都有按长度测量的数据。

| Model | Accuracy: New Sources（新来源准确率） | Accuracy: Trained Sources（已训练来源准确率） | Brier: New Sources（新来源 Brier 分数） |
|---|---|---|---|
| Kev-0.8B | 0.648 / 0.697 | 0.827 / 0.838 | 0.481 / 0.416 |
| Kev-4B | 0.817 / 0.838 | 0.873 / 0.865 | 0.269 / 0.242 |
| Kev-9B | 0.820 / 0.852 | 0.874 / 0.873 | 0.289 / 0.217 |
| Kev-27B | **0.851 / 0.889** | 0.865 / 0.866 | **0.225 / 0.156** |
| Jev | 0.857 / – | 0.845 / – | 0.211 / – |

每个单元格为 **development / test**（开发集 / 测试集）。"New sources"（新来源）指 Kev 在训练时从未见过的、数据集和策略规则。它最接近你自己的问题。"Trained sources"（已训练来源）指来自 Kev 所训练数据集的留出（held-out）样本。我们使用开发集挑选 checkpoint，并且每个已发布的模型只对每个测试集读取一次。Jev 目前只在这两套数据的开发集上跑过。Brier 分数对整个概率分布打分，而不只是对最优答案；越低越好。

在新来源上，Kev-27B 与 Jev 差距在一个百分点以内（0.851 对比 0.857），Kev-4B 和 Kev-9B 在四个百分点以内。我们不知道 Jev 训练了什么数据，因此这不是对两种架构的受控对比。[What to Expect](#what-to-expect) 说明了 Kev 在哪些方面与 Jev 一样好、在哪些方面不如。

Kev-0.8B、4B 和 9B 都从 Qwen 基础模型出发，并共用同一套训练方案：在冻结的基础模型上加一个小适配器（adapter）。Kev-27B 从 Qwen 的 post-trained（训练后）版本出发，我们不知道它训练了什么；它的每个权重都经过微调，因此它以 51 GB 的完整权重而非适配器的形式发布。每个模型卡都包含完整方案、所有结果，以及以 Hub tag 形式保留的早期版本。

## Kev 1.0

上面的四个模型作为 Kev 1.0 一起发布。每个 Hub repo 都有一个 `v1.0` tag，因此 `--run jaredpalmer/kev-4b@v1.0` 总是加载同一份权重，并且 GitHub release [`kev-1.0`](https://github.com/jaredpalmer/kev/releases/tag/kev-1.0) 带有 0.8B、4B 和 9B 的 checkpoint 以及 SHA-256 校验和。Kev-27B 的 51 GB 权重对于 release 资产来说太大，仅存放在 Hub 上。

| Model | Hub revision of the weights（权重的 Hub 版本） | Temperature（温度） | Trained on states up to（训练时状态 token 上限） |
|---|---|---|---|
| Kev-0.8B | `9a45d25e` | 2.35 | 7,552 tokens |
| Kev-4B | `139fdd94` | 2.41 | 7,552 tokens |
| Kev-9B | `b5d8c18e`（v2） | 2.19 | 7,552 tokens |
| Kev-27B | `28be62e9`（v2，完整权重） | 1.32 | 32,768 tokens |

Kev 1.0 没有训练任何新东西。它锁定了下一代 Kev 将与之对比的 checkpoint、模型卡、评估套件和服务代码。[release notes](docs/releases/kev-1.0.md) 列出了自上一个家族版本以来的变更，以及已知表现不佳的部分。

## Quick Start（快速开始）

### Try It in the Browser（在浏览器中试用）

[Hugging Face Space](https://huggingface.co/spaces/jaredpalmer/kev) 运行 Kev-4B 和 Kev-0.8B，无需安装任何东西。

### Run It Locally（在本地运行）

你需要 Python 3.12 或 3.13，以及 [uv](https://docs.astral.sh/uv/)。仓库的 `.python-version` 会让 `uv sync` 使用 3.13；torch 目前还没有 3.14 的 wheel。

```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev
uv sync --extra serve
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b --port 8009
```

这会在你的机器上启动 Kev-4B：如果你有 GPU，则使用 CUDA 或 ROCm；在 Apple Silicon 上使用 MLX。首次运行会下载适配器和基础模型。`--run` 也接受本地 checkpoint 目录或 Hub 版本，例如 `jaredpalmer/kev-4b@qwen3`。

在另一个终端里，向它发送一张工单：

```bash
curl -s localhost:8009/v1/systemone -H 'content-type: application/json' -d '{
  "state": "Shoes arrived two weeks late and in the wrong size. Also I see two charges on my card.",
  "model": "kev-latest",
  "questions": {
    "department":  {"type": "choice", "instructions": "Which team should handle this?",
                    "criteria": {"returns": "Exchanges, refunds, wrong or damaged items",
                                 "shipping": "Delivery status, delays, lost packages",
                                 "billing": "Charges, invoices, payment problems"}},
    "escalate":    {"type": "noul",  "instructions": "Does this need urgent human attention?"},
    "frustration": {"type": "score", "instructions": "How frustrated is the customer?",
                    "criteria": ["Calm", "Frustrated", "Very angry"]}
  }}'
```

在 Apple M5 上以 bf16 运行时的 Kev-4B 示例响应：

```json
{
  "model": "kev-latest",
  "answers": {
    "department":  { "type": "choice", "choice": "returns", "confidence": 0.21,
                     "probabilities": { "returns": 0.47, "shipping": 0.28, "billing": 0.25 } },
    "escalate":    { "type": "noul", "noul": 0.93 },
    "frustration": { "type": "score", "score": 1.44, "confidence": 0.34,
                     "legend": { "0": "Calm", "1": "Frustrated", "2": "Very angry" },
                     "probabilities": { "0": 0.00, "1": 0.56, "2": 0.44 } }
  },
  "usage": { "input_tokens": 101, "output_tokens": 161 },
  "latency_ms": 495
}
```

这张工单提到了退货、延迟送达和账单问题，部门概率也说明了这一点。这正是 Kev 返回概率而非单个标签的原因：你的代码可以路由那些高置信度的情形，并把其余的交给人工处理。

### Use It From Python（从 Python 使用）

如果你已经在调用 Jev，把你的客户端指向 Kev，其余代码保持不变即可。`uv sync --extra serve` 已包含 TypeSafe SDK：

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

client = TypeSafeClient(
    api_key="local",
    base_url="http://127.0.0.1:8009",
    model="kev-latest",
)
response = client.system_one(
    state="I was charged twice. Please fix this ASAP.",
    questions={
        "billing": Noul(instructions="Is this ticket about billing?"),
        "tone": Choice(
            instructions="What is the customer's tone?",
            criteria={"calm": None, "frustrated": None, "angry": None},
        ),
        "urgency": Score(
            instructions="How urgent is this ticket?",
            criteria=["can wait", "this week", "today"],
        ),
    },
)
print(response.nouls["billing"].noul)
print(response.choices["tone"].choice)
print(response.scores["urgency"].score)
```

## Fine-Tune on Your Own Data（在你自己的数据上微调）

已发布的模型是在公开数据集和生成的策略样本上训练的。如果你的问题形态不同，比如你自己的路由分类、你自己的升级（escalation）规则或另一种语言，那么一次简短的微调通常比任何 prompt 改动都更有帮助。它还会把温度拟合到你的数据上，因此你用来设定阈值的置信度，是在你自己的标签上测量出来的。

预期效果：在一个示例客服工作负载上（三个问题、1,050 条生成记录、在 H100 上 15 分钟），微调将 Kev-4B 的准确率从 67.7% 提升到 73.6%，并在 5% 错误预算下能自动处理的决策占比从 34% 提升到 48%（[details](skills/kev-finetune/README.md#why-fine-tune-at-all)）。在真实数据上，对 5,219 条标注的消费金融投诉跑一个 epoch，Kev-4B 在它从未见过的投诉上准确率从 0.804 提升到 0.904。这类提升都属于同分布（in distribution）：它们说明的是 Kev 学习你任务的能力，而非它在其他所有事情上的表现。先确定你的数据集规模。在仅有 400 条记录的情况下，在示例工作负载上的提升落在了噪声范围内。

### With a Coding Agent（使用编码代理）

```bash
npx skills add jaredpalmer/kev@kev-finetune
```

然后让你的 agent "fine-tune Kev on my support tickets"（在我的客服工单上微调 Kev）。[`kev-finetune` skill](skills/kev-finetune/) 会先与你沟通，找到你代码已经在向 Jev 或 TypeSafe 提出的问题，转换你已有的标签，或用任意 LLM 生成足够多的样本以衡量收益，从已发布的 checkpoint 在 Modal 上微调，在留出切分上拟合温度，对照未改动的模型打分，部署一个端点，并在结束时拆除一切。你不需要本地 GPU，也不需要克隆本仓库。在 H100 上跑一次 Kev-4B 训练大约花费 $1。

### By Hand（手动操作）

该 skill 的 [README](skills/kev-finetune/README.md) 是面向人工的同一套方案：六个简短的标准库脚本和一个 Modal app。如果要从本仓库训练，就把你的样本放进一个 JSONL 文件，每行一个请求。它和 API 请求的形状一致，只是在每个问题上多了一个 `label`：

```jsonl
{"state": {"subject": "Charged twice", "body": "I see two charges for order #4411. Please refund one."},
 "questions": {
   "team":     {"type": "choice", "instructions": "Which team should handle this ticket?",
                "criteria": {"billing": "Payments and refunds", "shipping": "Delivery problems", "access": "Login and account access"}, "label": "billing"},
   "angry":    {"type": "noul",   "instructions": "Is the customer angry?", "label": false},
   "priority": {"type": "score",  "instructions": "How urgent is this ticket?", "criteria": ["low", "normal", "high"], "label": 1}}}
```

对于 `choice`，标签是选项名称；对于 `noul`，标签是 `true` 或 `false`；对于 `score`，标签是层级从 0 开始的序号。保留文件 10–20% 的样本用于评估。

然后用 `--init_from` 从已发布的 checkpoint 开始：

```bash
uv run python -m kev.train --data train.jsonl --base Qwen/Qwen3.5-4B-Base --init_from jaredpalmer/kev-4b \
    --epochs 2 --lr 2e-5 --batch 1 --accum 8 --dtype bf16 --checkpointing 1 --device cuda --out runs/mine

uv run python -m kev.benchmark --run runs/mine --data heldout.jsonl --out runs/mine-eval
uv run --extra serve python -m kev.serve --run runs/mine --port 8009
```

`--init_from` 在训练前从已发布模型加载适配器和指针头（pointer head），因此你保留了 Kev 已有的知识，并在其上叠加你的领域知识。如果从基础模型重新开始，则会丢弃这些：在某用户 836 条支持工具决策的测试中，从基础模型开始的微调在其自身的评估集上得分 0.33，而已发布模型为 0.84；同样的数据加上 `--init_from` 在该集上保持了 0.83，并在新领域上达到 0.88。使用比从零开始方案更小的学习率（`2e-5` 是个不错的起点），并选择与你起始 checkpoint 匹配的 `--base`；训练器在加载任何东西之前会检查基础模型、版本、LoRA rank 和头大小是否一致。

`--batch 1 --accum 8` 在 bf16 下能让 0.8B 模型在 4 GB GPU 上运行。benchmark 会按问题类型报告准确率、Brier 分数和校准情况，因此你可以看到微调对哪些问题有帮助。你起始的 checkpoint 记录在 `runs/mine/training_config.json` 中。在 Mac 上，一次只跑一个训练任务；同一块 Apple GPU 上跑两个任务会慢得多。

## Deploy Your Own Endpoint（部署你自己的端点）

若要获得 HTTPS 端点而非本地服务器，你不需要本仓库，只需要一个 [Modal](https://modal.com) 账户：

```bash
pip install modal && modal setup
curl -LO https://raw.githubusercontent.com/jaredpalmer/kev/main/skills/kev-deploy/scripts/kev_serve.py
KEV_API_KEY=$(openssl rand -hex 24) modal deploy kev_serve.py
```

这样会在 L40S 上以 `https://<your-workspace>--kev-api.modal.run` 提供 Kev-4B 服务，其后端 API 与上面相同，由 `Authorization: Bearer <key>` 保护。空闲时自动缩容到零，因此一个未使用的端点不花任何费用。空闲后的首个请求会等待约 35 秒以启动容器。`KEV_MODEL=jaredpalmer/kev-9b` 会在适合它的 GPU 上提供另一个模型；Kev-27B 会分配到 B200，回退到 H200 或 H100。如果你使用编码代理，`npx skills add jaredpalmer/kev@kev-deploy` 会做同样的事，并把 URL 接入你的代码。[skills/kev-deploy](skills/kev-deploy/) 有 GPU 与费用表。

你用 `kev-finetune` skill 微调过的模型，通过其自身的 Modal app 以同样方式部署（`KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=<run> modal deploy scripts/kev_modal.py`；见 [其部署指南](skills/kev-finetune/references/deploy.md)）。若要在你自己的机器上托管 Kev，可在带 GPU 的机器上运行 [Run It Locally](#run-it-locally) 中的 `kev.serve`，加上 `--host 0.0.0.0` 并放在你自己的代理之后；[Serving Performance](#serving-performance) 说明了该选哪块 GPU。

## What to Expect（预期表现）

**Accuracy（准确率）。** 在下方的图表里，Kev-27B 在 11 个新来源类别中的 9 个上与 Jev 差距在三个百分点以内，或优于它。Kev-4B 和 Kev-9B 在路由、蕴含（entailment）和科学问题这类分类型来源上同样接近。知识类问题主要取决于基础模型：在 MMLU 上 Kev-9B 得分为 0.73，Kev-27B 以 0.90 与 Jev 持平，但在更难的 MMLU-Pro 上 Kev-27B 得分为 0.675，而 Jev 为 0.840。较小的模型在按天精度的日期算术上也落后。

![Accuracy by source for Kev and Jev](docs/kev-family.png)

**Confidence（置信度）。** 每个 checkpoint 都附带一个拟合好的温度，因此其概率默认是经过校准的。在服务状态下，Kev-9B 会把至少 0.9 的概率分配给错误答案，这一比例在新来源问题中为 2.4%，而 Jev 为 3.7%。Jev 的排序仍然更好：在 5% 错误预算下，Kev-4B、9B 和 27B 能自动处理 0.52–0.69 的新来源决策，Kev-0.8B 为 0.14，Jev 为 0.70。在依赖它之前，先在你自己的数据上检验一个阈值。

**Speed（速度）。** Kev-4B 在 H100 上回答关于一段新的短文本的六个问题需要 18.1 ms 模型时间，在 L40S 上为 41.5 ms，一个容器在 H100 上每秒可服务约 101 个请求。在 Apple M5 上，Kev-4B 回答五个问题需要 721 ms；当文本重复并命中缓存时则为 136 ms。[Serving Performance](#serving-performance) 列出了每种 GPU 和批量大小。

**Length（长度）。** Kev-0.8B、4B 和 9B 主要训练在最多 384 个 token 的状态上，在它们的文档和 skill 微调中则有更长的（最多 7,552 tokens），Kev-27B 训练在最多 32,768 的状态上。服务器接受最多 65,536 个 token 的状态，每个问题再额外 8,192 个 token，并以 422 拒绝更长的内容，而不是截断它。每个模型在超过其训练长度后还能保持多准确的"Validated context"（已验证上下文）列在 [Models](#models)。对于 Kev-0.8B、4B 和 9B，这个值是 8,192 tokens：在 16k 时，对真实合同的测量已无法排除超过 3 个百分点的下降，而在 32k 时三者都比在 8k 时明显更不准确。Kev-27B 一直保持到 65,536-token 上限。在最多 64k tokens 的真实合同（CUAD）上，Kev-27B 得分为 0.874，并且它在那里的置信度不如短文本可靠；其 [模型卡](docs/model-cards/kev-27b.md) 有按长度列出的数字。

## Playground（交互式演示）

在服务器运行的情况下，打开另一个终端。你需要 Node 20.9+：

```bash
cd playground
npm install
npm run dev -- -p 3001
```

打开 [localhost:3001](http://localhost:3001)，加载一个预设，并编辑文本和问题。按 `⌘↵` 运行它。"Packed vs separate"（打包 vs 分开）比较一次性提出所有问题与逐个提问。"Permute"（排列）会用六种选项顺序运行一个 Choice 问题。还有用于测试问题隔离和伪造分隔符 token 的预设。

![Kev playground](docs/playground.png)

还有一个 [国际象棋演示](http://localhost:3001/chess)。棋盘是输入，合法走法是 Choice 选项，一个 Score 问题为局面评分。你可以和 Kev 对弈，也可以让它自己下。对局保存在 `localStorage` 中。

## API

### `POST /v1/systemone`

`state` 是要评估的文本。每个问题都有 instructions（说明），并在需要时提供一组可供选择的答案。

```jsonc
{
  "state": "…",                          // string | object | array — 要评估的内容
  "model": "kev-latest",
  "questions": {
    "<id>": {                            // 由你选择 id；模型永远不会看到它
      "type": "noul" | "choice" | "score",
      "instructions": "…",               // string | object | array，可选
      "criteria": …                      // noul: {true?, false?}  choice: {option: description|null}  score: [level, …]
    }
  }
}
```

| Type（类型） | Criteria（标准） | Answer（答案） |
|---|---|---|
| `noul` | 针对 `true` 和 `false` 的可选描述 | `noul`：是（yes）的概率 |
| `choice` | 1–255 个选项名称，每个带有描述或 `null` | `choice`：最可能的选项；`probabilities` 和 `confidence` |
| `score` | 1–255 个描述，从低到高排序 | `score`：均值层级序号，从 0 开始；`legend`、`probabilities` 和 `confidence` |

对于具有 `K > 1` 个选项的 Choice，置信度为 `(p_max − 1/K) / (1 − 1/K)`。单个选项的置信度为 1。Score 置信度为 `max(0, 1 − E|level − mode| / D)`：`mode` 是最可能的层级，`D` 是层级上均匀分布距其中点的距离期望（三个层级时为 2/3），因此所有概率集中在一个层级上得 1，而均匀分布或更分散的分布得 0。两个公式都来自 TypeSafe 的参考适配器（[`system-one-adapter`](https://github.com/typesafe-ai/system-one-adapter-python) 0.2.1）。这两个字段都不是实测的准确率数值。

对象和数组会被转换为带标签的文本。用户输入中类似分隔符的字符串会在分词前被转义。无效的请求会返回 `422`，超过 65,536 个 token 的状态也是如此：服务器永远不会静默丢弃文档的一部分，错误会给出状态的 token 数和上限。`usage.output_tokens` 统计序列化答案中的 token 数，而非生成的 token 数。

| Method（方法） | Path（路径） | Purpose（用途） |
|---|---|---|
| `GET` | `/v1/models` | 模型卡（`name`、`description`、`release_date`）加上已加载 checkpoint 的详情 |
| `POST` | `/v1/systemone/permute` | 用不同的选项顺序运行一个 Choice 问题（`n_perm` 1 到 64，默认 6） |
| `POST` | `/v1/systemone/separate` | 在每个问题各自的 forward pass 中运行 |

一个请求可以携带任意数量的问题。服务器每次按一个 token 预算运行它们（每个 forward pass 一行最多 16,384 个 token，在该 pass 中每个问题按一次缓存的文档计算），因此内存不会随问题数量增长，答案也不依赖于切分方式。每个响应都携带一个 `x-typesafe-request-id` 头。服务器默认绑定到 `127.0.0.1`（`--host 0.0.0.0` 可接受其他机器），并且默认是开放的；设置 `KEV_API_KEY` 即可在 `/v1/*` 上要求 `Authorization: Bearer <key>`，TypeSafe 客户端始终会发送它。

| Variable（变量） | Effect（作用） |
|---|---|
| `KEV_TEMPERATURE=1.0` | 返回原始概率，而非校准后的概率 |
| `KEV_DATE_FACTS=1` | 在状态中追加任意两个日期之间的天数（见 [Benchmarks](#benchmarks)） |
| `KEV_TRUNCATE_STATES=1` | 读取更长状态的前 65,536 个 token，而不是拒绝它；此后每个响应都带有 `truncated` 和 `usage.state_tokens` / `state_tokens_used` |
| `KEV_DTYPE=fp32` | 使用评估所用的精确 fp32 路径（GPU 上默认是 bf16） |
| `KEV_API_KEY` | 要求一个 bearer key |

## How It Works（工作原理）

每个 checkpoint 都是一个 rank-16 的 LoRA 适配器和一个小型指针头，位于 Qwen 基础模型之上。在仅注意力的基础模型（Qwen3）上，状态和问题进入同一个 token 序列：

```text
<state> …state…
<q> instructions <opt> option 1 </opt> <opt> option 2 </opt> … <decide>
<q> instructions <opt> option 1 </opt> <opt> option 2 </opt> … <decide>
```

注意力掩码让一个 token 能读取状态和它自己的问题，但不能读取其他问题或未来的 token。每个问题的位置 ID 在状态之后重新开始。这让模型处理一次状态并独立回答每个问题。

Qwen3.5 和 Qwen3.8 将注意力层与 Gated DeltaNet 层混合，后者是递归的，并且会忽略注意力掩码。对于这些模型——也就是当前所有的 Kev——每个问题作为自己的一行运行：状态后接该问题，位置与上面相同。这些行相互独立，因此隔离是精确的，服务器和 `DecisionModel.probs()` 会将状态计算一次，并为每一行复用其缓存。`forward()`（即 `kev.benchmark` 打分和所有已发布数字所依据的）保留纯行形式，并为每个问题将状态计算一次；两者在 fp32 舍入范围内一致。在仅注意力的模型上，这些行和上面的掩码给出相同的概率（`tests/test_model.py`）。

Kev-27B 在 `Qwen/Qwen3.8-27B` 上使用相同的设计，但有两处不同。它的基础是 Qwen 的 post-trained 发布版本，而非 `-Base` checkpoint，我们不知道它 post-trained 了什么。而且每个骨干（backbone）权重都被训练过，不只是适配器，并以 bf16 保存，因此 checkpoint 是整个模型：51 GB 的 bf16 权重加上指针头。它只以 bf16 提供（加上服务缓冲区约占用 66 GB 常驻内存），这也是它需要 80 GB 显卡的原因。在 Apple Silicon 上，MLX 后端按原样加载这些权重，不做合并（见 [Serving Performance](#serving-performance)）；我们预计它能装进 96–128 GB 的 Mac，但尚未实测。它在 H200 上提供的服务概率与评估路径的差异在 0.022 以内（`runs/serving-27b-r23`）。

指针头将每个选项的 `</opt>` 隐藏状态与问题的 `<decide>` 隐藏状态进行打分。一个 softmax 将这些分数转换为概率。由于 `<decide>` 在最后，它可以关注到完整的选项列表。

训练使用对正确答案的交叉熵（cross-entropy）。适配器和头一起训练；基础模型的其余权重保持固定（Kev-27B 训练了所有权重）。训练样本和 API 请求使用相同的文本格式。训练时未使用任何 Jev 的输出。

一起提问或分开提问产生的概率在 fp32 测试中相差在 4e-6 以内。这**并不**意味着选项顺序无关紧要：同一问题内的选项仍然可能相互影响。见 [the model code](kev/model.py) 和 [parity tests](tests/test_model.py)。

## Training（训练）

已发布的模型共用同一个基础训练集 `decision-v7`：来自十个公开数据集的 10,000 个样本、896 个生成的策略样本，以及来自 60 个生成规则结构的 1,680 个样本。Kev-0.8B、4B 和 9B 在它上面训练两个 epoch，使用 LoRA rank 16 和交叉熵。学习率为 0.8B 的 `1e-4`，4B 和 9B 的 `5e-5`。在这些混合（hybrid）基础模型上，适配器覆盖注意力、MLP 和 DeltaNet 投影；`kev.train` 会从模型配置中挑选正确的目标。

Kev-0.8B、4B 和 9B 随后通过与其你自己数据相同的 `--init_from` 路径，从它们已发布的 checkpoint 进行简短的后续微调：生成陈述天数的用例或移除决定性证据的用例（三者皆是），然后是真实文档和生成的 skill 数据（三者皆是；Kev-9B 自 v2 起，2026-09-30）。Kev-27B 的训练方式不同。基础模型的每个权重都在八张 H200 上微调一个 epoch（`--full_ft 1`，学习率 `2e-6`），语料包含 145,840 条记录：Kev 自己的数据、文档、skill 和开发者工具套件、公开数据集、有许可证的任务族，以及生成的长文档、工具路由、agent 日志和护栏记录，状态最多 32,768 个 token。然后将结果与早期适配器训练的 Kev-27B 以 0.85 比 0.15 取平均。模型卡列出了每个阶段及其数据和成本。

```bash
# sanity run，约 1 分钟
uv run python -m kev.train --n_per_source 40 --accum 4 --out runs/smoke

# Kev-0.8B 的第一阶段（一张 H100 上约 20 分钟；Mac 路径可用但 Qwen3.5 基础模型上较慢）
uv run python -m kev.train --suite evals/v7/decision-v7 --base Qwen/Qwen3.5-0.8B-Base --base_revision dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68 \
    --epochs 2 --lr 1e-4 --batch 8 --dtype bf16 --p_none_pair 0.25 --device cuda --out runs/kev-0.8b

# Kev-4B 的第一阶段（通过 Modal 在一张 H100 上，约 1 小时；见下文）。把 Qwen/Qwen3-4B-Base 换入即为上一代。
uv run python -m kev.train --suite evals/v7/decision-v7 --base Qwen/Qwen3.5-4B-Base --base_revision 1001bb4d826a52d1f399e183466143f4da7b741b \
    --epochs 2 --lr 5e-5 --batch 4 --accum 2 --dtype bf16 --checkpointing 1 --p_none_pair 0.25 --device cuda --out runs/kev-4b
```

使用 `uv run python -m kev.train --help` 查看所有训练选项。已发布的模型没有使用可选的 `--perm_kl` 或 `--ord_w` 损失。[PLAN.md](PLAN.md) 记录了尝试过什么、哪些有用、哪些没用。

### Modal

每次试验获得自己的一张 H100。即使你断开连接，研究也会继续运行，完成后你可以下载结果：

```bash
uv run modal token new                                    # 一次；打开浏览器
KEV_GPU=T4 uv run modal run modal_app.py::smoke           # 端到端检查，约 1 分钟 GPU

uv run modal deploy modal_app.py                          # 一次；研究在部署的 app 上运行，并在断开后存活
uv run modal run modal_app.py::study \
    --suite evals/v7/decision-v7 --plan experiments/v7-final.json \
    --name my-study --transfer evals/v4/transfer-v4 --budget 30 --timeout 7200
uv run modal run modal_app.py::pull --name my-study       # 结果 -> runs/my-study，已排序
```

[Study plans](experiments/v7-final.json) 列出了训练设置。每次试验都会保存设置、代码哈希、数据集哈希和结果。使用开发结果来挑选模型，而不是锁定的测试。选定最终候选后，你可以读取它的测试结果一次：

```bash
uv run modal run modal_app.py::locked_test --trial my-study/00-trial-0 --name my-candidate   # 一次读取，永久
```

## Benchmarks（基准测试）

`evals/` 下的评估数据是被冻结的：数据集版本和文件校验和记录在各自的 manifest 中。大文件从 [the Hub mirror](https://huggingface.co/datasets/jaredpalmer/kev-suites) 下载，并与这些哈希进行比对。上表中每个模型的打分都基于相同的条目。本 README 和模型卡中的数字在 CI 中与它们来源的报告（已提交）进行核对（`docs/claims.json`，`uv run python scripts/verify_claims.py`）。

| Suite（套件） | What it measures（测量内容） |
|---|---|
| `decision-v7` | 来自十个训练数据集、生成的策略以及规则结构的留出样本（"已训练来源"） |
| `transfer-v4` | 来自 Kev 从未训练过的数据集、策略和规则类型的 764 条记录：QNLI、SciQ、PAWS、MMLU、Emotion、TweetEval、留出的策略和规则（"新来源"） |
| `transfer-v9` | `transfer-v4` 加上 10 选 1 的 MMLU-Pro、埋在无关文本中的记录，以及决定性证据被移除的"不可知（unknowable）"记录 |

```bash
uv run python -m kev.benchmark --run jaredpalmer/kev-4b --suite evals/v4/transfer-v4 --out runs/my-eval      # 新来源
uv run python -m kev.benchmark --run jaredpalmer/kev-4b --suite evals/v9/transfer-v9 --out runs/my-eval-v9   # + MMLU-Pro、埋藏状态、不可知条目
uv run python -m kev.benchmark --run jaredpalmer/kev-4b --suite evals/v7/decision-v7 --out runs/my-eval-id   # 已训练来源
uv run python -m kev.benchmark --remote http://127.0.0.1:8009 --suite evals/v4/transfer-v4 --out runs/my-remote   # 任意 System One 端点，包括 Jev
```

这些命令使用的是开发数据。测试数据需要 `--allow-test`。benchmark 会报告准确率、Brier 分数、校准误差、在 5% 错误预算下能自动化的决策占比、选项顺序变化，以及问题隔离情况。在不可知记录上，它会报告模型仍然以至少 0.9 置信度作答的频率（Kev-9B 为 0%，Jev 为 9%）。已发布的准确率数字使用的是 fp32 评估，而非 bf16 服务路径。`kev.jev` 通过 Vercel AI Gateway 对 Jev 运行相同的问题，`kev.compare` 使用配对 bootstrap 置信区间对比两次保存的运行结果。

**Calibration（校准）。** 每个 checkpoint 都存储了一个温度，指针头会在模型加载时应用它。Kev-4B（2.41）和 Kev-0.8B（2.35）是在其同分布开发集上拟合的温度；Kev-27B（1.32）和 Kev-9B（2.19）是在它们从未训练过的留出数据集上拟合的。曾对两个较小模型在那些留出数据集上重新拟合进行了测试，但两者都未保留：它没有改善 Kev-4B，反而使 Kev-0.8B 在其文档和 skill 套件上的校准变差（模型卡上有数字）。一个温度永远不会改变哪个答案胜出。在新来源上，它将 Kev-9B 的校准误差从 0.103 降到 0.041，将其置信错误（概率 ≥ 0.9 的错误答案）从 8.2% 降到 2.4%，低于 Jev 的 3.7%。上面的准确率数字无论哪种方式都一样；Brier 数字针对的是原始概率。`scripts/calibrate_checkpoint.py` 还会报告一个折外（out-of-fold）估计，因此可以对未见过记录的样本内拟合进行核对。

**Dates（日期）。** Kev 无法可靠地做日期减法，但可以使用给定的天数。`KEV_DATE_FACTS=1` 会为状态中每对日期追加一句话（"June 26, 2026 is 8 days before July 4, 2026"）。在截止日期策略问题上，这将 Kev-9B 从 0.80 提升到 0.90（Jev 为 0.93）。任何表格都没有使用它。

**Other people's test sets（其他项目的测试集）。** `evals/external/` 保存着来自其他项目的测试集，已转换为本格式，并附带其已发布的实时 Jev 结果。有些是在 Kev 权重的较早版本上打分的，Kev 列会注明。有三个被移除，因为它们无法作为门槛（gate），模型卡保留了其发布所依据的数字：scienthoon 在 2026-09-27 的合成客服工单（模板化文本；其三个问题中的一个依赖文本未陈述的规则），以及 2026-09-30 的 WANLI（`wanli-v1`、`wanli-v2`：四分之一的样本对是 WANLI 两位标注者标注不同、且 gold 被设定为其中之一的），以及 TypeSafe 的公开评估（`typesafe-v1`：gold 是两个封闭式前沿模型答案的平均值，在 89 个问题上它无法区分 checkpoint）。

| Suite（套件） | What it is（是什么） | Jev | Kev |
|---|---|---|---|
| [SemIf](https://github.com/TheoLeeCJ/SemIf) | 144 个作者撰写决策 | 0.965 | 0.917（Kev-9B at `v7-base`） |

SemIf 的标签经得起推敲，但它已接近饱和：每个 Kev-27B checkpoint 都能正确回答 144 个中的 130 个，因此它是一个健全性检查，而非给模型排名的方法。

## Serving Performance（服务性能）

按模型选择 GPU：

| Model | GPU（$/h） | 6 个问题，短文本 | 5 个问题，2,200-token 文本 | 每秒请求数，64 客户端 |
|---|---|---|---|---|
| Kev-0.8B | L4（0.80） | 22.7 / 16.1 ms | 108.6 / 32.3 ms | 62.8 |
| Kev-4B | L40S（1.95） | 41.5 / 27.7 ms | 145.2 / 43.0 ms | 51.4 |
| Kev-4B | H100（3.95） | 18.1 / 12.9 ms | 89.4 / 22.5 ms | 100.8 |
| Kev-9B | L40S（1.95） | 66.4 / 42.7 ms | 235.6 / 57.5 ms | 32.7 |
| Kev-9B | H100（3.95） | 24.0 / 16.6 ms | 88.5 / 26.4 ms | 79.5 |
| Kev-27B | B200（6.25） | 46.5 / 32.2 ms | 178.0 / 52.1 ms | 44.2 |
| Kev-27B | H200（4.54） | 67.2 / 50.0 ms | 274.8 / 73.8 ms | 28.6 |
| Kev-27B | H100（3.95） | 75.0 / 52.0 ms | 277.5 / 79.3 ms | 28.9 |

时间为每个请求的模型时间（API 返回的 `latency_ms`），20 次的中位数，针对新文本 / 再次使用相同文本。服务器缓存文本，因此对已发送文档提出更多问题只需支付问题本身的开销。每秒请求数是针对 64 个并发客户端各自发送一段新的短文本的六个问题；服务器会对它们进行批处理。Kev-27B 的 B200 和 H100 行是在其上一版本上测量的，即以 bf16 提供服务的相同架构（`runs/fused-27b-*`）；H200 行是当前 checkpoint（`runs/serving-27b-r23`）。网络时间是额外的：通过同一区域的 Modal web 端点，每次往返约 65 ms。

L4 足够用于 Kev-0.8B，但对 Kev-4B 来说太慢。这里的 A100 比 L40S 慢且更贵。Kev-9B 需要约 17 GB 的 GPU 内存，Kev-27B 需要 51 GB 的权重（加上批处理缓冲区约 66 GB）；在负载下 Kev-27B 受计算限制，B200、H200 或 H100 每个请求的成本大致相同。在 CUDA 上，为 Qwen3.5 模型安装 `flash-linear-attention`（`kev_serve.py` 和 Modal 镜像已经做了）。

在 Apple Silicon 上，`uv sync --extra serve` 会安装 [MLX](https://github.com/ml-explore/mlx-lm)，服务器会自动使用它。在 M5（32 GB）上对约 270-token 文本回答五个问题：

| Model | 新文本 | 再次使用相同文本 |
|---|---|---|
| Kev-0.8B | 149 ms | 28 ms |
| Kev-4B | 721 ms | 136 ms |

长文档以每次 1,024 个 token 读入缓存，因此内存保持在接近权重大小。对于一个 65,000-token 的文档，Kev-0.8B 首次耗时 21.2 s，之后为 202 ms，峰值 3.8 GB；Kev-4B 为 84.5 s 和 716 ms，峰值 13.0 GB（`runs/mlx-long-states`；模型卡上有每个长度的数字）。Kev-9B 尚未以这种方式测量。

适配器 checkpoint 在加载时折叠进基础模型，这会短暂持有第二份权重副本。像 Kev-27B 这样的完整权重 checkpoint 按保存状态加载，不做任何合并，因此加载只需要权重本身。我们在以完整 bf16 权重写出的 Kev-4B 上核实了这一点：加载峰值 8.4 GB 对应 8.4 GB 权重，而适配器路径为 15.9 GB。一旦两者持有相同的 bf16 值，它的答案与适配器路径逐位一致，并在 60 个问题上与 fp32 路径的差异在 0.015 以内（`runs/mlx-full-4b`）。Kev-27B 的权重为 51 GB。根据同样的测量，它需要约 51 GB 加上工作内存，因此 64 GB 的 Mac 处于临界，96–128 GB 的 Mac 应该能装下。我们尚未在这么大的 Mac 上运行过。Kev-27B 的第一个版本是一个适配器，确实在 128 GB 的 M5 Max 上以这种方式运行过，匹配了已发布的准确率（感谢 Sean Connelly，[#175](https://github.com/jaredpalmer/kev/pull/175)）。

服务器在 GPU 和 Mac 上以 bf16 运行。它的概率与已发布评估所使用的 fp32 路径的差异，在 GPU 上最多约 0.03，在 Mac 上最多约 0.05，并且最优答案大约每 300 个问题中有一个会改变。设置 `KEV_DTYPE=fp32` 可获得精确路径。`/v1/models` 会报告正在使用的后端和精度。`uv run modal run modal_app.py::serving --run jaredpalmer/kev-4b --gpu L40S --name <name>` 会在你自己的账户上测量表中一行（上面的行：`runs/serve-*`、`runs/grouping-4b-h100`、`runs/fused-27b-*`、`runs/serving-27b-r23`）。

## Limitations（局限性）

- 校准使用单一温度。它无法对置信度重新排序，因此在 5% 错误预算下你能自动化的新来源决策占比（Kev-4B、9B 和 27B 为 0.52–0.69）仍然低于 Jev 的 0.70。在依赖它之前，先在你自己的数据上检验一个概率阈值。
- 知识类问题由基础模型决定。MMLU 在 Kev-9B 上为 0.73，而 Jev 为 0.90；MMLU-Pro 为 0.59 对比 0.84。
- 微调可能让基础模型在个别任务上变差。日期算术是最明显的例子（[issue #8](https://github.com/jaredpalmer/kev/issues/8)）；在陈述天数的数据上训练加上 `KEV_DATE_FACTS=1` 可以恢复它。
- 改变选项顺序可能改变答案。问题隔离无法防止这种情况。
- Kev-0.8B、4B 和 9B 主要训练在最多 384 个状态 token、以及状态加一个问题 1,024 个 token 上（它们的文档和 skill 微调在最多 7,552 个 token 的状态上），Kev-27B 训练在最多 32,768 个 token 的状态上。服务提供允许 65,536-token 的状态；每个模型的已验证上下文长度见 [Models](#models)。
- 在 Mac 上，回答需要数百毫秒，而非数十毫秒。Kev-27B 需要 80 GB 的 GPU。在 Mac 上它需要约 51 GB 加上工作内存；我们预计 96–128 GB 的 Mac 能装下它，但尚未实测。
- Kev-27B 从一个我们不知道其训练数据的 post-trained 模型出发。

## Development（开发）

```bash
uv run --extra serve python -m pytest tests/test_unit.py tests/test_research.py tests/test_generators.py tests/test_conventions.py \
    tests/test_documents_tools.py tests/test_hard_v1.py tests/test_devtools_v1.py tests/test_breadth_v1.py tests/test_rounds.py tests/test_skill_scripts.py -q   # 无权重，无服务器；CI 运行的内容
KEV_BASE_URL=http://127.0.0.1:8009 uv run --extra serve python -m pytest tests/test_api.py -q   # 针对一个运行中的服务器
cd playground && npm run lint && npx next typegen && npx tsc --noEmit -p .
```

API 测试会针对你的本地服务器运行 TypeSafe 的示例请求和官方 SDK。[PLAN.md](PLAN.md) 是研究计划：我们学到了什么、每个实验都遵循的规则，以及每一轮（round）一行。完整的日志（每个实验、运行前设定的标准，以及结果如何）保存在 git tag `research-archive-2026-09-24`。

<details>
<summary>Previous generation（上一代，Qwen3）与 prototype（原型）</summary>

第一个 Kev 家族使用 Qwen3 基础模型和相同的数据与设置。那些权重仍然发布，并可在 Mac 上运行于纯 PyTorch，但已不再开发。

| Model | Base（基础模型） | Accuracy: Trained Sources（已训练来源准确率） | Accuracy: New Sources（新来源准确率） | Brier: New Sources（新来源 Brier） | Model Card（模型卡） |
|---|---|---|---|---|---|
| Kev-0.6B（Qwen3）— `jaredpalmer/kev-0.6b` | Qwen3-0.6B-Base | 0.801 / 0.808 | 0.620 / 0.642 | 0.536 / 0.483 | [Details](docs/model-cards/kev-0.6b-qwen3.md) |
| Kev-4B（Qwen3）— `jaredpalmer/kev-4b@qwen3` | Qwen3-4B-Base | 0.854 / 0.856 | 0.790 / 0.806 | 0.328 / 0.294 | [Details](docs/model-cards/kev-4b-qwen3.md) |
| Kev-8B（Qwen3）— `jaredpalmer/kev-8b` | Qwen3-8B-Base | 0.863 / 0.870 | 0.796 / 0.780 | 0.337 / 0.327 | [Details](docs/model-cards/kev-8b-qwen3.md) |

原始的 [Kev-0.5B](https://huggingface.co/jaredpalmer/kev-0.5b) 使用 Qwen2.5-0.5B，保留作为参考；见其 [模型卡](docs/model-cards/kev-0.5b.md)。

</details>

<details>
<summary>Troubleshooting（故障排查）</summary>

- 如果 MPS 在训练期间内存不足，检查你是否只运行了一个任务。不要启用 `output_hidden_states`，也不要用 peft 的 `trainable_token_indices` 添加 token；两者都曾在这里引发内存问题。
- 如果 playground 加载了但按钮不起作用，使用 `localhost:3001`。Next.js 会检查开发主机名。其他主机需要在 `playground/next.config.ts` 的 `allowedDevOrigins` 中加一条。
- 如果数据集加载报 `Dataset scripts are no longer supported`，使用 `legacy-datasets/banking77`。本仓库已经在使用它。

</details>

## Authors（作者）

- Jared Palmer（[@jaredpalmer](https://github.com/jaredpalmer)）

由 [Devin](https://devin.ai) 构建。感谢 [Archer Hume](https://archerhume.com/posts/jevs-architecture-unmasked) 撰写的架构文章、[TypeSafe](https://docs.typesafe.ai/api) 设计的 API，以及 [Qwen](https://huggingface.co/Qwen/Qwen3.5-9B-Base) 提供的基础模型。

相关作品：[Hydragen](https://arxiv.org/abs/2402.05099)、[DeFT](https://arxiv.org/abs/2404.00242)、[FIRST](https://arxiv.org/abs/2406.15657)。

## License（许可证）

[Apache-2.0](LICENSE)。Qwen3、Qwen3.5 和 Qwen3.8 基础模型也是 Apache-2.0。训练数据集有各自的许可证；见 [模型卡](docs/model-cards/)。


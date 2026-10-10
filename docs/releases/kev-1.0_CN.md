<p align="center">
  <a href="./kev-1.0_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./kev-1.0.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# Kev 1.0

Kev 1.0 是整个 Kev 家族的第一个带版本号的发布：四个决策模型，读取一份文档和一组带类型的问题，并在一次前向传播中、在 TypeSafe 的 System One API 背后，返回选项上的校准概率。这里面没有任何新训练的内容。它钉住了下一代理 Kev 所对照衡量的那些 checkpoint、model card、评估套件和服务代码，在每个 Hub repo 上都使用同一个标签（`v1.0`）。

## What's in 1.0（1.0 里有什么）

| Model | Hub repo | Weights revision | Form | Base | Temperature | Validated context |
|---|---|---|---|---|---|---|
| Kev-0.8B | [`jaredpalmer/kev-0.8b`](https://huggingface.co/jaredpalmer/kev-0.8b) | `9a45d25e` | LoRA adapter + head | Qwen3.5-0.8B-Base (Apache-2.0) | 2.35 | 8,192 tokens |
| Kev-4B | [`jaredpalmer/kev-4b`](https://huggingface.co/jaredpalmer/kev-4b) | `139fdd94` | LoRA adapter + head | Qwen3.5-4B-Base (Apache-2.0) | 2.41 | 8,192 tokens |
| Kev-9B (v2) | [`jaredpalmer/kev-9b`](https://huggingface.co/jaredpalmer/kev-9b) | `b5d8c18e` | LoRA adapter + head | Qwen3.5-9B-Base (Apache-2.0) | 2.19 | 8,192 tokens |
| Kev-27B (v2) | [`jaredpalmer/kev-27b`](https://huggingface.co/jaredpalmer/kev-27b) | `28be62e9` | full bf16 weights (51 GB) + head | Qwen3.8-27B, post-trained (Apache-2.0) | 1.32 | 65,536 tokens |

头条数字（fp32 评估路径，每个模型在它发布的 temperature 下；transfer-v4 测试是锁定的，每个模型读取一次）：

| | Kev-0.8B | Kev-4B | Kev-9B | Kev-27B | Jev |
|---|---|---|---|---|---|
| Held-out datasets: breadth-v1 test, chance-corrected index | 23.3 | 38.0 | 41.0 | 52.3 | 54.0 |
| Out-of-domain: transfer-v4 development accuracy | 0.648 | 0.817 | 0.820 | 0.851 | 0.857 |
| Out-of-domain: transfer-v4 locked test accuracy / Brier | 0.697 / 0.397 | 0.838 / 0.224 | 0.852 / 0.199 | 0.889 / 0.154 | – |
| Skills: hard-v1 test | 0.665 | 0.803 | 0.834 | 0.918 | – |
| Developer tooling: devtools-v1 test, all sources | 0.637 | 0.756 | 0.791 | 0.790 | – |
| Real documents: documents-v1 test | 0.851 | 0.903 | 0.900 | 0.908 | – |
| MMLU-Pro (transfer-v9 development) | 0.230 | 0.565 | 0.590 | 0.675 | 0.840 |

hard-v1、devtools-v1 和 documents-v1 都有每个 Kev 都训练过的训练划分：那些行测量的是已训练家族的留出条目，而非迁移（transfer）。breadth-v1 和 transfer-v4 的行是没有任何 Kev 训练过的数据集。Jev 只在 development 划分上以及 breadth-v1 test 上被读取。每一个数字都通过 `docs/claims.json` 追溯到一份已提交的报告；model card（`docs/model-cards/`）有其余部分，带区间。

## What changed since the last family release（自上次家族发布以来的变化）

以 GitHub 发布 `kev-family` 为基准测量，该发布是在 2026-09-24 为当前家族首次组装的（Kev-27B v1、Kev-9B v1，以及和这里相同的 Kev-4B 和 Kev-0.8B）。它 2026-09-30 的更新（Kev-27B v2、Kev-9B v2）也列在这里，因为 1.0 是它们成为带版本号发布的一部分的地方。

- **Kev-27B v2：full weights。** Qwen3.8-27B 的全部权重在一个 145,840 条记录的语料上微调了一个 epoch，然后和 v1 以 0.85 / 0.15 平均。在测试集上对比 v1：held-out datasets +1.2 pp [+0.3, +2.2]，held-out task families +5.3 [+3.7, +6.8]，skills、tooling 和 documents +8.9 [+7.5, +10.3]；锁定的 out-of-domain test 为 0.889 对 0.896，Brier 0.154 对 0.160。在长合同上更差且过度自信（CUAD ECE 0.053 对 0.007）。v1 在 `jaredpalmer/kev-27b@v1-lora`。
- **Kev-9B v2。** v1 加上在文档和 skills 数据上一个 epoch，这些数据 Kev-4B 和 Kev-0.8B 已经有了。在测试集上对比 v1：hard-v1 + devtools-v1 +18.7 pp [+16.7, +20.8]，documents-v1 +7.1 [+4.7, +9.2]；在锁定的 out-of-domain test 上持平（两者都是 0.852），Brier 0.199 对 0.224。v1 在 `jaredpalmer/kev-9b@v1`。
- **没有静默截断（No silent truncation）。** 服务器过去会把一个超过其限制的状态悄悄截断而不说明。它现在会以一个 422 拒绝一个超过 65,536 token 的状态，并指名 token 数和限制；`KEV_TRUNCATE_STATES=1` 退回截断模式，而这样的服务器此后每个响应都会说 `truncated`。deploy 和 fine-tune 技能把 `KEV_REF` 钉到一个带有此修复以及下文长文档和 MLX 变更的提交（`71d4829`），并且 Space 在该修复之后被重新发布。
- **每个尺寸都支持长文档。** 评估路径在长行上保留了 fp32 注意力的数学 kernel，所以 Kev-0.8B、4B 和 9B 在 32k–64k token 的状态上耗尽了 GPU 内存。长行现在在 fp32 下运行省内存的 kernel：Kev-4B 在 H100 上读取一个 61k token 的状态用时 17.2 s，在权重之上多占 17.2 GiB，而较短的行逐位保留它们的 logits。正是这一点让上文那些已验证的上下文长度变得可测量。
- **Apple Silicon。** MLX 后端按保存时的样子加载 full-weight checkpoint，不做合并，这给了 Kev-27B 一条 Mac 路径（预计需要约 51 GB 加上工作内存；尚未在该尺寸下运行过）。长状态以每次 1,024 个 token 做 prefill，并且缓存在一次前向之前逐出，所以 Kev-4B 在一个 32 GB 的 M5 上以 13.0 GB 的峰值（新状态 84.5 s，缓存后 716 ms）服务一个 65,000 token 的状态。
- **Kernel provenance（kernel 来源）。** 在评估镜像中的一个 kernel 变更被发现会在 Kev 自身代码没有任何改动的情况下，把 Kev-27B v1 的读取在概率上移动 0.03–0.06 之后，现在每一份评估报告和 trial 都会记录它的 logits 所依赖的 kernel 集合（包版本、GPU、dtype、attention 和 DeltaNet 实现）。
- **评估审计（Evaluation audit）。** 三个套件因为对选模型来说不合理而被移除：scienthoon（模板化工单，有一个文本无法回答的问题）、WANLI-v2 / WANLI-v1（四分之一的金标是两个互相不同意的标注者之一）以及 TypeSafe 的公开 evals（金标来自两个闭源模型，问题太少）。头条 panel 排除了审计发现的不可回答或未标注的条目。过往发布在这些套件上的数字保留在它们各自的记录中，而不在 1.0 的 card 上。
- **校准（Calibration）。** Kev-4B 和 Kev-0.8B 发布的是在它们训练数据的留出条目上拟合的 temperature。一次在留出数据集上做的已注册 refit 对两者都做了评估，但两者都没采用：它没有改善 Kev-4B（Brier 差异 −0.0001 [−0.0005, +0.0003]），而且它让 Kev-0.8B 在其文档和 skill 家族上校准得更差，超出了注册的容差。Kev-9B 和 Kev-27B 已经发布的是留出数据集的 temperature。
- **训练数据已发布。** documents-v1 和 hard-v1 的训练划分在 `jaredpalmer/kev-suites` 数据集中，所以小模型的训练数据可以被获取并做哈希校验。
- **已验证的上下文长度（Validated context length）。** 现在每张 card 都说明，在该状态下，CUAD contracts 上的 accuracy 保持在和同一个模型在 8k token 时相比、落在 3 pp 以内（95 % 下界）的最长状态。Kev-27B 保持到 65,536 token，即服务上限（它的 64k 下界是 −2.4 pp）。Kev-0.8B、4B 和 9B 只验证它们训练过的 8,192：每一个在 16k 就已经超出容差（下界 −8.5、−3.4 和 −3.7 pp），所以在 8k token 之后，它们在长文档上的答案不在该测量的覆盖范围内。
- **正式的 model card（Formal model cards）。** 四张 card 都遵循同一结构：summary、details、intended and out-of-scope uses、how to use、training data and procedure、evaluation、limitations、risks、compute、provenance。

## Known limitations（已知限制）

- **In-distribution 收益。** 去年那些大的提升来自训练划分在训练数据中的套件。在没有 Kev 训练过的数据集上，Kev-27B 在 breadth-v1 test 上比 Jev 低 1.7 个指数点，而较小的尺寸低 13–31 个点。
- **未训练过的长度（Untrained lengths）。** Kev-0.8B、4B 和 9B 训练的状态最多 7,552 token，Kev-27B 最多 32,768；服务器接受 65,536。使用已验证的上下文长度，而不是服务上限。
- **Kev-27B 在长合同上**比 v1 更不准确且过度自信（CUAD test ECE 0.053 对 0.007）；在你自己的文档上 refit 这个 temperature，或对于合同审查使用 `@v1-lora`。
- **Kev-0.8B 与工具路由（tool routing）。** 在它的 documents-and-skills 阶段之后，它的 When2Call accuracy 跌到了机会水平以下（测试集上 0.133）；不要把它用于工具调用路由。
- **日期计算（Date arithmetic）** 是 27B 以下每个尺寸都最弱的一家（`deadline` 策略 accuracy 0.35 / 0.65 / 0.725，对比 Jev 的 0.95）；`KEV_DATE_FACTS=1` 有帮助。
- **知识（Knowledge）** 由 base 决定（MMLU-Pro 0.230–0.675，对比 Jev 的 0.840）。
- **Kev-9B 在 Mac 上**尚未被测量，而 Kev-27B 在 Mac 上预计能装下 96–128 GB，但还没运行过。
- **选择（Selection）。** Kev-27B v2 和 Kev-9B v2 是在审计过的规则下、已知了较早的 development 读取之后重新选出来的；它们的测试 margin 是乐观的。
- **每个模型一个 temperature**无法给置信度重新排序，所以在 5 % 的误差预算下，这些模型在域外自动化的决策比 Jev 少。

## How to run（如何运行）

```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev && uv sync --extra serve
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b@v1.0 --port 8009    # CUDA，或 Apple Silicon 上的 MLX
```

从一个发布 tarball：

```bash
shasum -a 256 -c SHA256SUMS.txt
tar -xzf kev-4b.tar.gz
uv run --extra serve python -m kev.serve --run kev-4b --port 8009
```

TypeSafe SDK 原样可用：`TypeSafeClient(api_key="local", base_url="http://127.0.0.1:8009", model="kev-latest")`。Kev-27B 需要一台 B200、H200 或 H100 80 GB：`--run jaredpalmer/kev-27b@v1.0`。要在 Modal 上部署一个 HTTPS 端点，参见 `skills/kev-deploy`。

## Assets（资源文件）

每个 tarball 都持有在它的 weights revision 下、和 Hub 上一样的一个 checkpoint（LoRA adapter、带 temperature 的 `head.pt`、tokenizer 文件、训练 trial 的 `result.json`、`provenance.json`、`training_config.json`、`training_metrics.json` 和 log）、作为 `README.md` 的 Kev 1.0 model card，以及作为 `locked_test.json` 的锁定 transfer-v4 读取。它们由 `scripts/build_release_assets.py` 从 `docs/releases/kev-1.0-assets.json` 构建，重新构建会得到相同的字节。它们中的每个文件都标注日期 2026-10-01 00:00 UTC，这是 `kev.serve` 报告为一个解包后 checkpoint 的发布日期。那些在 2026-10-01 首次附上的 tarball 把它们的文件标成 1970-01-01，所以 `kev.serve` 报告的是 1969-12-31；它们在当天就被这些替换了。权重和每一个其他文件都是逐字节相同的；只有 tarball 哈希改变了。

| File | SHA-256 | Checkpoint | adapter / head SHA-256 |
|---|---|---|---|
| `kev-0.8b.tar.gz` (46 MB) | `0ae144c7675f0c3f333be0bb878a0f202ab9e6fa84169fb7cb16efe6176c1ef1` | `jaredpalmer/kev-0.8b@9a45d25e` | `9b908623…` / `f400bd12…` |
| `kev-4b.tar.gz` (131 MB) | `2e707e2ebd08980dc7881222b7024cea5606401441c1a086afb170ae7784201c` | `jaredpalmer/kev-4b@139fdd94` | `90e81735…` / `dd633435…` |
| `kev-9b.tar.gz` (172 MB) | `acd13320b7d1b052ce989f19ca9d1d9ba5219b8beced0ee67337908aef1deb3f` | `jaredpalmer/kev-9b@b5d8c18e` | `2b2a70cf…` / `8e1dab2c…` |

Kev-27B 没有被附上，因为它的 51 GB 权重超过了 GitHub 对每个资源文件 2 GB 的限制。从 Hub 下载它：[`jaredpalmer/kev-27b@v1.0`](https://huggingface.co/jaredpalmer/kev-27b/tree/v1.0)（weights commit `28be62e9`，`head.pt` `7968f17b…`）。

在每个 Hub repo 上，`v1.0` 标签指向那个上传了 Kev 1.0 card 的提交。那个提交只改动了 `README.md`，所以它的权重与第一张表中的权重修订是相同字节：kev-0.8b `bf75a6a8`、kev-4b `6cfce5c2`、kev-9b `db029f08`、kev-27b `af0e6d55`。

## Release plan（for the maintainer; not part of the published notes）（发布计划（给维护者；不属于已发布说明的一部分））

**完成于 2026-10-01**（记录 `runs/release/kev-1.0.json`；PLAN.md「Released: Kev 1.0」）。步骤 3 和 4：仅 card 的提交，每个 card 提交都带 `v1.0`（0.8B `bf75a6a8`、4B `6cfce5c2`、9B `db029f08`、27B `af0e6d55`；所有其他文件未变）。步骤 5 和 6：资源文件构建两次，哈希相同，发布并标记为 Latest。步骤 7：`kev-family` 保留，移除它的资源文件，它的 body 是一个指向 `kev-1.0` 的指针，它的旧说明在 `runs/release/kev-family-notes-retired.md`。步骤 8：pin 不变。步骤 9：collection 和 Space 已检查；Space 没有重新发布。发布前写好的计划如下。顺序：

1. **Placeholders: 已填**（2026-10-01），取自 28 轮的已注册 context 读出、`runs/r28-readout/context.json`（`scripts/longdoc_report.py --context-margin -0.03` 作用于 `runs/r28-{4b-r10,08b-r15}-longdoc`、`runs/r29-9b-r18a-longdoc` 和 `runs/r23-27b-k-w85-longdoc`；原始 `runs/r28-context`，在发布 T 下的 ECE `runs/r28-context-served`），数字在 `docs/claims.json` 中。
2. **Merge**（合并）此 PR。
3. **Hub cards。** 每个 1.0 card 只作为 `README.md` 上传（不带权重）：card-only 提交不需要 `kev.publish`；`hf upload jaredpalmer/kev-<size> docs/model-cards/kev-<size>.md README.md --commit-message "Kev 1.0 model card (weights unchanged)"`。用 `HfApi().model_info(..., files_metadata=True)` 检查 `adapter_model.safetensors` / `head.pt`（27B：`model.safetensors.index.json` 和每个分片）按如下方式哈希。
4. **Hub tags。** 四个 repo 都打 `v1.0`。默认（如所指定）：确切的权重修订；如果步骤 3 先跑了，则改为给 card 提交打标签，这样 `@v1.0` 显示的是 1.0 card（权重逐字节相同；在 PLAN.md 中记录两个提交）。

   | Repo | `v1.0` target (weights) | adapter / head sha256 |
   |---|---|---|
   | `jaredpalmer/kev-0.8b` | `9a45d25eb2ab761841196625383fa1dff0e56c1e` | `9b908623…` / `f400bd12…` |
   | `jaredpalmer/kev-4b` | `139fdd94f1b6a6ad80cc15e08fcb99cac885a101` | `90e81735…` / `dd633435…` |
   | `jaredpalmer/kev-9b` | `b5d8c18e44c60888d138b65cb6507ff0a5a448a0` | `2b2a70cf…` / `8e1dab2c…` |
   | `jaredpalmer/kev-27b` | `main`（今天 `ef78cc8a34d5f426fb229c52089db189218cfe5c`：权重 `28be62e9`，之后三个 card-only 提交） | weights `d27af6ab…` / head `7968f17b…` |

   ```bash
   hf repos tag create jaredpalmer/kev-0.8b v1.0 --revision 9a45d25eb2ab761841196625383fa1dff0e56c1e -m "Kev 1.0"
   hf repos tag create jaredpalmer/kev-4b   v1.0 --revision 139fdd94f1b6a6ad80cc15e08fcb99cac885a101 -m "Kev 1.0"
   hf repos tag create jaredpalmer/kev-9b   v1.0 --revision b5d8c18e44c60888d138b65cb6507ff0a5a448a0 -m "Kev 1.0"
   hf repos tag create jaredpalmer/kev-27b  v1.0 --revision <main at release> -m "Kev 1.0"
   ```

5. **Assets。** `uv run python scripts/build_release_assets.py --release docs/releases/kev-1.0-assets.json --out /tmp/kev-1.0-assets` 构建 `kev-0.8b.tar.gz`、`kev-4b.tar.gz`、`kev-9b.tar.gz`（每个：上面那个修订下的 Hub 快照，即 adapter、带 temperature 的 `head.pt`、tokenizer 文件、trial 的 `result.json`、`provenance.json`、`training_config.json` 和 `training_metrics.json`；作为 `README.md` 的 1.0 card；作为 `locked_test.json` 的锁定读取）、`SHA256SUMS.txt` 和 `manifest.json`（每个成员的 sha256）。它会拒绝一个 adapter 或 head 哈希和 spec 不同的下载。Kev-27B 不是一个资源文件（51 GB；GitHub 把每个资源文件限制在 2 GB）：说明指向 Hub。
6. **GitHub release。** 在 merge 提交上打 `kev-1.0` 标签；把这份说明中已发布部分作为 body 创建一个草稿发布（本节以上的一切），附上三个 tarball 和 `SHA256SUMS.txt`，把它们下载回来，`shasum -a 256 -c SHA256SUMS.txt`，解压一个并服务它，然后发布并标记为 Latest。
7. **每个尺寸一个发布（One release per size）。** 发布策略在一个 GitHub 发布中只保留每个尺寸的最佳版本。一旦 `kev-1.0` 发布，`kev-family` 就重复它：删除它的三个 tarball 和 `SHA256SUMS.txt`，把它的 body 换成指向 `kev-1.0` 的指针（或删除该发布；Jared 的决定）。更早的版本留在每张 card 列出的 Hub 标签上。
8. **Deploy pins。** `skills/kev-deploy` 和 `skills/kev-finetune` 把 `KEV_REF` 钉到 71d4829；1.0 的 checkpoint 不需要更新的代码。只有当之后一个服务修复应当随 1.0 一起发布时，才移动这个 pin。
9. **Collection 和 Space。** Kev collection 已经列出了四个 repo。Space 从 `main` 服务 Kev-4B 和 Kev-0.8B，那就是 1.0 权重；除非 `kev/model.py`、`kev/api.py` 或 `kev/checkpoint.py` 在它上次发布之后改过，否则没什么需要重新发布的。

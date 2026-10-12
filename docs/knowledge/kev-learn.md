仓库里已有一套模块文档,我先读取它与其他关键材料。

下面是结合本仓库真实代码/文档梳理出的"读懂 Kev 需要的基础知识地图"。先说一个前提:仓库自己已有一套四篇模块文档 + 交互动画,在 `docs/knowledge/`(`README.md`、`01-model-architecture.md`、`02-training-framework.md`、`03-inference-serving.md`、`04-evaluation-system.md`、`architecture-flow.html`)。我的回答按你要求的四个层次组织,并把这些文档当作"已存在的教材"接进去,而不是重复抄一遍。

---

## 0. 一句话定位(决定你要学什么、不学什么)

Kev **不是对话模型**,而是 `AGENTS.md` 第一行写的"causal LM + LoRA,以 block-causal mask 做 prefill-only 推理,用 pointer readout 读选项边界 token"的**决策模型**:输入 `state + questions`,输出**每个问题的一组校准概率**,全程不生成文字。

这个定位直接决定了学习权重的分布:

- **生成式 LLM 的那一半知识**(采样、解码循环、stop token、prompt 工程、RLHF/DPO)在这里几乎用不上 → 可跳过。
- **判别式/校准/评测的那一半知识**(softmax 概率、交叉熵、温度缩放、ECE/Brier/NLL、选择性预测、bootstrap 置信区间、数据泄漏纪律)是**主干** → 必须补。
- 再加一小撮**非典型系统工程知识**(hybrid 线性注意力、4D 掩码、prefix cache、bf16/fp32 master、FSDP2、token 级的显存预算)→ 决定你能不能读懂 `shared_prefix`/`fused_qwen35`/训练计划这些"看起来过度设计"的代码。

---

## 1. 通用前置知识(最低门槛)

按"缺了就完全读不动"排序,并给出仓库里第一个会撞上它的地方。

| 前置知识 | 具体要掌握到什么程度 | 在 Kev 里第一次出现在 |
|---|---|---|
| 因果语言模型 & self-attention | causal mask 是什么;**additive 4D mask `[B,1,L,L]`** 如何覆盖默认因果掩码;**position ids 可自定义**(RoPE 按 position 而不是按 index) | `kev/model.py:branch_mask_batch()`、`encode()` 的 `pos` 字段 |
| prefill vs decode、KV cache | 一次前向算完 prompt = prefill;Kev 只要 prefill,因此丢掉 LM head(`AutoModel`/`.model`) | `kev/model.py:DecisionModel.__init__`、`docs/knowledge/01` §1.1 |
| tokenizer 与特殊 token | 复用 Qwen 已有的 `<\|state\|> \<\|q\|> \<\|opt\|> \</opt\|> \<\|decide\|>`,不新增 embedding 行;用户文本里的 `<\|x\|>` 必须被改写,否则**选项边界可伪造** | `kev/model.py:SPECIAL`、`user_tokens()` |
| token 预算/上下文窗口 | state/branch/packed 三个预算分别限制什么;训练预算 ≠ 服务预算 | `kev/model.py:MAX_STATE/MAX_BRANCH/MAX_PACKED` vs `SERVE_MAX_STATE/ROW_PASS_TOKENS`;`ContextOverflow` |
| 概率与损失 | softmax/交叉熵/logits/log-prob;**soft target 与 KL 散度**(含对称 KL);label smoothing、focal、Brier、ranked probability score 各自优化什么 | `kev/train.py:question_loss()`、`anchor_loss()`、`--perm_kl` |
| 校准基础 | temperature scaling 为什么**不改变 argmax** 却改变 ECE/Brier/NLL;ECE 的分桶定义;NLL 可从 logits 精确算 | `kev/model.py:PointerHead.temperature`、`kev/metrics.py:fit_temperature()`、`nll_at_temperature()` |
| 统计与比较 | bootstrap 置信区间;**为什么同一 record 的多个问题必须整体重采样**(record-clustered);配对差值 vs 点估计;chance-corrected index | `kev/rounds.py:paired()`、`scripts/breadth_report.py` |
| 优化与微调 | LoRA 原理(rank、targets、合并);全量微调的显存代价;AdamW + fp32 master weights;梯度累积;gradient checkpointing | `kev/train.py --lora_targets`、`kev/full_ft.py:MasterAdamW` |
| 混合精度 | bf16 autocast vs 权重 dtype;`--dtype` 与 `--weights_dtype` 的区别;为什么 fused Moe experts 需要 bf16 权重 | `AGENTS.md` 的 `--dtype` vs `--weights_dtype`;`README.md`「Serving Performance」 |
| 工程基座 | `uv sync --extra serve`、FastAPI + Pydantic、pytest、Docker Compose、Next.js(只需会跑)、serverless GPU(Modal) | `pyproject.toml`、`kev/serve.py`、`playground/`、`modal_app.py` |

**一条最低成本的前置补法**:如果你已经会 HF `transformers` 的 `AutoModelForCausalLM` + 会写交叉熵训练循环,那前置就够了,直接进入第 2 层。缺 attention mask 细节的,建议先手写一个 `[B,1,L,L]` 掩码把两条序列"隔离"的小实验,再读 `branch_mask_batch` —— 否则这段代码看起来只是"一堆 torch 广播"。

---

## 2. Kev 特有概念(这些是真正需要"重新学"的)

按概念 → 代码锚点 → 为什么存在:

1. **state + questions 输入范式**:`state` 是所有问题共享的"待判断文本"(合同/工单/告警),每个问题编成一条 **branch**(`<q> 指令 <opt>…</opt>… <decide>`)。→ `kev/model.py:encode()`。
2. **block-causal mask / 分支隔离**:token 能读"state + 自己那条分支",读不到兄弟分支 → `branch_mask()` / `branch_mask_batch()`。业务动机:一次请求问三个问题(归口部门 / 是否升级 / 情绪),不能被彼此措辞污染。
3. **prefill-only 决策输出**:不生成 token,输出 K 维 logits。三种题型统一到一个指针头:`noul`→`p(true)`,`choice`→argmax+分布,`score`→期望等级 `Σ i·p[i]`。→ `kev/api.py:to_record()/to_answers()`。
4. **pointer readout(指针头)**:用 `<decide>` 的隐向量 query 每个 `</opt>` 边界隐向量 → logits。→ `kev/model.py:PointerHead.forward()`。这是"为什么必须存在 `<opt>/</opt>` 边界 token"的答案。
5. **row form 与 hybrid backbone**:Qwen3.5/3.8 含 **Gated DeltaNet** 线性注意力层,它是递归的、**不认任意 4D 掩码**;于是每问拆成"state + 该分支"一条独立因果行,数学上等价。→ `kev/model.py:is_hybrid()`、`rows_of()`,等价性由 `tests/test_model.py::test_rows_match_packed` 守住。**这一条是整个仓库复杂度的根源**。
6. **conv state / recurrent state / prefix cache**:hybrid 走行形式会把 state 重复算 q 次,于是服务侧缓存"state 前缀"(attention 的 K/V + DeltaNet 的 conv 窗口与 recurrent state)跨请求复用 → `kev/serve.py:PrefixCache`;训练侧对应 `kev/shared_prefix.py:Prefix/branch_hidden()`。
7. **option isolation 与排列不变性**:默认 packing 里选项 2 能看见选项 1。`encode(option_isolation=True)` 把每个选项 span 变子分支、共享 position,使表示天然排列不变;**仅在 attention-only 骨干可用**。→ `branch_mask_batch(opts=...)`。⚠️ 注意 `README.md` Limitations:选项顺序仍可能改变答案。
8. **校准概率与"温度从哪来"的纪律**:每个 checkpoint 在 `head.pt` 里带一个 T,加载时应用。round 19 的教训写进了 `PLAN.md` standing rules 与 `docs/knowledge/04` §4:温度只能拟合在**训练语料之外的 held-out 数据集池**上,拟合在训练源的 development 行上是 in-distribution(ECE 虚低 0.059 vs 0.0085)。护栏:`kev.rounds.pool_conflicts`、`scripts/calibrate_checkpoint.py`、`kev/metrics.py:served()`。
9. **冻结套件与四分区**:`evals/<version>/<suite>/{manifest.json, *.jsonl}`,分区 `train / calibration / development / test`,manifest 钉死 dataset+base revision+每个分区 sha256。→ `kev/suite.py:CONTEXT / SERVING_CONTEXT / ADMISSION_TOKENIZER / load_split()`。
10. **development 选点、test 只读一次**:`--allow-test` 是唯一读锁定 test 的通道;读数面板一旦读过就成为后续的选择/回归集。→ `PLAN.md`「Standing rules for every round」。
11. **指标族**:`accuracy / ECE / Brier / NLL / coverage_at_error / AURC(risk-coverage curve) / permutation flip / isolation / calibration_by_length`。→ `kev/metrics.py`。
12. **environment(kernel set)**:logits 依赖包版本、GPU、backbone dtype、attention 实现、DeltaNet forward 是否被 `fused_qwen35` 替换……**逐 bit 配对两次读数前必须先对 environment**。→ `kev/predictors.py:kernel_environment()`,写进 `report.json`。
13. **rounds 科研流水线**:round spec 先 commit 再训练/读数;`validate → launch → watch → launch-reads → readout → confirm`;arms/parents/panels/criteria/temperature pool。→ `kev/rounds.py`、`experiments/rounds/r<N>.json`。
14. **垂直部署 = 发布 ckpt + 行业 delta + 行业 head + 行业 T**,路由只看**声明风险等级**、**绝不看 state 内容**(否则在校准模型前插了个未校准分类器)。→ `kev/vertical.py`。
15. **token 级显存预算**:`--pass_tokens_max N` / `--row_budget N` / `--length_sort 1` / `--none_pair_max_state N`。存在理由是 round 21 用"字符计划"在第 62 步 OOM(`AGENTS.md`)。→ `kev/train.py:plan_shapes()`、`none_pairs()`。

---

## 3. 按模块拆分:核心概念 / 关键入口 / 常见陷阱

### 3.1 模型架构

- **要懂的概念**:causal LM backbone 去头、4D additive mask、自定义 position ids、指针读出、hybrid 的两种路径(packed mask vs row form)、option isolation、训练/服务两套上下文预算、special token 复用与转义。
- **入口(建议按此顺序读)**:`kev/model.py` 的 `SPECIAL`/常量 → `user_tokens()` → `encode()` → `branch_mask_batch()` → `rows_of()` → `PointerHead` → `DecisionModel.__init__/forward` → `admit()`;然后 `kev/fused_qwen35.py:fuse()/deltanet_forward()`(服务侧融合 kernel)、`kev/shared_prefix.py`(训练侧等价实现)、`kev/cuda_graphs.py`、`kev/mlx_model.py`(Apple Silicon 后端,同一 `SCORING_INTERFACE`)。教材:`docs/knowledge/01-model-architecture.md`。
- **陷阱**:
  - 以为 hybrid 能跑 packed mask → `DecisionModel.__init__` 会直接拒绝 `hybrid + option_isolation`。
  - 以为"packed 与 separate 概率一致"等于"选项顺序无关"——不等价(`README.md` Limitations)。
  - `row_pass` 的 memory 逻辑:`rows_per_pass()` 每行都算一遍 cached state,64 问 × 4.8k state 会冲到 24.7 GB(`kev/model.py` 注释)。
  - 不要开 `output_hidden_states`、不要用 peft `trainable_token_indices` 加 token —— `README.md` Troubleshooting 明确记为内存事故。
  - 长 state 用显式 64k×64k mask 会让一步从 44 s 变 150 s 并填满 GPU(`runs/sft-probe/lc-27b-8xh200-mask-ab`),所以无 padding 的 state 走 SDPA flash 因果核 (`kev/shared_prefix.py:_forward` 的 `plain` 分支)。

### 3.2 训练框架

- **要懂的概念**:LoRA 路径 vs `--full_ft`(整 backbone,vision tower/LM head/MTP 永不加载)、损失叠加(CE 主 + permutation KL + anchor KL + label_smoothing/brier/focal/ord_w)、数据三入口(`--suite` / `--data` / `--n_per_source`)、增强(`--p_none*`、`--synthetic_repeat`、`--public_frac`)、显存可预测性(token 形状计划、length sort、row budget)、resume/snapshot 的二分性、`--init_from` 的配方一致性校验。
- **入口**:`kev/train.py`(docstring 是全参数总览;`question_loss`/`anchor_loss`/`permuted_copy`/`none_pairs`/`plan_shapes`)→ `kev/data.py` → `kev/full_ft.py:MasterAdamW/SnapshotWriter` → `kev/suite.py:load_split` → `kev/anchors.py`、`kev/contrastive.py` → 编排层 `kev/experiment.py`(`DEFAULTS/CHOICES/validated_trial`、`provenance.json`)、`kev/rounds.py`、`modal_app.py`、`kev/budget.py`。教材:`docs/knowledge/02-training-framework.md`;配方与教训:`PLAN.md`、`AGENTS.md` 的 Commands 段。
- **陷阱**:
  - `--init_from` 必须 `--base`/revision/LoRA rank/head 尺寸都对得上,否则加载前就拒绝;从 base 直接训会丢掉 Kev 已有能力(`README.md` 举例 0.33 vs 0.84)。
  - `--none_pair_max_state` / `--pass_tokens_max` 有前置条件(前者要 `--p_none_pair>0`,后者要 `--length_sort 1` + hybrid),`--row_budget` 与 `--perm_kl`/`--anchor_w` 互斥。
  - 一次只能跑一个训练进程(MPS 上两个任务互相拖慢约 10×)。
  - resume 要求"同参数同 world size"才 bit-for-bit;snapshot 永不自动删除,27B 一个约 51 GB,不要擅自从 volume 清理(`AGENTS.md`)。
  - full-weight 试验的续跑由 `kev.rounds watch` 负责,不是 Modal retries;lease(`attempt.json`)机制防止两个容器同时写同一 trial。
  - 表观"免费"的校准损失(round 3 的 `--label_smoothing/--brier_w/--focal_gamma`)没有一个进过发布配方——别指望它们提升排名,smooth 还伤 AURC(`PLAN.md` round 19 段)。

### 3.3 推理服务

- **要懂的概念**:TypeSafe **System One** 契约(drop-in Jev)、`to_record`/`to_answers` 的双向翻译、置信度公式镜像参考适配器、一次 prefill 的批处理预算、prefix cache、准入与 422、可选项预处理 `date_facts`、后端与精度选择。
- **入口**:`kev/api.py`(`SystemOneRequest/Noul/Choice/Score`、`render()`、`to_record()`、`choice_confidence()/score_confidence()`、`date_facts()`)→ `kev/serve.py`(`MODEL_NAMES`、`PrefixCache`、`/v1/systemone`、`/permute`、`/separate`、`/v1/models`)→ `kev/checkpoint.py:LoadOptions`(Hub id / 本地目录、dtype、fused、backend)→ 部署:`deploy/docker-compose*.yml`、`skills/kev-deploy/scripts/kev_serve.py`、`modal_app.py::serving`、`playground/`(Next.js UI)、`kev/console/`(编排控制台,同端口挂 `/console/api/*`)。教材:`docs/knowledge/03-inference-serving.md`;契约与指标:`README.md`「API」「Serving Performance」。
- **陷阱**:
  - 默认 bf16 服务路径与 **fp32 评估路径**概率差 ~0.03(GPU)/0.05(Mac),约 300 题翻一次 top-1;要复刻发表数字用 `KEV_DTYPE=fp32`。
  - `KEV_TEMPERATURE=1` 返回 **raw** 概率而不是校准概率——对比数字前先确认这一点。
  - 超长 state 默认 **422 而非静默截断**;只有 `KEV_TRUNCATE_STATES=1` 才截,且响应会带 `truncated`/`state_tokens`。
  - `usage.output_tokens` 统计的是**序列化答案**的 token,不是生成 token。
  - 融合 kernel 需要 `flash-linear-attention==0.5.2` 且只覆盖 dense MLP(MoE 会拒绝,需 `KEV_FUSED=0`)。
  - 服务侧的融合路径 **没有 backward**,且"继续读 cached DeltaNet state 的那一趟不回写 state" —— 这是与参考实现的两处契约差异(`kev/fused_qwen35.py` docstring)。
  - `KEV_API_KEY` 未设即开放本地服务;生产务必设。

### 3.4 评估系统

- **要懂的概念**:分数行的最小单位是"每个问题一行"(带 logits);校准三件套 ECE/Brier/NLL;选择性预测 `coverage_at_error` / AURC;按 state 长度分桶的校准;permutation 与 isolation 稳健性;温度拟合;配对 record-clustered bootstrap;冻结套件与分区泄漏;`environment` 可比性;rounds 面板/判据/确认阶段。
- **入口**:`kev/benchmark.py`(`validate_distribution()`、`prediction_rows()`,产物 `rows.json` + `report.json`)→ `kev/metrics.py`(`_row_scores`/`ece`/`nll_at_temperature`/`fit_temperature`/`coverage_at_error`/`risk_coverage_curve`/`calibration_by_length`/`served`)→ `kev/predictors.py`(`LocalPredictor`/`RemotePredictor`/`RotationAveraged`、`kernel_environment`)→ `kev/calibrate.py`、`kev/compare.py`、`kev/rounds.py`、`kev/jev.py`(经 Vercel AI Gateway 打 Jev)、`scripts/breadth_report.py`、`docs/claims.json` + `scripts/verify_claims.py`。教材:`docs/knowledge/04-evaluation-system.md`。
- **代表套件的作用**(读 `evals/` 时的分工):`evals/v7/decision-v7`=发布训练配方与 in-distribution 读数;`evals/v4/transfer-v4`、`evals/v9/transfer-v9`=新源(MMLU-Pro、埋状态、不可知);`evals/breadth-v1`=14 个 held-out 数据集的 Decision Index(README 的 index 就来自它,**绝不能进训练语料**);`evals/hard-v1`、`devtools-v1`、`documents-v1/v2`、`longdoc-v1`=技能/真实文档/长文探针;`evals/smoke-v1`=测试用。
- **陷阱**:
  - 对两次读数逐 bit 配对前 **先比 `report.json.environment`**(包版本/GPU/dtype/attention 实现/DeltaNet forward)。
  - `accuracy` 对温度不变(argmax 不变),`Brier/ECE/NLL/AURC` 全都变——"served against served" 是硬规则。
  - 外部套件的 `rows.json` 是入库的,专门为了事后重算校准;私有数据集的行要靠 `scripts/private_rows.py` 还原,否则 `tests/test_rounds.py` 相应 case 会 skip。
  - 只有干净 `_meta.variant` 的行会被评分(`_meta.twin` 表示被筛查出近重复孪生)。
  - `REMOVED_SUITES`(scienthoon-v1、wanli-v1/v2、typesafe-v1)带原因拒绝读取,后续轮次直接拒绝;过去 verdict 不改。
  - `kev.evaluate` 是**旧原型**评测(`runs/kev`、`eval.json`),不用于发布——别拿它的数字比较。

---

## 4. 新手循序渐进路径(含"可跳过 / 必须先补")

### 阶段 0:半天,建立体感(先跑再读)

```powershell
uv sync --extra serve
# 1 分钟 smoke:整条 encode → loss → step 链路
uv run python -m kev.train --n_per_source 40 --accum 4 --out runs/smoke
# 对冻结的 smoke 套件评分,产出 rows.json / report.json
uv run python -m kev.benchmark --run runs/smoke/checkpoint --suite evals/smoke-v1 --out runs/smoke-bench
# 起服务并打一发混合请求(noul + choice)
uv run --extra serve python -m kev.serve --run runs/smoke/checkpoint --port 8009
```

再打开 `docs/knowledge/architecture-flow.html` 的动画,以及 `playground/`(`npm run dev -- -p 3001`)里的 "Packed vs separate" 和 "Permute" 预设 —— 这两个交互一次能讲清"分支隔离"和"顺序敏感性",比读代码快。

### 阶段 1:1–2 天,架构主线(必读,不可跳)

`docs/knowledge/01-model-architecture.md` + 按顺序读 `kev/model.py`:`encode → branch_mask_batch → rows_of → PointerHead → DecisionModel.__init__`,并跑 `uv run pytest tests/test_model.py -k rows_match_packed` 亲眼看到两条路径等价。
此阶段必须补齐的前置:**4D additive mask + 自定义 position ids**(不补就只能背结论)。
此阶段可跳:`fused_qwen35.py`、`shared_prefix.py`、`cuda_graphs.py`、`mlx_model.py`(知道它们存在、分别解决什么问题即可)。

### 阶段 2:1–2 天,评估与校准(必读,不可跳 —— Kev 的"灵魂")

读 `docs/knowledge/04-evaluation-system.md`,配 `kev/benchmark.py:prediction_rows` → `kev/metrics.py:_row_scores/ece/fit_temperature/served`。
动手:对上一步的 `runs/smoke-bench/rows.json` 跑 `uv run python -m kev.calibrate --rows ...`(report-only),看 raw / shipped / OOF 的差别。
然后读 `README.md` 的「Benchmarks/Calibration/Models」三节 + 一份 model card(`docs/model-cards/kev-4b.md`)和一个 `runs/*/report.json`,理解"发表数字是怎么来的"。
必须补的前置:**ECE/Brier/NLL/AURC 的概率论含义 + bootstrap CI**。可跳:`kev/jev.py`、`evals/breadth-v1` 的 14 个数据集细节。

### 阶段 3:2–3 天,训练框架(先 LoRA,后 full_ft)

读 `docs/knowledge/02-training-framework.md`,再按 `kev/train.py` docstring → `question_loss/anchor_loss/permuted_copy` → 数据三入口(`--suite`/`--data`/`--n_per_source`)→ `kev/suite.py:load_split` 走。
用 README「Fine-Tune on Your Own Data」那条 `--init_from` 命令做一次真实微调(数据用 `data/critical-value.jsonl` 或自备 JSONL),然后 `kev.benchmark --data heldout.jsonl` 对比微调前后 —— 这是理解"配方一致性校验 + 温度重拟合"最快的路径。
**可跳(先跳过,后面再回来)**:`--full_ft` 分支、FSDP2/torchrun、`MasterAdamW`、`SnapshotWriter`、resume 的 RNG/数据位置、Modal lease/spawn ledger、`plan_shapes/pass_tokens_max/row_budget` 的细节。它们存在理由是 27B 的显存/超时/续跑工程,读 0.8B/4B 的 LoRA 路径完全不需要。

### 阶段 4:1–2 天,推理服务与部署

读 `docs/knowledge/03-inference-serving.md`,顺序 `kev/api.py` → `kev/serve.py`(重点 `PrefixCache` 与三个路由)→ `kev/checkpoint.py:LoadOptions`。对照 `README.md`「Serving Performance」表理解"为什么一次 pass 只放一行 16,384 token"。部署侧挑一条走通即可:`deploy/docker-compose.yml` 或 `skills/kev-deploy`。
**可跳**:`mlx_model.py`、`cuda_graphs.py`、`fused_qwen35.py` 的 kernel 级细节、`kev/console/`、医疗/垂直路由 `kev/vertical.py`(除非你要做行业部署 —— 但它 docstring 里"路由不看 state 内容"那条红线值得提前读,它是最能体现这个项目判断力的地方)。

### 阶段 5:进阶(只在你要动研究流水线时才读)

`kev/experiment.py`(`validated_trial`、`provenance.json`)→ `kev/rounds.py`(`validate/launch/watch/launch-reads/readout/confirm`、`paired`、`pool_conflicts`)→ 一份 spec(`experiments/rounds/r24.json` 或已归档的 r5)→ `PLAN.md` 的 standing rules 与 round 19/20 结果表(它们是"为什么会失败、护栏为什么长这样"的案例研究)→ `AGENTS.md` 的 Study/Rounds 大段 + `docs/autoresearch.md`(无人值守研究的运行手册)→ `modal_app.py` 与 `kev/budget.py`。
离线复现:`uv run python -m kev.rounds validate experiments/rounds/r5.json`、`uv run --extra serve python -m pytest tests/test_rounds.py -q`。

### 必须先补 vs 可以后补(压缩结论)

- **必须优先补(否则读不动)**:4D attention mask 与 position ids;softmax/CE/KL;temperature scaling 与 ECE/Brier/NLL;coverage/AURC 的选择性预测;bootstrap 配对区间与 record 聚类;LoRA 与 target 选择;token 预算与冻结套件/分区泄漏纪律;`uv`/`pytest`/FastAPI-Pydantic 基本操作。
- **可以先跳过,遇到再回来**:DeltaNet/fla Triton kernel 的实现细节、CUDA graphs、MLX 后端、FSDP2 + host-memory master 的分片续训、snapshot/mirror/HF Hub 镜像、Modal lease 与 spawn ledger、私有 SFT 语料与 `sft-v2` 组件、`playground` 与 `console` 前端、rounds 19–26 的具体判据数值、被移除套件的历史仲裁。

### 一个 useful mental model

把 Kev 想成"**一个带自定义掩码和自定义读出头的多分类器**",而不是"一个 LLM"。于是你所有传统 LLM 直觉都要做一次替换:输出不是词表分布而是选项分布;评价不是 BLEU/win-rate 而是 ECE/Brier/AURC;prompt 工程不存在,替代物是"题型的编码方式 + 可选的 `date_facts` 预处理";"上下文长度"不再是能不能装下,而是**在训练过的 state 长度之外准确率还准不准**(`calibration_by_length` + model card 的 validated context);而"更强模型"也不等于更好 —— `README.md` Limitations 与 `PLAN.md` round 19/20 反复说明:全量微调带来广度增益的同时,可能赔掉短状态校准与个别技能,这正是这套评估系统存在的理由。
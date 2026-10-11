# 17. 分阶段学习路径（必补 / 可跳）

> 《Kev 基础知识系统学习指南》· 第四部分 路径与总结
>
> **本部分目标**：把前三部分收拢成可执行的东西——一条按背景分叉的学习路径、一张公式与常量的速查表、 一份术语表，以及一个能逐条复现的示例索引。
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](16-rounds.md) · [下一章 →](18-cheatsheet.md)

---


### 17.1 概念定义

**一张图、三条路径。** 本文档的 18 章不是必经序列：它们按“概念依赖”而不是“页码”排列，所以不同背景的人应该走不同的子集。
三个变量决定你该读什么：会不会写 PyTorch 的 attention mask、有没有“校准”这个概念、是否需要改训练代码。

<div style="font-family:monospace;background:#0d1117;color:#c9d1d9;padding:18px;border-radius:8px;overflow-x:auto">
<style>
@keyframes pw { 0%{left:0;opacity:0} 6%{opacity:1} 92%{opacity:1} 100%{left:100%;opacity:0} }
.pw-pipe{position:relative;padding:12px 0}
.pw-dot{position:absolute;top:50%;margin-top:-5px;width:10px;height:10px;border-radius:50%;
  background:#58a6ff;box-shadow:0 0 8px #58a6ff;animation:pw 5.2s linear infinite}
.pw-dot.p2{animation-delay:1.7s;background:#3fb950;box-shadow:0 0 8px #3fb950}
.pw-dot.p3{animation-delay:3.4s;background:#d2a8ff;box-shadow:0 0 8px #d2a8ff}
.pw-l{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:2px 7px;margin:0 3px;font-size:12px}
.pw-l b{color:#58a6ff}
.pw-note{color:#8b949e;font-size:12px;margin-top:8px}
.pw-a{color:#58a6ff}.pw-b{color:#3fb950}.pw-c{color:#d2a8ff}
</style>
<div class="pw-pipe">
  <span class="pw-dot"></span><span class="pw-dot p2"></span><span class="pw-dot p3"></span>
  <span class="pw-l"><b>入门篇</b> 1–5</span>→
  <span class="pw-l"><b>进阶篇</b> 6–12</span>→
  <span class="pw-l"><b>应用篇</b> 13–16</span>→
  <span class="pw-l"><b>速查</b> 17–18 + 附录</span>
</div>
<div class="pw-note">
  <span class="pw-a">路径 A（有 DL 基础的后端/服务工程师）</span>：1 → 5 → 6 → 8 → 14 → 附录；
  <span class="pw-b">路径 B（算法/评估背景）</span>：1 → 4 → 9 → 10 → 11 → 12 → 15 → 16；
  <span class="pw-c">路径 C（训练方向）</span>：1 → 3 → 5 → 6 → 7 → 8 → 11 → 12 → 13 → 16。
</div>
</div>

### 17.2 路径表：每章的前置与可跳条件

| 章 | 前置 | 必读人群 | 可跳条件（以及代价） |
|---|---|---|---|
| 1 定位与地图 | 无 | 所有人 | 不可跳（它定义“不做什么”） |
| 2 Transformer 最小集 | 会写 PyTorch | 路径 A 可快速扫 | 已能手写 additive mask 与理解 \(\sqrt{d}\) 缩放 |
| 3 Tokenizer 与特殊 token | 2 | 所有人 | 不打算自己拼 record / 不改 `encode()` |
| 4 概率与损失 | 无 | 路径 B | 熟 softmax / 交叉熵 / KL，且知道温度为何不改 argmax |
| 5 record 数据单元 | 3 | 所有人 | 不可跳（它是后面所有章的公共语言） |
| 6 block-causal mask | 5 | 训练/架构 | 只想调服务参数且相信“分支互不影响” |
| 7 PointerHead | 4, 6 | 训练/架构 | 不碰 `--head_dim` / `--special_embeddings` |
| 8 行形式与混合骨干 | 6 | 训练/服务 | 不读 `shared_prefix` / 不懂为何批处理不影响答案 |
| 9 温度校准 | 4 | 评估/服务 | 不可跳：部署时一定会被问“这个概率能不能用” |
| 10 指标族 | 9 | 评估 | 不读 ECE / AURC / coverage 的含义（报告只能当装饰品） |
| 11 配对 bootstrap | 10 | 评估/科研 | 不做“A 比 B 好吗”的判定 |
| 12 冻结套件与数据纪律 | 5 | 所有人 | 不可跳：它是一条红线而不是一个选项 |
| 13 训练实操 | 7, 8, 12 | 训练 | 不训新 checkpoint |
| 14 服务实操 | 5, 8 | 服务 | 不部署、不调前缀缓存/批量 |
| 15 评估实操 | 10, 11, 12 | 评估 | 不读 `report.json`（那所有结论全部不可验证） |
| 16 rounds | 11, 12, 15 | 科研 | 不做轮次比较（它本身是科研专用引擎） |
| 17 路径 | 无 | 刚开始的人 | — |
| 18 速查 | 全部 | 所有人 | — |

### 17.3 三个可执行路线

**路线一：45 分钟，只弄懂“一句话模型”。**

注意 `examples/kev_example.py` **不是独立脚本，它是一个 HTTP 客户端**（docstring 第一行就写着“对接本地已部署的 `kev.serve`”）。所以正确顺序是先起服务、再跑例子；直接跑它只会得到 `❌ 无法连接 http://127.0.0.1:8008：[WinError 10061]`。

```powershell
uv sync                                                            # 安装（可编辑）

# 要自己训一个 smoke checkpoint 才需要网络（--n_per_source 从公开数据集现造记录）
uv run python -m kev.train --n_per_source 40 --accum 4 --out runs/smoke   # 有网时约 1 分钟

# 终端 1：起服务（serve extra 里有 FastAPI；用仓库里现成的 smoke checkpoint，可离线）
$env:HF_HUB_OFFLINE = "1"                                          # 没网就把这一步当路线一的起点
uv run --extra serve python -m kev.serve --run runs/smoke-mirror --port 8008
# 终端 2：等 /v1/models 返 200 之后
uv run python examples/kev_example.py                              # 第 1 章的例子
```

本机实测（服务与例子那两步）：`Application startup complete` + `serving runs/smoke-mirror … on cpu via torch (float32) 127.0.0.1:8008; states over 65,536 tokens refused (422)`，随后两条 `POST /v1/systemone` 都是 200。真实响应（纯 smoke checkpoint，数值只验结构不验质量）：

```text
✅ 服务可达：http://127.0.0.1:8008
已加载模型：name kev-latest / run runs/smoke-mirror / base Qwen/Qwen3-0.6B-Base (lora rank 8)
           device cpu / torch / float32 / temperature 1.0000
pick        [choice] 选中 kev-4b  置信度 0.0654  prob {kev-4b 0.5327, kev-0.8b 0.4673}
fits_vram   [noul]   yes 的概率 0.5447
fit_score   [score]  期望等级 2.0325  legend 0..4（很差..很好）
           probabilities {0:0.1571, 1:0.2988, 2:0.1321, 3:0.1787, 4:0.2333}  confidence 0.0
usage      input_tokens 247 / output_tokens 252 / latency_ms 1120.6
```

三个数字值得先记住：`score` 的 `confidence 0.0` 不是 bug——概率几乎摊平时 `score_confidence` 就是 0（第 10 章）；`output_tokens 252 > input_tokens 247` 也不是生成了文本，它是“选项边界 token + 分支”的计数口径（第 3、14 章）；`latency_ms` 是这一批的模型时间，不含排队。

完成后你应能回答：一条 record 里 `state` 与 `questions` 的关系？为什么不生成文本？为什么批处理不影响任何一条答案？

**路线二：一天，把第 5 / 6 / 10 / 11 章的🟢例子全部跑完。**

```powershell
# 不下载任何 checkpoint、不需要 GPU 的那批示例（文中每个🟢块都已在本机实测）
uv run python -c "from kev.metrics import metrics; print(sorted(metrics([{'variant':'clean','type':'noul','label':1,'p':[0.3,0.7],'keys':['false','true'],'task':'t','source':'s','group':'g'}]).keys()))"
```

完成后你应能回答：ECE 与 confidence_bias 什么时候符号不同？为什么不聚类会让区间偏窄？`coverage_at_5pct_error` 为何不是部署保证？

**路线三：一周，从训练到读数跑一轮完整链条。**

逐步的可跑状态：第 2/3/4/5 步的**命令形状**已在本机对 `runs/smoke-mirror` 跑通（把 `--run` 换成你自己的目录即可，第 15/16 章的数字就建立在这些跑通的产物上）；只有第 1 步（从新基座训一个 checkpoint）需要网络。

```powershell
# 1) 训练一个自己的小 checkpoint（第 13 章）
uv run python -m kev.train --suite evals/smoke-v1 --base Qwen/Qwen3-0.6B-Base --out runs/my-kev
# 2) 读数（第 15 章）
uv run python -m kev.benchmark --run runs/my-kev --suite evals/smoke-v1 --out runs/my-kev-bench
# 3) 温度体检（第 15 章）
uv run python -m kev.calibrate --rows runs/my-kev-bench/rows.json
# 4) 服务它（第 14 章）
uv run --extra serve python -m kev.serve --run runs/my-kev --port 8008
# 5) 读一份真实 spec，但不 launch（第 16 章）
uv run python -m kev.rounds validate experiments/rounds/r27.json
```

### 17.4 自检清单（能不看文档复述才算过）

- **入门篇**：① 一句话讲 Kev 做什么；② record 的两层结构与三个题型；③ 为何选项边界 token 不可伪造；④ `softmax` 与温度的关系；⑤ 为何公开数据 + 策略记录能训一个不生成的模型。
- **进阶篇**：① block-causal mask 中 padded key / padded query 两个不同处理；② 行形式与 packed 为何等价（因而可批处理）；③ `PointerHead` 读的仍是选项边界而非生成；④ 温度不改 argmax；⑤ ECE / Brier / NLL / AURC / coverage 各自回答什么问题；⑥ 为何 bootstrap 必须按 record 聚簇；⑦ 哪些数据永远不能进训练 corpus。
- **应用篇**：① 一条请求在 `Server` 里的八步；② 前缀缓存三条边界与它的实测数量级；③ 训练预算的三种互相排斥的语言（`--none_pair_max_state` / `--pass_tokens_max` / `--row_budget`）；④ `report.json` 的 22 个顶层块与三条红线；⑤ 为什么隔离不在 `report.json`；⑥ rounds 为什么“先提交规则再读数”。

### 17.5 常见陷阱（关于学习本身）

- **先读 13–16 再回头补 6–8**：应用章里每一个开关都是架构章里某个不变量（只看命令参数会记住开关而记不住它为何存在）。
- **把“能跑”当“懂了”**：本文的🟢例子故意不依赖 GPU；它们能跑不等于你能解释为何 `none_absent` 的 acc 必须是 0。
- **跳过第 12 章**：它是唯一一章“错了就污染所有后续结果”的章；其它章的陷阱只会让你慢，这一章的陷阱会让你错。
- **想一次读完 18 章**：路径 A/B/C 都只覆盖 8–10 章；剩下的当参考页用。

**关键结论**：路径不是课程表，是依赖图的拓扑排序。**不可跳只有四章：1、5、9、12**；它们分别定义“做什么 / 数据长什么样 / 概率能不能用 / 什么数据不能碰”。其余章按你的任务加。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](16-rounds.md) · [下一章 →](18-cheatsheet.md)

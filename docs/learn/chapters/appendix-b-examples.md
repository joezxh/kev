# 附录 B. 示例代码索引

> 《Kev 基础知识系统学习指南》· 第四部分 路径与总结
>
> [⌂ 目录与架构图](../index.html) · [← 上一章](appendix-a-glossary.md) · [下一章 →](../README.md)

---


### B.1 图例

| 标记 | 含义 |
|---|---|
| 🟢 | **不下载模型、不需要 GPU、不需要网络**；秒级跑完，最适合验证“你真的读懂了” |
| 🟡 | 需一次下载（基座或 tokenizer）**或** 需较长时间 / GPU；结果不依赖随机性 |
| ▶ | 文档里的命令块（可直接粘到 PowerShell） |
| 产物 | 写盘的位置；除注明外均为本机实际生成过的路径 |

### B.2 全量索引

行号指各章文件（`chapters/NN-*.md`）内的行号；目录页 `index.html` 的每章卡片也给出该章的起点行。

| 章 | 示例（行号） | 依赖 | 它验的是什么 |
|---|---|---|---|
| 1 | 起服务 + 问三种题（84, 90） | 🟡 | 一句话模型对外长什么样；库路径不需要服务 |
| 2 | 手写 additive 因果掩码（33）；transformers 尊重自定义 4D mask（50） | 🟢 | \([1,1,L,L]\) 加性掩码与 `position_ids` 的关系 |
| 3 | 一条 record 变成 token 序列（41） | 🟡（tokenizer） | 边界 token 为何不可伪造；`<state>` 计入长度 |
| 4 | 从 logits 到训练损失（32） | 🟢 | softmax / 交叉熵 / KL 的最小可跑样例 |
| 5 | 标注行 → 模型输入（90） | 🟡 | record 的两层结构与三个题型 |
| 6 | 自实现块因果掩码（77）；Kev 实现（99）；**隔离性实验**（110） | 🟢 | 改题 1 的选项文字，题 2 的 logits 逐 bit 不变 |
| 7 | 直接操作 head（75）；三题型共用一个头（94） | 🟢 | 温度改形状不改 argmax；题型只是映射差异 |
| 8 | 行拆分结构（78）；packed 拆行（90）；两条路径等价（105） | 🟢 / 🟡 | 行形式与 packed 为何等价（因而可批处理） |
| 9 | 拟合温度（74）；in-sample vs out-of-fold（107） | 🟢 | 温度的乐观偏差：同一批行拟合会好看 |
| 10 | 读真实 rows 打印全字段（131）；acc 不变 / ece 变（153）；长上下文分桶（177） | 🟢 | 16 个指标字段各自回答什么问题 |
| 11 | 聚类 vs 独立的区间宽度（103）；四道拒绝条件（153, 169）；`runs/compare-demo.json`（170） | 🟢 | 不聚簇会错多少；`suite_sha256` 不等就拒 |
| 12 | 读套件合同并验 `suite_sha256`（121）；五道门（143）；eval-only 进训练被拒（178）；移除套件带理由拒绝（202） | 🟢 | 数据纪律在代码里是哪五道门 |
| 13 | 损失装配（115）；预算与长度排序（145）；smoke 训练与产物（159, 160） | 🟢 / 🟡（需网络） | 开关 → 损失项 → 预算的对应关系 |
| 14 | A 对外合同（131）；B PrefixCache（168）；C 选项序平均（196）；D 端到端（222）；E HTTP 面（263, 266） | 🟢 ×3 / 🟡 ×2 | 八步生命周期、缓存三条边界、服务路径 vs 精确路径 |
| 15 | A 端到端评估（186）；B 逐块读 `report.json`（216）；C 温度四臂（255）；D 手造 6 行走 `summarize`（265）；E 隔离门控（301） | 🟡 / 🟢 / 🟡 / 🟢 / 🟢 | 22 个顶层块、objective 逐位验证、无模型也能懂汇总 |
| 16 | A `validate` 两种真实输出（120）；B `readout` 表格（141）；C read-out 与 verdict 结构（160）；D `paired()`（191）；E 判据路径语言（209） | 🟢 ×5 | spec 先提交、面板/判据/排序、配对区间手算 |
| 17 | 三条路线（69, 100, 109） | 🟡 | 从起服务到读数到验证的完整链条 |
| 18 | 公式与常量速查 | — | 不需要跑：这一章是其它 17 章的索引 |

### B.3 本文产物清单（均在本机生成过）

| 路径 | 怎么来 | 内容 |
|---|---|---|
| `runs/smoke-mirror` | 仓内已有 | 第 1/14/15/17 章的服务与读数对象（Qwen3-0.6B-Base + LoRA rank 8） |
| `runs/learn-smoke-bench/{report,rows,predictions}.json(l)` | `python -m kev.benchmark --run runs/smoke-mirror --suite evals/smoke-v1 --out runs/learn-smoke-bench` | 第 15 章全部字段实测来源（clean n=18） |
| `runs/learn-smoke-bench/calibration.json` | `python -m kev.calibrate --rows runs/learn-smoke-bench/rows.json` | 第 15 章四臂（raw/shipped/workload/workload_oof） |
| `runs/learn-r5-readout/round5.json` | `python -m kev.rounds readout experiments/rounds/r5.json --out runs/learn-r5-readout` | 第 16 章的离线可读 read-out |
| `runs/learn-r27-readout/round27.json` | 同上，针对 r27 | 第 16 章的 **incomplete** 对照组（缺私有读数） |
| `runs/compare-demo.json` | 第 11 章 🟢 块写出 | 两个合成读数目录，给 `kev.compare` 的四道拒绝用 |

> **重跑注意**：读数目录不可覆写（`mkdir(exist_ok=False)`）。重跑同一命令需先换名或删旧目录。

### B.4 一分钟健康检查（本机实测结果如实记录）

```powershell
uv sync
# 离线的纯 CPU 子集：实测 7 passed, 118 deselected in 15.15s
uv run pytest tests/test_unit.py -q -k "mask or metrics or temperature"
# 不碰数据、不下载，秒级：实测 `round 27: ok (2 arms, 0 studies)`
uv run python -m kev.rounds validate experiments/rounds/r27.json
```

**哪些命令需要网络（而不是你的显卡）**：

- `pytest tests/test_unit.py -q` 的**全量**跑需要网络。本机离线实测：`35 failed, 88 passed` + 2 errors，失败原因都是 `httpx.ConnectTimeout` / HF datasets 缓存未命中（不少用例要拉 tokenizer 或小模型）——不是仓库坏了。想离线绿灯就用上面的 `-k` 子集。
- `python -m kev.train --n_per_source N` 需要网络：它从公开数据源现造记录。本机离线实测失败于 `FileNotFoundError: …huggingface\datasets\Yelp___yelp_review_full\…dataset_info.json`。
- 不需要网络就能跑完的链路（本文所有 🟡 服务/评估示例走的都是它）：`HF_HUB_OFFLINE=1` + `--run runs/smoke-mirror`（基座已在 HF 缓存里）。

三条都绿，本文的🟢示例全部可跑；🟡示例只需多一次基座/数据集下载（CPU 可跑完，慢但不依赖显卡）。

---

**文档结束。** 全文 18 章 + 附录 A/B：入门篇 1–5 建立“record → 概率”的共同语言，进阶篇 6–12 拆开 Kev 特有的六个不变量（隔离、指针读出、形式等价、温度、指标口径、数据纪律），应用篇 13–16 把四个入口实操一遍，路径与总结（17–18）回答“先看哪里”与“记错什么会坏”。所有数字均来自仓内代码或本机实测产物；如与代码不一致，以代码为准，欢迎报告本文与仓库的出入。

---

[⌂ 目录与架构图](../index.html) · [← 上一章](appendix-a-glossary.md) · [下一章 →](../README.md)

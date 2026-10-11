# Kev 基础知识系统学习指南（分章版）

> 18 章 + 两个附录，每章一个独立 Markdown 文件；[`index.html`](./index.html) 负责**章节目录**、
> **架构流程动画**与**浏览器内渲染**（不依赖任何 CDN，不需要联网）。
> 想按模块深挖，另有四篇教材在 [`docs/knowledge/`](../knowledge/README.md)：本指南是它的前置课。

## 怎么读

1. **浏览器打开 [`index.html`](./index.html)** —— 顶部是数据流转动画（推理路径 + 训练/验证闭环 + block-causal 掩码呼吸），
   下面是章节目录，点卡片直接在本页阅读该章；页内还提供**通读模式**（20 章拼接，可 Ctrl-F 与打印存 PDF）、
   **全文搜索**（搜章名也搜正文）、**深/浅主题**、`[` `]` 翻页，本 README 本身也能在页内渲染。
2. 或者在编辑器里直接读 `chapters/*.md` —— 每章开头有面包屑（目录 / 上一章 / 下一章），结尾有回跳导航。
   章节文件是**唯一真相源**，`index.html` 不复制任何正文，只用浏览器 `fetch` 读它们。

### 让 md 在浏览器里可读（两种办法，任选）

```powershell
# ① 起一个静态服务（推荐：这样 chapters/*.md 与指向 kev/*.py 的代码锚点都能直接点开）
uv run python -m http.server 8199          # 在仓库根目录执行
# 然后访问 http://127.0.0.1:8199/docs/learn/index.html

# ② 不想起服务：双击打开 index.html（file://），再把 chapters/ 里的任意 .md 拖进页面即可渲染
```

浏览器默认禁止 `file://` 页面读取本地文件（Chrome / Edge 的标准行为），所以直接双击时页面会提示上面的两种办法——
这是浏览器规则，不是本文档坏了。即便你的浏览器允许同目录读取（部分内核会放行），指向 `kev/*.py` 的代码锚点仍然需要办法 ①。

## 学习路线图

| 阶段 | 章 | 文件 | 你会搞懂 | 前置 | 依赖 |
|---|---|---|---|---|---|
| 入门 | 1 | [定位与学习地图](./chapters/01-positioning.md) | 决策模型而非聊天模型；一次请求端到端长什么样 | 无 | 🟡 |
| 入门 | 2 | [Transformer 最小集](./chapters/02-transformer.md) | 自回归、加性 mask、`position_ids`、√d 缩放 | 会写 PyTorch | 🟢 |
| 入门 | 3 | [Tokenizer 与特殊 token](./chapters/03-tokenizer.md) | 选项边界为何不可伪造 | 2 | 🟡 |
| 入门 | 4 | [概率与损失](./chapters/04-probability.md) | softmax / 交叉熵 / KL；温度为何不改 argmax | 无 | 🟢 |
| 入门 | 5 | [数据单元 record](./chapters/05-record.md) | state + questions + 三种题型；unknowable 与弃答 | 3 | 🟡 |
| 进阶 | 6 | [block-causal mask](./chapters/06-block-causal-mask.md) | 分支隔离；隔离性实验（改题 1，题 2 的 logits 逐 bit 不变） | 5 | 🟢 |
| 进阶 | 7 | [PointerHead](./chapters/07-pointer-head.md) | prefill-only 的指针读出，三题型共用一个头 | 4, 6 | 🟢 |
| 进阶 | 8 | [行形式与混合骨干](./chapters/08-row-form.md) | DeltaNet 无法用块掩码 → 每问一行；两条路径为何等价 | 6 | 🟢/🟡 |
| 进阶 | 9 | [温度校准](./chapters/09-temperature.md) | 一个标量掰准分布；四臂对照与 in-sample 乐观 | 4 | 🟢 |
| 进阶 | 10 | [指标族](./chapters/10-metrics.md) | accuracy / ECE / Brier / NLL / coverage / AURC 的口径边界 | 9 | 🟢 |
| 进阶 | 11 | [配对 bootstrap](./chapters/11-bootstrap.md) | 按 record 聚簇重采样；不聚簇会把区间做窄 | 10 | 🟢 |
| 进阶 | 12 | [冻结套件与数据纪律](./chapters/12-frozen-suites.md) | 五道门 + 三条纪律：eval-only 永不进训练 | 5 | 🟢 |
| 应用 | 13 | [训练框架实操](./chapters/13-training.md) | 开关 → 损失 → 预算；LoRA/全量、resume/snapshot | 7, 8, 12 | 🟡 |
| 应用 | 14 | [推理服务实操](./chapters/14-serving.md) | 请求的一生、prefix cache、批量、错误面 | 5, 8 | 🟢/🟡 |
| 应用 | 15 | [评估系统实操](./chapters/15-evaluation.md) | `report.json` 逐块读、objective、隔离门控 | 10, 11, 12 | 🟡/🟢 |
| 应用 | 16 | [科研流水线 rounds](./chapters/16-rounds.md) | 面板 / 判据 / 排序 / 确认，温度池规则 | 11, 12, 15 | 🟢 |
| 总结 | 17 | [分阶段学习路径](./chapters/17-paths.md) | 三条可执行路线与自检清单 | 无 | 🟡 |
| 总结 | 18 | [公式速查与红线](./chapters/18-cheatsheet.md) | 21 条公式 + 22 个常量 + 十二条红线 | 全部 | — |
| 附录 | A | [术语表](./chapters/appendix-a-glossary.md) | 约 48 条术语，五组，各带所在章 | — | — |
| 附录 | B | [示例索引与体检](./chapters/appendix-b-examples.md) | 每个示例的依赖标记与行号、产物清单、离线健康检查 | — | — |

**标记约定**：🟢 = 不下载模型、不要 GPU、不要网络，秒级跑完；🟡 = 需一次下载或较长时间；📖 = 去仓库读哪段代码；▶ = 跑哪条命令。
代码锚点形如 `[kev/model.py](../../kev/model.py)`，指向仓库真实文件；正文优先引用**函数名/类名/常量名**，行号会漂。

## 按角色的三条路线

| 你是谁 | 走这几章 |
|---|---|
| 后端 / 服务工程师（会 PyTorch） | 1 → 5 → 6 → 8 → 14 → 附录 B |
| 算法 / 评估背景 | 1 → 4 → 9 → 10 → 11 → 12 → 15 → 16 |
| 训练方向 | 1 → 3 → 5 → 6 → 7 → 8 → 11 → 12 → 13 → 16 |

每条路线的**可执行命令**（含哪些离线可跑、哪些需要网络）写在 [第 17 章](./chapters/17-paths.md) 与 [附录 B.4](./chapters/appendix-b-examples.md)。

## 一条命令建立体感

```powershell
uv sync --extra serve
# 需要网络：从公开数据源现造记录，约 1 分钟
uv run python -m kev.train --n_per_source 40 --accum 4 --out runs/smoke
# 离线也能跑：用仓内现成的 smoke checkpoint 起服务（第 14 章）
$env:HF_HUB_OFFLINE = "1"
uv run --extra serve python -m kev.serve --run runs/smoke-mirror --port 8008
```

## 目录结构

```
docs/learn/
├── index.html          目录 + 架构流程动画 + md 渲染器（单文件、零依赖、可打印）
├── README.md           本导读
├── chapters/           20 个章节文件（唯一真相源，可在编辑器里直接读）
└── kev-fundamentals.md 单文件版（拆分前的原始稿，只用于整体打印对照；**不再同步更新**，改内容请改 chapters/）
```

---

**下一步**：读完本指南后进入 [`docs/knowledge/`](../knowledge/README.md) 的四篇模块教材（模型架构 / 训练框架 / 推理服务 / 评估系统），
它们的定位是"按模块深挖"，而本指南的定位是"把共同语言先补齐"。

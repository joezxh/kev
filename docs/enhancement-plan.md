# 控制台增强计划 · Console Enhancement Plan

> 依据 `docs/pipeline.md` §4.2 的局限性清单（L1–L8，全部含代码证据）制定。
> Based on the evidence-backed limitations L1–L8 in `docs/pipeline.md` §4.2.
>
> 优先级定义：**P0** = 主链断链（不修则某条端到端路径无法走通）；**P1** = 高摩擦（能用但显著增加人工/易错）；**P2** = 体验与运营增强。
> Priority: P0 breaks a path end-to-end; P1 = high friction; P2 = operational polish.

---

## 1. 能力清单 Capability List

### P0-1 · 打通 G2 的 plan 证据链（修复 L1）

| 项 | 内容 |
|---|---|
| 现状 | `plan_size` 无产物注册（`data.py:113-116`）、`parse_plan_size` 无消费方、前端无 `plan` 字段 → G2 恒失败 → train 无法提交 |
| 差距 | plan 证据在「stdout → 表单 → 请求参数」三步中全部悬空 |
| 方案 | 给 `plan_size` 增加 `artifacts_out=[f"plan:{dir}"]`（新产物类型，`artifacts.resolve` 映射到 `data/console/plan-{dir}.json`）；`_gate_products` 优先读该产物，保留 `request.params.plan` 兼容 |
| 预期目标 | 跑完 plan_size → generate → split → precheck 后，train 可直接提交，G2 自动比对记录数 |
| 验收 | 端到端集成测试：plan_size→generate→split→precheck→train 提交成功；G2 在 records 与 plan 不一致时仍拦截 |

### P0-2 · train / benchmark 暴露 `data` 参数（修复 L2）

| 项 | 内容 |
|---|---|
| 现状 | `JobStagePage` 只透传表单声明字段（`JobStagePage.tsx:89-94`）；train/benchmark 页未声明 `data`，而 distill 产物在 `data/{scenario}/{category}.jsonl` |
| 差距 | 蒸馏链路产出的分区，train/benchmark 无法指向 |
| 方案 | train 页与 benchmark 页各加 `data` 字段（train.py/eval.py 本就支持该参数，纯前端补字段 + ArgvPreview 自动生效）；同时 benchmark 页的 `split` 提示改为「data 模式下仅 development 有意义」 |
| 预期目标 | distill → split(data=…) → precheck → train(同 data) → benchmark(同 data) 全程 UI 内可通 |
| 验收 | 用一个自定义场景走通 distill→split→train→benchmark，全程不改代码 |

### P0-3 · 分离 G4 与 G6 的证据来源（修复 L3）

| 项 | 内容 |
|---|---|
| 现状 | `_gate_products` 只装配一个 comparison（`app.py:93`），G4/G6 都读它（`gates.py:211-216`） |
| 差距 | workload 增益与公开套件回归在语义上需要两份 compare 产物，现状后者覆盖前者 |
| 方案 | compare 阶段增加 `public` 布尔参数：`public=1` 时产物 id 用 `comparison:{run_name}-public`（或新增 `regression:` 类型）；`_gate_products` 同时装配 `comparison`（G4）与 `comparison_public`（G6）；`gates.py` G6 改读 `p.get("comparison_public")` |
| 预期目标 | workload compare 过 G4、公开套件 compare 过 G6，互不覆盖；eval 页分区展示两个 CI |
| 验收 | 单测覆盖两闸各读各的产物；端到端两次 compare 后 image 的 G4/G6 同时以正确语义通过 |

### P1-1 · 温度自动带出与一致性校验（修复 L4）

| 项 | 内容 |
|---|---|
| 现状 | calibration meta 已含 `workload_temperature`（`artifacts.py:98-103`），但 image/deploy 手填 |
| 方案 | image/deploy 表单预填最近一次 calibration 的 `workload_temperature`（前端拉 `api.artifacts("calibration")` 取 meta），并展示「来源 run」徽标；后端可选校验传入温度 == 产物温度，不一致给 warning 而非阻断 |
| 预期目标 | 零手工搬运；温度可追溯（UI 显示出自哪次 calibrate） |
| 验收 | calibrate 完成后打开 image 页，温度已填且标注来源 run |

### P1-2 · few-shot 范例生产闭环（修复 L5）

| 项 | 内容 |
|---|---|
| 现状 | `--examples` 需手工准备标注 JSONL（`data.py:201-206`） |
| 方案 | 新增轻量作业 `make_examples`：从已注册的合法数据/金标集按标签均衡抽样 N 条 → `data/{dir}.examples.jsonl`；distill 表单增加「范例来源」下拉（生成产物路径一键填入） |
| 预期目标 | 冷启动即可用：generate/goldset 产出 → 一键生成范例 → distill 自动引用 |
| 验收 | 从零开始：generate 500 条 → make_examples → distill 的 argv 含 `--examples` 且指向该产物 |

### P1-3 · distill 产物注册与血缘（修复 L7）

| 项 | 内容 |
|---|---|
| 现状 | distill 的 BuiltCommand 无 `artifacts_out`（对照 generate `data.py:150`），产物页/血缘断头 |
| 方案 | distill/distill_daemon 声明 `artifacts_out=[f"dataset:{_dataset_id(data_dir + '/' + category)}"]`；守护模式沿用 `persist=start` 语义的按日追加（沿用既有 upsert） |
| 预期目标 | 蒸馏产物在产物页可见、可追溯到 provider/job |
| 验收 | 跑一次 distill，产物列表出现对应 dataset 条目且血缘指向该 job |

### P1-4 · Modal 端点状态呈现（修复 L6）

| 项 | 内容 |
|---|---|
| 现状 | Modal 端点不在本地产物（`modal.py:52-54`），UI 无处可见 |
| 方案 | modal 作业完成后由 env 中的 `KEV_APP_NAME/KEV_SERVE_RUN` 拼 Modal URL 注册为 `endpoint:modal-{run}`（或新类型），部署页区分「本地/Modal」两栏 |
| 预期目标 | 部署页一处可见两种端点及在线状态 |
| 验收 | modal deploy 后部署页出现 Modal 端点条目并可点击探活 |

### P2-1 · 多端点与端口管理（修复 L8a）

deploy 端口可配（默认 8008 不变）+ 自动生成「改 playground rewrite」的提示片段；双端点共存不再需要手改代码。

### P2-2 · 蒸馏预算与成本视图（修复 L8b）

用量页增加：全局每日 token 预算、per-provider 预算告警（阈值触发 toast/邮件位）、按 job 的估算成本（token × 单价配置）。

### P2-3 · spec 编辑版本化（修复 L8c）

spec 保存前自动留档到 `data/console/spec-history/{slug}/{ts}.json`（保留最近 N 版），场景管理页提供 diff 与一键回滚；与 git 解耦，适配 DB 自定义场景的 spec 不在 git 内的情况。

---

## 2. 优先级排序与依赖 Priority Order & Dependencies

| 序 | 能力 | 优先级 | 依赖 | 预估规模 |
|---|---|---|---|---|
| 1 | P0-1 G2 plan 证据链 | P0 | 无（纯后端 + 产物类型） | 小 |
| 2 | P0-2 train/benchmark data 字段 | P0 | 无（纯前端） | 小 |
| 3 | P0-3 G4/G6 证据分离 | P0 | 无（后端 compare/gates/artifacts） | 中 |
| 4 | P1-1 温度自动带出 | P1 | 建议在 P0-3 后（复用产物拉取模式） | 小 |
| 5 | P1-3 distill 产物注册 | P1 | 无 | 小 |
| 6 | P1-2 范例生产闭环 | P1 | 依赖 P1-3（产物可引用） | 中 |
| 7 | P1-4 Modal 端点呈现 | P1 | 无 | 小 |
| 8 | P2-1/2/3 | P2 | 各自独立 | 小/中 |

**Key Point:** 三个 P0 全部完成后，「蒸馏 → 训练 → 评测 → 部署」才在 UI 内真正端到端贯通；P1 消除高摩擦手工步骤；P2 为运营增强。
The three P0s together make the distill→train→eval→deploy path truly end-to-end in the UI.

---

## 3. 分批落地建议 Suggested Batches

- **Batch 1（P0，1 个 PR 系列）**：P0-1 → P0-2 → P0-3。验收 = 用自定义场景从 distill 一路走到 image 闸门全绿。
- **Batch 2（P1 快赢）**：P1-1、P1-3、P1-4（各自独立、可并行）。
- **Batch 3（P1 闭环）**：P1-2（依赖 P1-3）。
- **Batch 4（P2）**：按需排期。

每批完成后回写 `docs/pipeline.md` 对应小节（保持文档与实现同步）。

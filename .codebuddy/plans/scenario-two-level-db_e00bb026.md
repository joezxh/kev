---
name: scenario-two-level-db
overview: 将场景模型从「硬编码单层列表」升级为「用户可在控制台自定义的两级体系（一级域 / 二级场景），存于 SQLite，支持中英双语，并在流水线的场景选择与各 stage 中使用」。二级场景通过 DB 中存储的 spec_path 解析到实际 workload 配置，现有 6 个医疗场景作为种子数据迁移进库以保证开箱即用。
design:
  architecture:
    framework: react
    component: shadcn
  styleKeywords:
    - Enterprise Admin
    - Two-pane Tree+Form
    - Clean Dashboard
    - Subtle Shadow
    - Consistent Console
  fontSystem:
    fontFamily: PingFang SC
    heading:
      size: 22px
      weight: 600
    subheading:
      size: 15px
      weight: 500
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#2563EB"
      - "#1D4ED8"
    background:
      - "#F8FAFC"
      - "#FFFFFF"
    text:
      - "#0F172A"
      - "#475569"
    functional:
      - "#16A34A"
      - "#DC2626"
      - "#D97706"
todos:
  - id: db-schema-seed
    content: db.py 新增两级场景表与幂等种子及 CRUD/解析方法
    status: completed
  - id: backend-routes
    content: app.py 暴露场景树与 CRUD 路由，data.py 改 _spec 按 DB spec_path 解析
    status: completed
    dependencies:
      - db-schema-seed
  - id: frontend-api-i18n
    content: console.ts 新增场景 API，strings.ts 补充中英词条
    status: completed
    dependencies:
      - db-schema-seed
  - id: scenarios-page
    content: 新建控制台场景管理页（两级树+双语编辑 CRUD）
    status: completed
    dependencies:
      - frontend-api-i18n
  - id: cascade-selector
    content: 新增 ScenarioCascade 并替换 datasets/JobStagePage 场景下拉，layout 加导航
    status: completed
    dependencies:
      - frontend-api-i18n
      - backend-routes
  - id: tests-verify
    content: 后端场景测试 + tsc 校验 + 用 [mcp:Playwright MCP Server] 走查交互
    status: completed
    dependencies:
      - scenarios-page
      - cascade-selector
---

## 场景两级-DB 管理：蒸馏/评测/训练提示词与配置的归属结论

### 关键判断（已实地核查底层脚本）

- **蒸馏提示词**：`generate_data.py::build_prompt` 完全由 spec 字段（`domain/state/state_example/questions.*.instructions/guidance/variety`）拼出 —— 蒸馏提示词与配置**天然 per-scenario 且内嵌在 spec JSON**。计划的二级场景 `spec_path` 字段指向各场景自己的 spec 文件，**已覆盖蒸馏提示词管理，无需额外配置表**。
- **评测 rubric**：`eval.py` 走 `kev.benchmark`，suite 从 spec 的 `questions` 派生；自定义场景只要有自己的 spec 文件，评测标准即随场景不同，**同样已被 `spec_path` 覆盖**。
- **训练**：`train.py::methods_for(scenario)` 对所有场景返回同一组训练方式，唯一区分是 `FOUR_B_ONLY`（4B 轨），与提示词/超参无关；计划的 `category` 回退默认值已处理未知域，**无需为训练单独建 per-scenario 配置**。
- **结论**：不新增蒸馏/评测/训练各自的配置表；per-scenario 的蒸馏与评测提示词、配置统一通过「每个二级场景的 `spec_path` 指向其 spec 文件」来管理。
- **新增需求（用户补充）**：spec JSON 文件（含提示词等）需在控制台**查看 / 编辑 / 保存回原文件**。

### 必要实现修正（补入后端任务）

- `data.py::_distill_build` 当前传 `--category <slug>` 给 `generate_data.py`，但该冻结脚本的 `CATEGORY_SPECS` 仅含原 6 个 key，**自定义场景 slug 不在其中会报 `cannot resolve spec`**。改为：用 DB `resolve_spec_path(slug)` 解析出 spec 文件绝对路径，作为位置参数传给 `generate_data.py`（其 `resolve_spec` 支持路径），绕开冻结硬编码映射。

---

## 用户需求

将场景模型从「硬编码单层列表」升级为「用户可在控制台自定义的两级体系」，落地 SQLite、中英双语、在流水线中使用。蒸馏/评测提示词统一由 `spec_path` 指向的 spec 文件管理；**且该 spec JSON 文件可在控制台查看、编辑并保存回原文件**。训练无 per-scenario 差异。

## 产品概述

- 一级「领域」（医疗/金融/教育/科研…）与二级「场景」（如医疗-护理）均可在控制台管理界面自由增删改。
- 每个二级场景绑定一个 spec JSON 路径；该 spec 文件（domain/state/questions/guidance/variety 等提示词与配置）可在控制台直接查看与编辑保存。
- 现有 6 个医疗场景作为种子数据写入数据库（含中英标签），spec_path 指向 `docs/medical/specs/*.json`，保证开箱即用、不回退。

## 核心功能

- DB 新增 `scenario_domains`（一级域）与 `scenarios`（二级场景）两张表，均含中英双语标签、排序字段；场景含 `spec_path`、`category`。
- 控制台「场景管理」页：左侧两级树（域+场景）、右侧双语编辑面板（中/英标签、所属域、spec 路径、分类、排序），支持增删改。
- **Spec 文件查看/编辑/保存**：选中二级场景后，编辑面板内含 spec JSON 编辑器（Textarea + 保存），读取 `spec_path` 指向的文件内容；保存时校验 JSON 合法性并写回原文件（路径限定在仓库根内）。
- 后端提供两级场景树与场景/域的 CRUD 接口（slug 唯一校验、spec 文件存在性提示），以及 spec 文件的读/写接口（GET 读、PUT 写并校验）。
- 流水线场景解析优先按 DB `spec_path` 解析，回退 `docs/medical/specs/<name>.json`；`_distill_build` 经 DB `spec_path` 把 spec 文件绝对路径传给 `generate_data.py`。
- datasets 与 stage 参数中的单层场景下拉，替换为「域→场景」两级级联选择器。
- 种子迁移：首次初始化把 6 个医疗 spec 落库到「医疗」域下。

## 技术栈

- 后端：Python + FastAPI（沿用 `kev/console/app.py`），SQLite + `sqlite3`（沿用 `kev/console/db.py` 的 `Store`/`DDL`/`PRAGMA user_version`）。
- 前端：React + TypeScript + Tailwind + shadcn 风格组件。
- 校验：前端 `npx tsc --noEmit`；后端 `pytest`。

## 实现方案

### 总体策略

`db.py` 的 `DDL` 新增两张表（`SCHEMA_VERSION` 升 3）+ 幂等种子；新增 `read_spec_file`/`write_spec_file`（仓库根内沙箱 + JSON 校验）。`app.py` 暴露场景树、域/场景 CRUD，以及 spec 读/写接口。`data.py` 的 `_spec` 经 DB 解析 `spec_path`，`_distill_build` 改传 spec 文件绝对路径。前端新增场景管理页（含 spec 编辑器）与 `ScenarioCascade` 级联选择器。

### 关键技术决策

1. **场景真相源改为 DB，向后兼容**：`SCENARIOS` 改由 DB slug 列表计算（DB 为空回退 run_matrix）；`_spec(slug)` 先查 `scenarios` 表取 `spec_path`（相对仓库根解析），查不到回退 `SPECS/"{slug}.json"`。
2. **蒸馏解耦冻结脚本**：`_distill_build` 用 `resolve_spec_path(slug)` 取得 spec 文件绝对路径，作为位置参数传给 `generate_data.py`。
3. **Spec 文件沙箱与校验**：读/写接口将 `spec_path` 解析为绝对路径后，`Path(paths.ROOT).resolve()` 校验其 `is_relative_to(ROOT)`（防任意路径写入）；写入前 `json.loads` 校验合法，并校验必要字段（`name`/`domain`/`state`/`questions`，口径同 `generate_data.load_spec`）。仅当场景存在且 spec_path 在仓库根内才允许写。
4. **不触碰冻结文件**：冻结列表仅 `kev/serve.py` 与 `skills/kev-finetune/scripts/generate_data.py`；本次改动集中在 `db.py / app.py / data.py / 前端`。
5. **双语存储**：域与场景各存 `label_zh`/`label_en`；接口与前端按当前 `lang` 返回对应标签。
6. **spec 路径校验**：创建/更新场景时校验 `spec_path` 文件存在性，缺失仅告警不阻断；运行时 `_spec` 对缺失路径抛 `Invalid`。
7. **分类 `category`**：场景携带 `category`（medical/finance…），供 `train.py::methods_for` 在未知分类场景回退默认方法集。

### 性能与可靠性

- 两张表均小；`scenarios.slug` 建 UNIQUE 索引。
- 种子函数幂等（`INSERT OR IGNORE` + 「表为空才播种」）。
- 前端场景树一次拉全量；spec 编辑器按需按 slug 加载文件内容。

## 目录结构与文件

```
kev/console/db.py                  # [MODIFY] DDL 新增两张表(SCHEMA_VERSION->3)；seed_scenarios() 幂等种子；
                                    #          list_scenario_tree / get_scenario_by_slug / resolve_spec_path /
                                    #          create/update/delete_domain / create/update/delete_scenario /
                                    #          read_spec_file / write_spec_file(仓库根沙箱+JSON校验)。
kev/console/app.py                 # [MODIFY] GET /console/api/scenario-domains(双语树) 与域/场景 CRUD；
                                    #          GET /console/api/scenarios/<slug>/spec 读、PUT 写 spec 文件；
                                    #          /console/api/scenarios 与 /console/api/config 保持旧形状(改从 DB 取)。
kev/console/stages/data.py         # [MODIFY] SCENARIOS 改基于 DB slug(回退 run_matrix)；
                                    #          _spec 优先 DB.spec_path 解析, 回退 SPECS/<slug>.json；
                                    #          _distill_build 改传 spec 文件绝对路径给 generate_data.py。
kev/console/stages/train.py        # [MODIFY] methods_for(scenario) 对未知分类场景回退默认方法集。
playground/src/lib/console.ts      # [MODIFY] 新增 scenarioDomains()/CRUD 封装 + getScenarioSpec()/saveScenarioSpec()。
playground/src/components/console/strings.ts  # [MODIFY] 新增场景管理页与级联选择器、spec 编辑器中英词条。
playground/src/app/console/layout.tsx         # [MODIFY] 侧边导航新增「场景 / Scenarios」入口。
playground/src/app/console/scenarios/page.tsx # [NEW] 场景管理页: 左两级树 + 右双语编辑面板 + spec JSON 编辑器(查看/编辑/保存)。
playground/src/components/console/ScenarioCascade.tsx # [NEW] 域→场景两级级联选择器。
playground/src/components/console/JobStagePage.tsx   # [MODIFY] scenario 下拉替换为 ScenarioCascade, 仍输出 slug。
playground/src/app/console/datasets/page.tsx         # [MODIFY] 相关 stage 的 scenario 参数改用 ScenarioCascade。
tests/test_console_scenarios.py    # [NEW] 域/场景 CRUD 往返、双语、种子幂等、resolve_spec_path、spec 读/写(含沙箱与非法 JSON 拒绝)、_distill_build 传路径。
```

## 实现要点（防爆半径）

- `DDL` 仅追加两张表 + `SCHEMA_VERSION` 升 3；不改动既有表。
- `data.py` 仅改 `_spec`、`SCENARIOS` 取值、`_distill_build` 的 spec 传参；`job` 行 `scenario` 字段语义不变。
- spec 读/写接口新增于 `app.py`，**读取/写回的是 `spec_path` 指向的真实文件**（种子场景即 `docs/medical/specs/*.json`），需沙箱在仓库根内并校验 JSON。
- 复用 `db.Store.tx()` 写事务做域/场景增删改。

## 设计风格

企业级后台（Material/Admin）风格，与现有 console 一致：浅色背景、左侧两级树导航 + 右侧编辑表单双栏、卡片化容器、克制阴影。级联选择器与 spec 编辑器复用现有 shadcn 外观（Select / Textarea / Button）。

## 页面规划

### 场景管理页（console/scenarios）

- 顶部栏：标题「场景管理 / Scenarios」+ 语言切换 +「新建域」「新建场景」按钮。
- 左栏（树）：两级折叠树，行内 hover 显示编辑/删除图标；搜索框本地过滤。
- 右栏（编辑面板）：
- 选中域或场景后展示表单——中文标签、英文标签、所属域(下拉)、spec 路径(文本+存在性徽标)、分类、排序；底部「保存/删除」。
- 选中二级场景时，表单下方含 **Spec 配置区**：只读展示/可编辑的 JSON 文本区（首屏按 slug 拉取 `spec_path` 文件内容），「保存配置」按钮写回；保存前客户端 JSON 校验，服务端再次校验并沙箱在仓库根内。
- 空状态：首次进入引导文案。

### 级联选择器（ScenarioCascade）

- 第一级 `Select` 选领域，第二级 `Select` 选场景（随域联动），输出 `scenario` slug；占位文案随 `lang` 切换。

## 交互

- 树节点 hover 微高亮、展开/收起 150ms 过渡；保存成功 toast；删除二次确认；spec 保存失败（非法 JSON / 越界路径）给出明确错误提示。

## Agent Extensions

### MCP

- **Playwright MCP Server**
- Purpose: 实现后通过浏览器走查场景管理页、spec 编辑器与级联选择器。
- Expected outcome: 确认场景树渲染、增删改生效、spec JSON 可查看/编辑/保存回文件、datasets 页级联选择器联动产出合法 `scenario` slug。
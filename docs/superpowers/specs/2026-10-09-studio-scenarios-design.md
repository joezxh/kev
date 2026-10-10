# Studio 控制台 · 第 1 章：场景与域管理

> 第 7 章中的第 1 章。设计目标：把 `docs/studio-preview/index.html` 控制台 UI 的场景与域管理面补齐，对应后端 `kev/console/app.py:317-444` 已有的全部路由。本章**不新增后端路由、不动 DB schema**，只在前端做表面。

## 范围

单页 `/console/scenarios`（playground 路由 `kev.studio/scenarios`），承载 3 个 hash 子视图：

| 子视图 | hash | 用途 |
|---|---|---|
| 域列表 | `#domains` | 两级树：域 → 场景，左 30% 树，右 70% 详情 |
| 场景编辑 | `#scenario/<slug>` | 单场景的元信息编辑（中英 label、分类、spec_path、排序、所属域迁移） |
| Spec 编辑器 | `#spec/<slug>` | JSON 在线编辑、校验、保存、版本历史、版本回滚 |

## 后端契约（不改动）

`kev/console/app.py` 已实现的全部路由：

- `GET /console/api/scenario-domains` — 扁平列表（带 `lang` 参数）
- `POST /console/api/scenario-domains` — 创建
- `PUT /console/api/scenario-domains/{domain_id}` — 更新（label_zh、label_en、sort）
- `DELETE /console/api/scenario-domains/{domain_id}` — 删除（仅当无场景时允许）
- `GET /console/api/scenarios` — 按 slug 扁平列表
- `POST /console/api/scenarios` — 创建（domain_id、slug、label_zh、label_en、spec_path、category、sort）
- `PUT /console/api/scenarios/{scenario_id}` — 更新（含 domain_id，跨域迁移）
- `DELETE /console/api/scenarios/{scenario_id}` — 删除
- `GET /console/api/scenarios/{slug}/spec` — 读主 spec
- `GET /console/api/scenarios/{slug}/spec/history` — 列出历史版本
- `GET /console/api/scenarios/{slug}/spec/history/{ts}` — 读单个历史版本
- `PUT /console/api/scenarios/{slug}/spec` — 写入（自动归档旧版到 history，FIFO 20 版本）

## 域列表视图（`#domains`）

双列布局，30% / 70%。

### 左列（树）

- 顶部「+ 新建域」按钮
- 每行：折叠箭头（无子项时隐藏）/ 域 label_zh / label_en（次级字号，灰）/ 场景数徽标
- 点行：右列切换到该域详情
- 行悬停：三点菜单 `重命名 / 删除（仅无子项）`
- 新建域：drawer（右侧滑入，**不**用模态）。字段 `slug`（创建后只读）、`label_zh`、`label_en`、`sort`
- drawer 底部「取消 / 保存」（`label_zh` 与 `label_en` 均非空 + slug 匹配 `^[a-z0-9-]+$` 才亮）

### 右列（详情）

- 空态（未选域）：居中提示「先在左侧创建一个域，或点击「+ 新建域」开始」
- 选中域：
  - 顶部「域属性」卡：slug / label_zh / label_en（双语，zh 在上）/ sort / created_at
    - 「编辑」按钮切换到 inline 编辑（同 drawer 表单，slug 在此只读）
  - 底部「场景表」：表头 `slug / 中 / 英 / 分类 / spec_path / 排序 / 操作`
    - 行操作：「进入场景编辑」/「删除」（带确认 `确认删除场景 <slug>？将影响所有引用该场景的作业`）/「调整排序」（数字输入）
    - 空态：「此域下还没有场景，点击下方「+ 新建场景」添加」

## 场景编辑视图（`#scenario/<slug>`）

单卡片，无子标签。标题行：`slug` + 状态徽标（`✓ 已配置` 当 spec_json 存在；`✗ 缺 spec` 否则）。

字段：

- 所属域：下拉（跨域迁移走现有 `update_scenario` PUT body）
- 中英 label（双语）
- spec_path（文本输入，可选；客户端校验必须以 `.json` 结尾）
- category（文本输入，默认 `medical`）
- sort（数字）

按钮：

- 「进入 Spec 编辑器」（路由 → `#spec/<slug>`）
- 「查看产物血缘」（侧抽屉列出路径含该场景 slug 的所有 `dataset:*` / `plan:*` 产物）

## Spec 编辑器（`#spec/<slug>`）—— 核心

布局：上 60% 编辑器面板，下 40% 标签页。

### 编辑器面板

- 纯 `<textarea>` + 等宽字体；**不**引入 Monaco（对预览版体积过大）
- 失焦时自动格式化（2 空格缩进，复用 `kev.suite.write_json` 风格）

### 底部标签

- **预览**：把 spec 渲染成可读表格
  - 域描述段（`domain` 字段）作为一段文字
  - `state_example` 作为 2 列表格 `字段 / 示例值`
  - 每个 `questions.<key>` 单独一张表：`instructions` 段落 + `criteria` 表格
- **校验**：实时 JSON 解析 + 业务校验
  - JSON 语法（错误带行/列）
  - `name` 非空
  - `questions` 非空，且每项 `type ∈ {choice, noul, score}`
  - `guidance` 非空
  - `variety` 数组非空
  - 错误时禁用「保存」并在出错行 inline 标红
- **历史**：版本列表
  - 每行：`时间戳 / 大小 / [查看] [回滚]`
  - 「查看」以只读 overlay 打开该版本（保留当前未保存编辑到 `localStorage` 草稿）
  - 「回滚」弹「确认回滚到 <ts>？当前未保存修改将丢失」，然后 PUT 该版本内容

### 顶部固定操作条

`场景 slug · spec_path · [保存] [放弃修改] [从历史回滚]`

- 保存：调 `PUT /console/api/scenarios/{slug}/spec`；后端自动把旧主 spec 归档到 history（FIFO 20）
- 放弃修改：把 textarea 还原到最后保存内容（或 `localStorage` 草稿若更新）
- 从历史回滚：打开历史标签，走同样确认流程

## 横切

- 空 / 错误 / 重试态：复用 DAG step card 同一套模板（小说明 + 主按钮）
- drawer 与 spec overlay 共用 `.drawer` / `.overlay` class；只换 body
- 域 / 场景变更只刷新当前激活子树；初次挂载才全量重载

## 前端位置

playground 新增模块 `playground/src/app/kev.studio/scenarios/`：

- `domains/page.tsx`（左 30% 树 + 右 70% 详情，hash 路由 `#domains`）
- `scenario/[slug]/page.tsx`（场景编辑，`#scenario/<slug>`）
- `spec/[slug]/page.tsx`（Spec 编辑器，`#spec/<slug>`）
- 共享 `components/ScenarioTree.tsx`、`components/ScenarioDetail.tsx`、`components/SpecEditor.tsx`
- API 封装在 `playground/src/lib/console.ts`，URL 前缀 `/console/api`

## 不在本期

- spec 版本之间的字段级 diff（Git 风格）
- 多人同时编辑的冲突解决（last-write-wins，无锁）
- spec 模板 / 向导（用现有 7 个 spec `data/console/specs/*.json` 作种子）
- 场景跨域迁移时自动重排 sort

# Studio 控制台 · 第 6 章：管理面

> 第 7 章中的第 6 章。承接 `docs/pipeline.md` §1.1，集中 3 个管理密度页：API Keys / 蒸馏配置 / 用量。场景管理已在第 1 章专述；Jobs 列表在第 3、4、5 章共享；端点在第 5 章。
>
> **后端策略**：复用 `kev/console/app.py` 已有的所有管理接口；本期不新增后端路由；如发现某个管理操作确实缺端点，扩展 console 后端，不另起新服务。

## 6.1 入口

侧边栏「管理」组已经包含 4 个：

- 场景（第 1 章专述）
- **API Keys**（本章 6.2）
- **蒸馏配置**（本章 6.3）
- **用量**（本章 6.4）

## 6.2 API Keys

**用途**：kev 核心接口用量计费的 key 池（hash 存储、`key_hints` 展示）。

**后端契约**（已存在，`app.py:687-712`）：

- `POST /console/api/apikeys` — 创建并一次性返回明文 id
- `GET /console/api/apikeys?all=1` / `?page=N&page_size=20` — 列表
- `DELETE /console/api/apikeys/{key_id}` — 撤销
- `POST /console/api/apikeys/{key_id}/reactivate` — 重新启用

**布局**：单页表格 + 顶部「+ 新建 Key」按钮。

| 列 | 内容 |
|---|---|
| name | 用户起的名 |
| id | 系统生成（**前端用来当 Bearer token**，后端校验 id 即可） |
| key_hint | `sk-...xxxx` 后 4 位 |
| created_at | |
| status | active / revoked |
| 操作 | 撤销 / 重新启用 / 复制 id（剪贴板） |

**新建**：弹模态（与场景管理那种 drawer 不同——这个是**真正会拿到敏感 id 的一次性操作**，用模态强聚焦）：

- name 必填
- 提交后**只显示一次**完整 id（带"已复制"提示 + 关闭即不重显）—— 服务端把明文 id 只在创建时返回一次，之后只剩 hash 校验

**撤销/重新启用**：行内即时刷新状态。

## 6.3 蒸馏配置

**用途**：provider 池（base_url / model / keys 池 / 每日阈值）。

**后端契约**（已存在，`app.py:756-810`）：

- `POST /console/api/distill-providers` — 创建
- `GET /console/api/distill-providers` — 列表
- `PUT /console/api/distill-providers/{id}` — 更新（name / model / base_url / daily_limit / keys 整组替换）
- `DELETE /console/api/distill-providers/{id}` — 停用

**布局**：单页表格 + 顶部「+ 新建 Provider」按钮。

| 列 | 内容 |
|---|---|
| name | 标识名 |
| model | 蒸馏模型 |
| base_url | （脱敏后显示前缀） |
| keys 数 | 数字徽标（不显示 key 内容） |
| daily_limit | per-key 软上限 |
| status | active / deactivated |
| 操作 | 编辑 / 停用 |

**新建/编辑**：drawer（与场景管理一致）—— 字段 `name` / `model` / `base_url` / `daily_limit` / `keys[]`（多 key 轮换，最多 `MAX_DISTILL_KEYS=6`）。

- `keys` 是 textarea（一行一个），不显示明文，只显示 hint
- 提交时**完整 keys 上传一次**（与 api keys 同模式，明文只在创建时提交一次）
- **编辑时 keys 字段语义：留空 = 保留原 keys；填入 = 整组替换**（每次保存都明确这个 provider 的 key 池，无歧义）

**蒸馏用量**（每个 provider 卡片下方折叠区）：

- 当日 / 当周 / 当月 token 用量进度条
- 超 daily_limit 80% 标黄、100% 标红 + 提示「明日起该 key 不会被轮询」

## 6.4 用量

**用途**：kev 核心接口用量 + 第三方蒸馏用量（按 job / 日）。

**后端契约**（已存在）：

- `GET /console/api/usage?from_ts=&to_ts=` — 核心接口 summary
- `GET /console/api/usage/{key_id}?from_ts=&to_ts=` — 时序
- `GET /console/api/distill-usage?provider_id=&from_day=&to_day=` — 蒸馏用量
- `GET /console/api/distill-usage/totals?from_day=&to_day=` — **L8 修复**后按日汇总

**布局**：上下两段。

### 上段（核心 kev 用量）

- 折线图（自绘 SVG，30 天）：每日请求数 / 输入 token / 输出 token 三条线
- 表格：日期 / 端点 / 方法 / 请求数 / 输入 token / 输出 token / 失败率 / p50 / p95 延迟
- 时间范围筛选：今日 / 7 日 / 30 日 / 自定义
- 按 key 筛选（下拉来自 API Keys 页）

### 下段（蒸馏用量）

- 柱状图（自绘 SVG）：每日 token 总用量
- 表格：日期 / provider / key_hint / 模型 / token / cost（硬编码价格表）
- 按 provider 筛选

### 告警（顶部红条）

- **参考上限** = 该 provider 所有 active keys 的 `daily_limit` 之和（不持久化总预算，schema 稳定）
- 当日累计达到参考上限 80% 标黄、100% 标红
- 顶部红条文案：「今日蒸馏参考上限已达 $X / $Y（Z%）—— 来自 N 个 provider 的 daily_limit 求和」

## 6.5 通用规则

- 三个管理页都用**抽屉**形式编辑（除了 API Keys 的一次性创建用模态）
- 删除类操作（撤销 key / 停用 provider）走「行内操作 + 即时刷新」，不弹模态
- 列表查询全部走 `?page=1&page_size=20` 分页信封（已实现 `app.py:697-701`），底部一个简单的分页条
- 「复制 id」按钮调浏览器剪贴板 API，**成功后短暂显示 ✓ 1.5s 后复原**

## 6.6 前端位置

新增 `playground/src/app/kev.studio/management/`：

- `apikeys/page.tsx`、`distill-providers/page.tsx`、`usage/page.tsx`
- 共享 `components/KeyTable.tsx` / `components/ProviderTable.tsx` / `components/UsageDashboard.tsx`
- 自绘 SVG 图表用 `components/charts.tsx`（极简 line + bar，避免引 chart 库）

## 6.7 已知 / 不在本期

- API Keys 不做"权限分组"（只有一种 scope：访问 kev 核心接口）
- 蒸馏 provider 不做 health check（依赖 spawn 时报错）
- 用量页的 cost 估算用硬编码价格表（每 1k tokens = $X），不做实时 API
- 不做数据导出（CSV/JSON 下载）
- 用量"参考上限"不持久化配置，每次进页根据 `daily_limit` 之和重算

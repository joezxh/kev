# Studio 控制台 · 第 7 章：总览与跨页交互

> 第 7 章（终章）。承接 `docs/pipeline.md` §0.1 全图 + §1.2 凭据注入原则。定义**贯穿全 6 章**的横切关注点：首页全局状态条、路由、错误/空/重试态、加载骨架、消息提示、键盘快捷键、国际化、a11y。

## 7.1 总览页（`#overview`）

当前是 `active` 但内容待定。**目标**：用户每天打开 studio，第一眼要回答 4 件事。

**布局**：4 块卡片，2x2：

| 块 | 字段 |
|---|---|
| **当前作业** | 活动作业（最多 3 个，badge 显示 stage + 进度）/ 闲置时显示「无活动作业，去 `#datasets`/`#endpoints` 开始」 |
| **最近事件** | 跨 stage 的最近 10 条事件（来自 SSE 聚合） |
| **资源** | GPU 锁 · 状态 / 花费 · 今日 $X / 蒸馏参考上限 |
| **最近发布** | HF Hub 最近一次 publish 状态 + Modal 端点列表（最多 3） |

## 7.2 系统状态条（侧边栏底部）

当前「系统」组里只有两行静态字（GPU 锁 · 空闲 / 花费 · $0.42 / $50），改为**实时拉取**：

- `GET /console/api/jobs?status=running` → 占用时显示「GPU 锁 · 占用（<作业 id 前 8>）」+ 链接跳作业详情
- `GET /console/api/usage` + `GET /console/api/distill-usage/totals` → 今日花费 + 蒸馏用量进度

更新频率：5s 轮询；切到其他页时停止该页对应的轮询。

## 7.3 路由表

playground 已有 `app router`（Next 16）。本章定义 studio 模块的路由树：

```
playground/src/app/kev.studio/
├── layout.tsx                       # studio 外壳（顶栏 + 侧边栏 + 状态条）
├── page.tsx                          # 重定向到 /kev.studio/overview
├── overview/page.tsx                 # 总览
├── datasets/page.tsx                 # 数据（§2 第 1 标签 概览）
├── jobs/
│   ├── page.tsx                      # Jobs 列表
│   ├── [id]/page.tsx                 # 作业详情（按 stage 类型切换卡片）
│   └── new/page.tsx                  # + 新建作业（按 stage 选不同表单）
├── scenarios/...                     # §1 三个 hash 路由
├── apikeys/page.tsx                  # §6.2
├── distill-providers/page.tsx        # §6.3
├── usage/page.tsx                    # §6.4
└── endpoints/...                     # §5 五个子标签
```

## 7.4 跨页组件

| 组件 | 路径 | 用途 |
|---|---|---|
| `Sidebar.tsx` | `playground/src/components/studio/Sidebar.tsx` | 侧边栏（导航 / 管理 / 系统三组） |
| `StatusBar.tsx` | 同上 | 侧边栏底部实时状态条 |
| `Drawer.tsx` | 同上 | 右侧抽屉（场景编辑、provider 编辑、spec 历史回滚） |
| `Modal.tsx` | 同上 | 中心模态（API Key 创建、危险操作二次确认） |
| `GatePanel.tsx` | 同上 | 闸门预检条（§3.3 / §4.7 / §5.8 共用） |
| `JobProgressBar.tsx` | 同上 | 训练/评测通用进度条（解析日志） |
| `LogStream.tsx` | 同上 | SSE 日志流（SSE 客户端 + 自动重连 + 断线续传） |
| `Toast.tsx` | 同上 | 消息提示（success / warn / error / info） |
| `EmptyState.tsx` | 同上 | 空状态（图标 + 描述 + 主操作） |
| `ErrorBoundary.tsx` | 同上 | 错误边界（捕获 + 报告 + 重试按钮） |
| `ArgvPreview.tsx` | 同上 | 提交前 argv 代码块预览 |

## 7.5 状态机

每个 stage 的作业有 4 个交互态：空闲 / 预览 / 提交中 / 闸门失败 / 提交成功。

- **闸门失败**：表单保留输入 + 顶部红条列失败明细 + 滚动到第一个失败字段
- **提交成功**：跳 `#jobs/<id>` + toast「<stage> 已入队，<id>」
- **网络错误**：toast「网络异常，已重试 N 次」+ 重试按钮（指数退避，1s / 2s / 4s 上限 3 次）

## 7.6 SSE 客户端规则

- 走 `EventSource`（Next 16 dev 信任 localhost，`127.0.0.1` 已在 `next.config.ts` allowlist）
- 断线自动重连，**沿用原 URL**（Playwright / curl 都靠 `Last-Event-ID` header，**绝不**改成 `?after_id=` 那种 query 形式，已踩过这个坑 `app.py:577-580`）
- 心跳：服务端 `event: ping\ndata: {}\n\n`（已实现）→ 客户端 30s 无 ping 则强制重连
- 同时打开 ≥ 3 个流时复用同一连接（合并订阅）

## 7.7 凭据与隐私

- **后端**只在 `GET /console/api/config` 返回 `credentials` 布尔态（`app.py:284-292`）
- **前端**不写任何把 `KEV_API_KEY` / `HF_TOKEN` 等明文拿到浏览器的逻辑
- 蒸馏 provider 详情页**只显示 key_hint 后 4 位**，从不显示完整 key
- API Key 创建后**只显示一次**完整 id，关闭模态后只留 hash 校验（不可再读）

## 7.8 国际化（i18n）

- 默认 zh-CN；右上角语言切换器，支持 en-US
- 文案集中在 `playground/src/i18n/zh-CN.ts` 与 `en-US.ts`
- 数字、日期用 `Intl.NumberFormat` / `Intl.DateTimeFormat`，**不用**手写格式化
- 不做复数规则（中文无复数；英文走 `Intl.PluralRules`）

## 7.9 可访问性（a11y）

- 所有交互元素有 `aria-label`
- 抽屉 / 模态有 `role="dialog"` + `aria-modal="true"`，ESC 关闭、focus trap
- 颜色对比度 ≥ WCAG AA（与现有色板已一致，studio 复用同一套 CSS variables）
- 键盘导航：表格行 ↑↓ 切换，Enter 打开详情，Cmd+K 全局搜索

## 7.10 性能预算

- 首次绘制（FP）< 1.5s（本地 dev）
- 路由切换 < 200ms
- 列表页首屏 50 条 / 分页 20（已实现）
- SSE 长连接每页最多 1 个

## 7.11 已知 / 不在本期

- 不做暗色主题切换（继承现有色板）
- 不做通知中心（toast 即可）
- 不做多 workspace / 切换数据库
- 不做 RBAC（本地单用户）

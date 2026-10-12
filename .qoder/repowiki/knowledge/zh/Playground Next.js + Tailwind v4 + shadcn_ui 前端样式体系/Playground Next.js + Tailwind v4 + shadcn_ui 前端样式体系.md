---
kind: frontend_style
name: Playground Next.js + Tailwind v4 + shadcn/ui 前端样式体系
category: frontend_style
scope:
    - '**'
source_files:
    - playground/package.json
    - playground/components.json
    - playground/postcss.config.mjs
    - playground/next.config.ts
    - playground/eslint.config.mjs
    - playground/src/app/globals.css
    - playground/src/components/ui/button.tsx
    - playground/src/components/ui/card.tsx
    - playground/src/components/ui/table.tsx
    - playground/src/components/ui/sonner.tsx
---

## 1. 使用的系统/技术栈

- **框架**: Next.js 16 (App Router, RSC)。
- **CSS 引擎**: Tailwind CSS v4（`tailwindcss: ^4`, `@tailwindcss/postcss: ^4`），通过 `postcss.config.mjs` 使用 `@tailwindcss/postcss` 插件，不再依赖传统 `tailwind.config.*` 文件。
- **组件库**: shadcn/ui（`shadcn: ^4.21.0`），采用 `base-nova` 风格、`neutral` 基础色、启用 CSS 变量模式（`cssVariables: true`）；组件源码位于 `playground/src/components/ui/*`，由 shadcn CLI 生成。
- **动画**: `tw-animate-css`（`^1.4.0`）提供预置动画类。
- **主题切换**: `next-themes` + `@base-ui/react` 实现亮/暗/跟随系统三种模式。
- **图标**: `lucide-react`。
- **工具函数**: `class-variance-authority` + `cn`（别名 `clsx/tw-merge`）组合 className。
- **字体**: `geist`（`--font-sans` / `--font-mono` / `--font-heading` 均指向 Geist Sans/Mono）。
- **Markdown 渲染**: `react-markdown` + `remark-gfm` + `mermaid` + `marked`，配合 `.doc-content` 自定义排版。

## 2. 关键文件

- `playground/package.json` — 依赖与脚本入口。
- `playground/components.json` — shadcn/ui 配置（style=`base-nova`、RSC、Tailwind v4、CSS 变量、`neutral` baseColor、`lucide` 图标库、路径别名 `@/components`、`@/components/ui`、`@/lib/utils`）。
- `playground/postcss.config.mjs` — 仅注册 `@tailwindcss/postcss`。
- `playground/next.config.ts` — `output: 'standalone'`、`reactCompiler: true`、`allowedDevOrigins`、`/kev/:path*` 反向代理到 FastAPI。
- `playground/eslint.config.mjs` — 基于 `eslint-config-next/core-web-vitals` + `typescript`，忽略 `.next/out/build`。
- `playground/src/app/globals.css` — 全局样式、设计令牌、暗色主题、`.studio` 独立深色主题、`.doc-content` Markdown 排版。
- `playground/src/components/ui/*.tsx` — shadcn 生成的 UI 原子组件（button、card、dialog、table、tabs、tooltip、sonner 等）。

## 3. 架构与约定

### 3.1 Tailwind v4 + CSS 变量设计令牌

`globals.css` 通过 `@import "tailwindcss"` 引入 Tailwind，并通过 `@theme inline { ... }` 将 shadcn 的 CSS 变量映射为 Tailwind 语义 token（`--color-primary`、`--color-muted`、`--radius-*`、`--font-sans` 等）。所有颜色以 `oklch(...)` 定义在 `:root` 和 `.dark` 两个作用域下，形成**亮/暗双主题**。响应式暗色通过 `@media (prefers-color-scheme: dark)` 覆盖 `:root:not(.light)`。

### 3.2 主题策略

- 默认亮色：`--background` = `oklch(1 0 0)`，主色 `--primary` = `oklch(0.205 0 0)`（中性深灰）。
- 暗色：`--background` = `oklch(0.145 0 0)`，`--sidebar-primary` 注入蓝色调 `oklch(0.488 0.243 264.376)`。
- 通过 `next-themes` 在运行时切换 `<html>` 上的 `light`/`dark` 类，配合 `@custom-variant dark { &:where(.dark, .dark *) { @slot; } }` 使 Tailwind 支持 `dark:` 前缀。
- **Studio 独立主题**（`.studio` 选择器，注释标注为 “Wave C”）：完全重写 shadcn 语义变量，采用近黑 IDE 配色（`#0a0a0a` 背景、`#3b82f6` 主色、`#262626` 边框），并设置 `color-scheme: dark` 与 `min-height: 100vh`，确保 JS 未加载时也不出现浅色闪烁。

### 3.3 shadcn/ui 组件组织

- 所有可复用 UI 组件位于 `src/components/ui/`，每个文件对应一个原子组件（如 `button.tsx`、`card.tsx`、`table.tsx`、`sonner.tsx`）。
- 组件通过 `class-variance-authority` 暴露 `variants`，用 `cn(...)` 合并 className。
- 路径别名由 shadcn 配置声明：`@/components` → `src/components`，`@/components/ui` → `src/components/ui`，`@/lib` → `src/lib`，`@/hooks` → `src/hooks`。

### 3.4 文档内容样式

`.doc-content` 是专门为 `react-markdown` 渲染输出定义的样式块，包含 h1–h4 层级、blockquote、code/pre、table、hr、img 等规则，统一了 Playground 中 docs/studio/console 页面里 Markdown 内容的视觉表现。

### 3.5 构建与部署约束

- `next.config.ts` 强制 `output: 'standalone'`，Playground 以独立 Node 服务器形式打包进镜像。
- `/kev/:path*` 通过 `rewrites` 代理到后端 FastAPI（`KEV_API` 环境变量，Compose 中设为 `http://kev-server:8008`），浏览器侧不直接处理跨域。
- ESLint 继承 `eslint-config-next` 的 Core Web Vitals 与 TypeScript 规则集。

## 4. 约定与约束

- **无传统 `tailwind.config.js`**：Tailwind v4 通过 PostCSS 插件工作，样式集中在 `globals.css` 的 `@theme inline` 与 CSS 变量中（来源：`postcss.config.mjs` + `components.json` 中 `tailwind.config: ""`）。
- **所有颜色走 CSS 变量**：shadcn 配置 `cssVariables: true`，组件内部引用 `var(--primary)` 等语义变量而非硬编码色值（来源：`components.json`）。
- **双主题 + 系统偏好**：亮/暗主题通过 `:root` 与 `.dark` 两套变量定义，同时监听 `prefers-color-scheme: dark`（来源：`globals.css`）。
- **Studio 子应用隔离主题**：`.studio` 选择器内重新定义全部 shadcn 语义变量，形成与全局主题解耦的深色 IDE 外观（来源：`globals.css` 第 248–297 行注释及样式块）。
- **UI 组件必须放在 `src/components/ui/`**：由 shadcn 的 `aliases.ui` 路径约定决定（来源：`components.json`）。
- **className 合并使用 `cn`**：shadcn 生成的组件统一通过 `cn(...)` 合并变体与外部 className（来源：各 `src/components/ui/*.tsx`）。
- **字体统一为 Geist**：`--font-sans` / `--font-mono` / `--font-heading` 均指向 Geist（来源：`globals.css` `@theme inline`）。
- **Next.js 构建产物为 standalone**：`next.config.ts` 显式设置 `output: 'standalone'`（来源：`next.config.ts`）。
- **后端 API 访问必须经 `/kev` 重写**：禁止前端直连 FastAPI 端口（来源：`next.config.ts` rewrites 段）。

// GeneratorTab 结构 + 状态初始化单测。沿用本仓库的 node:test + 原生类型剥离
// （node --test --experimental-strip-types），**不引 vitest** ——
// 它与本仓库锁定的 next 16.3.5 / react 19.2.8 解析冲突（ERESOLVE）。
//
// 跑：npm run test:console
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";

describe("GeneratorTab", () => {
  it("导出 GeneratorTab 组件", () => {
    const src = readFileSync(join(import.meta.dirname, "GeneratorTab.tsx"), "utf8");
    assert.match(src, /export\s+function\s+GeneratorTab\b/, "GeneratorTab.tsx 必须 export 一个 GeneratorTab 组件");
  });

  it("包含 4 个子 tab 的 trigger（Generator / Distill / Routing / Smoke Probe）", () => {
    const src = readFileSync(join(import.meta.dirname, "GeneratorTab.tsx"), "utf8");
    assert.match(src, /TabsTrigger\s+value="generator"/, "缺 Generator tab trigger");
    assert.match(src, /TabsTrigger\s+value="distill"/, "缺 Distill tab trigger");
    assert.match(src, /TabsTrigger\s+value="routing"/, "缺 Routing tab trigger");
    assert.match(src, /TabsTrigger\s+value="smoke_probe"/, "缺 Smoke Probe tab trigger");
  });

  it("包含 4 个 spec_json 子字段的 Textarea 编辑（generator/distill/routing/smoke_probe）", () => {
    const src = readFileSync(join(import.meta.dirname, "GeneratorTab.tsx"), "utf8");
    for (const field of ["generator", "distill", "routing", "smoke_probe"]) {
      assert.ok(
        new RegExp(`setDraft\\(\\{\\s*\\.\\.\\.draft,\\s*${field}:`).test(src),
        `缺 ${field} 字段的 onChange 处理`,
      );
    }
  });

  it("包含 Save 按钮 + onSave 调用 (1.1)", () => {
    const src = readFileSync(join(import.meta.dirname, "GeneratorTab.tsx"), "utf8");
    assert.match(src, /await\s+onSave\(/, "Save 流程必须 await onSave(subfields)");
    assert.match(src, /<Button[\s\S]*disabled=\{saving\}/, "Save 按钮需要 disabled={saving}");
  });

  it("spec 各子字段缺失时回退为空 JSON 对象", () => {
    const src = readFileSync(join(import.meta.dirname, "GeneratorTab.tsx"), "utf8");
    for (const field of ["generator", "distill", "routing", "smoke_probe"]) {
      assert.ok(
        new RegExp(`spec\\.${field}\\s*\\?\\?\\s*\\{\\}`).test(src),
        `${field} 在缺失时应回退到空对象 {}`,
      );
    }
  });
});
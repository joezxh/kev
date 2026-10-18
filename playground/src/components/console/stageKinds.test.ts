import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { CONSOLE_STRINGS } from "./strings.ts";

// 后端 kev/console/stages/__init__.py::REGISTRY 的全部 20 个作业 kind（单一真相源）。
// 阶段中文名在 JobBoard / DatasetTable / 提交表单 / 作业详情 / bundle 卡五处共用同一张
// console.data.kind.* 键表；此测试守住「每个 kind 都有 en+zh」，防止加 kind 时漏翻译。
const STAGE_KINDS = [
  "baseline", "benchmark", "calibrate", "compare", "deploy", "distill",
  "distill_daemon", "generate", "goldset", "goldset_audit", "image",
  "make_examples", "materialize", "modal", "plan_size", "precheck", "publish",
  "smoke", "split", "train",
];

describe("stage kind name table", () => {
  it("registry lists exactly 20 kinds", () => {
    assert.equal(STAGE_KINDS.length, 20);
    assert.equal(new Set(STAGE_KINDS).size, 20);
  });

  for (const kind of STAGE_KINDS) {
    it(`console.data.kind.${kind} has non-empty en and zh`, () => {
      const entry = (CONSOLE_STRINGS as Record<string, { en: string; zh: string } | undefined>)[
        `console.data.kind.${kind}`
      ];
      assert.ok(entry, `missing key console.data.kind.${kind}`);
      assert.ok(entry!.en.trim().length > 0, `empty en for ${kind}`);
      assert.ok(entry!.zh.trim().length > 0, `empty zh for ${kind}`);
    });
  }
});

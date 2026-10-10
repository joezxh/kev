// 控制台纯函数的单测。用 Node 内置 test runner + 原生类型剥离
// （node --test --experimental-strip-types），**不引 vitest** ——
// 它与本仓库锁定的 next 16.3.5 / react 19.2.8 解析冲突（ERESOLVE）。
//
// 跑：npm run test:console
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { deltaBadge, formatMetric, formatNumber, metricAt, objectAt, renderArgv } from "./format.ts";

describe("metricAt", () => {
  it("读取 report.json 的嵌套路径", () => {
    const report = { clean: { acc: 0.812, ece: 0.07 }, calibrated_clean: { ece: 0.05 } };
    assert.equal(metricAt(report, ["clean", "acc"]), 0.812);
    assert.equal(metricAt(report, ["calibrated_clean", "ece"]), 0.05);
  });

  it("路径缺失时返回 undefined 而不是抛错", () => {
    assert.equal(metricAt({}, ["clean", "ece"]), undefined);
    assert.equal(metricAt(null, ["clean"]), undefined);
    assert.equal(metricAt(undefined, ["clean", "ece"]), undefined);
  });

  it("够得到只有 kev.compare 才产出的配对 CI", () => {
    // kev.benchmark 的 report.json 没有 bootstrap 键，CI 只在 comparison.json 里
    const comparison = { paired: { acc: { ci95: [0.023, 0.097] } } };
    assert.equal(metricAt(comparison, ["paired", "acc", "ci95", 0]), 0.023);
    assert.equal(metricAt(comparison, ["paired", "acc", "ci95", 1]), 0.097);
  });

  it("非数字一律当缺失（布尔不算数字）", () => {
    assert.equal(metricAt({ clean: { acc: true } }, ["clean", "acc"]), undefined);
    assert.equal(metricAt({ clean: { acc: "0.8" } }, ["clean", "acc"]), undefined);
  });
});

describe("formatMetric", () => {
  it("比率按百分比渲染", () => {
    assert.equal(formatMetric(0.812), "81.2%");
    assert.equal(formatMetric(0.812, 0), "81%");
  });

  it("缺失时显示破折号而不是 0", () => {
    assert.equal(formatMetric(undefined), "—");
    assert.equal(formatMetric(Number.NaN), "—");
  });
});

describe("formatNumber", () => {
  it("按小数位渲染，缺失同上", () => {
    assert.equal(formatNumber(0.6234), "0.623");
    assert.equal(formatNumber(1.284, 2), "1.28");
    assert.equal(formatNumber(undefined), "—");
  });
});

describe("deltaBadge", () => {
  it("用 runbook 的说法描述配对 CI", () => {
    assert.equal(deltaBadge([0.023, 0.097]).label, "CI 排除 0");
    assert.equal(deltaBadge([0.023, 0.097]).ok, true);
    assert.equal(deltaBadge([-0.01, 0.03]).ok, false);
    assert.equal(deltaBadge([-0.01, 0.03]).label, "CI 含 0");
  });

  it("CI 缺失时明说缺什么", () => {
    const badge = deltaBadge(undefined);
    assert.equal(badge.ok, false);
    assert.match(badge.detail, /compare/);
  });
});

describe("renderArgv", () => {
  it("只给真正需要引号的参数加引号", () => {
    assert.equal(renderArgv(["python", "-m", "kev.train", "--out", "runs/cv-8b"]),
      "python -m kev.train --out runs/cv-8b");
    assert.equal(renderArgv(["--out", "runs/cv 8b"]), "--out 'runs/cv 8b'");
  });

  it("转义参数内部的单引号（POSIX 风格：闭合引号后接转义引号）", () => {
    assert.equal(renderArgv(["--x", "it's"]), `--x 'it'\\''s'`);
  });

  it("不渲染任何凭据（env 是分开的字段）", () => {
    assert.doesNotMatch(renderArgv(["python", "-m", "kev.train"]), /KEY|TOKEN|SECRET/);
  });
});

describe("objectAt", () => {
  // 三个图表取的是嵌套字典（top_bins / selective），metricAt 只返回数字会全部落空。
  it("取到 top_bins 这种嵌套字典", () => {
    const meta = { clean: { candidate: { top_bins: { "0.9": { n: 12, errors: 1 } } } } };
    const bins = objectAt(meta, ["clean", "candidate", "top_bins"]);
    assert.deepEqual(bins, { "0.9": { n: 12, errors: 1 } });
  });

  it("路径缺失或落在标量上时返回 undefined，不抛错", () => {
    assert.equal(objectAt({}, ["clean", "candidate", "selective"]), undefined);
    assert.equal(objectAt(undefined, ["clean"]), undefined);
    // 走到 ece 这个数字上再往下取，不该把数字当对象返回
    assert.equal(objectAt({ clean: { ece: 0.07 } }, ["clean", "ece", "n"]), undefined);
  });
});
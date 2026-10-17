import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { Job } from "@/lib/console";
import { groupJobsByStage, latestJobPerStage } from "./selectors.ts";

// 只用纯对象片段测试选择器逻辑，不触发任何 fetch / React。
const jobs = [
  { id: "a", stage: "train", created_at: "2026-10-01T00:00:00" },
  { id: "b", stage: "train", created_at: "2026-10-03T00:00:00" },
  { id: "c", stage: "eval", created_at: "2026-10-02T00:00:00" },
] as unknown as Job[];

describe("project selectors", () => {
  it("latestJobPerStage picks the newest job of each stage by created_at", () => {
    const latest = latestJobPerStage(jobs);
    assert.equal(latest.train?.id, "b");
    assert.equal(latest.eval?.id, "c");
  });

  it("groupJobsByStage groups every job under its stage", () => {
    const grouped = groupJobsByStage(jobs);
    assert.deepEqual(grouped.train.map((j) => j.id), ["a", "b"]);
    assert.deepEqual(grouped.eval.map((j) => j.id), ["c"]);
  });

  it("empty input yields empty maps", () => {
    assert.deepEqual(latestJobPerStage([]), {});
    assert.deepEqual(groupJobsByStage([]), {});
  });
});

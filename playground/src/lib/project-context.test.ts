import assert from "node:assert/strict";
import { describe, it, beforeEach } from "node:test";
import { PROJECT_STORAGE_KEY, readSelectedProject, writeSelectedProject } from "./project-context.ts";

type WindowWithStorage = {
  localStorage: {
    getItem: (k: string) => string | null;
    setItem: (k: string, v: string) => void;
    removeItem: (k: string) => void;
  };
};

describe("project-context", () => {
  beforeEach(() => {
    const mem = new Map<string, string>();
    (globalThis as unknown as { window: WindowWithStorage }).window = {
      localStorage: {
        getItem: (k: string) => mem.get(k) ?? null,
        setItem: (k: string, v: string) => { mem.set(k, v); },
        removeItem: (k: string) => { mem.delete(k); },
      },
    };
  });
  it("round-trips the selected project through one key", () => {
    writeSelectedProject("abc");
    assert.equal(readSelectedProject(), "abc");
    assert.equal(PROJECT_STORAGE_KEY, "kev.project.id");
  });
  it("is SSR-safe (no window)", () => {
    delete (globalThis as unknown as { window?: unknown }).window;
    assert.equal(readSelectedProject(), null);
    writeSelectedProject("x"); // must not throw
  });
});

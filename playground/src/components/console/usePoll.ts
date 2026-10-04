"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * 轻量轮询。**不引 swr / react-query** —— 本仓库没有，YAGNI（spec §11.5）：
 * 作业列表与详情是低频读，SSE 只负责日志与指标的增量。
 *
 * `load` 必须是稳定引用，所以调用方要用 useCallback 包一层，否则依赖每次渲染都变、
 * 轮询会不断重启。
 */
export function usePoll<T>(load: () => Promise<T>, initial: T, intervalMs = 3000) {
  const [value, setValue] = useState<T>(initial);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await load();
        if (!cancelled) { setValue(next); setError(null); }
      } catch (problem) {
        if (!cancelled) setError((problem as Error).message);
      }
    };
    void tick();
    const timer = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(timer); };
  }, [load, intervalMs]);

  return { value, error };
}
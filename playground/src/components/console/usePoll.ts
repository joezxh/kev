"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 轻量轮询。**不引 swr / react-query** —— 本仓库没有，YAGNI（spec §11.5）：
 * 作业列表与详情是低频读，SSE 只负责日志与指标的增量。
 *
 * `load` 必须是稳定引用，所以调用方要用 useCallback 包一层，否则依赖每次渲染都变、
 * 轮询会不断重启。`refresh` 在需要立即刷新的动作（创建/撤销后）手动调用。
 */
export function usePoll<T>(load: () => Promise<T>, initial: T, intervalMs = 3000) {
  const [value, setValue] = useState<T>(initial);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const refresh = useCallback(async () => {
    try {
      const next = await loadRef.current();
      setValue(next);
      setError(null);
    } catch (problem) {
      setError((problem as Error).message);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void refresh();
    const timer = setInterval(() => {
      if (!cancelled) void refresh();
    }, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [refresh, intervalMs]);

  return { value, error, refresh };
}

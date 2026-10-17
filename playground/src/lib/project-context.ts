"use client";

import { useEffect, useState } from "react";

// /studio（读面）与 /console（写面）共享的单一当前项目 key（D12）。
// 两处的项目选择器都读写这一个 key，切换一次即跨页面贯通。
export const PROJECT_STORAGE_KEY = "kev.project.id";

// 同标签页内广播项目切换：原生 `storage` 事件只在其他标签页触发，
// 顶栏常驻切换器要即时重算当前页的项目范围，靠这个自定义事件补齐同页联动。
const PROJECT_CHANGED_EVENT = "kev:project-changed";

/** 读取当前选中的项目 id；SSR（无 window）或空值时返回 null。 */
export function readSelectedProject(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(PROJECT_STORAGE_KEY);
}

/** 写入当前选中的项目 id（传 null 清除）；SSR 下静默 no-op。 */
export function writeSelectedProject(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id === null) window.localStorage.removeItem(PROJECT_STORAGE_KEY);
  else window.localStorage.setItem(PROJECT_STORAGE_KEY, id);
  window.dispatchEvent(new Event(PROJECT_CHANGED_EVENT));
}

/** 当前项目 hook：挂载时从 localStorage 读取，set 时写穿同一 key。 */
export function useSelectedProject(): [string | null, (id: string) => void] {
  const [projectId, setProjectId] = useState<string | null>(null);
  useEffect(() => {
    setProjectId(readSelectedProject());
    const sync = () => setProjectId(readSelectedProject());
    // 同标签页（顶栏切换）与其他标签页（原生 storage）都回到这里重算。
    window.addEventListener(PROJECT_CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(PROJECT_CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  const setSelected = (id: string) => {
    writeSelectedProject(id);
    setProjectId(id);
  };
  return [projectId, setSelected];
}

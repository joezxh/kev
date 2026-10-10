// playground 选定 key 的本地存储。明文只在此浏览器，后端只存哈希（spec §3 / §12）。
const LS_ALL = "kev_apikeys";   // { [id]: { prefix: string; key: string } }
const LS_CURRENT = "kev_apikey"; // 当前选中的明文 key

export type SavedKey = { id: string; prefix: string; key: string };

export const apikeyStore = {
  loadKeys(): SavedKey[] {
    if (typeof window === "undefined") return [];
    try {
      const map = JSON.parse(localStorage.getItem(LS_ALL) || "{}") as Record<string, { prefix: string; key: string }>;
      return Object.entries(map).map(([id, v]) => ({ id, ...v }));
    } catch {
      return [];
    }
  },
  saveKey(id: string, prefix: string, key: string) {
    if (typeof window === "undefined") return;
    const map = JSON.parse(localStorage.getItem(LS_ALL) || "{}") as Record<string, { prefix: string; key: string }>;
    map[id] = { prefix, key };
    localStorage.setItem(LS_ALL, JSON.stringify(map));
    localStorage.setItem(LS_CURRENT, key);
  },
  setCurrent(key: string) {
    if (typeof window === "undefined") return;
    localStorage.setItem(LS_CURRENT, key);
  },
  getCurrent(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(LS_CURRENT) || null;
  },
  clearKey(id: string) {
    if (typeof window === "undefined") return;
    const map = JSON.parse(localStorage.getItem(LS_ALL) || "{}") as Record<string, { prefix: string; key: string }>;
    const removed = map[id];
    delete map[id];
    localStorage.setItem(LS_ALL, JSON.stringify(map));
    if (removed && localStorage.getItem(LS_CURRENT) === removed.key) {
      localStorage.removeItem(LS_CURRENT);
    }
  },
};

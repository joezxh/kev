"use client";
import { useEffect, useState } from "react";
import { api, type ApiKey } from "@/lib/console";
import { apikeyStore } from "@/lib/apikey-store";
import { useLang } from "@/lib/i18n";

// 下拉列表以服务端为准（权威）：展示所有「已启用」的 key，只显示名称。
// 凭据即 key 的 id：用户从服务端列表选中某个 key，前端把该 id 作为 Bearer 提交，
// 服务端按 id 校验「存在且 active」即可用（见 kev.console app.proxy_kev），前端无需持有任何密钥。
type Row = { id: string; name: string };

export function ApiKeyPicker() {
  const { t, lang } = useLang();
  const [rows, setRows] = useState<Row[]>([]);
  const [currentId, setCurrentId] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    // 当前选择就是 key id（来自服务端），直接回显。
    setCurrentId(apikeyStore.getCurrent() ?? "");

    api.apikeysAll()
      .then((serverKeys: ApiKey[]) => {
        if (cancelled) return;
        const enabled = serverKeys.filter((k) => k.active); // 只展示已启用
        setRows(enabled.map((k) => ({ id: k.id, name: k.name })));
      })
      .catch(() => {
        // 拿不到服务端状态（如离线）：列表清空，不缓存任何本地密钥。
        if (cancelled) return;
        setRows([]);
      });

    return () => { cancelled = true; };
  }, []);

  const onSelect = (id: string) => {
    setCurrentId(id);
    // 选中即把 key id 提交给服务端（作为凭据）；服务端校验其存在且 active。
    apikeyStore.setCurrent(id);
  };

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">{t("console.apikeys.use")}</span>
      <select
        className="h-8 rounded-md border border-border bg-background px-2 text-xs"
        value={currentId}
        onChange={(e) => onSelect(e.target.value)}
      >
        <option value="">{lang === "zh" ? "未选择" : "none"}</option>
        {rows.map((r) => (
          <option key={r.id} value={r.id}>{r.name || r.id}</option>
        ))}
      </select>
      {rows.length === 0 && (
        <a className="text-xs underline" href="/console/apikeys">
          {t("console.apikeys.createHint")}
        </a>
      )}
    </div>
  );
}

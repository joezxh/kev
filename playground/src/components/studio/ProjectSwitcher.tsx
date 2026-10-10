"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { api, type Project } from "@/lib/console";

/** 拉取项目列表（ch6 各页面共用）。 */
export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setLoading(true);
    api.projects()
      .then((p) => {
        setProjects(p);
        setError(null);
      })
      .catch((e) => setError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  return { projects, loading, error, reload: load };
}

/** 项目切换器：下拉选择 + 跳去 Projects 页创建。 */
export function ProjectSwitcher({
  projectId,
  onChange,
  projects,
}: {
  projectId: string | null;
  onChange: (id: string) => void;
  projects: Project[];
}) {
  const { t, lang } = useLang();
  return (
    <div className="flex items-center gap-2">
      <select
        value={projectId ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-border bg-[#111111] px-2 py-1.5 text-sm outline-none focus:border-primary"
      >
        <option value="" disabled>
          {lang === "zh" ? "选择项目" : "Select project"}
        </option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} ({p.slug})
          </option>
        ))}
      </select>
      <Link href="/studio/projects" className="text-xs text-muted-foreground hover:text-foreground">
        + {t("studio.nav.projects")}
      </Link>
    </div>
  );
}

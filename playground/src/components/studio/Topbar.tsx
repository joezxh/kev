"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLang } from "@/lib/i18n";
import { ProjectSwitcher, useProjects } from "@/components/studio/ProjectSwitcher";
import { useSelectedProject } from "@/lib/project-context";

// 与项目管理不相干的页面不显示项目切换器（req 7）：域与场景、API Keys 是全局资源，
// 不隶属任何单个项目，顶栏切换器在这两页隐藏；其余页（含 members/quota/webhooks/billing）常驻。
const HIDE_SWITCHER = ["/studio/domains", "/studio/apikeys"];

export function StudioTopbar() {
  const { t, lang, setLang } = useLang();
  const { projects } = useProjects();
  const [projectId, setProjectId] = useSelectedProject();
  const pathname = usePathname();
  const showSwitcher = !HIDE_SWITCHER.some((p) => pathname.startsWith(p));
  return (
    <header className="flex h-11 shrink-0 items-center gap-3 border-b border-border bg-[#111111] px-4">
      <Link href="/studio" className="text-sm font-semibold tracking-tight">
        kev<span className="text-primary">.studio</span>
      </Link>
      <nav className="ml-2 hidden items-center gap-1 md:flex">
        <Link
          href="/console"
          className="rounded px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-[#161616] hover:text-foreground"
        >
          {t("kev.nav.console")}
        </Link>
      </nav>
      <div className="ml-auto flex items-center gap-2">
        {showSwitcher && (
          <ProjectSwitcher projectId={projectId} onChange={setProjectId} projects={projects} />
        )}
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-[#161616] px-2 py-0.5 text-[11px] text-[#22c55e]">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#22c55e]" />
          live
        </span>
        <button
          type="button"
          onClick={() => setLang(lang === "zh" ? "en" : "zh")}
          className="rounded border border-border bg-[#161616] px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          {t("lang.toggle")}
        </button>
      </div>
    </header>
  );
}

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "cn";
import { ArrowLeft, ChevronRight, FileText, Folder, Search } from "lucide-react";
import type { Lang } from "@/lib/docs";
import { Button, buttonVariants } from "@/components/ui/button";

// Mermaid is loaded lazily on the client only (its import touches `document`),
// so the docs HTML — including ```mermaid code fences — renders first, then the
// diagrams are upgraded into SVG after mount. `marked` emits the fence as
// `<pre><code class="language-mermaid">`, which we detect below.
let mermaidPromise: Promise<typeof import("mermaid").default> | null = null;
function getMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((m) => {
      m.default.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "loose" });
      return m.default;
    });
  }
  return mermaidPromise;
}

export type DocNode = {
  name: string;
  path?: string;
  children?: DocNode[];
};

type FlatFile = { name: string; path: string; depth: number };

function flattenFiles(nodes: DocNode[], depth = 0, acc: FlatFile[] = []): FlatFile[] {
  for (const n of nodes) {
    if (n.path) acc.push({ name: n.name, path: n.path, depth });
    if (n.children) flattenFiles(n.children, depth + 1, acc);
  }
  return acc;
}

function findFirstFile(nodes: DocNode[]): string | undefined {
  for (const n of nodes) {
    if (n.path) return n.path;
    if (n.children) {
      const f = findFirstFile(n.children);
      if (f) return f;
    }
  }
  return undefined;
}

function TreeNode({
  node,
  expanded,
  selected,
  onToggle,
  onSelect,
}: {
  node: DocNode;
  expanded: Set<string>;
  selected: string | null;
  onToggle: (name: string) => void;
  onSelect: (path: string) => void;
}) {
  const isFolder = !!node.children;
  const isOpen = expanded.has(node.name);
  const childCount = node.children?.length ?? 0;

  if (isFolder) {
    return (
      <li>
        <button
          type="button"
          onClick={() => onToggle(node.name)}
          aria-expanded={isOpen}
          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[13px] font-medium text-foreground/80 transition-colors hover:bg-muted hover:text-foreground"
        >
          <ChevronRight
            className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", isOpen && "rotate-90")}
          />
          <Folder className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{node.name}</span>
          <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">{childCount}</span>
        </button>
        {isOpen && node.children && (
          <ul className="mb-0.5 ml-3 border-l border-border pl-1.5">
            {node.children.map((c) => (
              <TreeNode key={c.name} node={c} expanded={expanded} selected={selected} onToggle={onToggle} onSelect={onSelect} />
            ))}
          </ul>
        )}
      </li>
    );
  }

  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(node.path!)}
        aria-current={selected === node.path ? "true" : undefined}
        className={cn(
          "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[13px] transition-colors",
          selected === node.path
            ? "bg-primary/10 font-medium text-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )}
      >
        <span className="w-3.5 shrink-0" />
        <FileText className="size-3.5 shrink-0 opacity-70" />
        <span className="truncate">{node.name}</span>
      </button>
    </li>
  );
}

export function DocsViewer({ tree, lang, initialPath }: { tree: DocNode[]; lang: Lang; initialPath: string | null }) {
  const router = useRouter();
  const allFiles = useMemo(() => flattenFiles(tree), [tree]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(tree.filter((n) => n.children).map((n) => n.name)));
  const [selected, setSelected] = useState<string | null>(initialPath ?? findFirstFile(tree) ?? null);
  const [query, setQuery] = useState("");
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fallback, setFallback] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // If the incoming path is not part of this language's tree, fall back to the first doc.
  useEffect(() => {
    if (selected && !allFiles.some((f) => f.path === selected)) setSelected(findFirstFile(tree) ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return allFiles.filter((f) => f.name.toLowerCase().includes(q) || decodeURIComponent(f.path).toLowerCase().includes(q));
  }, [query, allFiles]);

  function toggle(name: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  useEffect(() => {
    if (!selected) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setError(null);
    fetch(`/api/docs?lang=${lang}&path=${selected}`, { signal: ctrl.signal })
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "文档不存在" : `加载失败 (${r.status})`);
        setFallback(r.headers.get("X-Doc-Fallback") === "zh");
        return r.text();
      })
      .then((t) => setContent(t))
      .catch((e: Error) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setContent("");
        }
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [selected, lang]);

  // Upgrade ```mermaid code blocks into rendered SVG diagrams. We render from the
  // authoritative `content` HTML string (parsed via DOMParser) rather than reading
  // back the live DOM — this avoids the stale/accumulated DOM that results from
  // mutating React-managed `dangerouslySetInnerHTML`, so navigating between docs
  // always rebuilds the diagrams cleanly. `marked` emits `code.language-mermaid`.
  useEffect(() => {
    const root = contentRef.current;
    if (!root || !content) return;
    // Parse a fresh copy so we never read our own previous mutations.
    const doc = new DOMParser().parseFromString(content, "text/html");
    const blocks = Array.from(doc.querySelectorAll<HTMLElement>("code.language-mermaid"));
    let cancelled = false;
    (async () => {
      const mermaid = await getMermaid();
      for (const code of blocks) {
        if (cancelled) return;
        const pre = code.parentElement;
        if (!pre || !pre.parentElement) continue;
        const src = code.textContent ?? "";
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        try {
          const { svg } = await mermaid.render(id, src);
          if (cancelled) return;
          const wrap = doc.createElement("div");
          wrap.className = "mermaid-block my-6 flex justify-center overflow-x-auto rounded-lg border border-border bg-card p-2";
          wrap.innerHTML = svg;
          pre.replaceWith(wrap);
        } catch (err) {
          console.error("mermaid render failed", err);
        }
      }
      if (!cancelled) root.innerHTML = doc.body.innerHTML;
    })();
    return () => {
      cancelled = true;
    };
  }, [content]);

  const selectedName = useMemo(() => allFiles.find((f) => f.path === selected)?.name ?? "", [allFiles, selected]);
  const otherLang: Lang = lang === "zh" ? "en" : "zh";

  function switchLang() {
    const q = selected ? `?p=${encodeURIComponent(selected)}` : "";
    router.push(`/docs/${otherLang}${q}`);
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col px-6 pt-8 md:px-10">
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-medium tracking-tight">{lang === "en" ? "kev docs" : "kev文档"}</h1>
          <nav aria-label="返回" className="flex items-center gap-1.5">
            <Link
              href="/"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
            >
              <ArrowLeft className="size-3.5" />
              {lang === "zh" ? "返回 kev" : "kev"}
            </Link>
            <Link href="/chess" className={buttonVariants({ variant: "outline", size: "sm" })}>
              {lang === "zh" ? "chess" : "chess"}
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <p className="text-[13px] text-muted-foreground">{allFiles.length} 篇文档</p>
          <Button variant="outline" size="sm" onClick={switchLang} aria-label="切换语言">
            {lang === "zh" ? "EN" : "中文"}
          </Button>
        </div>
      </header>

      <div className="mt-8 grid min-h-[70vh] gap-6 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-8 lg:h-[calc(100vh-7rem)] lg:overflow-hidden">
          <div className="flex h-full flex-col rounded-xl border border-border bg-card">
            <div className="border-b border-border p-3">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={lang === "en" ? "Search docs…" : "搜索文档…"}
                  className="w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-2 text-[13px] outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                />
              </div>
            </div>
            <nav aria-label="文档目录" className="flex-1 overflow-y-auto p-2">
              {filtered ? (
                filtered.length === 0 ? (
                  <p className="px-2 py-4 text-[13px] text-muted-foreground">{lang === "en" ? "No results" : "无匹配结果"}</p>
                ) : (
                  <ul className="flex flex-col gap-0.5">
                    {filtered.map((f) => (
                      <li key={f.path}>
                        <button
                          type="button"
                          onClick={() => setSelected(f.path)}
                          aria-current={selected === f.path ? "true" : undefined}
                          className={cn(
                            "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[13px] transition-colors",
                            selected === f.path
                              ? "bg-primary/10 font-medium text-foreground"
                              : "text-muted-foreground hover:bg-muted hover:text-foreground",
                          )}
                        >
                          <FileText className="size-3.5 shrink-0 opacity-70" />
                          <span className="truncate">{f.name}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )
              ) : (
                <ul className="flex flex-col gap-0.5">
                  {tree.map((n) => (
                    <TreeNode
                      key={n.name}
                      node={n}
                      expanded={expanded}
                      selected={selected}
                      onToggle={toggle}
                      onSelect={setSelected}
                    />
                  ))}
                </ul>
              )}
            </nav>
          </div>
        </aside>

        <main className="min-w-0">
          <article className="rounded-xl border border-border bg-card p-6 md:p-8">
            {loading && <p className="text-[13px] text-muted-foreground">{lang === "en" ? "Loading…" : "加载中…"}</p>}
            {error && <p className="text-[13px] text-destructive">{error}</p>}
            {!loading && !error && content && (
              <>
                <h1 className="doc-title mb-5 text-2xl font-semibold tracking-tight">{selectedName}</h1>
                {fallback && (
                  <p className="mb-5 rounded-md border border-border bg-muted/50 px-4 py-2.5 text-[13px] leading-5 text-muted-foreground">
                    {lang === "en"
                      ? "English version not available yet — showing the Chinese original."
                      : "中文版暂不可用，已显示英文原文。"}
                  </p>
                )}
                <div className="doc-content" ref={contentRef} dangerouslySetInnerHTML={{ __html: content }} />
              </>
            )}
            {!loading && !error && !content && (
              <p className="text-[13px] text-muted-foreground">
                {lang === "en" ? "Select a document from the left to start reading." : "从左侧目录选择一篇文档开始阅读。"}
              </p>
            )}
          </article>
        </main>
      </div>
    </div>
  );
}

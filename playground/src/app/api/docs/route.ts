import { NextRequest } from "next/server";
import fs from "fs";
import path from "path";
import { marked } from "marked";
import { docsRoot, isLang, stripCitations, type Lang } from "@/lib/docs";

export const dynamic = "force-dynamic";

// Render markdown to HTML on the server with `marked`. Doing this here (instead
// of on the client) avoids a Turbopack ESM-interop bug where `remark-gfm`'s
// default import is mangled into the literal `remark - gfm` expression in the
// client bundle. We deliberately do NOT use react-dom/server (renderToStaticMarkup)
// because Next.js 16 forbids importing it from a server module. `marked` emits a
// plain HTML string that is safe to inject.
function renderHtml(md: string): string {
  return marked.parse(md, { gfm: true }) as string;
}

export function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const langParam = sp.get("lang") ?? "zh";
  const p = sp.get("path");
  if (!p) return new Response("missing path", { status: 400 });
  if (!isLang(langParam)) return new Response("invalid lang", { status: 400 });
  const lang = langParam as Lang;

  const segments = p.split("/").map((s) => decodeURIComponent(s));
  const root = docsRoot(lang);
  const abs = path.resolve(root, ...segments);

  // Guard against path traversal and non-markdown requests.
  if (abs !== root && !abs.startsWith(root + path.sep)) {
    return new Response("invalid path", { status: 400 });
  }
  if (!abs.toLowerCase().endsWith(".md") || !fs.existsSync(abs) || !fs.statSync(abs).isFile()) {
    // Graceful fallback: if an English page has not been translated yet, serve
    // the Chinese original so the language toggle always lands on readable content.
    if (lang === "en") {
      const zhRoot = docsRoot("zh");
      const zhAbs = path.resolve(zhRoot, ...segments);
      if (zhAbs.startsWith(zhRoot + path.sep) && fs.existsSync(zhAbs) && fs.statSync(zhAbs).isFile()) {
        return new Response(renderHtml(stripCitations(fs.readFileSync(zhAbs, "utf-8"))), {
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Doc-Fallback": "zh",
          },
        });
      }
    }
    return new Response("not found", { status: 404 });
  }

  return new Response(renderHtml(stripCitations(fs.readFileSync(abs, "utf-8"))), {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}

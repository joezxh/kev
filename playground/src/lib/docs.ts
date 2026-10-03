import fs from "fs";
import path from "path";

export type Lang = "zh" | "en";

export function isLang(v: string): v is Lang {
  return v === "zh" || v === "en";
}

// Source of the docs. The playground lives at <repo>/playground, the repowiki
// export at <repo>/.qoder/repowiki/<lang>/content.
export function docsRoot(lang: Lang): string {
  return path.resolve(process.cwd(), "..", ".qoder", "repowiki", lang, "content");
}

export type DocNode = {
  /** Display name from the file's first `#` heading (fallback: file name). */
  name: string;
  /** Relative posix path (percent-encoded segments) for a markdown file. */
  path?: string;
  /** Child nodes for a folder. */
  children?: DocNode[];
};

const headingCache = new Map<string, string>();

/** First `# heading` of a markdown file, used as its tree label. */
function firstHeading(abs: string, fallback: string): string {
  const cached = headingCache.get(abs);
  if (cached !== undefined) return cached;
  let label = fallback;
  try {
    const text = fs.readFileSync(abs, "utf-8");
    const m = text.match(/^#\s+(.+)$/m);
    if (m) label = m[1].trim();
  } catch {
    /* keep fallback */
  }
  headingCache.set(abs, label);
  return label;
}

function walk(dir: string, rel: string, isTop: boolean): DocNode[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }

  const dirs: DocNode[] = [];
  const files: DocNode[] = [];

  for (const e of entries) {
    const seg = encodeURIComponent(e.name);
    const childRel = rel ? `${rel}/${seg}` : seg;
    if (e.isDirectory()) {
      // A folder often has a sibling overview file sharing its base name; use
      // that file's first heading as the folder's label.
      const overview = path.join(dir, e.name, `${e.name}.md`);
      const label = fs.existsSync(overview) ? firstHeading(overview, e.name) : e.name;
      dirs.push({ name: label, children: walk(path.join(dir, e.name), childRel, false) });
    } else if (e.isFile() && e.name.toLowerCase().endsWith(".md")) {
      files.push({ name: firstHeading(path.join(dir, e.name), e.name.replace(/\.md$/i, "")), path: childRel });
    }
  }

  const byName = (a: DocNode, b: DocNode) => a.name.localeCompare(b.name, "zh");
  dirs.sort(byName);
  files.sort(byName);
  // Top level: intro pages first, then categories. Nested: categories first.
  return isTop ? [...files, ...dirs] : [...dirs, ...files];
}

export function buildDocsTree(lang: Lang): DocNode[] {
  return walk(docsRoot(lang), "", true);
}

/**
 * Remove the repowiki citation apparatus that does not make sense in a web
 * viewer: the top-level `<cite>` "本文引用的文件" index, the `**章节来源**` /
 * `**图表来源**` headings, and every `file://` reference bullet (those paths
 * only resolve inside the source repo). Plain content is left untouched.
 */
export function stripCitations(md: string): string {
  return md
    .replace(/<cite>[\s\S]*?<\/cite>/gi, "")
    .replace(/^\*\*[^*]*来源\*\*\s*$/gm, "")
    .replace(/^- \[[^\]]+\]\(file:\/\/[^)]+\)\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

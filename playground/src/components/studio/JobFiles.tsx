"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, type Job } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

/**
 * 作业的文件查看：输出产物、输入产物 / 文件入参、执行脚本，全部点击弹窗，不跳转。
 *
 * 内容真相源：
 * - 注册产物（`dataset:x/summary`、`plan:y` 等 id）→ GET /artifacts/{id}/content，
 *   id 到路径的解析归 artifacts.resolve()，前端不推断；
 * - 直接写路径的入参（如 make_examples 的 --data data/critical-value.jsonl）→
 *   GET /files/content（后端白名单：仅 data/ 与 runs/ 下的文本文件）；
 * - 执行脚本 → 作业行自带的 argv/cwd（提交时由阶段 build() 定死，无需再请求）。
 */

/** 弹窗打开目标：注册产物按 id、入参文件按仓库相对路径、脚本按作业。 */
export type ViewerSpec =
  | { mode: "artifact"; id: string }
  | { mode: "file"; path: string }
  | { mode: "argv"; job: Job };

// 哪些入参值算「文件」：与后端 files/content 的白名单同形状（data|runs 顶层 + 文本后缀）。
// 后端放宽一类而这里没跟上，就会出现点得开却读不到的芯片，两处要一起改。
const FILE_PARAM_RE = /^(data|runs)\/\S+\.(jsonl|json|txt|md|csv|ya?ml)$/i;

export function isFilePathParam(value: unknown): value is string {
  return typeof value === "string" && FILE_PARAM_RE.test(value.trim());
}

function Chip({ label, onClick, title }: { label: string; onClick: () => void; title?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="max-w-64 truncate rounded border border-border bg-[#111111] px-1.5 py-0.5
        font-mono text-[11px] text-[#3b82f6] transition-colors hover:bg-[#1e3a8a]/30"
    >
      {label}
    </button>
  );
}

/** 作业行下方的详情条：输出产物 / 输入（产物 + 文件入参）/ 执行脚本，逐芯片可点。 */
export function JobFilesStrip({ job, onOpen }: { job: Job; onOpen: (spec: ViewerSpec) => void }) {
  const { t } = useLang();
  const dash = <span className="text-[11px] text-muted-foreground">{t("studio.jobfiles.none")}</span>;

  // request 即提交时的 params 字典（retry 也按它重放）；只挑像文件的路径值。
  const fileParams = Object.entries(job.request ?? {}).filter(
    ([, value]) => isFilePathParam(value),
  ) as [string, string][];

  const group = (label: string, chips: ReactNode) => (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className="shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      {chips}
    </div>
  );

  return (
    <div className="flex flex-col gap-1.5">
      {group(t("studio.jobfiles.outputs"), job.artifacts_out.length
        ? job.artifacts_out.map((id) => (
            <Chip key={id} label={id} title={t("studio.jobfiles.clickFile")}
                  onClick={() => onOpen({ mode: "artifact", id })} />
          ))
        : dash)}
      {group(t("studio.jobfiles.inputs"), (
        <>
          {job.artifacts_in.map((id) => (
            <Chip key={id} label={id} title={t("studio.jobfiles.clickFile")}
                  onClick={() => onOpen({ mode: "artifact", id })} />
          ))}
          {fileParams.map(([key, path]) => (
            <Chip key={`${key}:${path}`} label={`${key}=${path}`} title={t("studio.jobfiles.clickFile")}
                  onClick={() => onOpen({ mode: "file", path })} />
          ))}
          {job.artifacts_in.length === 0 && fileParams.length === 0 && dash}
        </>
      ))}
      {group(t("studio.jobfiles.script"), (
        <Chip label={`argv (${job.argv.length})`} title={t("studio.jobfiles.clickScript")}
              onClick={() => onOpen({ mode: "argv", job })} />
      ))}
    </div>
  );
}

type ViewerResult = {
  key: string; error: string | null;
  sub: string; text: string; truncated: boolean;
};

/** 同一目标只取一次：key 变才重取；关闭再开同一目标命中缓存。 */
function specKey(spec: ViewerSpec): string {
  if (spec.mode === "artifact") return `a:${spec.id}`;
  if (spec.mode === "file") return `f:${spec.path}`;
  return `v:${spec.job.id}:${spec.job.argv.join(" ")}`;
}

/** spec -> 展示内容。产物/文件走只读接口；argv 就地格式化（不请求，旧后端也能看）。 */
async function resolveSpec(spec: ViewerSpec): Promise<Omit<ViewerResult, "key">> {
  if (spec.mode === "argv") {
    const lines = spec.job.argv.map((part, i) => (i === 0 ? `$ ${part}` : `    ${part}`));
    // cwd 里可能带仓库绝对路径，仅作展示；env 不回显（凭据一律不进响应，spec §12）。
    return { error: null, sub: `cwd: ${spec.job.cwd}`, text: lines.join("\n"), truncated: false };
  }
  if (spec.mode === "artifact") {
    const c = await api.artifactContent(spec.id);
    return { error: null, sub: c.path, text: c.content, truncated: c.truncated };
  }
  const c = await api.fileContent(spec.path);
  return { error: null, sub: spec.path, text: c.content, truncated: c.truncated };
}

/**
 * 统一查看弹窗。spec 为 null 时关闭；关闭时不清展示目标（shown），淡出动画期间
 * 内容保留。目录型产物 / 端点型产物由后端返回可读的 404/415 文案。
 *
 * 状态同步用 React 官方的「渲染期调整状态」模式而非 effect 里同步 setState
 * （lint 规则 set-state-in-effect 禁止后者）；取数只在 effect 里异步回写。
 */
export function FileViewerDialog({ spec, onClose }: { spec: ViewerSpec | null; onClose: () => void }) {
  const { t } = useLang();
  const [shown, setShown] = useState<{ spec: ViewerSpec; key: string } | null>(
    spec ? { spec, key: specKey(spec) } : null);
  const [result, setResult] = useState<ViewerResult | null>(null);

  const key = spec ? specKey(spec) : null;
  // 目标切换（首次打开或换了文件）才重置展示态；key 相等不 setState，不会循环。
  if (key !== null && spec && key !== shown?.key) {
    setShown({ spec, key });
    setResult(null);
  }

  useEffect(() => {
    if (!shown) return;
    let cancelled = false;
    resolveSpec(shown.spec)
      .then((r) => { if (!cancelled) setResult({ key: shown.key, ...r }); })
      .catch((e) => {
        if (cancelled) return;
        // ApiError.message 已是「message —— hint」的中文可读形状；目录/端点产物就在这里被说明。
        setResult({ key: shown.key, error: e instanceof Error ? e.message : String(e),
                    sub: "", text: "", truncated: false });
      });
    return () => { cancelled = true; };
  }, [shown]);

  const title = shown
    ? shown.spec.mode === "argv" ? `${shown.spec.job.kind} argv`
    : shown.spec.mode === "artifact" ? shown.spec.id : shown.spec.path
    : "";
  const loading = !!spec && !result;

  return (
    <Dialog open={!!spec} onOpenChange={(open) => { if (!open) onClose(); }}>
      {/* DialogContent 挂在 document.body 上的 portal，落在 `.studio` 那套近黑 IDE 调色板
          （globals.css）作用域之外，于是退回 :root 的浅色：白卡片 + 近黑文字，而下面代码块的
          底色写死 #050505 —— 黑字压黑底，产物与脚本内容等于看不见。给弹窗自己加 dark 作用域：
          自定义属性从最近的定义祖先继承，弹窗整棵子树（含右上角关闭按钮）随之换成暗色，
          文字继承 --popover-foreground 变浅色，与它所在的页面同一套配色。 */}
      <DialogContent className="dark sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="break-all font-mono text-sm">
            {title || t("studio.jobfiles.loading")}
          </DialogTitle>
          <DialogDescription className="break-all font-mono text-[11px]">
            {result?.sub || (loading ? t("studio.jobfiles.loading") : "")}
          </DialogDescription>
        </DialogHeader>
        {result?.error ? (
          <p className="rounded-md border border-[#ef4444]/40 bg-[#ef4444]/10 p-3 text-xs text-[#ef4444]">
            {result.error}
          </p>
        ) : loading || !result ? (
          <p className="p-3 text-xs text-muted-foreground">{t("studio.jobfiles.loading")}</p>
        ) : (
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-[#050505] p-3 font-mono text-xs leading-relaxed">
            {result.text || t("studio.datasets.noContent")}
            {result.truncated && (
              <span className="text-muted-foreground"> …{t("studio.jobfiles.truncated")}</span>
            )}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}

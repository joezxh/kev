"use client";

import { use, useEffect, useState } from "react";
import { api, type Artifact } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { EmptyState, Kpi, Panel } from "@/components/studio/primitives";

export default function StudioDatasetDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useLang();
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [content, setContent] = useState<{ content: string; truncated: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dataset(id)
      .then(setArtifact)
      .catch(() => setArtifact(null));
    api
      .artifactContent(id)
      .then((c) => setContent(c))
      .catch((e) => setError(e?.message ?? "failed"));
  }, [id]);

  if (error && !artifact) {
    return <EmptyState title={t("studio.domains.loadFailed")} hint={error} />;
  }
  if (!artifact) {
    return <p className="text-sm text-muted-foreground">{t("console.jobs.loading")}</p>;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label={t("studio.datasets.records")} value={String((artifact.meta?.records as number) ?? "—")} />
        <Kpi label={t("studio.datasets.invalid")} value={String((artifact.meta?.invalid_lines as number) ?? "—")} />
        <Kpi label="bytes" value={artifact.bytes != null ? String(artifact.bytes) : "—"} />
        <Kpi label="kind" value={<span className="text-base">{artifact.kind}</span>} />
      </div>

      <Panel title={t("studio.datasets.detail")} desc={artifact.path}>
        <div className="flex flex-col gap-1 text-xs">
          <div className="text-muted-foreground">id: <span className="font-mono text-foreground">{artifact.id}</span></div>
          <div className="text-muted-foreground">name: <span className="font-mono text-foreground">{artifact.name}</span></div>
          <div className="text-muted-foreground">created: <span className="font-mono text-foreground">{artifact.created_at.slice(0, 19)}</span></div>
        </div>
      </Panel>

      <Panel title={t("studio.datasets.content")}>
        {content ? (
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-[#050505] p-3 font-mono text-xs leading-relaxed">
            {content.content || t("studio.datasets.noContent")}
            {content.truncated && <span className="text-muted-foreground"> …(truncated)</span>}
          </pre>
        ) : (
          <EmptyState title={t("studio.datasets.noContent")} />
        )}
      </Panel>
    </div>
  );
}

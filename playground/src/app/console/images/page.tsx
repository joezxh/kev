"use client";

import { useCallback } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { JobStagePage } from "@/components/console/JobStagePage";
import { usePoll } from "@/components/console/usePoll";

export default function ImagesPage() {
  const { t, lang } = useLang();
  const load = useCallback(() => api.artifacts("image"), []);
  const images = usePoll(load, []);

  return (
    <div className="space-y-6">
      <JobStagePage
        kind="image"
        gateStage="image"
        title={t("console.nav.image")}
        fields={[
          { key: "temperature", label: "TEMPERATURE",
            hint: lang === "zh"
              ? "必填。从 calibration.json 的 workload_temperature 取 —— 绝不在 development.jsonl 上拟合温度"
              : "Required. Take it from calibration.json's workload_temperature; never fit it on development.jsonl" },
        ]}
      >
        <Alert>
          <AlertTitle>{t("console.image.noBake")}</AlertTitle>
          <AlertDescription>
            {lang === "zh"
              ? "默认只提供 GPU 镜像：kev/serve.py 的服务默认值在非 CPU 设备上开 bf16 + CUDA graphs，CPU 路径未在 0.8B 规模上验证过。"
              : "GPU image only by default: kev/serve.py enables bf16 + CUDA graphs on non-CPU devices, and the CPU path is unverified at 0.8B scale."}
          </AlertDescription>
        </Alert>
      </JobStagePage>

      <section className="space-y-2">
        <h2 className="text-sm font-medium">{t("console.image.list")}</h2>
        {images.value.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {lang === "zh" ? "还没有镜像" : "No images yet"}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow><TableHead>tag</TableHead><TableHead>built from</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {images.value.map((artifact) => (
                <TableRow key={artifact.id}>
                  <TableCell className="font-mono text-xs">{artifact.id}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {artifact.lineage?.map((edge) => edge.parent).join(", ")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatMetric } from "@/components/console/format";

export type ComparisonRow = {
  name: string;
  reference?: number;
  candidate?: number;
};

/**
 * Side-by-side metric comparison table shared by /studio/eval and /studio/eval/compare.
 * The compare page shows a Δ column (signed candidate − reference); the run page does not.
 */
export function ComparisonTable({
  rows,
  candidateLabel,
  referenceLabel,
  withDelta = false,
  metricLabel,
}: {
  rows: ComparisonRow[];
  candidateLabel: string;
  referenceLabel: string;
  withDelta?: boolean;
  metricLabel: string;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{metricLabel}</TableHead>
          <TableHead className="text-right">{referenceLabel}</TableHead>
          <TableHead className="text-right">{candidateLabel}</TableHead>
          {withDelta && <TableHead className="text-right">Δ</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => {
          const ref = r.reference ?? 0;
          const cand = r.candidate ?? 0;
          const delta = cand - ref;
          const up = delta >= 0;
          return (
            <TableRow key={r.name}>
              <TableCell className="font-mono text-xs">{r.name}</TableCell>
              <TableCell className="text-right font-mono text-xs">{formatMetric(r.reference)}</TableCell>
              <TableCell className="text-right font-mono text-xs">{formatMetric(r.candidate)}</TableCell>
              {withDelta && (
                <TableCell
                  className={`text-right font-mono text-xs ${up ? "text-[#22c55e]" : "text-[#ef4444]"}`}
                >
                  {delta >= 0 ? "+" : ""}
                  {delta.toFixed(3)}
                </TableCell>
              )}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
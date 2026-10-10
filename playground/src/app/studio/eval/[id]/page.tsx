"use client";

import { use } from "react";
import { JobDetailPanel } from "@/components/console/JobDetailPanel";

export default function StudioEvalJobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <JobDetailPanel jobId={id} />;
}

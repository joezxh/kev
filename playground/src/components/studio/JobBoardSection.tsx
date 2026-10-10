"use client";

import { JobBoard } from "@/components/studio/JobBoard";

export function JobBoardSection({
  title,
  kinds,
  stage,
  hrefFor,
}: {
  title: string;
  kinds?: string[];
  stage?: string;
  hrefFor: (id: string) => string;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium">{title}</h2>
      <JobBoard kinds={kinds} stage={stage} hrefFor={hrefFor} />
    </section>
  );
}
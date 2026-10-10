import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { buildDocsTree, isLang, type Lang } from "@/lib/docs";
import { DocsViewer } from "../DocsViewer";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang } = await params;
  const title = lang === "en" ? "kev docs" : "kev文档";
  return { title, description: "Kev 项目文档：架构、训练、推理、评估与部署指南。" };
}

export default async function DocsPage({
  params,
  searchParams,
}: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<{ p?: string }>;
}) {
  const { lang: raw } = await params;
  const { p } = await searchParams;
  if (!isLang(raw)) notFound();
  const lang = raw as Lang;

  const tree = buildDocsTree(lang);
  return <DocsViewer tree={tree} lang={lang} initialPath={p ?? null} />;
}

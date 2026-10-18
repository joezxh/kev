"use client";

import { DomainsManager } from "@/components/studio/DomainsManager";

export default function StudioDomainsPage() {
  // 标题行（含右侧「新建域」按钮）由 DomainsManager 自带：按钮要触达其内部 drawer 状态，
  // 与标题同处一个组件最自然，这里只做路由页外壳。
  return <DomainsManager />;
}

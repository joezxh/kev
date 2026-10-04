// 薄代理：控制台 UI 与编排服务同源，规避 CORS，并给以后加鉴权留一个位置。
// SSE 必须用 ReadableStream 逐块透传 —— Response.json 会把流缓冲掉，EventSource 收不到帧。
import type { NextRequest } from "next/server";

const CONSOLE_API = process.env.KEV_CONSOLE_API ?? "http://127.0.0.1:8790/console/api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(request: NextRequest, path: string[]) {
  const target = new URL(`${CONSOLE_API}/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined : await request.text();
  const lastEventId = request.headers.get("last-event-id");

  const upstream = await fetch(target, {
    method: request.method,
    headers: {
      "Content-Type": "application/json",
      // 透传断点续传游标：EventSource 重连时浏览器把它放在 Last-Event-ID 头里，
      // 编排层优先读它。只读查询参数会让重连从 0 全量重放（Task 2 评审发现）。
      ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
    },
    body,
    cache: "no-store",
  });

  const type = upstream.headers.get("content-type") ?? "";
  if (!upstream.body || !type.includes("text/event-stream")) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": type || "application/json" },
    });
  }

  // 逐块转发：EventSource 需要增量到达，全量缓冲会让曲线在训练结束时才一次性出现
  const reader = upstream.body.getReader();
  const stream = new ReadableStream({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        controller.close();
        return;
      }
      controller.enqueue(value);
    },
    cancel(reason) {
      void reader.cancel(reason);
    },
  });
  return new Response(stream, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
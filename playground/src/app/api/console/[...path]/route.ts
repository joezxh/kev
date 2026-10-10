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

  // 透传鉴权头：浏览器把用户选中的 key id 放在 Authorization: Bearer <id> 里，
  // 编排层(kev.console)据此按 id 校验存在且启用，并注入管理 key 转发给 kev.serve。薄代理必须原样转发，
  // 否则控制台收到的是无 Authorization 的请求，会返回 401「缺少 API Key」。
  const auth = request.headers.get("authorization");

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
        // 透传断点续传游标：EventSource 重连时浏览器把它放在 Last-Event-ID 头里，
        // 编排层优先读它。只读查询参数会让重连从 0 全量重放（Task 2 评审发现）。
        ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
      },
      body,
      cache: "no-store",
    });
  } catch (cause) {
    // 编排服务没起，或地址不通 —— 容器部署里最常见的两种：
    // 1) 服务根本没启动（默认连 127.0.0.1:8790，宿主机上没进程就 ECONNREFUSED）
    // 2) playground 跑在容器里，而容器内的 127.0.0.1 是容器自己，不是宿主机
    // 必须返回前端认得的错误体；让它冒成 500 只会得到一个没有信息量的栈。
    return Response.json(
      { error: {
          kind: "upstream",
          message: `连不上编排服务：${target.origin}`,
          field: "KEV_CONSOLE_API",
          hint: "先在宿主机启动 `python -m kev.console`；从容器访问宿主机要用网关地址（不是 127.0.0.1），"
                + "并在启动服务时设 KEV_CONSOLE_HOST=0.0.0.0，同时把 KEV_CONSOLE_API 指向那个网关地址。",
          stderr_tail: cause instanceof Error ? `${cause.message} ${String(cause.cause ?? "")}`.trim() : String(cause),
        } },
      { status: 503 },
    );
  }

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

export async function PUT(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function DELETE(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
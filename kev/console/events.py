"""把 kev.train 的日志文本解析成结构化事件。

kev.train 没有 logger，全部是 print(..., flush=True)（kev/train.py 全仓无 logging）。
唯一进度行是 kev/train.py:642-643 的：
    ep{ep} step {step}/{total} loss {L} kl {K} anchor {A} {R}s/rec
每 10 个 optimizer step 一次。kev/plot.py:11 已有同形状的正则在用（从日志文本画 loss 图），
这里复用同一形状，不重新发明。

持久化的只有日志行本身（真相源是日志文件）；metric 帧在 SSE 推流时从行派生，不额外落库。
"""
from __future__ import annotations

import json
import re
from collections import deque

    # 三个损失都是 `:.3f` 格式化的（kev/train.py:643），而 F.kl_div(reduction="sum")
    # 在 float32 下、两个分布趋于重合时可能给出极小负值 => 渲染成 `-0.000`。
    # 所以数值子式必须允许前导负号，否则整行失配、**连合法的 loss 一起丢掉** ——
    # 而 kev/plot.py 用的是不带锚的 finditer 且只取 loss，它照样能画出来，
    # 于是变成「图能画、曲线在收敛段无声缺点」这种最难查的分叉。
    # 同时不接受 `1.2.3` / `nan` 这类 float() 会抛 ValueError 的串。
_NUM = r"[-+]?\d*\.?\d+"
STEP_RE = re.compile(
    rf"^ep(?P<ep>\d+) step (?P<step>\d+)/(?P<total>\d+) "
    rf"loss (?P<loss>{_NUM}) kl (?P<kl>{_NUM}) anchor (?P<anchor>{_NUM}) "
    rf"(?P<sec>{_NUM})s/rec"
)
DROPPED_RE = re.compile(r"^dropped (?P<dropped>\d+) of (?P<total>\d+) records")
# 路径用惰性匹配到行尾：--out 没有校验（train.py:415），`--out "runs/cv 8b"` 经
# API 可达，用 \S+ 会把路径截断成 "runs/cv"，产物链接 404。\s*$ 顺带兜住 \r。
SAVED_RE = re.compile(r"^saved (?P<path>.+?)\s*$")
NONFINITE_RE = re.compile(r"non-finite training loss")

DEFAULT_BUFFER = 2000


def parse_step(line: str):
    """一行进度日志 -> 指标点；不是进度行返回 None。

    `parse_step` 是对外公开接口，reader 线程（Task 3）会无保护地调用它 ——
    一行怪数据抛异常会把线程打死、作业永远不到终态、UI 永久转圈。所以 float()
    的 ValueError 在这里收敛成 None（"这行不是指标"），而不是往上抛。
    """
    match = STEP_RE.match(line)
    if match is None:
        return None
    try:
        return _point(match.groupdict())
    except ValueError:
        return None


def _point(got: dict) -> dict:
    return {
        "ep": int(got["ep"]),
        "step": int(got["step"]),
        "total": int(got["total"]),
        "loss": float(got["loss"]),
        "kl": float(got["kl"]),
        "anchor": float(got["anchor"]),
        "sec": float(got["sec"]),
    }


def parse_note(line: str):
    """识别需要主动提示的运行期事件（丢弃记录、非有限损失、保存完成）。"""
    match = DROPPED_RE.match(line)
    if match is not None:
        return {"kind": "dropped", "dropped": int(match["dropped"]), "total": int(match["total"])}
    match = SAVED_RE.match(line)
    if match is not None:
        return {"kind": "saved", "path": match["path"]}
    if NONFINITE_RE.search(line):
        return {"kind": "nonfinite"}
    return None


def sse_frame(event: dict, metric: dict | None = None) -> str:
    """一条 SSE 文本帧。metric 非空时附一帧 metric 事件，供前端直接画曲线而不必自己解析。

    两处 json.dumps 都带 allow_nan=False（与 kev.console.db 的序列化语义一致）：
    SSE 帧是给浏览器 EventSource 吃的，而裸 `NaN` 不是合法 JSON，前端会表现为
    「曲线莫名断了」而不是「训练崩了」—— 后者才是我们想要的失败方式。
    """
    frame = (f"id: {event['id']}\nevent: log\n"
             f"data: {json.dumps(event, ensure_ascii=False, allow_nan=False)}\n\n")
    if metric is not None:
        frame += f"event: metric\ndata: {json.dumps(metric, allow_nan=False)}\n\n"
    return frame


class MetricBuffer:
    """内存里的最近 N 个指标点。溢出时记 dropped，前端要如实提示「仅显示最近 N 点」。"""

    def __init__(self, limit: int = DEFAULT_BUFFER):
        self._limit = limit
        self._points = deque(maxlen=limit)
        self._dropped = 0

    def push(self, point: dict) -> None:
        if len(self._points) == self._limit:
            self._dropped += 1
        self._points.append(point)

    def points(self) -> list[dict]:
        return list(self._points)

    def dropped(self) -> int:
        return self._dropped

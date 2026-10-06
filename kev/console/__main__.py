"""python -m kev.console —— 启动编排服务.

只绑 127.0.0.1：本地单用户、无鉴权（spec §12）。Windows 侧的 playground 通过
WSL2 的 localhostForwarding 访问这个端口.

编排服务跑在 WSL2 内（与 torch 同环境）—— 这样拉起 kev.train 就是普通本地子进程，
不需要在 Windows 上 spawn('wsl.exe', ...) 去处理路径转义、shell 引号与 stdio 转发。
"""
import os

import uvicorn

from . import paths
from .app import DB_ENV, create_app

DEFAULT_PORT = 8790


def main() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    paths.JOB_LOGS.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(), host="0.0.0.0",
                port=int(os.environ.get("KEV_CONSOLE_PORT", DEFAULT_PORT)), log_level="info")


if __name__ == "__main__":
    main()

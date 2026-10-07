"""python -m kev.console —— 启动编排服务 / 初始化数据库.

只绑 127.0.0.1：本地单用户、无鉴权（spec §12）。Windows 侧的 playground 通过
WSL2 的 localhostForwarding 访问这个端口.

编排服务跑在 WSL2 内（与 torch 同环境）—— 这样拉起 kev.train 就是普通本地子进程，
不需要在 Windows 上 spawn('wsl.exe', ...) 去处理路径转义、shell 引号与 stdio 转发。

子命令：
  serve    默认；启动 FastAPI（uvicorn）。后端由 KEV_CONSOLE_DB_BACKEND 决定。
  initdb   按当前后端执行 deploy/console/schema.<backend>.sql 建表 + 初始数据；
           文件缺失时回退到 Store() 的建库 + 种子逻辑。
"""
import argparse
import os
import sys
from pathlib import Path

import sqlalchemy as sa
import uvicorn
from sqlalchemy import text

from . import paths
from .app import create_app
from .db import backend_url

DEFAULT_PORT = 8790


def _initdb() -> None:
    backend = os.environ.get("KEV_CONSOLE_DB_BACKEND", "sqlite").lower()
    dialect = "postgres" if backend in ("postgres", "postgresql") else "sqlite"
    schema_file = ROOT / "deploy" / "console" / f"schema.{dialect}.sql"
    if not schema_file.is_file():
        # 回退：直接建库 + 种子（两种后端都支持）
        from .db import Store
        Store()
        print(f"initialized schema via Store() (no {schema_file.name} found)")
        return
    engine = sa.create_engine(backend_url())
    sql = schema_file.read_text(encoding="utf-8")
    # 用 exec_driver_sql（原始驱动 SQL）逐条执行：spec_json 内容里含 ":0.5" 这类子串，
    # SQLAlchemy 的 text() 会误当成命名绑定参数；而 sqlite/postgres 的驱动在单引号字符串
    # 内不会把 :name 当作参数，故原始执行可正确落库。
    with engine.begin() as conn:
        for stmt in sql.split(";"):
            stripped = stmt.strip()
            if stripped:
                conn.exec_driver_sql(stripped)
    print(f"initialized {dialect} schema from {schema_file}")


def main() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    parser = argparse.ArgumentParser(prog="kev.console")
    parser.add_argument("command", nargs="?", default="serve",
                        choices=("serve", "initdb"), help="serve=启动服务（默认），initdb=初始化数据库")
    args = parser.parse_args()

    if args.command == "initdb":
        paths.JOB_LOGS.mkdir(parents=True, exist_ok=True)
        _initdb()
        return

    paths.JOB_LOGS.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(), host="0.0.0.0",
                port=int(os.environ.get("KEV_CONSOLE_PORT", DEFAULT_PORT)), log_level="info")


ROOT = Path(__file__).resolve().parents[2]


if __name__ == "__main__":
    main()

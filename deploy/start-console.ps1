# 在宿主机（WSL2 / Windows）启动 kev.console，使用现成的 PostgreSQL 作为后端。
# 控制台是 playground 模型调用的必需中间人（不是 2 个容器镜像之一）。
# 容器内的 playground 通过 host.docker.internal:8790 访问它。
$env:KEV_CONSOLE_DB_BACKEND = "postgres"
$env:KEV_CONSOLE_DB_HOST     = "localhost"
$env:KEV_CONSOLE_DB_PORT     = "5432"
$env:KEV_CONSOLE_DB_USER     = "ai-user"
$env:KEV_CONSOLE_DB_PASSWORD = "admin123"
$env:KEV_CONSOLE_DB_NAME     = "kev_db"
Set-Location $PSScriptRoot/..
uv run python -m kev.console

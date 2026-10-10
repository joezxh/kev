"""`python -m kev.console.daemon_runner` — thin CLI wrapper around DataDaemon.

The master process spawns this entry as a Popen child for each
`distill_daemon` job (see `kev/console/stages/data.py::_distill_daemon`).
We keep the CLI surface tiny so the argv going through LocalExecutor.spawn
is short and easy to read in the job log:

    python -m kev.console.daemon_runner \
        --master-url http://127.0.0.1:8790 \
        --daemon-id <uuid> --job-id <uuid> --log-path <path> \
        --cwd <project root> -- \
        python <SKILL_SCRIPTS>/generate_data.py <spec> --schedule HH:MM ...

Everything after `--` is forwarded to the long-lived child verbatim.

This file is intentionally a one-liner. Anything non-trivial (event proxying,
cancel polling, child lifecycle) lives in `kev/console/data_daemon.py` so it
is unit-testable without spawning a subprocess.
"""
from __future__ import annotations

from .data_daemon import main

if __name__ == "__main__":
    raise SystemExit(main())

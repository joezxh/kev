"""python -m kev.console.generators.engine entry point. Forwards argv into engine.run()."""
from __future__ import annotations

import sys
from .engine import run

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))

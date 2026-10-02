# ============================================================================
# Kev-4B serving image — built from the local source tree (no git clone, no
# external repo dependency). Serve extra = FastAPI + uvicorn + typesafe-sdk;
# base deps pull torch/transformers/peft (the Linux torch wheel bundles CUDA
# 12.x runtime, so GPU works with the NVIDIA container toolkit / Docker Desktop).
#
# The model checkpoint is NOT baked into the image: `--run` resolves either a
# local run directory (mount ./runs to /kev/runs) or a Hub id like
# jaredpalmer/kev-4b (downloaded to the HF cache — mount a volume for it).
# ============================================================================

FROM python:3.13-slim-bookworm

LABEL description="Kev decision model server (kev.serve) for Kev-4B"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /kev

# Install the local package with the serve extra (kev/pyproject.toml)
COPY pyproject.toml README.md LICENSE ./
COPY kev ./kev
RUN pip install --no-cache-dir ".[serve]"

RUN mkdir -p /kev/runs

EXPOSE 8008

# Defaults for kev.serve; overridable at runtime
ENV KEV_RUN=jaredpalmer/kev-4b \
    KEV_DTYPE=bf16 \
    KEV_PREFIX_CACHE=4

# python:3.13-slim has no curl — use urllib; carry the Bearer token so the check
# passes when KEV_API_KEY is set (empty = open server, also 200)
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request,os,sys; req=urllib.request.Request('http://127.0.0.1:8008/v1/models', headers={'Authorization': 'Bearer ' + os.environ.get('KEV_API_KEY','')}); sys.exit(0 if urllib.request.urlopen(req, timeout=5).status==200 else 1)" || exit 1

# --run decides the checkpoint: a local dir (e.g. /kev/runs/<name>) or a Hub id
ENTRYPOINT ["sh", "-c", "exec python -m kev.serve --host 0.0.0.0 --port 8008 --run \"${KEV_RUN}\""]

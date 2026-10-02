# ============================================================================
# Kev Decision Model Serving Dockerfile (Simplified)
# Single-stage build to avoid network issues
# ============================================================================

FROM python:3.13-slim-bookworm

LABEL maintainer="kev-deploy"
LABEL description="Kev-4B Decision Model Server with GPU Support"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装 Python 依赖
RUN pip install --upgrade pip && \
    pip install fastapi>=0.115 typesafe-sdk>=0.6.0 uvicorn>=0.30 \
                torch>=2.6 transformers>=5.17 peft>=0.21 accelerate>=1.15 \
                datasets>=3.0 pydantic>=2.9

# 创建工作目录
WORKDIR /kev

# 克隆轻量级源码仓库
RUN git clone --depth 1 https://github.com/jaredpalmer/kev.git . || true

# 创建模型缓存目录
RUN mkdir -p /kev/checkpoints /kev/runs

# 暴露服务端口
EXPOSE 8008

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8008/v1/models || exit 1

# 默认环境变量
ENV KEV_MODEL="jaredpalmer/kev-4b" \
    CUDA_VISIBLE_DEVICES="0" \
    KEV_PREFIX_CACHE="4" \
    KEV_DTYPE="bf16"

ENTRYPOINT ["python", "-m", "kev.serve"]
CMD ["--host", "0.0.0.0", "--port", "8008"]

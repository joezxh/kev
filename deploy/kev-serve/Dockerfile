# Kev System One 端点镜像。控制台按 run_matrix 的运行名规范传入 KEV_SERVE_RUN 与 TEMPERATURE。
#
# spec §16 开放问题 1 的默认值：**先只提供 GPU 镜像** —— kev/serve.py:332 的服务默认值
# 在非 CPU 设备上开 bf16 + CUDA graphs，而 CPU 路径未在 0.8B 规模上验证过。
#
# 医疗模型**禁止** --public 发布，所以权重不烘进镜像：运行时由编排层挂载
# /srv/kev/runs，或由 kev.checkpoint 按 KEV_SERVE_RUN 从私有库解析。
ARG CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
FROM ${CUDA_IMAGE}

ARG KEV_SERVE_RUN=smoke
ARG TEMPERATURE=1.0
ENV KEV_SERVE_RUN=${KEV_SERVE_RUN} \
    TEMPERATURE=${TEMPERATURE} \
    PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    HF_ENDPOINT=${HF_ENDPOINT:-https://hf-mirror.com}

WORKDIR /srv/kev
COPY . /srv/kev

RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" "typesafe-sdk>=0.6.0" \
 && pip install --no-cache-dir "torch>=2.6,<2.9" "transformers>=5.17,<6" "peft>=0.21"

# 权重与 checkpoint 由编排层挂载或按 KEV_SERVE_RUN 解析；HF 缓存单独挂一层。
VOLUME ["/srv/kev/runs", "/root/.cache/huggingface"]
EXPOSE 8008

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8008/v1/models').status==200 else 1)"

# 温度由编排层从 calibration.json 拟合后显式传入；**不读 KEV_TEMPERATURE**
# （tests/test_conventions.py 规定它只能经 kev.checkpoint.LoadOptions.from_env）。
CMD ["sh", "-c", "python -m kev.serve --run runs/${KEV_SERVE_RUN} --port 8008 --temperature ${TEMPERATURE}"]

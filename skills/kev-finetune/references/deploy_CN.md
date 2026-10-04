<p align="center">
  <a href="./deploy_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./deploy.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 服务、接线、发布与拆除

[← 返回中文首页](../README_CN.md) · 索引：[数据格式](./data-format_CN.md) · [数据获取](./data-generation_CN.md) · [读数与迭代](./hill-climbing_CN.md)

## Modal 端点

```bash
modal secret create kev-serve-key KEV_API_KEY=$(openssl rand -hex 24)
KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=x-v1 modal deploy scripts/kev_modal.py
```

`KEV_SERVE_RUN` 是 `kev-finetune-runs` 卷上的一个运行名，或者一个 Hub id（`jaredpalmer/kev-4b`、`you/kev-4b-x`、
`repo@tag`）。部署会打印 URL，格式为 `https://<workspace>--kev-finetune-api.modal.run`。容器只加载一次
checkpoint（LoRA 被折进 bf16 权重，增量用 fp32 计算，拟合好的温度会自动应用），
预热融合 kernel 并捕获 CUDA graph（一个 6 问题的 Kev-4B 请求：在 H100 上约 17 ms，不捕获则约 130 ms），
最多并发 8 个请求，空闲 5 分钟后缩放到零。4B 空闲后的冷启动是 1-2 分钟；
部署时设置 `KEV_SERVE_MIN_CONTAINERS=1` 可以保持一个温热容器（L4 上约 $0.80/小时）。

| 基座 | `KEV_SERVE_GPU` |
| --- | --- |
| kev-0.8b、kev-4b | `L4`（默认；最便宜，但在 4B 有负载时会算力吃紧：那里用 `L40S`） |
| kev-9b | `H100` 或 `L40S`（bf16 下约 17 GB 显存） |

不带 `KEV_SERVE_SECRET` 时端点是公开的（URL 本身就是唯一的秘密）；带上它，则请求需要
`Authorization: Bearer <KEV_API_KEY>`，其余一律返回 401。用另一个 `KEV_SERVE_RUN` 重新部署
会在同一个 URL 后面替换模型。想同时跑多个模型：`KEV_APP_NAME=kev-support modal deploy ...`（新 app，
新的 URL 标签）。

## 接入用户代码

该端点讲的是 TypeSafe 的 System One 协议，所以要改的只是 base URL 和 key，请求形状不变。
`instructions` 和选项名必须与模型训练时用的完全一致。

TypeSafe Python SDK：

```python
client = TypeSafeClient(api_key=KEV_KEY, base_url=KEV_URL, model="kev-latest")   # 原来是：TypeSafeClient(api_key=TYPESAFE_KEY)
```

AI SDK / 裸 HTTP（AI SDK 的 `experimental_evaluate` 面向的是网关，所以那些调用要改成 fetch）：

```ts
const r = await fetch(`${KEV_URL}/v1/systemone`, { method: "POST",
  headers: { "content-type": "application/json", authorization: `Bearer ${KEV_KEY}` },
  body: JSON.stringify({ state, model: "kev-latest", questions }) });   // 问题用 type "noul"，不是 "boolean"
```

curl：

```bash
curl -s $KEV_URL/v1/systemone -H "authorization: Bearer $KEV_KEY" -H 'content-type: application/json' -d '{
  "state": "...", "model": "kev-latest",
  "questions": {"department": {"type": "choice", "instructions": "...", "criteria": {"returns": "...", "shipping": "..."}},
                "escalate":   {"type": "noul",   "instructions": "..."}}}'
```

响应中每个问题都有 `probabilities`（已校准）、`choice` / `noul` / `score`（期望等级）、`confidence`、
`usage`、`latency_ms`。`GET /v1/models` 会报告所服务的运行、基座和温度。

在切换流量之前，先确认线上数字与离线打分一致：
`KEV_REMOTE_API_KEY=$KEV_KEY modal run scripts/kev_modal.py::evaluate --data data/x --name x-v1-served --remote $KEV_URL`。

### 阈值

要做阈值处理的是校准后的 `confidence`（choice）或 noul 概率。`result.json` 里的
`development.calibrated.coverage_at_5pct_error` 是通过 5% 误差预算的那部分流量占比，而
`development.calibrated.selective["0.5"|"0.8"].confidence_cutoff` 则是 50% / 80% 覆盖率下的截断点。
低于截断点的流量路由给人。阈值和温度都是按 checkpoint 而定的：每次重新训练后都要重新读一次。

## 改为在本地运行

```bash
modal run scripts/kev_modal.py::pull --name x-v1 --checkpoint
git clone https://github.com/jaredpalmer/kev.git && cd kev && uv sync --extra serve
KEV_DTYPE=bf16 uv run --extra serve python -m kev.serve --run ../runs/x-v1/checkpoint --port 8009
```

同一套 API 跑在 `127.0.0.1:8009` 上。Qwen3.5 基座在 Apple Silicon 上很慢（MPS 没有 DeltaNet kernel，
4B 每个请求约 0.8 s）；有 CUDA 的机器就很快。本仓库的 playground 可以直接对着这个服务器用。

## 发布（可选，默认私有）

只有在用户希望把权重放到 Modal 之外时才需要。Hub 仓库默认私有，除非加 `--public`。

```bash
modal secret create huggingface-secret HF_TOKEN=hf_...            # 一个 write token
KEV_HF_SECRET=huggingface-secret modal run scripts/kev_modal.py::publish --name x-v1 --repo you/kev-4b-x
```

会上传 adapter、`head.pt`（含温度）、tokenizer、`result.json`、`training_config.json`、`train.log`
以及一张自动生成的卡片（`--card your.md` 可替换它）。之后该 repo id 在任何能接受 Kev checkpoint 的地方都能用：
`KEV_SERVE_RUN=you/kev-4b-x`、`kev.serve --run you/kev-4b-x`、下一轮差分用 `--init-from you/kev-4b-x`。
删除方式：`hf repo delete you/kev-4b-x`。

## 拆除

| 命令 | 移除什么 |
| --- | --- |
| `modal run scripts/kev_modal.py::teardown --run x-v1 --yes` | 单次运行：权重、报告、上传的数据（`--run a,b` 可指定多个） |
| `modal run scripts/kev_modal.py::teardown --endpoint` | 已部署的 app：URL 不再响应，各次运行保留 |
| `modal run scripts/kev_modal.py::teardown --everything --yes` | app 以及 `kev-finetune-runs` 卷 |
| `... --everything --cache --yes` | 连共享的 `kev-hf-cache`（基座权重；下次运行会重新下载）也一并删除 |

等价的手工命令：`modal app stop kev-finetune`、`modal volume delete kev-finetune-runs --yes`、
`modal secret delete kev-serve-key`。脚本永远不会删除 secret。本地清理：`rm -rf runs/ data/`。
空闲的已部署端点不花钱；而卷要按 Modal 的存储费率计费，取决于其上的 checkpoint
（每个 4B 差分约 0.3 GB）。

---

[← 返回中文首页](../README_CN.md) · 英文原文：[deploy.md](./deploy.md)

# Kev-4B 本地部署推理范例（中文问答）

这些范例面向**本地已部署**的 Kev-4B 服务（`kev.serve`，本地 run 模式
`KEV_RUN=/kev/runs/kev-4b-local`），演示 TypeSafe *System One* 协议
（`POST /v1/systemone`）在**中文输入**下的真实输入输出。

> 协议与问题类型定义在 `skills/kev-deploy/SKILL.md`。
> 服务地址：`http://localhost:8008`，鉴权：`Authorization: Bearer <KEV_API_KEY>`
> （将 `<KEV_API_KEY>` 替换为部署时生成的密钥）。

---

## 公共请求结构

每个请求体包含三段：

- `state`：模型要理解的输入文本（如一段中文客户投诉）。
- `model`：固定为 `kev-latest`（指向本地 checkpoint）。
- `questions`：一组**带类型**的问题，模型不做文本生成，只对每题输出结构化判断。

本批范例使用的三类问题（后续各例均复用此结构）：

```json
{
  "department": {
    "type": "choice",
    "instructions": "这个问题应该由哪个团队处理？",
    "criteria": {
      "returns": "退换货、退款、错发或破损商品",
      "shipping": "配送状态、延误、丢件",
      "billing": "扣款、账单、支付问题"
    }
  },
  "escalate": {
    "type": "noul",
    "instructions": "这件事需要紧急人工介入吗？"
  },
  "frustration": {
    "type": "score",
    "instructions": "这位客户的情绪有多激动？",
    "criteria": ["平静", "不满", "非常愤怒"]
  }
}
```

问题类型语义（`SKILL.md`）：

| 类型 | 含义 | 返回字段 |
|------|------|----------|
| `choice` | 在命名选项里选一 | `choice` + `probabilities` + `confidence` |
| `noul` | yes/no 概率 | `noul`（0–1） |
| `score` | 在有序等级上打分 | `score` + `legend` + `probabilities` + `confidence` |

> 注意：问题里的 `type` 字段（`choice`/`noul`/`score`）是协议固定值，必须保留英文；
> 而 `instructions`（问法）与 `criteria`（选项/等级文案）可自由使用中文，响应会按中文键返回。

通用 curl 模板：

```bash
curl -H "Authorization: Bearer <KEV_API_KEY>" \
     -H 'content-type: application/json' \
     -d '{ "state": "<中文STATE>", "model": "kev-latest", "questions": { ... } }' \
     http://localhost:8008/v1/systemone
```

---

## 范例 1 — 混合诉求工单（晚到 + 错码 + 双扣款）

### 请求
```json
{
  "state": "鞋子晚了两周才送到，而且尺码还发错了。另外我发现信用卡被扣了两次款。",
  "model": "kev-latest",
  "questions": { "<同上公共结构>" }
}
```

### 返回
```json
{
  "model": "kev-latest",
  "answers": {
    "department": {"type": "choice", "choice": "returns", "confidence": 0.3815,
                   "probabilities": {"returns": 0.5877, "shipping": 0.1796, "billing": 0.2328}},
    "escalate":   {"type": "noul", "noul": 0.7643},
    "frustration":{"type": "score", "score": 1.1957,
                   "legend": {"0": "平静", "1": "不满", "2": "非常愤怒"},
                   "probabilities": {"0": 0.0571, "1": 0.6902, "2": 0.2527}, "confidence": 0.5353}
  },
  "usage": {"input_tokens": 102, "output_tokens": 213},
  "latency_ms": 3193.1
}
```

---

## 范例 2 — 纯账单双扣款

### 请求
```json
{ "state": "我这个月的订阅被扣了两次款，两份收据都和我的套餐对不上。请把多扣的费用退给我。",
  "model": "kev-latest", "questions": { "<同上公共结构>" } }
```

### 返回
```json
{
  "model": "kev-latest",
  "answers": {
    "department": {"type": "choice", "choice": "billing", "confidence": 0.9464,
                   "probabilities": {"returns": 0.0337, "shipping": 0.0021, "billing": 0.9643}},
    "escalate":   {"type": "noul", "noul": 0.7498},
    "frustration":{"type": "score", "score": 0.9526,
                   "legend": {"0": "平静", "1": "不满", "2": "非常愤怒"},
                   "probabilities": {"0": 0.1681, "1": 0.7113, "2": 0.1207}, "confidence": 0.5669}
  },
  "usage": {"input_tokens": 105, "output_tokens": 213},
  "latency_ms": 3094.8
}
```

---

## 范例 3 — 物流丢件

### 请求
```json
{ "state": "我的包裹已经卡在运输途中 10 天了，物流信息一直没更新。我的订单 8842 到底去哪了？",
  "model": "kev-latest", "questions": { "<同上公共结构>" } }
```

### 返回
```json
{
  "model": "kev-latest",
  "answers": {
    "department": {"type": "choice", "choice": "shipping", "confidence": 0.9454,
                   "probabilities": {"returns": 0.0321, "shipping": 0.9636, "billing": 0.0043}},
    "escalate":   {"type": "noul", "noul": 0.8679},
    "frustration":{"type": "score", "score": 1.2291,
                   "legend": {"0": "平静", "1": "不满", "2": "非常愤怒"},
                   "probabilities": {"0": 0.0576, "1": 0.6557, "2": 0.2867}, "confidence": 0.4836}
  },
  "usage": {"input_tokens": 110, "output_tokens": 213},
  "latency_ms": 1366.1
}
```

---

## 范例 4 — 冷静客诉（改地址）

### 请求
```json
{ "state": "你好，我想在订单 5521 发货前把收货地址改成橡树街 12 号。谢谢！",
  "model": "kev-latest", "questions": { "<同上公共结构>" } }
```

### 返回
```json
{
  "model": "kev-latest",
  "answers": {
    "department": {"type": "choice", "choice": "shipping", "confidence": 0.5887,
                   "probabilities": {"returns": 0.2122, "shipping": 0.7258, "billing": 0.062}},
    "escalate":   {"type": "noul", "noul": 0.5617},
    "frustration":{"type": "score", "score": 0.086,
                   "legend": {"0": "平静", "1": "不满", "2": "非常愤怒"},
                   "probabilities": {"0": 0.9205, "1": 0.0731, "2": 0.0065}, "confidence": 0.871}
  },
  "usage": {"input_tokens": 109, "output_tokens": 210},
  "latency_ms": 2994.0
}
```

---

## 范例 5 — 重发范例 2（相同 state，验证可复现性）

与范例 2 的 `state` / `questions` 完全一致。

### 返回
```json
{
  "model": "kev-latest",
  "answers": {
    "department": {"type": "choice", "choice": "billing", "confidence": 0.9464,
                   "probabilities": {"returns": 0.0337, "shipping": 0.0021, "billing": 0.9643}},
    "escalate":   {"type": "noul", "noul": 0.7498},
    "frustration":{"type": "score", "score": 0.9526,
                   "legend": {"0": "平静", "1": "不满", "2": "非常愤怒"},
                   "probabilities": {"0": 0.1681, "1": 0.7113, "2": 0.1207}, "confidence": 0.5669}
  },
  "usage": {"input_tokens": 105, "output_tokens": 213},
  "latency_ms": 2954.6
}
```

---

## 范例 6 — 重发范例 4（相同 state，验证可复现性）

与范例 4 的 `state` / `questions` 完全一致。

### 返回
```json
{
  "model": "kev-latest",
  "answers": {
    "department": {"type": "choice", "choice": "shipping", "confidence": 0.5887,
                   "probabilities": {"returns": 0.2122, "shipping": 0.7258, "billing": 0.062}},
    "escalate":   {"type": "noul", "noul": 0.5617},
    "frustration":{"type": "score", "score": 0.086,
                   "legend": {"0": "平静", "1": "不满", "2": "非常愤怒"},
                   "probabilities": {"0": 0.9205, "1": 0.0731, "2": 0.0065}, "confidence": 0.871}
  },
  "usage": {"input_tokens": 109, "output_tokens": 210},
  "latency_ms": 2996.3
}
```

---

## 结果对比

| 例 | state 主题 | department（choice 最高项） | escalate（noul） | frustration（score） | latency_ms |
|----|-----------|----------------------------|------------------|----------------------|------------|
| 1 | 晚到+错码+双扣款 | returns 58.8%（conf 0.38） | 0.764 | 1.20（不满） | 3193 |
| 2 | 纯账单双扣款 | billing 96.4%（conf 0.95） | 0.750 | 0.95（不满偏平静） | 3095 |
| 3 | 物流丢件 10 天 | shipping 96.4%（conf 0.95） | 0.868 | 1.23（不满） | 1366 |
| 4 | 冷静改地址 | shipping 72.6%（conf 0.59） | 0.562 | 0.09（平静） | 2994 |
| 5 | = 例2 重发 | billing 96.4%（conf 0.95） | 0.750 | 0.95 | 2955 |
| 6 | = 例4 重发 | shipping 72.6%（conf 0.59） | 0.562 | 0.09 | 2996 |

## 观察

1. **中文输入下路由依然合理**：单一诉求时路由又准又自信（例2 billing 96.4%、例3 shipping 96.4%）；混合诉求时（例1）模型在 returns/shipping/billing 间权衡，returns 最高 58.8%（置信度 0.38，低于单诉求场景）——与英文版结论一致：给 Kev 的 `state` 越聚焦，路由越准。

2. **frustration（score）校准良好**：冷静请求（例4）score 0.09 → 平静 92%；投诉类 0.95–1.23 → 不满为主，概率分布合理。

3. **escalate（noul）整体偏高但有分寸**：全部场景落在 0.56–0.87。相比英文版（0.70–0.80），中文冷静客诉（例4）降到 **0.562**， benign 请求误判率更低；物流丢件（例3）升到 0.868，符合"10 天无更新"更紧急的直觉。说明该头在中文下仍有合理判别力，若作自动升级闸门仍可抬高阈值（如 >0.85）。

4. **延迟**：本地约 1.4–3.2s/请求（RTX 5070 Ti 笔记本 GPU）。例3 仅 1366ms，明显快于其他——该 shape 的 CUDA graph 已在前序请求中捕获，复用后变快，印证 `SKILL.md` 关于"首 shape 慢、后续快"的描述。`SKILL.md` 给出的 H100 ~42ms 需数据中心 GPU + 热重复请求。

5. **推理可复现**：例5 与例2、例6 与例4 输出逐位一致，确认中文输入下推理确定性不变。

6. **中文可用性结论**：Kev-4B 在中文 state / 中文问题下可正常工作（选项与等级以中文键返回），路由与情绪判断质量与英文版接近。若要在中文工单上进一步提升准确率，建议用 `kev-finetune` skill 在中文标注数据上微调。

---

## 边界范例（异常与不同等级数）

### 边界 A — 超长 state 触发 422

服务端在 `admit` 阶段对 `state` 做词元化并计数，超过 `SERVE_MAX_STATE`（默认 65,536 token）即拒绝，返回 **422** 而非截断。注意限制单位是 **token 而非字符**：中文约 0.5 token/字，约 13 万字才会触顶。

请求（`state` 为约 15.5 万字符、词元化后 **88,001 token** 的中文长文档，正文省略）：

```bash
curl -H "Authorization: Bearer <KEV_API_KEY>" -H 'content-type: application/json' \
  -d '{ "state": "<约 15.5 万字符的中文长文档，重复的企业投诉文本…>",
        "model": "kev-latest",
        "questions": { "department": {"type":"choice","instructions":"这个问题应该由哪个团队处理？","criteria":{"returns":"退换货","shipping":"配送","billing":"账单"}} } }' \
  http://localhost:8008/v1/systemone
```

返回（**HTTP 422**）：

```json
{
  "detail": "state is 88,001 tokens, over the 65,536-token limit (the <state> token included): shorten the document or split it across requests; or start the server with KEV_TRUNCATE_STATES=1 to read only its first 65,536 tokens (responses then say truncated: true)"
}
```

要点：

- 拒绝发生在推理之前，因此**很快返回**（若 state 没超 65536 但实际超过 GPU 显存，才会进入前向计算并 OOM → 500，那是一种服务端错误而非预期的 422）。
- 错误体给出**实际 token 数与上限**，并提示 `KEV_TRUNCATE_STATES=1` 可改为截断模式（此后响应带 `truncated: true` 与 `usage.state_tokens` / `state_tokens_used`）。
- state 即便在 8,192（本机 Kev-4B 的验证上下文）与 65,536 之间也不会被 422 拒绝，但准确率会下降——建议客户端自行限制更短的长度，而不是依赖服务端上限。

### 边界 B — `score` 仅 2 个等级

`criteria` 传 `["低","高"]` 两级，`legend` 只有 0/1：

```json
{
  "model": "kev-latest",
  "answers": {
    "escalate":   {"type": "noul", "noul": 0.8854},
    "frustration":{"type": "score", "score": 0.9842,
                   "legend": {"0": "低", "1": "高"},
                   "probabilities": {"0": 0.0158, "1": 0.9842}, "confidence": 0.9685},
    "department": {"type": "choice", "choice": "shipping", "confidence": 0.8759,
                   "probabilities": {"billing": 0.0141, "shipping": 0.9173, "returns": 0.0686}}
  },
  "usage": {"input_tokens": 83, "output_tokens": 167},
  "latency_ms": 2553.1
}
```

### 边界 C — `score` 取 5 个等级

`criteria` 传 `["很低","低","中","高","很高"]` 五级，`legend` 为 0–4：

```json
{
  "model": "kev-latest",
  "answers": {
    "escalate":   {"type": "noul", "noul": 0.7643},
    "frustration":{"type": "score", "score": 2.2374,
                   "legend": {"0": "很低", "1": "低", "2": "中", "3": "高", "4": "很高"},
                   "probabilities": {"0": 0.2107, "1": 0.0827, "2": 0.1955, "3": 0.2805, "4": 0.2305},
                   "confidence": 0.0},
    "department": {"type": "choice", "choice": "returns", "confidence": 0.5427,
                   "probabilities": {"billing": 0.0915, "shipping": 0.2134, "returns": 0.6951}}
  },
  "usage": {"input_tokens": 105, "output_tokens": 236},
  "latency_ms": 3730.1
}
```

观察：`score` 支持任意 1–255 个等级；`score` 字段始终是从 **0 起**的等级均值索引，`legend` 键为字符串形式的等级序号。边界 C 的概率分布较平，`confidence` 按公式 `1 − E|level−mode| / D`（D 为均匀分布在各等级上的平均离中距，五级时 D=0.8）得到 **0.0**，符合预期——分布越分散，置信度越低。

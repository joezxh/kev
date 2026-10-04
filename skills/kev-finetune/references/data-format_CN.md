<p align="center">
  <a href="./data-format_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./data-format.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 带标签的记录格式

[← 返回中文首页](../README_CN.md) · 索引：[数据获取](./data-generation_CN.md) · [读数与迭代](./hill-climbing_CN.md) · [部署](./deploy_CN.md)

每行一个 JSON 对象。每条记录都是一个 System One 请求（`state` + `questions`），并且每个问题都带一个 `label`。
这与已部署端点所接受的形状相同，只是去掉了标签——所以你训练用的东西，就是你服务时用的东西。

```json
{"state": "Order 5521 arrived two weeks late and now I see two charges on my card. Fix this today.",
 "questions": {
   "department":  {"type": "choice", "instructions": "Which team should handle this ticket first?",
                   "criteria": {"returns": "Exchanges, refunds, wrong or damaged items",
                                "shipping": "Delivery status, delays, lost packages",
                                "billing": "Charges, invoices, payment problems"},
                   "label": "billing"},
   "escalate":    {"type": "noul", "instructions": "Does this need urgent attention from a human within the hour?",
                   "label": true},
   "frustration": {"type": "score", "instructions": "How frustrated is the customer?",
                   "criteria": ["Calm or neutral", "Annoyed", "Angry or threatening to leave"],
                   "label": 2}}}
```

## 字段

| 字段 | 规则 |
| --- | --- |
| `state` | 一个字符串，或一个 JSON 对象 / 数组（会渲染成 `key: value` 形式的行；字段名对模型可见）。约不超过 1400 个字符（384 tokens）。非空。 |
| `questions` | 以问题 id 为键的对象。1 个或更多。各问题只看得到 `state`，彼此看不到。 |
| `type` | `noul`（是/否）、`choice`（具名选项）、`score`（有序等级）。 |
| `instructions` | 问题正文。必填。就按端点将来会怎么问来写。 |
| `criteria` | `choice`：对象 `{名称: 描述或 null}`，1-255 个选项，模型返回的就是这些名称。`score`：2-255 条等级描述的列表，由低到高。`noul`：可选的 `{"true": ..., "false": ...}` 描述。 |
| `label` | `choice`：一个选项名。`noul`：`true` 或 `false`。`score`：等级下标，从 0 开始的整数。 |
| `target`（可选） | 软标签：`{选项键: 权重}`；键是选项名 / `"true"`、`"false"` / 以字符串表示的等级下标。对那些被刻意抽掉了证据的记录，用 `{"false": 0.5, "true": 0.5}`，以此教会模型"没有证据，就没有把握"。 |

整个请求（`state` + 所有问题 + 选项）必须装进 2048 tokens；每个问题分支 1024 tokens。放不下的记录会
被训练器丢弃并打印一个数量；`kev_modal.py::validate` 会提前把它们报出来。

## 好的训练数据长什么样

- **与线上完全相同的问题。** `instructions` 和选项名要与你在服务时要发送的完全一致。
  微调绑定的正是这些确切的字符串；服务时改用近义表述仍然有效，但收益更小。
- **每个选项都均衡。** 每个选项至少在 5% 的情况下是正确的，理想情况下大致相等。
  `generate_data.py` 会自动朝这个目标生成；`split_data.py` 在做不到时会给出警告。
- **难负例。** 提到两个选项、但规则只选其中一个的 state；有礼貌的愤怒；短输入与长输入。
  把规则写进 spec 的 `guidance`，生成器才能给出一致的标注。
- **彼此不同的 state。** 相同 state 配不同 label 的记录会作为冲突被丢弃。近似重复会抬高分数；
  `split_data.py` 只对完全相同的做分组，所以要在名称、数字和措辞上做出变化。
- **一条记录多个问题**没问题，而且更便宜（一个 state，多个 label），只要每个 label 都正确。
- **先用真实样例。** 如果你有 50 个真实的带标签案例，把它们作为生成器的 `--examples`，
  并另外保留一个只含真实数据的开发集文件用于最终检查。

## 规模

| 记录数 | 用途 |
| --- | --- |
| 100-200 | 流水线的冒烟测试；分数很嘈杂（开发集约 30 条记录） |
| 300-600 | 第一次正式跑；bootstrap 的 CI 开始能把 baseline 与微调模型区分开 |
| 1000-3000 | 生产模型；可以考虑 `--epochs 2` |

默认划分是 70 / 15 / 15（`--calibration`、`--development`）。calibration 和 development 各自至少保留
40 条记录；低于这个数，温度拟合和各项分数都会不稳定。

## 转换已有的标签

把每一行源数据映射成一条记录。让模型的 `instructions` 和 `criteria` 在所有记录之间保持不变
（放进一个小的 Python dict 里复用）。把标签转成所需类型：路由名 -> `choice` 选项名，标志位 ->
`noul` 布尔值，评分 -> `score` 下标（如果你的量表从 1 开始就减 1）。然后运行
`python3 scripts/split_data.py yours.jsonl`，在划分之前先做校验。

---

[← 返回中文首页](../README_CN.md) · 英文原文：[data-format.md](./data-format.md)

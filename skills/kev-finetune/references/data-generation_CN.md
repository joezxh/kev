<p align="center">
  <a href="./data-generation_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./data-generation.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 获取带标签的数据

[← 返回中文首页](../README_CN.md) · 索引：[数据格式](./data-format_CN.md) · [读数与迭代](./hill-climbing_CN.md) · [部署](./deploy_CN.md)

四个来源，按优劣排序。混着用：真实行用来度量，合成行用来训练。

## 1. 已有标签（`convert_data.py`）

任何"旁边就放着一条人工决策"的输入文本：带路由结果的工单导出、带裁决结果的审核队列、
带线索评分的 CRM、某个人填好的表格。

```bash
python3 scripts/convert_data.py workload.json tickets.csv \
    --state subject,body \                        # 一列 = 字符串 state；多列 = 对象 state {列: 值}
    --label department=team --label escalate=was_escalated --label priority=prio_1_to_3 \
    --map department="Billing Ops:billing,Ship:shipping" --score-offset 1 \
    --out data/support.real.jsonl
```

列名默认就是问题 id。标签按不区分大小写的方式与选项名或选项描述匹配；
yes/no/1/0 会变成 noul 布尔值；score 标签可以是下标、从 1 开始的评分（`--score-offset 1`）或等级文本。
被跳过的行会按原因计数并给出一个示例值，所以漏掉 `--map` 很容易被发现。JSONL 输入支持点号
路径（`--label team=meta.team`）。

然后决定这些真实行拿来做什么：

- **很少（< 200）：** 把它们当作量尺。`split_data.py generated.jsonl --out data/x --holdout data/x.real.jsonl`
  会把真实行对半分进 calibration 和 development，绝不进入 train，并丢弃与它们共享
  state 的生成行。同时把它们作为 `--examples` 传给生成器，好让合成行贴合它们的风格。
- **很多（1000+）：** 你可能根本不需要合成数据。`split_data.py real.jsonl --out data/x` 然后训练即可。
  只为补上真实数据很少标注的选项而生成一点。

## 2. 让 LLM 来写这些记录（`generate_data.py`）

```bash
export KEV_GEN_API_KEY=...                           # 或用 OPENAI_API_KEY；设置 AI_GATEWAY_API_KEY 会自动把 base URL 切到网关
export KEV_GEN_BASE_URL=https://api.openai.com/v1    # 也可以是 https://ai-gateway.vercel.sh/v1、http://localhost:11434/v1（Ollama）、任何 OpenAI 兼容的 URL
python3 scripts/generate_data.py workload.json --n 1000 --out data/x.jsonl --model gpt-4.1-mini --examples data/x.real.jsonl
```

每次调用索取一批 20 条记录，并按文件中已有的内容计算每个问题的标注目标，
因此输出在每个选项上是均衡的；state 会去重；文件随着各批到达而追加（用更大的
`--n` 重跑即可补足）。成本：用 gpt-4.1-mini 每 1000 条记录约 $0.25；更强的模型（gpt-4.1、claude-sonnet）
对含糊case的标注更一致，在最终数据集上值得用。

让生成数据变好的是 spec 本身：

- `guidance`：一个谨慎的人会套用的规则，包括如何处理含糊情形（"一次既迟到又要求退款的投递，
  在包裹被找到之前算 shipping"）。`errors.jsonl` 里每一种反复出现的错误，都是这里缺的一句话。
- `variety`：需要铺开的维度（语气、长度、语言、有无 id / 日期、含两个问题的输入）。没有它，
  模型会写出同一条工单的 1000 个变体。
- `state_example`：当输入是对象时（`{"subject": ..., "body": ..., "customer_tier": ...}`），给一个例子；
  生成器会复现这个形状，而 Kev 会把字段名渲染进文本。

为 hill-climbing 做定向生成：复制 spec，把 `domain`/`variety` 收窄到失败的那种模式（例如"同时提到两个部门的工单"），
生成 200 条到同一个输出文件里，然后重新划分。

## 3. 你（也就是 agent）来写

`python3 scripts/generate_data.py workload.json --dry-run` 会原样打印脚本将要发送的提示，
包括下一批的标注目标。自己回答它，把 `records` 追加成带标签的 JSONL
（即 `{"state", "questions": {id: {..., "label"}}}` 这个形状，见 [数据格式](./data-format_CN.md)），然后重复。
实用上限约 100 条记录；超过这个数量就改用来源 2。

## 4. 程序化生成

当标签可以由结构化字段上的规则推导出来时（策略窗口、阈值、日期运算），写一个小的
Python 生成器来采样字段并算出标签，再渲染出 state。Kev 自己的对比式策略数据就是这么构建的；
它产出的标注完全一致，并且自带最小对（同一个 state 只改一个事实，label 就翻转），
以此教会模型决策究竟取决于什么。输出同样的 JSONL，然后走 `split_data.py`。

## 需要多少数据

`python3 scripts/plan_size.py workload.json --baseline-acc <实测值或 0.75> --min-gain 0.05` 给出配对比较
在 80% 检验功效下所需的记录数（McNemar 近似；同时也会打印非配对下的界）。典型答案：
每条记录三个问题、目标 5 个点时约 1000 条；目标 10 个点时约 300 条。跑完一轮之后，
`plan_size.py --from-result runs/x/result.json` 会告诉你再加大数据量能否让观测到的增益变得显著，
还是说这个增益小到不值得追。

校准至少需要约 100 个问题才能拟合出稳定的温度；规划器会强制这一点。

## 改造这些脚本

它们很短，只用标准库。常见的改动：

- **别的记录形状**（每条记录多个输入、额外元数据）：把字段加到对象形式的 `state` 里；Kev 会渲染
  它们。`questions` 保持原样。
- **软标签**用于无法判定的情形：不要依赖硬标签，改在问题上设置 `"target": {"true": 0.5, "false": 0.5}`；
  `split_data.py` 接受它，训练器会把它当作一个分布来用。
- **别的生成器 API**（Anthropic Messages、Gemini）：替换 `generate_data.py` 里的 `chat()`（就一个函数，
  用 urllib）；保留 `parse_records`/`to_record`。
- **别的均衡策略**（匹配线上的标签分布而不是均匀分布）：改 `batch_targets`。
- **加权划分**（按某个元数据字段分层）：改 `split()`；它目前按 state 哈希分组。

---

[← 返回中文首页](../README_CN.md) · 英文原文：[data-generation.md](./data-generation.md)

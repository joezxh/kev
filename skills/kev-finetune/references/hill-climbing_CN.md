<p align="center">
  <a href="./hill-climbing_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./hill-climbing.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 读懂这些数字，并改进模型

[← 返回中文首页](../README_CN.md) · 索引：[数据格式](./data-format_CN.md) · [数据获取](./data-generation_CN.md) · [部署](./deploy_CN.md)

`train` 和 `evaluate` 会写出 `runs/<name>/result.json` 并打印一张表。每个指标都由 `kev.metrics.metrics`
在 development 的**问题**维度上计算（一条记录带三个问题，就是三行）。

## 这张表

| 行 | 含义 | 你想要什么 |
| --- | --- | --- |
| accuracy | argmax == label | 越高越好；温度永远不会改变它 |
| brier | 概率误差的平方和 | 越低越好；同时奖励"答对"和"诚实" |
| nll | label 的负对数似然 | 越低越好；温度就是在 calibration 上拟合以最小化它 |
| ece | 期望校准误差（10 个分箱） | 越低越好；校准后应当远低于未校准 |
| confident errors (p>=0.9, wrong) | 所有问题中，以 >= 0.9 的置信度答错的比例 | 越低越好，最好接近 0：这些就是静默失败 |
| coverage at 5% error | 在误差不超过 5% 的前提下、按置信度从高到低能接受的最大问题占比 | 越高越好：这就是能自动化的工作量比例 |
| mean confidence | top 概率的平均值 | 应当与 accuracy 同步；远高于 accuracy 就是过度自信 |

列是成对出现的：`raw` 是模型训练时的原始 logits；`calibrated` 则是把它们除以在 `calibration.jsonl` 上
拟合出的温度。两个模型都在你的 calibration 切片上各自做拟合，所以这个比较是公平的。

为什么这件事对 Jev 而言很重要：托管模型的概率无法针对你的数据重新拟合，所以在你自己的领域上，
它的 `confident errors` 和 `coverage at 5% error` 就是它们本来的样子。而 Kev 的 calibrated 列
是一个你能掌控的数字。

## 怎么决策

1. **这个增益是真的吗？** `result.json` 里的 `bootstrap` 保存了配对 bootstrap 的差值（微调减 baseline），
   覆盖 `acc`、`brier` 和 `ece`，带 95% CI，通过对 development 记录重采样得到。排除零的 CI 才意味着
   在这个开发集上确实发生了变化。只有 60 条 development 记录时，CI 宽度约为 ±7 点，什么都得不出一致结论。
   `python3 scripts/plan_size.py --from-result runs/<name>/result.json` 会把观测到的差值和 CI 换算成
   能定论所需的记录数，或者告诉你这个增益小到不值得靠堆量去追。
2. **它忘了吗？** `regression` 会在 300 条公开的 `decision-v7` development 记录上给两个模型打分（用原始 logits）。
   可以接受大约 2 个 accuracy 点的下降；更多就说明差值漂移了。调低 `--lr`（减半），保留 `--replay 2000`，
   不要加 epoch。
3. **它诚实吗？** 微调模型的校准后 `confident_error_rate` 应当 <= baseline 的，且
   `mean_conf` 与 `acc` 相差在几个点之内。微调后仍然过度自信，通常意味着 epoch 太多，或者
   训练 state 近似重复（模型背下来了）。检查 `split_data.py` 的输出里有没有重复。
4. **按问题看。** `development.per_question` 按问题 id 拆分了指标。一个没有变化的问题，
   要么 baseline 已经解决得很好了，要么你的数据里它的标注前后不一致；打开 `errors.jsonl` 并按它过滤。

## 收益排序：能调的旋钮

1. **更多更好的数据。** 读 `errors.jsonl` 的前 20 行（最有把握的错误）。典型原因与修法：
   - 同一种 state 被标了两种方式 -> 收紧 spec 里的 `guidance`；重新生成；重新划分。
   - 某个选项很少是正确的 -> 提高它的占比（`generate_data.py` 会针对文件中已有的内容重新做均衡；
     只要再要更多 `--n` 即可）。
   - 模型对、标签错 -> 生成器误读了规则；补一条明确的规则和一个参考样例。
   - state 太短、无法判定 -> 在 spec 的 `state` 描述里要求更多细节，或者对真正无法判定的情况
     接受并使用 `target` 软标签。
   把训练集翻倍通常胜过任何超参数调整。
2. **Epoch。** 当你有 1000+ 条记录、且 `train.log` 里的训练损失在第 1 个 epoch 结束时仍在下降时，用 `--epochs 2`。
   之后盯住 `mean_conf` 与 `acc` 的关系。
3. **学习率。** 默认值取自初始化 checkpoint 自身的训练参数（kev-0.8b 为 4e-5，kev-4b 和 kev-9b 为 2e-5），
   上限 5e-5。出现回退就减半；为了某个差值而超过上限则绝不要做。
4. **Replay。** `--replay 2000`（默认）会混入公开记录，让模型保住通用能力。如果你的
   数据量很大（3000+）且训练时间要紧，用 `--replay 500`；`--replay 0` 只用于一次性的实验。
5. **基座规模。** 当两轮数据改动都无法再推动 4B 时，把同样的数据跑在 `jaredpalmer/kev-9b` 上
   （`--init-from jaredpalmer/kev-9b`，约 40 分钟）。用 `KEV_SERVE_GPU=A100-80GB` 或 H100 来服务它。

每次改动都用一个新名字（`support-v2`、`support-v3`），然后比较：
`modal run scripts/kev_modal.py::compare --a support-v2 --b support-v1`（在校准后概率上做配对 bootstrap；
两次运行必须给同一个 `development.jsonl` 打过分）。

## 与 Jev 或其他端点比较

`evaluate --remote <base_url> --remote-model <id>`（key 放在 `KEV_REMOTE_API_KEY`）可以在同一个开发集文件上，
用一个 CPU 容器给任何兼容 System One 的端点打分。把它指向你部署好的 Kev 可以确认线上数字与线下一致；
如果你有 TypeSafe key，也可以指向 Jev。远程返回的概率按原样采用（不做温度拟合），
所以这个比较精确地回答了"服务给你的东西" vs "你校准后的 Kev 给你的东西"。

## 卷上的文件

```
/runs/<name>/data/{train,calibration,development}.jsonl   上传了哪些内容
/runs/<name>/config.json                                  解析后的训练配置、基座、kev commit
/runs/<name>/train.log                                    kev.train 的输出（每 10 步一个 loss）
/runs/<name>/checkpoint/                                  LoRA adapter、head.pt（含温度）、tokenizer
/runs/<name>/{calibration,development}/                   predictions.jsonl、rows.json、report.json
/runs/<name>/baseline/{calibration,development}/          初始化 checkpoint 在同样记录上的结果
/runs/<name>/regression/{finetuned,baseline}/             公开的 decision-v7 样本
/runs/<name>/result.json, errors.jsonl
```

`pull --name <name>` 会把除 checkpoint 和预测转储之外的一切都复制到 `runs/<name>/`；
`pull --checkpoint` 会额外加上权重（几百 MB），用于本地服务。

---

[← 返回中文首页](../README_CN.md) · 英文原文：[hill-climbing.md](./hill-climbing.md)

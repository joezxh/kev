# 蒸馏层

[← 返回主方案](../README.md) · [数据格式](../data-format.md) · [执行手册](../distill.md) · [操作手册入口](../distill.md)

用**蚂蚁百灵**（云端 Open API）作教师、**EasyDistill 2** 作框架，为医疗决策模型产出两轨数据。框架与接入细节见
[双语方案文档](../../sft-distill_CN.md)。

## 一眼看懂：流水线是反的

```
 规则引擎采样 state + 算出标签        零 token、零漂移
          |
          +--> <scenario>.state.jsonl ------> seed_to_kev.py --> Kev 决策记录
          |      （旁路 sidecar：标签的唯一来源）                      |
          |                                                            |--> 训练 Kev-0.8B / 4B
          +--> 渲染成 instruction
                 |
                 +--> <scenario>.seed.jsonl --> EasyDistill --> 百灵写参考回答 --> 裁判 --> 过滤
                                                    |                              |
                                                    +------ 只看见 instruction ----+
                                                                   |
                                                        生成式 SFT 样本 --> 微调医疗助手模型
```

**LLM 全程不碰标签。** 这不是约定，是结构：`seed_to_kev.py` 只读 `state.jsonl`，物理上接触不到 SFT 输出。

## 文件

| 文件 | 作用 |
| --- | --- |
| `make_seeds.py` | 种子生成器。复用 `../generators/gen_*.py` 采样 state 与标签，渲染成 instruction，写出**双文件** |
| `seed_to_kev.py` | 转换器。种子 + 旁路 state -> Kev 记录；`--from-sft` 只做教师/规则一致性对账 |
| `check_volume.py` | 量级保障。分布断言（5% 下限、选项覆盖、记录数）+ token 预算核算 |
| `configs/*.yaml` | 五个场景各一份 EasyDistill 配置 |
| `seeds/README.md` | 种子目录说明 |

## 种子双文件契约

| 文件 | 字段 | 谁读 |
| --- | --- | --- |
| `<scenario>.seed.jsonl` | `id` / `instruction` / `system` | EasyDistill |
| `<scenario>.state.jsonl` | `id` / `scenario` / `state` / `labels` / `soft` | `seed_to_kev.py` |

**为什么分两个文件**：EasyDistill 文档只保证 `id` 是行标识符、`instruction_balance` 会「保留原始字段并新增
`category`」，**不保证每个阶段都透传全部未知字段**。把 `state` / `labels` 放在它触及不到的旁路文件里，
join 就永远不依赖它的字段透传行为。两文件必须同序同长，`id` 是唯一 join 键。

## 五个场景

| 蒸馏场景 | Kev 轨（复用 spec） | SFT 轨 |
| --- | --- | --- |
| `inquiry` | `triage` | 医生式问诊对话 |
| `medication` | `medication-review` | 适应证 / 剂量 / 相互作用 / 禁忌 |
| `diagnosis` | `diagnosis`（新建） | 鉴别诊断 / 依据 / 建议检查 |
| `record-summary` | `record-summary`（新建） | 六要素结构化摘要 |
| `knowledge-qa` | **无** | 医学知识问答（唯一纯生成式轨） |

`knowledge-qa` 没有 Kev 轨的原因：Kev 是 pointer-readout 模型，只在**预声明选项集**上输出概率、一个 token
都不生成，开放式问答在结构上无法成为 Kev 任务。强行做只能退化成 4 选 1 判断题，失去问答轨的全部价值。

## 新增一个场景：3 步

1. 在 `../generators/` 加 `gen_<name>.py`（若该场景的标签可规则派生）并在 `../specs/` 加同名 spec
2. 在 `make_seeds.py` 的 `SCENARIOS` 与 `SYSTEM_PROMPTS` 登记，加 `ASK` 模板
3. 复制一份 `configs/<name>.yaml` 改 `dataset` 路径与 system prompt，并在 `seed_to_kev.py` / `check_volume.py`
   的 `SPEC_FOR` 登记 spec 名

## 凭据

配置里**不写凭据**，只引用环境变量：

```powershell
$env:KEV_GEN_API_KEY = "..."                                  # 你的百灵 API key
$env:KEV_GEN_BASE_URL = "https://<官方 base URL>/v1"          # 以 developer.ant-ling.com 为准
```

> ⚠️ 百灵的 **base URL、模型 id、定价、免费额度、并发上限均未在官网公布**，需以
> `https://developer.ant-ling.com/zh-CN/docs` 为准。第三方博客（2026-02）称 base URL 为
> `api.tbox.cn/api/llm/v1`、免费额度 50 万 tokens/日、并发 1、3 次/分 —— **未经官方确认**，
> 仅供估算量级用，不要当作采购依据。

## 两条合规红线

1. **PHI 脱敏前置**：结构化字段将离开内网（用户已选云端 API），脱敏必须在**进入生成器之前**完成。
   生成器与 EasyDistill 都只接触已脱敏字段。
2. **医疗模型禁止 `--public`**：`publish` 默认私有，不要传 `--public`。优先把 checkpoint 留在
   Modal volume 上。

## 已知上游缺陷（影响 SFT 轨）

`../generators/gen_triage.py` 的 `SYMPTOMS` 表把「儿童咳嗽」「小儿呕吐」等**儿科关键词作为独立词条**，
而年龄采样覆盖 2–78 岁，因此会产出「78 岁 + 小儿呕吐」这类临床上不连贯的记录。实测 500 条 inquiry 种子中
**34 条（6.8%）**存在成人携带儿科关键词的情况。

- 对 **Kev 轨**：标签仍自洽（规则按表索引起作用），只是现实性差，模型可能学到字面捷径
- 对 **SFT 轨**：教师模型会被这种 incoherent state 带偏，产出困惑的参考回答 —— **必须在蒸馏前修掉**

修法是给该词表按年龄加护栏（儿科词条仅当 `age < 14` 时才可被采样），属 `gen_triage.py` 的逻辑变更，
需单独授权后修改上游生成器，本层不擅自动手。

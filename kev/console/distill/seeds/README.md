# 种子目录

种子由 `../make_seeds.py` **生成**，不要手工往这里写文件，也不要把真实产出提交进仓库。

```bash
# 生成五个场景各 500 条种子（Tier A 建议规模）
python3 kev/console/distill/make_seeds.py --all --n 500 --out-dir data/seeds

# 单场景
python3 kev/console/distill/make_seeds.py --scenario inquiry --n 2000 --out-dir data/seeds
```

每个场景产出两个文件：

| 文件 | 喂给谁 | 内容 |
| --- | --- | --- |
| `<scenario>.seed.jsonl` | EasyDistill | `id` / `instruction` / `system` |
| `<scenario>.state.jsonl` | `seed_to_kev.py` | `id` / `scenario` / `state` / `labels` / `soft` |

`instruction` 是结构化 state 渲染出的自然语言提问，**只陈述事实，不透露任何标签线索** ——
标签是规则引擎的事，LLM 不参与。`id` 是两文件的唯一 join 键。

## 为什么要两个文件

EasyDistill 只保证 `id` 是行标识符，不保证每个阶段透传全部未知字段。把 `state` / `labels` 放在
EasyDistill 触及不到的旁路文件里，join 就不依赖它的字段透传行为。详见 [../README.md](../README.md)。

## 真实产出放哪

`data/seeds/` 在 `.gitignore` 内。仓库里只保留生成器与配置，不保留任何真实产出 ——
即使这些数据是合成的，量大之后也不适合进版本库。

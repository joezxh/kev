"""数据阶段「提交作业」表单的参数 schema（单一真相源）。

这些 FieldSpec 定义前端 `JobStagePage` 动态渲染，并作为 `stage_param_specs` 表的
初始种子落库（`Store.seed_stage_params`）。字段与 `stages/data.py` 各 `build()`
实际读取的键一一对应；`default` 与 `build()` 的默认值对齐。

`when`（条件显示）是纯前端概念、不可序列化，故这里不表达；数据阶段当前也不需要。
存储在 DB 里的 schema 从此表出发，可经 `PUT /console/api/stage/<kind>/params` 改，
改一份写一条 `stage_param_spec_history`（版本化，仿 scenarios.spec_json）。
"""
from __future__ import annotations

# 每个 kind 的字段列表。值全部为可 JSON 序列化的标量。
#   key       写入 params 的字段名（与后端 build 读取键一致）
#   label     前端显示（可带 -- 前缀）
#   kind      控件类型：text / number / select / checkbox / textarea
#   required  必填：提交前前端校验 + 后端 Invalid 双保险
#   default   默认值（字符串；select 给某个 option.value）
#   hint      placeholder 下方的说明
#   options   select 的静态枚举；optionsUrl 则动态拉取（如蒸馏配置）
#   fillFrom  "plan" 表示可一键从 plan_size 产物回填（generate --n）
DEFAULT_SCHEMAS: dict[str, list[dict]] = {
    "plan_size": [],

    "generate": [
        {"key": "data", "label": "--data", "kind": "text", "default": "",
         "hint": "数据目录，默认 data/<场景>；留空用默认"},
        {"key": "n", "label": "--n", "kind": "text", "default": "787", "fillFrom": "plan",
         "hint": "787 = 5 个 spec 都是 4 问题/记录时的计划量；可「从计划读取」"},
        {"key": "seed", "label": "--seed", "kind": "text", "default": "0"},
    ],

    "distill": [
        {"key": "provider_id", "label": "provider", "kind": "select", "required": True,
         "optionsUrl": "/console/api/distill-providers",
         "hint": "蒸馏配置在「蒸馏配置」页创建；未选则无凭据"},
        {"key": "category", "label": "--category", "kind": "text", "default": "",
         "hint": "默认取场景名"},
        {"key": "examples", "label": "--examples", "kind": "text", "default": "",
         "hint": "可选：真实标注记录的 JSONL，作为 few-shot 范例"},
        {"key": "n_examples", "label": "--n-examples", "kind": "text", "default": "",
         "hint": "范例条数，默认 4（仅在填了 --examples 时生效）"},
        {"key": "concurrency", "label": "--concurrency", "kind": "text", "default": "3"},
        {"key": "n", "label": "--n", "kind": "text", "default": "787"},
        {"key": "schedule", "label": "--schedule", "kind": "text", "default": "",
         "hint": "HH:MM（可选；守护模式下必填）"},
        {"key": "state_dir", "label": "--state-dir", "kind": "text", "default": "",
         "hint": "进度状态目录（用量采集依据）"},
    ],

    "distill_daemon": [
        {"key": "provider_id", "label": "provider", "kind": "select", "required": True,
         "optionsUrl": "/console/api/distill-providers",
         "hint": "蒸馏配置在「蒸馏配置」页创建；未选则无凭据"},
        {"key": "category", "label": "--category", "kind": "text", "default": "",
         "hint": "默认取场景名"},
        {"key": "examples", "label": "--examples", "kind": "text", "default": ""},
        {"key": "n_examples", "label": "--n-examples", "kind": "text", "default": ""},
        {"key": "concurrency", "label": "--concurrency", "kind": "text", "default": "3"},
        {"key": "n", "label": "--n", "kind": "text", "default": "787"},
        {"key": "schedule", "label": "--schedule", "kind": "text", "required": True, "default": "",
         "hint": "HH:MM；每天蒸馏到当日配额后睡到本地该时刻（必填）"},
        {"key": "state_dir", "label": "--state-dir", "kind": "text", "default": ""},
    ],

    "goldset": [
        {"key": "n", "label": "--n", "kind": "text", "default": "200",
         "hint": "150-250 是有用区间"},
        {"key": "seed", "label": "--seed", "kind": "text", "default": "0"},
        {"key": "out", "label": "--out", "kind": "text", "default": "",
         "hint": "默认 <数据目录>.gold.jsonl"},
    ],

    "split": [
        {"key": "calibration", "label": "--calibration", "kind": "text", "default": "0.15"},
        {"key": "development", "label": "--development", "kind": "text", "default": "0.15"},
        {"key": "seed", "label": "--seed", "kind": "text", "default": "0"},
        {"key": "holdout", "label": "--holdout", "kind": "text", "default": "",
         "hint": "金标对半分进 calibration/development，永不进 train"},
    ],

    "precheck": [
        {"key": "init_from", "label": "--init-from", "kind": "text", "default": "jaredpalmer/kev-0.8b",
         "hint": "A1 用 kev-0.8b；A2/B 用裸基座的 tokenizer"},
        {"key": "split", "label": "--split", "kind": "select", "default": "train",
         "options": [{"value": "train", "label": "train"},
                     {"value": "calibration", "label": "calibration"},
                     {"value": "development", "label": "development"}]},
    ],

    "make_examples": [
        {"key": "data", "label": "--data", "kind": "text", "required": True, "default": "",
         "hint": "已标注 JSONL，如 data/critical-value.jsonl（必填）"},
        {"key": "n", "label": "--n", "kind": "text", "default": "8",
         "hint": "范例条数，默认 8"},
        {"key": "seed", "label": "--seed", "kind": "text", "default": "0"},
        {"key": "out", "label": "--out", "kind": "text", "default": "",
         "hint": "默认 <data 同目录>/examples.jsonl"},
    ],
}

__all__ = ["DEFAULT_SCHEMAS"]

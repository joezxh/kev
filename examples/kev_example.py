#!/usr/bin/env python3
"""Kev 使用范例 —— 对接本地已部署的 kev.serve（默认 http://localhost:8008）。

运行：
    uv run python examples/kev_example.py
    KEV_BASE_URL=http://other-host:8008 uv run python examples/kev_example.py

演示三种问题类型（与 kev/api.py 的 Question 联合类型一一对应）：
    - choice：从多个命名选项中挑一个（返回选中项 + 置信度 + 各选项概率）
    - noul  ：是/否判断（返回 yes 的概率）
    - score ：对有序等级打分（返回期望等级 + 各档概率）
"""
import argparse
import json
import os

import httpx


def round_prob(x: float) -> float:
    return round(float(x), 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kev usage example against a deployed kev.serve")
    # 用 127.0.0.1 而非 localhost：本机 localhost 可能优先解析为 IPv6，而服务只监听 IPv4
    parser.add_argument("--base-url", default=os.environ.get("KEV_BASE_URL", "http://127.0.0.1:8008"))
    parser.add_argument("--model", default="kev-latest")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    # 1) 健康检查
    with httpx.Client(timeout=300.0) as client:
        try:
            resp = client.get(f"{base}/v1/models")
            resp.raise_for_status()
        except Exception as e:
            print(f"❌ 无法连接 {base}：{e}")
            print("   确认容器已启动：docker ps （应看到 kev-server 为 healthy）")
            return
        print(f"✅ 服务可达：{base}\n")

        # 2) 模型信息（节选）
        models = resp.json()["models"]
        m0 = models[0]
        print("已加载模型：")
        print(f"  name      : {m0['name']}")
        print(f"  run       : {m0['run']}")
        print(f"  base      : {m0['base']} (lora rank {m0.get('lora')})")
        print(f"  device    : {m0['device']} / {m0['backend']} / {m0['dtype']}")
        print(f"  temperature: {m0['temperature']:.4f}")
        print()

        # 3) 决策场景：一个结构化 state + 三种问题
        state = {
            "task": "为边缘设备部署一个决策模型",
            "constraints": {
                "vram_mb": 12288,          # 12 GB 笔记本显卡
                "latency_budget_ms": 50,
                "offline_required": True,
            },
            "candidates": [
                {"name": "kev-4b", "params_b": 4, "bf16_mb": 8192},
                {"name": "kev-0.8b", "params_b": 0.8, "bf16_mb": 1638},
            ],
        }

        questions = {
            "pick": {
                "type": "choice",
                "instructions": "在满足显存与延迟约束的前提下，选择最适合部署的候选模型。",
                "criteria": {
                    "kev-4b": "精度更高，但 bf16 权重约 8 GB，余量紧张",
                    "kev-0.8b": "精度略低，但权重约 1.6 GB，余量大、延迟低",
                },
            },
            "fits_vram": {
                "type": "noul",
                "instructions": "所选模型能否在 12 GB 显存内以 bf16 运行？",
            },
            "fit_score": {
                "type": "score",
                "instructions": "对部署方案的适配度打分（0=很差，4=很好）。",
                "criteria": ["很差", "较差", "一般", "较好", "很好"],
            },
        }

        resp = client.post(
            f"{base}/v1/systemone",
            json={"state": state, "model": args.model, "questions": questions},
        )
        resp.raise_for_status()
        body = resp.json()

    print("=== 决策结果 ===")
    for qid, ans in body["answers"].items():
        print(f"\n问题 {qid} [{ans['type']}]")
        if ans["type"] == "choice":
            print(f"  选中     : {ans['choice']}")
            print(f"  置信度   : {ans['confidence']}")
            print("  概率分布 :")
            for name, p in ans["probabilities"].items():
                mark = "  <--" if name == ans["choice"] else ""
                print(f"    {name:10s}: {p:.4f}{mark}")
        elif ans["type"] == "noul":
            print(f"  yes 概率 : {ans['noul']}")
        elif ans["type"] == "score":
            print(f"  期望等级 : {ans['score']}  (0..{len(ans['legend']) - 1})")
            print(f"  图例     : {ans['legend']}")
            print("  概率分布 :")
            for i, p in ans["probabilities"].items():
                print(f"    level {i}: {p:.4f}")

    usage = body.get("usage", {})
    print("\n=== 服务用量 ===")
    print(f"  输入 tokens : {usage.get('input_tokens')}")
    print(f"  输出 tokens : {usage.get('output_tokens')}")
    print(f"  推理延迟 ms : {body.get('latency_ms')}")
    print(f"  完整响应(JSON):\n{json.dumps(body, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()

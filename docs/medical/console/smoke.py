#!/usr/bin/env python3
"""对已部署的 System One 端点做冒烟测试：5 个场景各 1 例。

只读、不写业务数据；输出 JSON 报告供 UI 展示 p 分布与 argmax。
探针的 state 字段名与 docs/medical/data-format.md 的 state_example 对齐 —— 字段名对模型可见，
改字段名等于换了一个任务。

Run: python docs/medical/console/smoke.py --base-url http://127.0.0.1:8008 --out runs/x-smoke.json
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kev.suite import write_json            # noqa: E402
from kev.console.stages import deploy as dp  # noqa: E402  探针的唯一真相源


def post(base_url: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    report = {"base_url": args.base_url, "models": None, "probes": [], "failures": 0}
    try:
        report["models"] = get(args.base_url, "/v1/models")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        report["error"] = f"端点不可达：{error}"
        write_json(args.out, report)
        print(f"endpoint unreachable: {error}")
        return 1

    for probe in dp.SMOKE_PROBES:
        questions = [{"id": q["qid"], "type": q["type"], "instructions": q["instructions"]}
                     for q in probe["questions"]]
        try:
            answer = post(args.base_url, "/v1/systemone",
                          {"state": probe["state"], "questions": questions})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as error:
            report["failures"] += 1
            report["probes"].append({"scenario": probe["scenario"], "error": str(error)})
            continue
        answers = answer.get("answers") or answer.get("response", {}).get("answers") or []
        report["probes"].append({"scenario": probe["scenario"], "answers": answers})

    write_json(args.out, report)
    print(f"probes {len(report['probes'])} failures {report['failures']}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

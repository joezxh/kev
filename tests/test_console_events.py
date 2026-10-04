"""从训练日志文本解析结构化事件。

kev.train 全程用 print(flush=True)，每 10 个 optimizer step 打一行
（kev/train.py:642-643）；training_metrics.json 只在训练完全结束时写一次
（kev/train.py:672），--stop_after 早退甚至不写（kev/train.py:660-661）。
所以日志文本是唯一实时数据源，kev/plot.py:11 已经用同样的正则刮 loss —— 这里沿用同一形状。

Run: uv run python -m pytest tests/test_console_events.py -q
"""
import pytest

from kev.console.events import MetricBuffer, parse_note, parse_step, sse_frame


def test_parse_step_reads_the_real_training_line():
    line = "ep0 step 10/139 loss 0.623 kl 0.000 anchor 0.000 1.284s/rec"
    assert parse_step(line) == {
        "ep": 0, "step": 10, "total": 139,
        "loss": 0.623, "kl": 0.0, "anchor": 0.0, "sec": 1.284,
    }


def test_parse_step_accepts_the_second_epoch():
    line = "ep1 step 40/139 loss 0.412 kl 0.031 anchor 0.004 0.512s/rec"
    got = parse_step(line)
    assert (got["ep"], got["step"], got["loss"], got["kl"], got["anchor"]) == (1, 40, 0.412, 0.031, 0.004)


def test_parse_step_ignores_other_output():
    for line in ("saved runs/cv-8b-lora-v1", "device=cuda world=1 trainable params=5.6M",
                 "ep0 step 10/139 loss nan kl 0.000 anchor 0.000 1.000s/rec", ""):
        assert parse_step(line) is None


def test_dropped_records_note_is_surfaced():
    note = parse_note("dropped 3 of 787 records that exceed the training context")
    assert note == {"kind": "dropped", "dropped": 3, "total": 787}


def test_saved_and_nonfinite_notes():
    assert parse_note("saved runs/cv-8b-lora-v1") == {"kind": "saved", "path": "runs/cv-8b-lora-v1"}
    assert parse_note("!!! non-finite training loss at step 12") == {"kind": "nonfinite"}
    assert parse_note("ep0 step 10/139 loss 0.623") is None


def test_sse_frame_emits_log_and_optional_metric():
    event = {"id": 7, "ts": "2026-10-04T00:00:00+00:00", "stream": "stdout",
             "line": "ep0 step 10/139 loss 0.623 kl 0.000 anchor 0.000 1.284s/rec"}
    metric = {"ep": 0, "step": 10, "total": 139, "loss": 0.623, "kl": 0.0,
              "anchor": 0.0, "sec": 1.284}
    frame = sse_frame(event, metric)
    assert frame.startswith("id: 7\nevent: log\n")
    assert "ep0 step 10/139" in frame
    assert "event: metric" in frame
    assert frame.endswith("\n\n")


def test_sse_frame_without_metric_has_no_metric_event():
    event = {"id": 8, "ts": "t", "stream": "stderr", "line": "boom"}
    frame = sse_frame(event, None)
    assert "event: metric" not in frame
    assert frame == 'id: 8\nevent: log\ndata: {"id": 8, "ts": "t", "stream": "stderr", "line": "boom"}\n\n'


def test_sse_frame_refuses_to_emit_invalid_json():
    """裸 NaN 不是合法 JSON：EventSource 会静默断流，前端表现为「曲线莫名断了」
    而不是「训练崩了」。宁可在这里炸掉。"""
    event = {"id": 1, "ts": "t", "stream": "stdout", "line": "ep0 step 1/1 loss nan"}
    bad = {"ep": 0, "step": 1, "total": 1, "loss": float("nan"), "kl": 0.0,
           "anchor": 0.0, "sec": 1.0}
    with pytest.raises(ValueError):
        sse_frame(event, bad)


def test_metric_buffer_keeps_the_last_n_points():
    buffer = MetricBuffer(limit=3)
    for step in (1, 2, 3, 4):
        buffer.push({"ep": 0, "step": step, "total": 9, "loss": 0.5,
                     "kl": 0.0, "anchor": 0.0, "sec": 1.0})
    assert [point["step"] for point in buffer.points()] == [2, 3, 4]
    assert buffer.dropped() == 1

"""DistillRenderer — Jinja2-based rendering of system_prompt + ask_template from spec_json.distill.

Spec §3.5. Replaces the hardcoded SYSTEM_PROMPTS + ASK dicts in kev/console/distill/make_seeds.py.
"""
from __future__ import annotations

from jinja2 import Environment, BaseLoader, StrictUndefined
from typing import Any, Dict


class DistillRenderer:
    def __init__(self, distill: Dict[str, Any]):
        # autoescape=False: LLM prompts are plain text, not HTML. StrictUndefined catches typos in
        # {state.foo} placeholders at render time.
        self.env = Environment(loader=BaseLoader(), autoescape=False, undefined=StrictUndefined)
        self.distill = distill
        self.system_prompts = distill.get("system_prompt", {})
        self.ask_template = distill.get("ask_template", "")

    def render_system_prompt(self, lang: str = "zh") -> str:
        text = self.system_prompts.get(lang) or self.system_prompts.get("zh", "")
        return self.env.from_string(text).render()

    def render_ask(self, state: Dict[str, Any]) -> str:
        return self.env.from_string(self.ask_template).render(state=render_state(state))

    def render_topics(self) -> list:
        return self.distill.get("topics", [])


def render_state(state: Dict[str, Any]) -> str:
    """Port of make_seeds.render_state: flatten a state object into key: value lines."""
    lines = []
    for key, value in state.items():
        if isinstance(value, dict):
            inner = "，".join(f"{k} {v}" for k, v in value.items())
            lines.append(f"{key}：{inner}")
        elif isinstance(value, list):
            lines.append(f"{key}：" + ("、".join(str(v) for v in value) if value else "无"))
        else:
            lines.append(f"{key}：{value}" if value not in ("", None) else f"{key}：未记录")
    return "\n".join(lines)

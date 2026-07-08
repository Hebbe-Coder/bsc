"""组件级「跳过上下文」：子组件渲染失败时记录并继续，而非整格式中止。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import List


class DegradeContext:
    def __init__(self) -> None:
        self.component_failures: List[dict] = []

    @contextmanager
    def component(self, name: str):
        try:
            yield
        except Exception as e:  # noqa: BLE001
            self.component_failures.append(
                {"type": "component_failed", "component": name, "message": str(e)}
            )

from __future__ import annotations

import importlib.util
import os
from typing import Any


def expand_all_sections_and_packages(
    device_factory: Any,
    device_id: str | None,
    *,
    aggressive_expand: bool = False,
    max_rounds: int = 72,
):
    """
    复用现有 Android-/3.py 里的“展开模块”逻辑。

    为避免改动主文件结构：这里对 3.py 做一次动态加载，只调用其中的
    expand_all_sections_and_packages(...)。
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    three_path = os.path.join(base_dir, "..", "3.py")
    three_path = os.path.abspath(three_path)

    spec = importlib.util.spec_from_file_location("_xiecheng_three", three_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    if aggressive_expand:
        return mod.expand_all_sections_and_packages(
            device_factory, device_id, max_rounds=max_rounds, allow_section_click=True
        )

    print("[步骤] 全量展开模式（安全版）：展开每个房型（含已订完折叠区；状态图标+几何兜底，不点更多价格）。")
    return mod.expand_all_sections_and_packages(
        device_factory,
        device_id,
        max_rounds=max_rounds,
        allow_geom_fallback=True,
        allow_more_price_click=False,
        allow_section_click=True,
    )


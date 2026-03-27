from __future__ import annotations

import os
from typing import Any

from Xiecheng.expand import expand_all_sections_and_packages
from Xiecheng.ocr_scroll_collect import collect_rooms_via_ocr_scroll
from Xiecheng.export import export_to_1json


def run(
    device_factory: Any,
    device_id: str | None,
    *,
    aggressive_expand: bool = False,
    expand_only: bool = False,
    max_rounds: int = 72,
    max_swipes: int = 40,
    swipe_sleep: float = 1.0,
    scroll_to_top_flings: int = 22,
    no_filter: bool = False,
    out_name: str = "1.json",
):
    """
    串联逻辑：
    1) 展开折叠套餐（复用 3.py 展开模块）
    2) 回顶：多次下滑手势把房型列表滚回顶部，再系统性向下滑动全扫
    3) 每屏截图 + GLM-OCR 提取“房型+早餐分档+价格”
    4) 导出与 Android-/1.json 相同结构
    """
    expand_all_sections_and_packages(
        device_factory,
        device_id,
        aggressive_expand=aggressive_expand,
        max_rounds=max_rounds,
    )

    if expand_only:
        return None

    base_dir = os.path.dirname(os.path.abspath(__file__))
    # 按你的要求：无条件固定输出到 Android-/Xiecheng/1.json
    out_path = os.path.join(base_dir, "1.json")
    if out_name != "1.json":
        print(f"[提示] out_name={out_name!r} 已被忽略，固定输出到 {out_path}")

    rooms, page_info = collect_rooms_via_ocr_scroll(
        device_id=device_id,
        screens=max_swipes,
        flings=scroll_to_top_flings,
        lines=20,
        no_top=(scroll_to_top_flings <= 0),
        swipe_sleep=swipe_sleep,
        no_filter=no_filter,
        wait_before_scrape_sec=1.0,
    )
    export_to_1json(rooms, page_info, out_path)

    return out_path


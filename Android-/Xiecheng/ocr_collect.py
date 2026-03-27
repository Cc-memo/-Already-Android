from __future__ import annotations

import hashlib
import os
import time
from typing import Any

import uiautomator2 as u2

from Xiecheng.ocr_extract import extract_packages_from_screen_glm, glm_ocr_diag_line
from Xiecheng.page_info_ocr import extract_page_info_from_screen_ocr


def scroll_room_list_to_top(d, *, max_flings: int = 22, sleep_sec: float = 0.22) -> None:
    """
    展开阶段多在「向上滑」浏览列表；OCR 全扫前应回到列表顶部，避免从中间/底部开始漏采前段房型。

    与 Android-/3.py 中「回到列表顶部附近」手势一致：手指从上段滑向下段（y 增大），
    让列表内容向上滚动，逐渐露出顶部房型。
    """
    try:
        w, h = d.window_size()
    except Exception:
        w, h = 1080, 2400
    sx = w // 2
    y1 = int(h * 0.34)
    y2 = int(h * 0.84)
    print(f"  [OCR前] 回顶：约 {max_flings} 次下滑手势（露出列表顶部后再全扫）…")
    for _ in range(max_flings):
        try:
            d.swipe(sx, y1, sx, y2, duration=0.28)
        except Exception:
            break
        time.sleep(sleep_sec)
    time.sleep(0.5)


def _quick_img_hash(img: Any, *, size=(240, 420)) -> str | None:
    """对截图做轻量 hash，用于 OCR-only 模式的滑动终止判定。"""
    if img is None:
        return None
    try:
        small = img.convert("RGB").resize(size)
        return hashlib.md5(small.tobytes()).hexdigest()
    except Exception:
        return None


def collect_all_rooms_ocr_only(
    *,
    device_id: str | None,
    max_swipes: int = 40,
    swipe_sleep: float = 1.0,
    no_filter: bool = False,
    swipe_xy=(500, 1900, 500, 450),
    scroll_to_top_flings: int = 22,
) -> tuple[list[dict], dict]:
    """
    OCR-only 采集：
    只依赖“套餐折叠展开后的屏幕截图 -> GLM-OCR 解析套餐和价格”，不再使用 XML 套餐归属。
    """
    try:
        d = u2.connect(device_id) if device_id else u2.connect()
    except Exception:
        return [], {}

    if scroll_to_top_flings > 0:
        scroll_room_list_to_top(d, max_flings=scroll_to_top_flings)

    all_rooms: list[dict] = []
    seen_keys: set[tuple] = set()
    page_info: dict = {}

    last_hash = None
    same_hash_count = 0
    empty_count = 0

    # no_filter 压测模式：跨屏不过度去重
    dedupe = not no_filter

    for i in range(max_swipes):
        img = d.screenshot()
        if img is None:
            break

        if i == 0:
            page_info = extract_page_info_from_screen_ocr(img)

        rooms_glm = extract_packages_from_screen_glm(img)

        if i == 0 and not rooms_glm:
            print(f"  [OCR说明] {glm_ocr_diag_line()}")

        if rooms_glm:
            empty_count = 0
        else:
            empty_count += 1

        if dedupe:
            for r in rooms_glm:
                k = (
                    (r.get("房型名称") or "").strip(),
                    (r.get("价格") or "").strip(),
                    (r.get("备注") or "").strip(),
                    (r.get("剩余房间") or "").strip(),
                    (r.get("窗户信息") or "").strip(),
                )
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                all_rooms.append({kk: vv for kk, vv in r.items() if kk != "_bounds"})
        else:
            all_rooms.extend([{kk: vv for kk, vv in r.items() if kk != "_bounds"} for r in rooms_glm])

        print(f"  第{i+1}屏: GLM-OCR 本屏 {len(rooms_glm)} 条, 累计 {len(all_rooms)} 条")

        # 终止条件：hash 连续相同 >= 3
        cur_hash = _quick_img_hash(img)
        if cur_hash and cur_hash == last_hash:
            same_hash_count += 1
            if same_hash_count >= 3:
                print("  退出原因: 连续 3 屏截图 hash 相同，认为滑动已到底。")
                break
        else:
            same_hash_count = 0
            last_hash = cur_hash

        # 终止条件：连续空识别（回顶后前几屏可能是头图/筛选条，多给几屏再判失败）
        if empty_count >= 8 and i >= 5:
            print("  退出原因: 连续多屏无 OCR 识别结果。")
            break

        # 向下滑动一屏
        sx, sy, ex, ey = swipe_xy
        try:
            d.swipe(sx, sy, ex, ey, duration=0.5)
        except Exception:
            # 兜底：adb swipe（若 u2 swipe 不可用）
            try:
                adb = ["adb"]
                if device_id:
                    adb = ["adb", "-s", device_id]
                # 这里不做复杂兜底，尽量让 u2 成功
                pass
            except Exception:
                break
        time.sleep(swipe_sleep)

    return all_rooms, page_info


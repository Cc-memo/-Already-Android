from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any


def _contract_room_item(item: dict) -> dict:
    name = (item.get("房型名称") or "").strip()
    if "「" in name:
        name = name.split("「")[0].strip()
    if len(name) > 24:
        name = name[:24].rstrip() + "…"

    remark = (item.get("备注") or "").strip()
    if len(remark) > 80:
        remark = remark[:77].rstrip() + "..."

    return {
        "房型名称": name,
        "窗户信息": (item.get("窗户信息") or "").strip(),
        "价格": (item.get("价格") or "").strip(),
        "剩余房间": (item.get("剩余房间") or "").strip(),
        "备注": remark,
    }


def _date_md_to_iso(md: str, ref) -> str:
    """把 "2月6日" 转为 YYYY-MM-DD，年份用 ref 的年份。"""
    if not md:
        return md
    m = re.match(r"(\d{1,2})月(\d{1,2})日?", str(md))
    if not m:
        return md
    try:
        month, day = int(m.group(1)), int(m.group(2))
        y = ref.year
        # 使用 ref 的年月替换（不做“跨年校正”，避免额外规则误差）
        d = ref.replace(year=y, month=month, day=day)
        return d.strftime("%Y-%m-%d")
    except Exception:
        return md


def build_1json_from_ocr(room_list: list[dict], page_info: dict | None = None) -> dict:
    """
    基于 Android-/1.json 的“字段结构”构造输出。
    OCR-only 模式下：尽量保留 OCR 得到的价格/已订完信息，避免把价格清空。
    """
    info = page_info or {}
    now = datetime.now()
    search_time = now.strftime("%Y-%m-%d %H:%M:%S")

    check_in = info.get("入住日期") or ""
    check_out = info.get("离店日期") or ""

    if not check_in or not check_out:
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        if not check_in:
            check_in = today
        if not check_out:
            check_out = tomorrow

    if check_in and re.match(r"^\d{1,2}月\d{1,2}日", str(check_in)):
        check_in = _date_md_to_iso(check_in, now)
    if check_out and re.match(r"^\d{1,2}月\d{1,2}日", str(check_out)):
        check_out = _date_md_to_iso(check_out, now)

    contracted = [_contract_room_item(r) for r in room_list]

    return {
        "搜索时间": search_time,
        "入住日期": check_in,
        "离店日期": check_out,
        "地址": info.get("地址") or "",
        "酒店名称": info.get("酒店名称") or "",
        "房型总数": len(contracted),
        "房型列表": contracted,
    }


def export_to_1json(room_list: list[dict], page_info: dict | None, out_path: str) -> None:
    data = build_1json_from_ocr(room_list, page_info)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已生成房型 JSON：{out_path}")


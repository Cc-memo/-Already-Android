from __future__ import annotations

import re
from typing import Any


def _clean_hotel_name(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    # 去掉括号后的噪声补充信息
    s = re.split(r"[（(]", s)[0].strip()
    # 常见 OCR 头部噪声：数字/英文/符号串，保留“首个中文字符”开始的主体
    m = re.search(r"[\u4e00-\u9fff]", s)
    if m:
        s = s[m.start() :].strip()
    # 去除首尾杂质符号
    s = re.sub(r"^[^0-9A-Za-z\u4e00-\u9fff]+", "", s)
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+$", "", s)
    # 兜底：如果包含“酒店”，尽量截到“酒店”结尾
    if "酒店" in s:
        s = s[: s.find("酒店") + 2]
    return s[:60].strip()


def _extract_clean_address(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    # 优先取“地图右侧地址”分隔符后的部分：xxx | 黄浦区福州路555号
    for sep in ("|", "｜", "丨"):
        if sep in s:
            right = s.split(sep)[-1].strip()
            if right:
                s = right
                break
    # 去掉“地图/导航/查看地图”等尾部按钮词
    s = re.sub(r"(地图|查看地图|导航).*$", "", s).strip()

    # 抽取更像地址的核心片段：xx区/县 + ... + 路/街/弄 + 门牌号
    m = re.search(
        r"([\u4e00-\u9fff]{1,8}(?:区|县)[\u4e00-\u9fff0-9]{0,24}?(?:路|街|弄)\d{1,6}号?)",
        s,
    )
    if m:
        return m.group(1).strip()[:80]

    # 次优：只有“路/街/弄+号”，尝试补齐到最近的“区/县”边界；仍不完整则宁可返回空
    m2 = re.search(r"((?:路|街|弄)\d{1,6}号?)", s)
    if m2 and ("区" in s or "县" in s):
        left = s[: m2.start()]
        p = max(left.rfind("区"), left.rfind("县"))
        if p >= 1:
            cand = (left[max(0, p - 8) : p + 1] + s[m2.start() : m2.end()]).strip()
            if re.search(r"[\u4e00-\u9fff]{1,8}(?:区|县).*(?:路|街|弄)\d{1,6}号?", cand):
                return cand[:80]
    return ""


def _glm_merge_lines(screen_img: Any) -> list[str]:
    try:
        from glm_ocr_client import glm_ocr_words_result
    except Exception:
        return []

    try:
        words_result = glm_ocr_words_result(screen_img, probability=False)
    except Exception:
        return []

    if not words_result:
        return []

    lines: list[tuple[int, str]] = []
    for it in words_result:
        loc = it.get("location") or {}
        top = int(loc.get("top", 0))
        height = int(loc.get("height", 0))
        yc = top + height // 2
        t = str(it.get("words") or it.get("text") or "").strip().replace(" ", "")
        if t:
            lines.append((yc, t))

    if not lines:
        return []

    lines.sort(key=lambda x: x[0])
    merged_lines: list[str] = []
    cur_y = lines[0][0]
    cur_parts: list[str] = []
    for yc, t in lines:
        if abs(yc - cur_y) > 22:
            s = "".join(cur_parts).strip()
            if s:
                merged_lines.append(s)
            cur_parts = [t]
            cur_y = yc
        else:
            cur_parts.append(t)
    s = "".join(cur_parts).strip()
    if s:
        merged_lines.append(s)
    return merged_lines


def extract_page_info_from_screen_ocr(screen_img: Any) -> dict:
    """
    顶层信息 OCR 完全化：
    酒店名称 / 入住日期 / 离店日期 / 地址
    """
    out = {"酒店名称": "", "入住日期": "", "离店日期": "", "地址": "", "酒店关键词": ""}
    merged_lines = _glm_merge_lines(screen_img)
    if not merged_lines:
        return out

    full_text = "\n".join(merged_lines)

    # 日期：优先 ISO
    date_iso = re.findall(r"(\d{4})-(\d{2})-(\d{2})", full_text)
    if len(date_iso) >= 2:
        out["入住日期"] = f"{date_iso[0][0]}-{date_iso[0][1]}-{date_iso[0][2]}"
        out["离店日期"] = f"{date_iso[1][0]}-{date_iso[1][1]}-{date_iso[1][2]}"
    else:
        parts = re.findall(r"(\d{1,2})月(\d{1,2})日?", full_text)
        if len(parts) >= 2:
            out["入住日期"] = f"{int(parts[0][0])}月{int(parts[0][1])}日"
            out["离店日期"] = f"{int(parts[1][0])}月{int(parts[1][1])}日"
        elif len(parts) == 1:
            out["入住日期"] = f"{int(parts[0][0])}月{int(parts[0][1])}日"

    # 酒店名称：命中“酒店”且长度合理的第一条，做脏字符清洗
    for line in merged_lines:
        if "酒店" in line and len(line) <= 80:
            cleaned = _clean_hotel_name(line)
            if cleaned:
                out["酒店名称"] = cleaned
                break

    # 地址：优先抽“地图右侧地址点”，并清洗成核心地址
    for line in merged_lines:
        if len(line) > 120:
            continue
        addr = _extract_clean_address(line)
        if addr:
            out["地址"] = addr
            break

    return out


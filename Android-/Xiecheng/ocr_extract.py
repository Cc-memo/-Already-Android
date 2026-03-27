from __future__ import annotations

import os
import re
from typing import Any

# 行合并：同一物理行内多个词框中心 y 差可能略大，过小会拆碎「无早餐¥328」等
_MERGE_Y_GAP = 36

# 酒店日历价常见区间；原先 200–1999 会漏低价房/套房
_PRICE_MIN = 50
_PRICE_MAX = 99999

# extract_packages_from_screen_glm 写入，glm_ocr_diag_line 读取，避免首屏诊断重复调 GLM
_LAST_GLM_PROBE: dict[str, Any] = {}


def _item_center_y_and_text(it: Any, seq_index: int) -> tuple[int, str] | None:
    """从 GLM-OCR 单条结果取 (中心y, 文本)。兼容 location/bbox/根级字段及纯字符串列表。"""
    if isinstance(it, str):
        t = it.strip().replace(" ", "")
        if not t:
            return None
        return seq_index * 40, t
    if not isinstance(it, dict):
        return None
    t = str(it.get("words") or it.get("text") or "").strip().replace(" ", "")
    if not t:
        return None
    loc = it.get("location")
    if not isinstance(loc, dict):
        loc = it
    top: int | None = None
    h = 0
    try:
        if "top" in loc:
            top = int(loc["top"])
            h = int(loc.get("height", loc.get("h", 0)))
        elif "bbox" in loc and isinstance(loc["bbox"], (list, tuple)) and len(loc["bbox"]) >= 4:
            y1, y2 = int(loc["bbox"][1]), int(loc["bbox"][3])
            top, h = y1, max(y2 - y1, 1)
    except (TypeError, ValueError):
        top = None
    if top is None:
        return seq_index * 40, t
    return top + max(h // 2, 0), t


def _dedupe_flat_y_coords(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """若接口把所有 top 写成 0 或几乎相同，合并会得到一行巨串，改为按阅读顺序用伪 y。"""
    if len(lines) <= 1:
        return lines
    ys = [a[0] for a in lines]
    spread = max(ys) - min(ys)
    if spread < 8 and len(lines) > 4:
        return [(i * 40, t) for i, (_, t) in enumerate(lines)]
    return lines


def merged_lines_from_words_result(words_result: list[Any]) -> list[str]:
    """与 extract 相同的行合并逻辑，供调试脚本在单次 GLM 调用后打印 merged_lines。"""
    lines: list[tuple[int, str]] = []
    for idx, it in enumerate(words_result):
        pair = _item_center_y_and_text(it, idx)
        if pair:
            lines.append(pair)
    lines = _dedupe_flat_y_coords(lines)
    if not lines:
        return []
    lines.sort(key=lambda x: x[0])

    merged_lines: list[str] = []
    cur_y = lines[0][0]
    cur_parts: list[str] = []
    for yc, t in lines:
        if abs(yc - cur_y) > _MERGE_Y_GAP:
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


def last_glm_words_result() -> list[Any] | None:
    """最近一次 extract_packages_from_screen_glm 调用得到的 GLM 原始列表（无则 None）。"""
    return _LAST_GLM_PROBE.get("words_result")


def glm_ocr_diag_line() -> str:
    """紧跟 extract 之后调用：根据最近一次 GLM 返回区分「未安装 / 空 / 字段形态」。"""
    if "import_error" in _LAST_GLM_PROBE:
        return f"未导入 glm_ocr_client: {_LAST_GLM_PROBE['import_error']}"
    if "api_error" in _LAST_GLM_PROBE:
        return f"glm_ocr_words_result 失败: {_LAST_GLM_PROBE['api_error']}"
    wr = _LAST_GLM_PROBE.get("words_result")
    if wr is None:
        return "内部无 GLM 缓存（不应出现）。"
    if not wr:
        return "GLM 返回空列表：请查网络、API Key、配额或 glm_ocr_client 实现。"
    first = wr[0]
    if isinstance(first, str):
        return f"GLM 返回 List[str]（{len(wr)} 段），已按顺序当多行解析；若仍 0 条请设 XIECHENG_OCR_DEBUG=1。"
    if isinstance(first, dict):
        keys = sorted(first.keys())
        sample = {}
        for k in keys[:6]:
            v = first[k]
            if isinstance(v, (dict, list)) and len(str(v)) > 80:
                sample[k] = f"<{type(v).__name__} len={len(v)}>"
            else:
                sample[k] = v
        return f"GLM 返回 {len(wr)} 条 dict，首条键: {keys[:12]}，样例: {sample!r}"
    return f"GLM 返回未知元素类型: {type(first)!r}"


def _variant_from_line(line: str) -> str:
    """
    将页面中可能出现的早餐分档文本归一化为：
    无早餐 / 1份早餐 / 2份早餐 / 含早餐
    """
    # 统一归一化：页面可能显示“无早/1早/2早”，OCR 也可能读成这些缩写
    if "无早餐" in line or "无早" in line:
        return "无早餐"
    if "1份早餐" in line or "1份早" in line or "1早" in line:
        return "1份早餐"
    if "2份早餐" in line or "2份早" in line or "2早" in line:
        return "2份早餐"
    if "含早" in line or "含早餐" in line:
        return "含早餐"
    # 如果出现“份早餐”但没写数字，尝试提取“数字份早餐”
    if "份早餐" in line:
        m = re.search(r"(\d)份早餐", line)
        if m:
            return f"{m.group(1)}份早餐"
        return "份早餐"
    return ""


def _extract_prices_fallback(line: str, *, min_price: int, max_price: int) -> list[int]:
    """
    在 glm_ocr_client 的 extract_prices_from_text 解析失败/规则不兼容时兜底。
    兼容常见样式：
    - ￥635起
    - ￥1588￥858抢购
    """
    if not line:
        return []
    s = str(line).replace(" ", "")
    # 统一币种符号
    s = s.replace("￥", "¥")
    # 捕获 ¥ 后面的数字（2~6 位，足够覆盖携程常见价格）
    nums: list[int] = []
    for m in re.finditer(r"¥\s*(\d{2,6})", s):
        try:
            v = int(m.group(1))
        except Exception:
            continue
        if min_price <= v <= max_price:
            nums.append(v)
    return nums


def _remain_from_line(line: str) -> str:
    for k in ("已订完", "售罄", "无房", "仅剩"):
        if k in line:
            return line
    return ""


def _main_name_from_room_line(line: str) -> str:
    # 截取引号内或直取“房”相关的主要片段
    if "“" in line and "”" in line:
        return line.split("“", 1)[1].split("”", 1)[0].strip()
    if "\"" in line:
        line = line.replace("\"", "").replace("“", "").replace("”", "")
    # 优先返回包含“房/间/床”的前段
    for k in ("房", "间", "床"):
        if k in line:
            idx = line.find(k) + 1
            cand = line[:idx].strip()
            return cand
    return line[:24].strip()


def extract_packages_from_screen_glm(screen_img: Any) -> list[dict]:
    """
    折叠套餐展开后：直接对当前屏做 GLM-OCR，并用规则解析出
    “每个早餐分档（无早/1份/2份/含早）对应的价格”作为独立 item。

    返回字段：房型名称 / 窗户信息 / 价格 / 剩余房间 / 备注
    """
    if screen_img is None:
        return []

    _LAST_GLM_PROBE.clear()
    try:
        from glm_ocr_client import glm_ocr_words_result, extract_prices_from_text
    except Exception as e:
        _LAST_GLM_PROBE["import_error"] = repr(e)
        return []

    try:
        words_result = glm_ocr_words_result(screen_img, probability=False)
    except Exception as e:
        _LAST_GLM_PROBE["api_error"] = repr(e)
        return []

    _LAST_GLM_PROBE["words_result"] = words_result
    if not words_result:
        return []

    merged_lines = merged_lines_from_words_result(words_result)
    if not merged_lines:
        return []

    room_start_keywords = (
        "大床房",
        "双床房",
        "大床",
        "双床",
        "三人间",
        "单人间",
        "家庭房",
        "高级",
        "豪华",
        "商务",
        "行政",
        "套房",
        "床房",
        "标间",
        "标准间",
        "榻榻米",
        "零压",
        "亲子",
        "景观",
        "城景",
        "江景",
        "园景",
        "海景",
        "智能",
        "影音",
        "雅致",
        "舒适",
        "优选",
        "特惠",
        "主题",
        "客房",
    )
    room_bad_keywords = (
        "健身房",
        "洗衣房",
        "服务与设施",
        "出行方便",
        "方便",
        "干净",
        "卫生",
        "WiFi",
        "评论",
        "点评",
        "热卖",
    )
    cancel_pay_keywords = (
        "不可取消",
        "可取消",
        "免费取消",
        "不可退",
        "可退",
        "在线付",
        "预付",
        "现付",
        "到店付",
        "立即确认",
    )

    def is_room_start(line: str) -> bool:
        if not line or len(line) > 80:
            return False
        if any(b in line for b in room_bad_keywords):
            return False
        if any(k in line for k in room_start_keywords):
            return True
        # 兜底：标题行常含「房/床」但不含上表关键词（如「美利居景观大床」）
        if 4 <= len(line) <= 46 and ("房" in line or "床" in line):
            if any(x in line for x in ("取消", "在线付", "预付", "现付", "到店付", "¥", "￥")):
                return False
            return True
        return False

    rooms: list[dict] = []
    cur_room_name = ""
    pending_variant = ""
    pending_remark_parts: list[str] = []
    pending_remain = ""

    for line in merged_lines:
        if is_room_start(line):
            cur_room_name = _main_name_from_room_line(line)
            pending_variant = ""
            pending_remark_parts = []
            pending_remain = ""
            continue

        if not cur_room_name:
            continue

        v = _variant_from_line(line)
        if v:
            pending_variant = v

        if any(k in line for k in cancel_pay_keywords):
            if "热卖" not in line:
                pending_remark_parts.append(line)

        rem = _remain_from_line(line)
        if rem:
            pending_remain = rem

        # 价格提取：优先使用 glm_ocr_client；失败则回退本地正则。
        norm_line = str(line).replace("￥", "¥")
        prices = extract_prices_from_text(norm_line, min_price=_PRICE_MIN, max_price=_PRICE_MAX)
        if not prices:
            prices = _extract_prices_fallback(norm_line, min_price=_PRICE_MIN, max_price=_PRICE_MAX)
        if prices and pending_variant:
            price_v = min(prices)
            remark_parts = [pending_variant] + [p for p in pending_remark_parts if p]
            if pending_remain:
                remark_parts.append(pending_remain)
            remark = " ".join(remark_parts).strip()
            rooms.append(
                {
                    "房型名称": cur_room_name,
                    "窗户信息": "",
                    "价格": f"¥{price_v}",
                    "剩余房间": pending_remain,
                    "备注": remark,
                }
            )
            pending_remark_parts = []
            pending_variant = ""
            pending_remain = ""

    # 基础去噪：只保留早餐分档 + 有价格的项
    out: list[dict] = []
    for r in rooms:
        name = (r.get("房型名称") or "").strip()
        remark = (r.get("备注") or "").strip()
        if not name:
            continue
        if "热卖" in name or "查看已订完房型" in name:
            continue
        if len(name) > 60:
            continue
        if not r.get("价格"):
            continue
        if (
            "无早餐" not in remark
            and "1份早餐" not in remark
            and "2份早餐" not in remark
            and "含早餐" not in remark
            and "份早餐" not in remark
        ):
            continue
        out.append(r)
    dbg = os.environ.get("XIECHENG_OCR_DEBUG", "").strip().lower() in ("1", "true", "yes")
    if dbg and not out and merged_lines:
        print(f"  [OCR调试] 有{len(merged_lines)}行文本但解析0条，前30行: {merged_lines[:30]!r}")
    return out


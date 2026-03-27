#!/usr/bin/env python3
"""
临时调试：在「酒店房型列表」页运行，复用 Xiecheng 的回顶 + 上滑与 GLM 合并行预览。
用法（在项目根 mobile 下）:
  python .\\Android-\\111\\test_ocr_scroll.py
  python .\\Android-\\111\\test_ocr_scroll.py -s <序列号> -n 10
测完可删除整个目录 Android-/111/。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ANDROID_DIR = Path(__file__).resolve().parent.parent
if str(ANDROID_DIR) not in sys.path:
    sys.path.insert(0, str(ANDROID_DIR))

import uiautomator2 as u2
import xml.etree.ElementTree as ET

from Xiecheng.ocr_collect import scroll_room_list_to_top
import re

from Xiecheng.ocr_extract import (
    extract_packages_from_screen_glm,
    last_glm_words_result,
    merged_lines_from_words_result,
)
from Xiecheng.page_info_ocr import extract_page_info_from_screen_ocr
from Xiecheng.export import build_1json_from_ocr

# 默认改为“小步重叠扫描”，避免一滑跨过整段套餐
SWIPE_FROM_RATIO = 0.78
SWIPE_TO_RATIO = 0.46
SWIPE_SLEEP = 1.0


ROOM_START_PAT = re.compile(
    r"(大床房|双床房|三人间|单人间|家庭房|套房|床房|标间|标准间|榻榻米|高级大床房|高级双床房|亲子家庭房)"
)

BREAKFAST_PATTERNS = [
    ("无早餐", re.compile(r"(无早餐|无早)")),
    ("1份早餐", re.compile(r"(1份早餐|1份早|1早)")),
    ("2份早餐", re.compile(r"(2份早餐|2份早|2早)")),
    ("含早餐", re.compile(r"(含早餐|含早)")),
]

CANCEL_PAT = re.compile(r"(不可取消|可取消|免费取消|立即确认|在线付|预付|现付|到店付)")
REMAIN_PAT = re.compile(r"(已订完|售罄|订完|无房|仅剩)")
PRICE_PAT = re.compile(r"[¥￥]\s*(\d{2,6})")


def _normalize_room_name(line: str) -> str:
    s = (line or "").strip()
    # 去掉“「...」”后缀，保留房型主干
    if "「" in s:
        s = s.split("「", 1)[0].strip()
    if len(s) > 48:
        s = s[:45].rstrip() + "…"
    return s


def _variant_from_line(line: str) -> str:
    s = line or ""
    for v, pat in BREAKFAST_PATTERNS:
        if pat.search(s):
            return v
    return ""


def _remain_from_lines_block(lines: list[str]) -> str:
    for s in lines:
        if REMAIN_PAT.search(s):
            # 只取第一次出现即可
            m = REMAIN_PAT.search(s)
            if m:
                return m.group(1)
    return ""


def _cancel_from_line(line: str) -> str:
    if not line:
        return ""
    m = CANCEL_PAT.search(line)
    return m.group(1) if m else ""


def _prices_from_line(line: str) -> list[int]:
    if not line:
        return []
    s = line.replace(" ", "")
    out: list[int] = []
    for m in PRICE_PAT.finditer(s):
        try:
            out.append(int(m.group(1)))
        except Exception:
            continue
    # OCR 漏币符兜底：仅在“套餐/支付”语境里提取 3-5 位数字价，避免把优惠额/面积/楼层当价格
    if not out:
        if any(k in s for k in ("在线付", "立即确认", "免费取消", "不可取消", "品牌首单")):
            if not any(k in s for k in ("m2", "㎡", "入住", "层", "张", "床", "间数")):
                for m in re.finditer(r"(?<!\d)(\d{3,5})(?!\d)", s):
                    try:
                        v = int(m.group(1))
                    except Exception:
                        continue
                    # 排除“优惠/立减/特惠”等折扣金额
                    lctx = s[max(0, m.start() - 6) : m.start()]
                    if any(k in lctx for k in ("优惠", "立减", "特惠", "会员价", "券包", "首单")):
                        continue
                    if 100 <= v <= 5000:
                        out.append(v)
    return out


def parse_room_and_packages_from_merged_lines(merged_lines: list[str]) -> list[dict]:
    """
    直接按你截图结构抽取：
    - 房型标题（房/床 + 携程常见房型关键字）
    - 下一段早餐分档（无早餐/1份早餐/2份早餐/含早餐）及其旁边的「不可取消/在线付/立即确认等」
    - 价格尽量从同一块附近的￥数字中找
    - 无论有没有“订完/售罄”，都保留 item（剩余房间字段可为空或写订完）
    """
    items: list[dict] = []
    n = len(merged_lines)

    noise_keywords = (
        "住客点评",
        "点评",
        "达人探店",
        "问答",
        "酒店卖点",
        "查看全部",
        "筛选",
        "外宾适用",
        "双床房含早餐",
    )
    tail_noise_tokens = ("问酒店", "查看全部", "收起", "展开全部", "达人探店", "住客点评")

    def is_room_start(line: str) -> bool:
        s = (line or "").strip()
        if not s:
            return False
        if any(k in s for k in noise_keywords):
            return False
        if "查看房型" in s or "热卖" in s:
            return False
        if len(s) < 6:
            return False
        return bool(ROOM_START_PAT.search(s))

    def is_package_start(line: str) -> bool:
        return bool(_variant_from_line(line))

    i = 0
    cur_room = ""
    while i < n:
        line_i = (merged_lines[i] or "").strip()
        if not line_i:
            i += 1
            continue

        if is_room_start(line_i):
            cur_room = _normalize_room_name(line_i)
            i += 1
            continue

        if not cur_room or not is_package_start(line_i):
            i += 1
            continue

        variant = _variant_from_line(line_i)
        remain = ""
        cancel = ""
        extra_parts: list[str] = []
        prices: list[int] = _prices_from_line(line_i)

        j = i
        # 价格/支付信息有时会晚 1~2 行才出现，窗口放宽
        while j < min(n, i + 14):
            s = (merged_lines[j] or "").strip()
            if j > i and (is_room_start(s) or is_package_start(s)):
                break
            if not remain:
                rr = _remain_from_lines_block([s])
                if rr:
                    remain = rr
            if not cancel:
                cc = _cancel_from_line(s)
                if cc:
                    cancel = cc
            if any(tn in s for tn in tail_noise_tokens):
                # 到了页面尾部/其他模块文案，停止继续吃这个套餐块
                break
            if "赠·" in s or "赠送" in s or "立即确认" in s or "在线付" in s:
                extra_parts.append(s)
            prices.extend(_prices_from_line(s))
            j += 1

        price_v = min(prices) if prices else 0
        remark_parts = [variant]
        if cancel:
            remark_parts.append(cancel)
        if extra_parts:
            remark_parts.extend(extra_parts[:2])
        remark = " ".join([p for p in remark_parts if p]).strip()

        items.append(
            {
                "房型名称": cur_room,
                "窗户信息": "",
                "价格": (f"¥{price_v}" if price_v else ""),
                "剩余房间": remain,
                "备注": remark,
            }
        )
        i = j

    return items


def _parse_bounds(bounds_str: str) -> tuple[int, int, int, int] | None:
    """解析 bounds 字符串 "[l,t][r,b]" -> (l,t,r,b)。"""
    if not bounds_str:
        return None
    m = re.findall(r"\d+", bounds_str)
    if len(m) != 4:
        return None
    return tuple(int(x) for x in m)  # type: ignore[return-value]


def _iter_all_elements(root: ET.Element):
    # 兼容两类 XML：
    # - 传统 uiautomator：大量 <node .../>
    # - 你的示例：直接用类名当 tag（<android.widget.TextView .../>）
    for e in root.iter():
        if e is root:
            continue
        yield e


def parse_rooms_from_hierarchy_xml(xml_str: str) -> list[dict]:
    """
    直接从层级 XML 抓“房型卡片 + 套餐(¥切分)”，尽量还原你截图里的结构。
    该解析器适配你提供的 `Android-/xml/111.xml`（标签名是类名而非 <node>）。
    """
    if not xml_str:
        return []
    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return []

    parent_map: dict[ET.Element, ET.Element] = {}
    for p in root.iter():
        for c in list(p):
            parent_map[c] = p

    blacklist_exact = {
        "洗衣房",
        "订房优惠",
        "房型",
        "有房提醒",
        "订房必读",
        "查看房型",
        "免费升房",
    }
    blacklist_contains = [
        "销量No.",
        "本店大床房销量",
        "点评",
        "评论",
        "服务与设施",
        "来上海旅游",
        "生活垃圾管理条例",
        "所有房型不可加床",
        "方便",
        "干净",
        "卫生",
        "健身房",
        "洗衣房",
        "免费客房",
        "WiFi",
        "出行方便",
        "房间干净",
        "地理位置方便",
        "非常方便",
        "健身房和洗衣",
        "有简单的健身房",
        "筛选",
        "外宾适用",
    ]

    # 房型标题尽量只抓卡片里的“床型/房型”关键字，不抓纯文案/标签
    title_keywords = (
        "大床房",
        "双床房",
        "三人间",
        "单人间",
        "家庭房",
        "套房",
        "床房",
        "高级",
        "豪华",
        "商务",
        "亲子",
        "景观",
        "行政",
    )

    # 备注/套餐关键字（早餐分档、不可取消、在线付、赠送等）
    remark_keywords = (
        "无早餐",
        "含早餐",
        "份早餐",
        "早餐",
        "不可取消",
        "可取消",
        "免费取消",
        "立即确认",
        "在线付",
        "预付",
        "现付",
        "到店付",
        "不可退",
        "可退",
        "赠·",
        "赠送",
        "礼",
        "票券",
        "订完",
        "已订完",
        "售罄",
        "无房",
        "仅剩",
    )

    # 防止 title 提取到奇怪的引号长串
    def _is_title_candidate(text: str) -> bool:
        t0 = (text or "").strip()
        if not t0:
            return False
        if t0 in blacklist_exact:
            return False
        if any(k in t0 for k in blacklist_contains):
            return False
        if not any(k in t0 for k in title_keywords):
            return False
        if re.match(r"^\d+张\d", t0):
            return False
        if "米大床" in t0 or "米双床" in t0:
            return False
        # filter bar/噪声一般会更长
        if len(t0) > 70:
            return False
        return True

    # 去重标题候选
    title_elems: list[ET.Element] = []
    seen_titles: set[tuple[str, int]] = set()
    for elem in _iter_all_elements(root):
        text = (elem.attrib.get("text") or elem.attrib.get("content-desc") or "").strip()
        if not _is_title_candidate(text):
            continue
        b = _parse_bounds(elem.attrib.get("bounds", ""))
        top = b[1] if b else -1
        key = (text, top)
        if key in seen_titles:
            continue
        seen_titles.add(key)
        title_elems.append(elem)

    room_items: list[dict] = []
    # 为了避免多个 title 命中同一张卡片导致重复，把 title 按 top 排序后尽量跳重叠
    def _bounds_top(e: ET.Element) -> int:
        b = _parse_bounds(e.attrib.get("bounds", ""))
        return b[1] if b else 999999

    title_elems.sort(key=_bounds_top)

    # used_card_boxes 只用于避免同一张卡片内重复命中标题造成爆量；
    # 不能太激进，否则会漏掉相邻房型卡片。
    used_card_boxes: list[tuple[int, int]] = []  # (top,bottom) 简化去重
    for title_elem in title_elems:
        title_text = (title_elem.attrib.get("text") or title_elem.attrib.get("content-desc") or "").strip()
        title_bounds = _parse_bounds(title_elem.attrib.get("bounds", ""))
        if title_bounds:
            t_top, _t_bottom = title_bounds[1], title_bounds[3]
        else:
            t_top, _t_bottom = 0, 0

        # 跳过强重叠的重复卡片
        # 如果标题位置过于接近，可能是同一张卡片内的多个文本命中；
        # 这里保守一点：阈值调小，尽量不误杀相邻卡片。
        overlapped = False
        for ut, _ub in used_card_boxes:
            if title_bounds and abs(t_top - ut) < 8:
                overlapped = True
                break
        if not overlapped and title_bounds:
            used_card_boxes.append((t_top, _t_bottom + 320))

        # 直接按 bounds 在整棵 XML 里筛选“同一张卡片”的文本：
        # 不依赖 parent container（你这个 ROM/WebView 层级下 price 可能不在 title 上两层里）。
        texts: list[str] = []
        if title_bounds:
            card_left, card_top, card_right, _card_bottom0 = title_bounds[0], title_bounds[1], title_bounds[2], title_bounds[3]
            card_bottom = _card_bottom0 + 450
            card_top = max(0, card_top - 50)
        else:
            card_left, card_top, card_right, card_bottom = 0, 0, 1080, 10**9

        x_margin = 120  # 防止边缘控件因为 bounds 偏差被裁掉（但不过大，避免跨卡）
        for sub in _iter_all_elements(root):
            sub_text = (sub.attrib.get("text") or sub.attrib.get("content-desc") or "").strip()
            if not sub_text:
                continue
            b = _parse_bounds(sub.attrib.get("bounds", ""))
            if b is None:
                continue
            l, t, r, bo = b
            if bo < card_top or t > card_bottom:
                continue
            # x 方向至少有重叠
            if r < (card_left - x_margin) or l > (card_right + x_margin):
                continue
            texts.append(sub_text)

        # 去重保持顺序
        seen = set()
        uniq_texts: list[str] = []
        for t in texts:
            if t in seen:
                continue
            seen.add(t)
            uniq_texts.append(t)

        # 卡片有效性校验：过滤“筛选标签/头部文案”这种不属于房型卡片的命中
        # 这些通常缺少“不可取消/在线付/订完”等关键状态词。
        # 有“套餐/房型相关信号”才算有效卡片；
        # 价格在 XML 里经常会被拆成“¥/数字”两个 token，所以不要只依赖价格正则。
        pkg_signals = (
            "不可取消",
            "可取消",
            "在线付",
            "立即确认",
            "订完",
            "已订完",
            "售罄",
            "仅剩",
            "无房",
            "无早餐",
            "含早餐",
            "份早餐",
        )
        has_pkg_signal = any(any(k in t for k in pkg_signals) for t in uniq_texts)
        if not has_pkg_signal:
            continue

        # 窗户信息：同一房型卡片内通常相同（全卡共享）
        window = ""
        for t in uniq_texts:
            if not window and ("有窗" in t or "无窗" in t):
                window = t
                break

        # 以价格为切分点：应兼容“¥ 和数字拆成两个 TextView”的情况
        packages: list[dict] = []
        current: dict | None = None
        prefix_remarks: list[str] = []
        prefix_remain = ""

        def _is_remain_token(s: str) -> bool:
            return any(k in s for k in ("订完", "已订完", "售罄", "无房", "仅剩"))

        def _is_breakfast_or_cancel_token(s: str) -> bool:
            # 作为“备注”保留：早餐/不可取消/在线付/赠送/立即确认等
            return any(k in s for k in ("无早餐", "含早餐", "份早餐", "不可取消", "可取消", "免费取消", "在线付", "预付", "现付", "到店付", "立即确认", "赠·", "赠送"))

        i2 = 0
        while i2 < len(uniq_texts):
            t = uniq_texts[i2]
            norm_t = (t or "").replace("￥", "¥").strip()

            # 情况 A：同一 token 内就是 ¥635 / ¥ 635 等
            m = re.search(r"¥\s*(\d{2,6})", norm_t)
            if m:
                price_num = m.group(1)
                price_str = f"¥{int(price_num)}"
                rest = (norm_t[: m.start()] + norm_t[m.end() :]).strip()

                if current is not None:
                    packages.append(current)

                current = {"价格": price_str, "备注_parts": [], "剩余房间": ""}
                if rest:
                    # rest 里可能带“早餐/不可取消/赠送/订完”等，我们只把“备注类”塞备注
                    if not _is_remain_token(rest) and _is_breakfast_or_cancel_token(rest):
                        current["备注_parts"].append(rest)
                if not packages and prefix_remarks:
                    current["备注_parts"] = list(prefix_remarks)
                if not packages and prefix_remain:
                    current["剩余房间"] = prefix_remain
                i2 += 1
                continue

            # 情况 B：token 只有“¥/￥”，数字在下一个 token（例如 XML：text="¥" + text="635"）
            if norm_t in ("¥", "¥.", "￥", "元"):
                if i2 + 1 < len(uniq_texts):
                    t_next = (uniq_texts[i2 + 1] or "").replace(" ", "")
                    if re.fullmatch(r"\d{2,6}", t_next):
                        price_str = f"¥{int(t_next)}"
                        if current is not None:
                            packages.append(current)
                        current = {"价格": price_str, "备注_parts": [], "剩余房间": ""}
                        if not packages and prefix_remarks:
                            current["备注_parts"] = list(prefix_remarks)
                        if not packages and prefix_remain:
                            current["剩余房间"] = prefix_remain
                        i2 += 2
                        continue

            # 非价格：若命中备注关键词就挂到当前套餐
            if any(k in (t or "") for k in remark_keywords):
                if _is_remain_token(t):
                    if current is not None:
                        if not current.get("剩余房间"):
                            current["剩余房间"] = t
                    else:
                        if not prefix_remain:
                            prefix_remain = t
                else:
                    if current is not None:
                        current["备注_parts"].append(t)
                    else:
                        prefix_remarks.append(t)
            i2 += 1

        if current is not None:
            packages.append(current)

        if not packages:
            packages = [{"价格": "", "备注_parts": list(prefix_remarks), "剩余房间": prefix_remain}]

        # 展开成房型列表：每个套餐生成 1 条房型 item
        for pkg in packages:
            remark = " ".join([x for x in (pkg.get("备注_parts") or []) if x]).strip()
            price = (pkg.get("价格") or "").strip()
            remain_val = (pkg.get("剩余房间") or "").strip()
            # 避免产生“空套餐占位”（例如筛选文案被误切成了 price 前后的片段）
            if not price and not remain_val and not remark:
                continue
            room_items.append(
                {
                    "房型名称": _normalize_room_name(title_text),
                    "窗户信息": window,
                    "价格": price,
                    "剩余房间": remain_val,
                    "备注": remark,
                }
            )

    return room_items


def collect_rooms_via_ocr_scroll(
    device_id: str | None = None,
    *,
    screens: int = 8,
    flings: int = 22,
    lines: int = 20,
    no_top: bool = False,
    swipe_from_ratio: float = SWIPE_FROM_RATIO,
    swipe_to_ratio: float = SWIPE_TO_RATIO,
    swipe_duration: float = 0.45,
    swipe_sleep: float = SWIPE_SLEEP,
    wait_before_scrape_sec: float = 3.0,
    no_filter: bool = False,
) -> tuple[list[dict], dict]:
    """
    可 import 的“主采集逻辑”：
    回顶 + 多屏截图（XML + GLM-OCR）+ OCR解析 + XML兜底 + 合并清洗

    返回：
    - rooms: 房型列表（已清洗/合并）
    - page_info: 酒店名/入住/离店/地址等页面级 OCR 信息
    """
    d = u2.connect(device_id) if device_id else u2.connect()
    print(f"设备: {d.serial}")
    if wait_before_scrape_sec > 0:
        print("请确保当前已在携程「房型」列表页（已展开套餐更佳）。准备开始…")
        time.sleep(wait_before_scrape_sec)

    try:
        sw, sh = d.window_size()
    except Exception:
        sw, sh = 1080, 2400

    sx = sw // 2
    sy = int(sh * max(0.20, min(0.92, swipe_from_ratio)))
    ey = int(sh * max(0.10, min(0.85, swipe_to_ratio)))
    if sy <= ey:
        # 保证是“手指上滑”
        sy = int(sh * 0.78)
        ey = int(sh * 0.46)
    print(f"滑动参数: from={sy}px to={ey}px duration={swipe_duration}s sleep={swipe_sleep}s")

    if not no_top:
        scroll_room_list_to_top(d, max_flings=flings)

    all_rooms: list[dict] = []
    page_info: dict = {}

    for i in range(screens):
        img = d.screenshot()
        # 关键改动：以 XML 为准（更稳定抓取“房型卡片 + 套餐¥切分”）
        xml = ""
        try:
            xml = d.dump_hierarchy() or ""
        except Exception:
            xml = ""

        wr = None
        merged: list[str] = []
        rooms_xml = parse_rooms_from_hierarchy_xml(xml)
        rooms_ocr: list[dict] = []
        try:
            _ = extract_packages_from_screen_glm(img)
            wr = last_glm_words_result()
            merged = merged_lines_from_words_result(wr) if wr else []
            rooms_ocr = parse_room_and_packages_from_merged_lines(merged)
        except Exception:
            rooms_ocr = []

        def _remark_variant(s: str) -> str:
            t = s or ""
            if "无早餐" in t:
                return "无早餐"
            if "1份早餐" in t:
                return "1份早餐"
            if "2份早餐" in t:
                return "2份早餐"
            if "含早餐" in t:
                return "含早餐"
            return ""

        # OCR 主抓（套餐结构更贴近截图）；XML 用于补齐“同房型缺失的早餐分档”
        if rooms_ocr:
            rooms = list(rooms_ocr)
            if rooms_xml:
                ocr_keys = {
                    (
                        (r.get("房型名称") or "").strip(),
                        _remark_variant(r.get("备注") or ""),
                    )
                    for r in rooms
                }
                # 仅补“同房型、不同早餐分档”的缺项，避免把 XML 噪声整段并进来
                for xr in rooms_xml:
                    name = (xr.get("房型名称") or "").strip()
                    v = _remark_variant(xr.get("备注") or "")
                    if not name or not v:
                        continue
                    key = (name, v)
                    if key not in ocr_keys:
                        rooms.append(xr)
                        ocr_keys.add(key)
        else:
            rooms = rooms_xml

        # 到了点评/卖点区就停，避免把无关内容混进结果
        if not rooms and merged and any(k in "".join(merged) for k in ("住客点评", "达人探店", "问答", "酒店卖点")):
            print("检测到已离开房型套餐区域，提前结束。")
            break

        if i == 0:
            # 页面级信息（酒店名/日期/地址等），用于对齐 Android-/1.json 字段结构
            try:
                page_info = extract_page_info_from_screen_ocr(img) or {}
            except Exception:
                page_info = {}

        # 不在这里做“强去重”，先累加，最后统一做合并（避免同一套餐被拆成 2 条）
        for r in rooms:
            if not (r.get("房型名称") or "").strip():
                continue
            all_rooms.append(r)

        print(f"第 {i+1} 屏：XML解析 {len(rooms)} 条，累计 {len(all_rooms)} 条")

        # 仅在兜底路径产生 merged_lines 时打印，避免 XML-only 场景冗余/报错
        if merged:
            print(f"\n--- 第 {i + 1} 屏 ---")
            print(f"  GLM 词条数: {len(wr) if wr else 0}  合并行数: {len(merged)}  规则解析条数: {len(rooms)}")
            print(f"  累计解析条数: {len(all_rooms)}")
            for j, line in enumerate(merged[: max(0, lines)], 1):
                short = line if len(line) <= 140 else line[:137] + "…"
                print(f"  {j:2d} | {short}")
            if len(merged) > lines:
                print(f"  ... 合并行共 {len(merged)} 行")

        d.swipe(sx, sy, sx, ey, duration=swipe_duration)
        time.sleep(swipe_sleep)

    # 后处理：同房型同早餐/同取消方式，把“价格为空”的碎片合并进“价格非空”的那条
    def _extract_breakfast_variant(rem: str) -> str:
        s = rem or ""
        for v, pat in BREAKFAST_PATTERNS:
            if pat.search(s):
                return v
        return ""

    def _extract_cancel_variant(rem: str) -> str:
        s = rem or ""
        if "不可取消" in s:
            return "不可取消"
        if "可取消" in s:
            return "可取消"
        return ""

    def _remain_priority(rem: str) -> int:
        # 数值越大优先级越高
        s = rem or ""
        if "仅剩" in s:
            return 5
        if "售罄" in s or "无房" in s:
            return 4
        if "订完" in s:
            return 3
        return 0

    merged: dict[tuple[str, str, str, str], dict] = {}
    for r in all_rooms:
        name = (r.get("房型名称") or "").strip()
        window = (r.get("窗户信息") or "").strip()
        rem = (r.get("备注") or "").strip()
        breakfast_v = _extract_breakfast_variant(rem)
        cancel_v = _extract_cancel_variant(rem)
        key = (name, window, breakfast_v, cancel_v)
        if key not in merged:
            merged[key] = dict(r)
            continue

        cur = merged[key]
        # 价格：优先保留非空/更“像价格”的
        if (not (cur.get("价格") or "").strip()) and (r.get("价格") or "").strip():
            cur["价格"] = r.get("价格") or ""

        # 剩余：按优先级选择更可靠的
        if _remain_priority(r.get("剩余房间") or "") > _remain_priority(cur.get("剩余房间") or ""):
            cur["剩余房间"] = r.get("剩余房间") or ""

        # 备注：合并去重 token
        tokens_cur = set((cur.get("备注") or "").split())
        tokens_new = set((r.get("备注") or "").split())
        cur["备注"] = (
            " ".join(sorted(tokens_cur.union(tokens_new)))
            if (tokens_cur or tokens_new)
            else (cur.get("备注") or "")
        )

    merged_rooms_raw = list(merged.values())

    # 最终清洗：去掉“筛选标签/头部文案”伪条目，只保留真正套餐信号
    def _looks_like_noise_item(r: dict) -> bool:
        name = (r.get("房型名称") or "").strip()
        price = (r.get("价格") or "").strip()
        remain = (r.get("剩余房间") or "").strip()
        remark = (r.get("备注") or "").strip()

        # 顶部筛选标签常见：短名字 + 含早餐/双份早餐 + 无价格无剩余
        if not price and not remain and len(name) <= 4:
            if ("含早餐" in remark or "双份早餐" in remark) and (
                "取消" not in remark and "在线付" not in remark and "立即确认" not in remark
            ):
                return True

        # 明显是酒店促销/榜单标签，不是房型名
        bad_name_tokens = ("销量No.", "好评No.", "筛选", "外宾适用", "查看全部")
        if any(t in name for t in bad_name_tokens):
            return True

        # 无价格无剩余且备注缺少套餐关键字，视为噪声
        if not price and not remain:
            if not any(
                k in remark
                for k in ("早餐", "取消", "在线付", "立即确认", "订完", "售罄", "无房", "仅剩")
            ):
                return True
        return False

    merged_rooms = merged_rooms_raw if no_filter else [r for r in merged_rooms_raw if not _looks_like_noise_item(r)]
    return merged_rooms, page_info


def main() -> None:
    ap = argparse.ArgumentParser(description="房型页：回顶 + 逐屏截图 + GLM 合并行 + 解析条数")
    ap.add_argument("--device", "-s", default=None, help="adb serial，省略则用默认设备")
    ap.add_argument("--screens", "-n", type=int, default=8, help="截图滑动轮数")
    ap.add_argument("--no-top", action="store_true", help="跳过回顶（已在列表顶时可用）")
    ap.add_argument("--flings", type=int, default=22, help="回顶时下滑次数")
    ap.add_argument("--lines", type=int, default=20, help="每屏打印前 N 行合并文本")
    ap.add_argument("--swipe-from", type=float, default=SWIPE_FROM_RATIO, help="上滑起点y占屏高比例，默认0.78")
    ap.add_argument("--swipe-to", type=float, default=SWIPE_TO_RATIO, help="上滑终点y占屏高比例，默认0.46")
    ap.add_argument("--swipe-duration", type=float, default=0.45, help="单次滑动时长秒，默认0.45")
    ap.add_argument("--swipe-sleep", type=float, default=SWIPE_SLEEP, help="每次滑动后等待秒数，默认1.0")
    args = ap.parse_args()

    rooms, page_info = collect_rooms_via_ocr_scroll(
        device_id=args.device,
        screens=args.screens,
        flings=args.flings,
        lines=args.lines,
        no_top=args.no_top,
        swipe_from_ratio=args.swipe_from,
        swipe_to_ratio=args.swipe_to,
        swipe_duration=args.swipe_duration,
        swipe_sleep=args.swipe_sleep,
        wait_before_scrape_sec=3.0,
        no_filter=False,
    )
    out_data = build_1json_from_ocr(rooms, page_info=page_info)
    out_path = str((ANDROID_DIR / "111" / "test_ocr_scroll_output.json").resolve())
    # 注意：ANDROID_DIR 已指向 Android- 下的目录，所以直接拼接到 Android-/111 即可
    with open(out_path, "w", encoding="utf-8") as f:
        import json

        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"\n结束：已生成测试 JSON：{out_path}")
    print("测完可删除目录 Android-/111/（如果你想保留 JSON，请不要整目录删除）。")


if __name__ == "__main__":
    main()

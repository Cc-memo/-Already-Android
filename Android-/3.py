"""
3.py：从首页到最终房型 JSON 的全流程自动化脚本。

流程概述（基于你的描述 & mtl/*.xml）：
1. 打开携程 App，停在首页（对应 mtl/首页.xml）；
2. 点击左上角的「酒店」入口，进入酒店搜索页（mtl/搜索.xml）；
3. 在「城市」输入框里填写地址，在「位置/品牌/酒店」输入框里填写酒店名称；
4. 点击「查询」/「搜索」按钮，进入搜索结果页（mtl/查询结果.xml）；
5. 在搜索结果中点击目标酒店卡片，进入酒店详情页 → 房型页（mtl/折叠房型.xml）；
6. 在房型页中点击「酒店热卖！查看已订完房型」等折叠入口；
7. 将折叠区内每个房型的「展开套餐」按钮全部点开；
8. 调用 1.py 的 collect_all_rooms + build_output_json，生成 1.json。

说明：
- 由于真机分辨率 / UI 细节存在差异，下面代码里所有「选择具体节点」的部分都尽量基于
  uiautomator dump 的 text / content-desc / resource-id，而不是死写坐标；
- 但在你本机上，可能仍然需要根据 mtl/首页.xml / 搜索.xml / 查询结果.xml / 折叠房型.xml
  微调若干关键词或增加 fallback 的坐标点击逻辑。
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from typing import Iterable, Optional, Tuple

import uiautomator2 as u2

from phone_agent.device_factory import get_device_factory


# ------------- 通用工具函数 -------------

def _parse_bounds(bounds: str) -> Optional[Tuple[int, int, int, int]]:
    """解析 uiautomator bounds 字符串: "[l,t][r,b]" -> (l, t, r, b)。"""
    if not bounds:
        return None
    m = re.findall(r"\d+", bounds)
    if len(m) != 4:
        return None
    l, t, r, b = map(int, m)
    return l, t, r, b


def _center_of(bounds: str) -> Optional[Tuple[int, int]]:
    """返回 bounds 中心点坐标 (x, y)。"""
    b = _parse_bounds(bounds)
    if not b:
        return None
    l, t, r, btm = b
    return (l + r) // 2, (t + btm) // 2


def _resolve_device_id():
    """复用 1.py 的思路：若只连了一台设备，返回其 device_id。"""
    device_factory = get_device_factory()
    try:
        devices = device_factory.list_devices()
    except Exception:
        devices = []
    connected = [d for d in devices if getattr(d, "status", None) == "device"]
    if len(connected) == 1:
        return connected[0].device_id
    if len(connected) > 1:
        print(f"检测到多台设备: {[d.device_id for d in connected]}，使用第一台。")
        return connected[0].device_id
    # 回退：直接用 adb devices（交给 1.py 里已有逻辑会更好，这里先简单处理）
    return None


def _get_xml_via_adb(device_id: Optional[str] = None) -> str:
    """当 device_factory 取 UI 树失败时，直接走 adb dump 兜底（增强重试与多路径）。"""
    adb = ["adb"]
    if device_id:
        adb = ["adb", "-s", device_id]
    paths = ["/sdcard/window_dump.xml", "/sdcard/__phone_agent_window_dump.xml"]

    def _dump_and_cat(path: str, compressed: bool = False) -> str:
        cmd = ["uiautomator", "dump", "--compressed", path] if compressed else ["uiautomator", "dump", path]
        r1 = subprocess.run(
            adb + ["shell", *cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
        )
        if r1.returncode != 0:
            return ""
        r2 = subprocess.run(
            adb + ["shell", "cat", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.5,
        )
        xml = r2.stdout or ""
        return xml if "<hierarchy" in xml else ""

    for _ in range(1):
        for p in paths:
            try:
                xml = _dump_and_cat(p, compressed=False)
                if xml:
                    return xml
                xml = _dump_and_cat(p, compressed=True)
                if xml:
                    return xml
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
        time.sleep(0.25)
    return ""


def _get_xml(device_factory, device_id: Optional[str] = None, retry: int = 2, sleep_sec: float = 0.3) -> str:
    """多次尝试获取当前 UI 树 XML（优先 uiautomator2，再走 adb/backend）。"""
    for i in range(retry):
        # 1) 优先 uiautomator2（对 WebView/动态页面命中率更高）
        xml = _safe_get_ui_xml_via_u2(device_id, retry=1, sleep_sec=0.05)
        if xml:
            return xml
        # 2) adb 直连兜底
        xml = _get_xml_via_adb(device_id)
        if xml:
            return xml
        # 3) backend 再兜底
        try:
            xml = device_factory.get_ui_hierarchy_xml(device_id)
        except Exception:
            xml = ""
        if xml:
            return xml
        time.sleep(sleep_sec)
    return ""


def _safe_get_ui_xml_via_u2(device_id: Optional[str], retry: int = 2, sleep_sec: float = 0.25) -> str:
    """
    使用 uiautomator2 获取完整 UI 树（含 WebView 内容）。
    携程房型列表在 WebView 中渲染，adb uiautomator dump 看不到，
    uiautomator2.dump_hierarchy() 可以抓到。
    """
    for attempt in range(retry):
        try:
            d = u2.connect(device_id) if device_id else u2.connect()
            xml = d.dump_hierarchy()
            if xml and ("<hierarchy" in xml or "<node" in xml):
                return xml
        except Exception:
            # 第一轮失败时可以打印一条日志，但这里保持安静，避免刷屏
            pass
        time.sleep(sleep_sec)
    return ""


def _looks_like_room_page(xml: str) -> bool:
    """是否已在可抓取的房型页（收紧判定，避免把搜索结果页误判为房型页）。"""
    if not xml:
        return False
    # 强信号：详情页房型列表曝光埋点
    strong_hints = (
        "htl_x_dtl_rmlist_mbRmCard_exposure",
        "htl_x_dtl_rmlist_rmCard_exposure",
        "htl_x_dtl_rmlist_mbRmCard_more_exposure",
    )
    if any(h in xml for h in strong_hints):
        return True
    # 次强信号：必须同时具备「详情页上下文」+「套餐关键词」
    detail_ctx = ("htl_x_dtl" in xml) or ("分享" in xml and "收藏" in xml)
    package_ctx = any(k in xml for k in ("无早餐", "不可取消", "在线付", "查看其他价格"))
    return bool(detail_ctx and package_ctx)


def _looks_like_hotel_detail_context(xml: str) -> bool:
    """是否至少处于酒店详情上下文（但不一定已经到房型页）。"""
    if not xml:
        return False
    return (
        "htl_x_dtl" in xml
        or ("分享" in xml and "收藏" in xml)
        or ("酒店详情" in xml)
        or ("查看房型" in xml and "酒店" in xml)
    )


def _ensure_room_page_before_scrape(
    device_factory,
    device_id: Optional[str],
    allow_tap_fix: bool = False,
) -> bool:
    """
    抓取前强校验：若不在房型页，可选纠偏（点顶部房型 tab / 底部查看房型）后再校验。
    返回 True 表示已确认进入房型页；False 表示仍未就绪，应停止抓取避免空结果。
    """
    def _read_xml() -> str:
        return _safe_get_ui_xml_via_u2(device_id, retry=2, sleep_sec=0.2) or _get_xml(
            device_factory, device_id, retry=2, sleep_sec=0.2
        )

    xml = _read_xml()
    if _looks_like_room_page(xml):
        return True

    if not allow_tap_fix:
        print("抓取前校验: 当前不像可抓取房型页（本次不做纠偏点击）。")
        print("可重试: python Android-/3.py --aggressive-expand")
        return False

    if not _looks_like_hotel_detail_context(xml):
        print("抓取前校验: 当前不像酒店详情上下文（更像搜索/列表页），不执行『房型』纠偏点击，避免误触。")
        return False

    print("抓取前校验: 当前不像房型页，尝试点击顶部『房型』标签纠偏。")
    try:
        root = ET.fromstring(xml) if xml else None
    except Exception:
        root = None
    clicked = False
    if root is not None:
        for node in _iter_nodes(root):
            t = (node.attrib.get("text") or "").strip()
            b = _parse_bounds(node.attrib.get("bounds", ""))
            if t == "房型" and b and b[1] < 420:
                _tap_nodes_center(device_factory, [node], device_id, delay=0.8)
                clicked = True
                break
    if not clicked:
        try:
            sw, sh = _get_screen_size_via_adb(device_id)
            device_factory.tap(int(sw * 0.85), int(sh * 0.90), device_id=device_id)  # 底部查看房型兜底
            time.sleep(0.8)
            clicked = True
        except Exception:
            pass

    xml2 = _read_xml()
    if _looks_like_room_page(xml2):
        print("抓取前校验: 已确认在房型页。")
        return True
    print("抓取前校验失败: 仍未进入房型页，已停止抓取以避免输出空结果。")
    return False


def _get_screen_size_via_adb(device_id: Optional[str] = None) -> Tuple[int, int]:
    """
    通过 adb shell wm size 获取当前设备分辨率。
    若失败则回退为典型的 1080x2400。
    """
    adb = ["adb"]
    if device_id:
        adb = ["adb", "-s", device_id]
    try:
        r = subprocess.run(
            adb + ["shell", "wm", "size"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
        )
        out = (r.stdout or "") + (r.stderr or "")
        # 形如: Physical size: 1080x2400
        m = re.search(r"Physical size:\s*(\d+)\s*x\s*(\d+)", out)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass
    return 1080, 2400


def _iter_nodes(root: ET.Element) -> Iterable[ET.Element]:
    """
    遍历 UI 树中的可读节点。

    兼容两类 dump 结构：
    1) 传统 uiautomator：大量 <node .../>；
    2) 部分 ROM/工具链：直接是 android.view.* / android.widget.* 标签。
    """
    if root.tag == "hierarchy":
        for e in root.iter():
            if e is root:
                continue
            yield e
        return
    # 兜底：非 hierarchy 根节点也尽量遍历所有子节点
    for e in root.iter():
        yield e


def _match_text(s: str, keywords: Iterable[str]) -> bool:
    s = (s or "").strip()
    return any(k in s for k in keywords)


def _find_clickable_nodes_by_text(xml: str, keywords: Iterable[str]) -> list[ET.Element]:
    """在 XML 里根据 text / content-desc 包含关键词找到候选节点。"""
    if not xml:
        return []
    try:
        root = ET.fromstring(xml)
    except Exception:
        return []
    result = []
    for node in _iter_nodes(root):
        text = (node.attrib.get("text") or "").strip()
        desc = (node.attrib.get("content-desc") or "").strip()
        if _match_text(text, keywords) or _match_text(desc, keywords):
            result.append(node)
    return result


def _tap_nodes_center(device_factory, nodes: Iterable[ET.Element], device_id: Optional[str] = None, delay: float = 0.5):
    """依次点击给定节点的中心点。"""
    for node in nodes:
        bounds = node.attrib.get("bounds", "")
        center = _center_of(bounds)
        if not center:
            continue
        x, y = center
        try:
            device_factory.tap(x, y, device_id=device_id)
            time.sleep(delay)
        except Exception as e:
            print(f"tap 失败: {e}")


def _type_text_with_adb_keyboard(device_factory, text: str, device_id: Optional[str]) -> bool:
    """统一封装 ADB 键盘输入，返回是否成功。"""
    try:
        original_ime = device_factory.detect_and_set_adb_keyboard(device_id)
        time.sleep(0.2)
        device_factory.clear_text(device_id)
        time.sleep(0.1)
        device_factory.type_text(text, device_id)
        time.sleep(0.2)
        device_factory.restore_keyboard(original_ime, device_id)
        return True
    except Exception as e:
        print(f"  - ADB 键盘输入失败: {e}")
        return False


def _fill_search_conditions_by_coordinates(device_factory, device_id: Optional[str], city: str, hotel_keyword: str) -> bool:
    """
    当搜索页 XML 拿不到时，按已知页面坐标执行保底流程：
    - 先点酒店名框进入“名称搜索页”
    - 在名称搜索页输入酒店名
    - 点候选项返回搜索页
    - 点大「查 询」按钮
    坐标来自 mtl/搜索.xml 与 mtl/名称搜索.xml。
    """
    print("  - 进入坐标保底流程（无 UI 树）。")
    try:
        # 1) 先做地址搜索（城市）
        # 1.1 搜索页城市框（mtl/搜索.xml: [93,666][253,730]）
        device_factory.tap(173, 698, device_id=device_id)
        time.sleep(0.8)
        # 1.2 地址搜索页输入框（mtl/地址搜索.xml EditText: [130,244][954,343]）
        device_factory.tap(542, 293, device_id=device_id)
        time.sleep(0.3)
        ok_city = _type_text_with_adb_keyboard(device_factory, city, device_id)
        if not ok_city:
            return False
        print(f"  - 已输入地址(坐标模式): {city}")
        time.sleep(0.8)
        # 1.3 点地址候选（优先“上海”所在区域）
        # mtl/地址搜索.xml: 文本“上海”约 [521,719][597,811]
        device_factory.tap(560, 765, device_id=device_id)
        time.sleep(1.0)

        # 2) 再做酒店名称搜索
        # 搜索页酒店名框（mtl/搜索.xml: [417,666][833,730]）
        # 注意这里显式点击搜索框区域，避免误触上方“钟点房”tab（y≈491-557）
        device_factory.tap(625, 698, device_id=device_id)
        time.sleep(0.8)

        # 2.1 名称搜索页输入框（mtl/名称搜索.xml EditText: [130,113][809,212]）
        device_factory.tap(470, 162, device_id=device_id)
        time.sleep(0.3)
        ok = _type_text_with_adb_keyboard(device_factory, hotel_keyword, device_id)
        if not ok:
            return False
        print(f"  - 已输入酒店名(坐标模式): {hotel_keyword}")
        time.sleep(0.8)

        # 2.2 名称搜索页：品牌短词时首条可能不是酒店，见 _tap_name_search_hotel_result_leave
        if not _tap_name_search_hotel_result_leave(device_factory, device_id, hotel_keyword):
            print("  - 坐标模式：名称搜索页未能点中有效酒店行。")
            return False

        # 3) 点击候选后通常会直接进入详情页或结果页，因此不再额外点击查询，
        # 避免误触其它控件（例如钟点房）。
        return True
    except Exception as e:
        print(f"  - 坐标保底流程失败: {e}")
        return False


def _xml_looks_like_main_hotel_inquiry(xml: str) -> bool:
    """
    名称/地址子页常用 hotel_search_page_view_root；
    回到主「酒店搜索」页时常出现 hotel_inquiery_view_root（拼写如此）与底部「查询」按钮 id。
    用正向特征避免仅依赖子页 marker 消失（跳转慢、或层级仍含旧节点时误判）。
    """
    if not xml:
        return False
    if "hotel_inquiery_view_root" in xml:
        return True
    if "htl_x_inquire_querybox_searchbut_exposure" in xml:
        return True
    if "htl_x_inquire_querybox_searchbut" in xml:
        return True
    return False


def _tap_first_result_and_verify_leave_search_page(
    device_factory,
    device_id: Optional[str],
    x: int,
    y: int,
    page_marker: str = "hotel_search_page_view_root",
) -> bool:
    """点击「第一个结果」后，校验是否离开名称/地址搜索子页或已回到主搜索页。"""
    try:
        device_factory.tap(x, y, device_id=device_id)
        last_xml_after = ""
        for attempt in range(1, 6):
            time.sleep(0.75 + attempt * 0.12)
            # 这里不要走 adb dump-cat，容易卡住；只用 uiautomator2 快速判断。
            xml_after = _safe_get_ui_xml_via_u2(device_id, retry=1, sleep_sec=0.2)
            if not xml_after:
                continue
            last_xml_after = xml_after
            # 如果点击直接进入“热卖排行/NO.1榜单”，则认为这不是我们要的酒店精确卡片
            hot_rank_markers = ("热卖排行", "热卖排名", "热卖排行榜", "热卖榜", "NO.1", "NO.2", "NO.3")
            if any(m in xml_after for m in hot_rank_markers):
                return False
            if _xml_looks_like_main_hotel_inquiry(xml_after):
                return True
            # 如果已经看不到子页 marker，先做一次二次确认：
            # - 若第二次出现热卖榜单标记，则失败
            # - 若第二次仍不在子页且无热卖标记，则认为离开成功
            if page_marker not in xml_after:
                time.sleep(0.35)
                xml2 = _safe_get_ui_xml_via_u2(device_id, retry=1, sleep_sec=0.15)
                if xml2:
                    if any(m in xml2 for m in hot_rank_markers):
                        return False
                    if _xml_looks_like_main_hotel_inquiry(xml2):
                        return True
                    if "htl_x_dtl_header_tab_exposure" in xml2 or "查看房型" in xml2:
                        return True
                    return True
                return True

            # 如果仍在子页 marker 内，继续等加载完成
            continue

        print("  - 已点击候选后，仍未确认进入主酒店查询态，或可能已落在中间页。")
        return False
    except Exception:
        return False


def _prefer_second_name_result_row(keyword: str) -> bool:
    """
    仅对很短的品牌词（≤6 字且无括号）先点第二行：首行常为「仅搜关键词」建议。
    「丽呈美利居酒店」等较长店名首条多为真实酒店，应优先点第一行，否则会跳过目标店。
    """
    k = (keyword or "").strip()
    if not k:
        return False
    if "（" in k or "(" in k:
        return False
    return False


def _name_search_result_tap_xy(device_id: Optional[str], row_index: int) -> Tuple[int, int]:
    """名称搜索页候选行中心（相对屏高）。row_index: 0/1/2 对应前三条。"""
    sw, sh = _get_screen_size_via_adb(device_id)
    # 你要求点“这一列的最右边”，减少点中间触发其它控件/分组入口的概率
    x = int(sw * 0.68)
    y_rel = (0.215, 0.275, 0.335)
    yi = y_rel[min(max(row_index, 0), len(y_rel) - 1)]
    return x, int(sh * yi)


def _tap_name_search_hotel_result_leave(
    device_factory,
    device_id: Optional[str],
    keyword: str,
) -> bool:
    """
    离开名称搜索子页：在名称搜索页中直接定位“包含关键词的可点击候选”，
    按从上到下顺序点第一个，并点在卡片右侧主体（bounds 的 75% 处），
    避免用 row_index/y 坐标造成“点到第二个/点反”的问题。
    """
    # 这些词指向“榜单/热卖分组框”，不应被当成具体酒店卡片
    excluded_group_kw = (
        "热卖",
        "酒店热卖",
        "热卖排名",
        "热卖排行榜",
        "热卖榜",
        "热卖排行",
        "榜",
        "排名",
        "NO.",
        "NO.1",
        "NO.2",
        "NO.3",
        "舒适型",
        "低价",
        "低价房",
        "热卖 No",
        "热卖排名",
    )

    def _subtree_text(n: ET.Element) -> str:
        parts: list[str] = []
        for it in n.iter():
            t = (it.attrib.get("text") or "").strip()
            d = (it.attrib.get("content-desc") or "").strip()
            if t:
                parts.append(t)
            if d and d != t:
                parts.append(d)
        return "".join(parts).replace(" ", "")

    # 1) 首选：用 XML 定位第一个“包含关键词的可点击候选”，点右侧主体
    try:
        xml_name = _safe_get_ui_xml_via_u2(device_id, retry=2, sleep_sec=0.2)
        if xml_name:
            try:
                root_name = ET.fromstring(xml_name)
            except Exception:
                root_name = None
            if root_name is not None:
                candidates: list[tuple[int, ET.Element, tuple[int, int, int, int]]] = []
                for node in _iter_nodes(root_name):
                    clickable = (node.attrib.get("clickable") or "").strip().lower() == "true"
                    if not clickable:
                        continue
                    b = _parse_bounds(node.attrib.get("bounds", ""))
                    if not b:
                        continue
                    l, t, r, bb = b
                    if t < 200:
                        continue
                    combo = _subtree_text(node)
                    if not keyword or keyword not in combo:
                        continue
                    if any(kw in combo for kw in excluded_group_kw):
                        continue
                    candidates.append((t, node, b))
                candidates.sort(key=lambda x: x[0])
                for _, _, b in candidates[:6]:
                    l, t, r, bb = b
                    x = int(l + (r - l) * 0.75)
                    y = int((t + bb) / 2)
                    if _tap_first_result_and_verify_leave_search_page(device_factory, device_id, x=x, y=y):
                        return True
    except Exception:
        pass

    # 2) fallback：回退到原来的“点行号”逻辑（用于 XML 抓不到时）
    prefer_second = _prefer_second_name_result_row(keyword)
    order = [1, 0, 2] if prefer_second else [0, 1, 2]
    tried: set[int] = set()
    for row in order:
        if row in tried:
            continue
        tried.add(row)
        x, y = _name_search_result_tap_xy(device_id, row)
        if _tap_first_result_and_verify_leave_search_page(device_factory, device_id, x=x, y=y):
            return True
    return False


# ------------- 分步操作：首页 → 搜索 → 结果 → 详情 -------------

def go_to_hotel_search(device_factory, device_id: Optional[str] = None):
    """
    从首页点击左上角「酒店」入口，进入酒店搜索页。
    依赖 mtl/首页.xml 的结构：左上角有一个“酒店”tab 或按钮。
    """
    print("[步骤] 首页 → 酒店搜索页")
    xml = _get_xml(device_factory, device_id)
    if not xml:
        # UI 树拿不到时，直接按首页酒店宫格坐标兜底点击一次
        print("提示: 首页未拿到 UI 树，改用坐标兜底点击『酒店』入口。")
        try:
            device_factory.tap(130, 310, device_id=device_id)
            time.sleep(1.0)
            return True
        except Exception:
            return False
    try:
        root = ET.fromstring(xml)
    except Exception:
        print("提示: 首页 UI 树解析失败，无法点击『酒店』入口。")
        return False

    # 1) 优先精确匹配首页酒店入口（最稳定）
    exact_nodes: list[ET.Element] = []
    for node in _iter_nodes(root):
        rid = (node.attrib.get("resource-id") or "").strip()
        cdesc = (node.attrib.get("content-desc") or "").strip()
        combo = f"{rid} {cdesc}"
        if "home_grid_hotel_widget" in combo:
            exact_nodes.append(node)
    if exact_nodes:
        _tap_nodes_center(device_factory, [exact_nodes[0]], device_id)
        return True

    # 2) 次优先：文本/描述里有“酒店”
    nodes = _find_clickable_nodes_by_text(xml, ["酒店", "酒店·民宿", "酒店/民宿"])
    if nodes:
        # 只点最靠左上的一个
        nodes.sort(key=lambda n: _parse_bounds(n.attrib.get("bounds", "")) or (9999, 9999, 9999, 9999))
        _tap_nodes_center(device_factory, [nodes[0]], device_id)
        return True

    # 3) 最后兜底：按首页常见坐标点“酒店”宫格（参考 mtl/首页.xml: [33,226][223,392]）
    try:
        device_factory.tap(130, 310, device_id=device_id)
        time.sleep(0.6)
        return True
    except Exception:
        print("提示: 未通过 resource-id/文本/坐标找到『酒店』入口。")
        return False


def fill_search_conditions(
    device_factory,
    device_id: Optional[str],
    city: str,
    hotel_keyword: str,
):
    """
    在搜索页（mtl/搜索.xml）中：
    - 第一个输入框：城市 / 地址；
    - 第二个输入框：「位置/品牌/酒店」。

    这里假设 device_factory 提供了 send_text / input_text 能力；
    如果当前封装没有，需要你在 device_factory 中补一层封装。
    """
    print("[步骤] 填写搜索条件")
    xml = _get_xml(device_factory, device_id)
    if not xml:
        print("未获取到搜索页 UI 树，改走坐标保底输入。")
        return _fill_search_conditions_by_coordinates(device_factory, device_id, city, hotel_keyword)

    try:
        root = ET.fromstring(xml)
    except Exception:
        print("搜索页 XML 解析失败，跳过自动填写。")
        return False

    city_box = None
    hotel_box = None
    # 若页面已带默认值（例如城市已是“上海”、酒店名已是目标值），可直接判定为已填写
    city_already_set = city in xml
    hotel_already_set = hotel_keyword in xml

    # 先用稳定的 resource-id/content-desc 命中输入框
    for node in _iter_nodes(root):
        rid = (node.attrib.get("resource-id") or "").strip()
        cdesc = (node.attrib.get("content-desc") or "").strip()
        combo = f"{rid} {cdesc}"
        if not city_box and "htl_x_inquire_querybox_destbox_exposure" in combo:
            city_box = node
        if not hotel_box and "htl_x_inquire_querybox_keybox_exposure" in combo:
            hotel_box = node

    # 再命中任意带 keybox 的 querybox（部分版本/皮肤 resource-id 略有差异）
    if not hotel_box:
        for node in _iter_nodes(root):
            rid = (node.attrib.get("resource-id") or "").strip()
            if "keybox" in rid.lower():
                hotel_box = node
                break

    # 再用文案兜底（仅当上面没命中）
    for node in _iter_nodes(root):
        text = (node.attrib.get("text") or "").strip()
        desc = (node.attrib.get("content-desc") or "").strip()
        hint_attr = (node.attrib.get("hint") or "").strip()
        # 兼容部分机型：输入框可能只在 hint 字段里可见
        candidate_text = " ".join(filter(None, [text, desc, hint_attr])).strip()
        if not candidate_text:
            continue
        # 非常粗糙的匹配：需要根据 mtl/搜索.xml 进一步微调关键字
        if not city_box and _match_text(candidate_text, ["城市", "目的地", "上海", "北京"]):
            city_box = node
        if not hotel_box and _match_text(candidate_text, ["位置/品牌/酒店", "酒店名", "品牌"]):
            hotel_box = node

    city_input_ok = False
    hotel_input_ok = False

    # 点击并输入城市（先地址）
    if city_box:
        center = _center_of(city_box.attrib.get("bounds", ""))
        if center:
            device_factory.tap(*center, device_id=device_id)
            time.sleep(0.8)
            xml_city = _get_xml(device_factory, device_id, retry=1, sleep_sec=0.2)
            on_city_search_page = "hotel_search_page_view_root" in (xml_city or "")
            if on_city_search_page:
                try:
                    ok_city = _type_text_with_adb_keyboard(device_factory, city, device_id)
                    if ok_city:
                        print(f"  - 已在地址搜索页输入城市: {city}")
                        time.sleep(0.8)
                        # 按你的要求：直接点击下面第一个结果
                        jumped = _tap_first_result_and_verify_leave_search_page(
                            device_factory, device_id, x=560, y=765
                        )
                        if jumped:
                            city_input_ok = True
                            print("  - 已点击地址搜索页第一个结果（校验通过）。")
                        else:
                            print("  - 地址搜索页点击第一个结果后仍未离开该页。")
                except Exception:
                    pass
            else:
                # 未进入地址搜索页时，尽量直接输入；失败再看是否已有目标城市
                try:
                    device_factory.send_text(city, device_id=device_id)
                    city_input_ok = True
                    print(f"  - 已输入城市: {city}")
                except Exception:
                    if city_already_set:
                        city_input_ok = True
                        print(f"  - 城市已是目标值: {city}（跳过输入）")
                    else:
                        print("device_factory.send_text(city) 未实现，且当前页面城市不是目标值。")
            time.sleep(0.5)
    else:
        if city_already_set:
            city_input_ok = True
            print(f"  - 未定位到城市输入框，但页面城市已是: {city}")
        else:
            print("  - 未找到城市输入框。")

    # 点击并输入酒店关键字：
    # 1) 在搜索页点击 keybox 进入“名称搜索页”（mtl/名称搜索.xml）
    # 2) 在名称搜索页 EditText 输入关键词
    # 3) 点击候选酒店（品牌短词时首行常为「搜关键词」建议，见 _tap_name_search_hotel_result_leave）
    name_page_ready = False
    if hotel_box:
        center = _center_of(hotel_box.attrib.get("bounds", ""))
        if center:
            device_factory.tap(*center, device_id=device_id)
            time.sleep(0.8)
            name_page_ready = True
    if not name_page_ready and (city_input_ok or city_already_set):
        try:
            sw, sh = _get_screen_size_via_adb(device_id)
            # 多组相对坐标：只点「城市下方、入住日期上方」的酒店/关键词行。
            # Y 过大（如 >0.34）易误点「3月25日-3月26日」日期行，勿把探测点放在日期区。
            probe_taps = [
                (0.62, 0.27),
                (0.58, 0.28),
                (0.72, 0.27),
                (0.50, 0.26),
                (0.55, 0.30),
            ]
            for tx, ty in probe_taps:
                device_factory.tap(int(sw * tx), int(sh * ty), device_id=device_id)
                time.sleep(0.75)
                xml_probe = _get_xml(device_factory, device_id)
                if "hotel_search_page_view_root" in (xml_probe or ""):
                    name_page_ready = True
                    print(f"  - 未命中 keybox 节点，已用相对坐标 ({tx:.2f},{ty:.2f}) 进入名称搜索页。")
                    break
        except Exception:
            pass

    if name_page_ready:
        xml_name = _get_xml(device_factory, device_id)
        on_name_search_page = "hotel_search_page_view_root" in (xml_name or "")

        if on_name_search_page:
            try:
                root_name = ET.fromstring(xml_name)
            except Exception:
                root_name = None

            edit_node = None
            if root_name is not None:
                for node in _iter_nodes(root_name):
                    cls = (node.attrib.get("class") or "").strip()
                    text = (node.attrib.get("text") or "").strip()
                    hint = (node.attrib.get("hint") or "").strip()
                    if "EditText" not in cls:
                        continue
                    combined = f"{text} {hint}"
                    if "位置" in combined or "品牌" in combined or "酒店" in combined:
                        edit_node = node
                        break
                if edit_node is None:
                    for node in _iter_nodes(root_name):
                        if "EditText" in (node.attrib.get("class") or ""):
                            edit_node = node
                            break

            if edit_node is not None:
                edit_center = _center_of(edit_node.attrib.get("bounds", ""))
                if edit_center:
                    device_factory.tap(*edit_center, device_id=device_id)
                    time.sleep(0.3)

            try:
                ok = _type_text_with_adb_keyboard(device_factory, hotel_keyword, device_id)
                if ok:
                    print(f"  - 已在名称搜索页输入酒店名: {hotel_keyword}")
                time.sleep(0.8)
                jumped = _tap_name_search_hotel_result_leave(device_factory, device_id, hotel_keyword)
                if jumped:
                    hotel_input_ok = True
                else:
                    print("  - 名称搜索页点击候选后仍未离开该页。")
            except Exception:
                if hotel_already_set:
                    hotel_input_ok = True
                    print(f"  - 酒店名已是目标值: {hotel_keyword}（跳过输入）")
                else:
                    print("酒店名称输入失败（ADB 键盘/输入流程异常）。")
        else:
            try:
                device_factory.send_text(hotel_keyword, device_id=device_id)
                hotel_input_ok = True
                print(f"  - 已输入酒店名: {hotel_keyword}")
            except Exception:
                if hotel_already_set:
                    hotel_input_ok = True
                    print(f"  - 酒店名已是目标值: {hotel_keyword}（跳过输入）")
                else:
                    print("device_factory.send_text(hotel_keyword) 未实现，且当前页面酒店名不是目标值。")
        time.sleep(0.5)
    else:
        if hotel_already_set:
            hotel_input_ok = True
            print(f"  - 未定位到酒店输入框，但页面酒店名已是: {hotel_keyword}")
        else:
            print("  - 未找到酒店名称输入框，且相对坐标未能进入名称搜索页。")

    # 严格模式：未完成输入就不继续点查询
    # 但你担心地址不对：为了避免搜错区域，若城市/酒店任意一项没填成功，
    # 直接走坐标兜底重置（会强制设置 city + hotel_keyword），然后继续执行点击查询。
    if not city_input_ok or not hotel_input_ok:
        print("提示: 输入未完成。尝试坐标兜底重新设置城市/酒店并触发查询。")
        ok = _fill_search_conditions_by_coordinates(device_factory, device_id, city, hotel_keyword)
        if not ok:
            return False
        city_input_ok = True
        hotel_input_ok = True

    # 点击「查询」/「搜索」按钮
    # 这里尽量不要走 adb dump/cat，容易卡住；优先 uiautomator2。
    xml = _safe_get_ui_xml_via_u2(device_id, retry=2, sleep_sec=0.2)
    if not xml:
        # 兜底：短重试 adb（避免长时间 hang）
        xml = _get_xml(device_factory, device_id, retry=1, sleep_sec=0.2)
    # 1) 优先按 resource-id/content-desc 匹配底部大「查 询」按钮：
    #    <android.view.ViewGroup ... content-desc="htl_x_inquire_querybox_searchbut_exposure"
    #    内部 TextView text="查 询"
    search_nodes: list[ET.Element] = []
    if xml:
        try:
            root2 = ET.fromstring(xml)
        except Exception:
            root2 = None
        if root2 is not None:
            for node in _iter_nodes(root2):
                rid = (node.attrib.get("resource-id") or "").strip()
                cdesc = (node.attrib.get("content-desc") or "").strip()
                combo = f"{rid} {cdesc}"
                if "htl_x_inquire_querybox_searchbut_exposure" in combo:
                    search_nodes.append(node)
                # 部分版本 content-desc 略短或带后缀变体
                elif "searchbut" in combo.lower() and "picsearch" not in combo.lower():
                    search_nodes.append(node)

    if search_nodes:
        # 一般只有一个，就点它的中心（大查询按钮）
        _tap_nodes_center(device_factory, [search_nodes[0]], device_id)
        print("  - 已点击查询按钮。")
        return True
    else:
        # 2) 退化：尝试用图片搜索按钮作为备选（放大镜图标）
        pic_nodes: list[ET.Element] = []
        if xml:
            try:
                root3 = ET.fromstring(xml)
            except Exception:
                root3 = None
            if root3 is not None:
                for node in _iter_nodes(root3):
                    rid = (node.attrib.get("resource-id") or "").strip()
                    cdesc = (node.attrib.get("content-desc") or "").strip()
                    combo = f"{rid} {cdesc}"
                    if "htl_x_inquire_querybox_picSearch_exposure" in combo:
                        pic_nodes.append(node)
        if pic_nodes:
            _tap_nodes_center(device_factory, [pic_nodes[0]], device_id)
            print("  - 已点击图片搜索按钮（查询兜底）。")
            return True
        # 3) 再退化：尝试用文本匹配“查询/搜索”（优先点屏幕下半区、靠下的大按钮，避免点到顶部 Tab）
        text_nodes = _find_clickable_nodes_by_text(
            xml, ["查询", "查 询", "搜索", "查看结果", "开始搜索"]
        )
        if text_nodes:
            try:
                sw, sh = _get_screen_size_via_adb(device_id)
                mid_y = int(sh * 0.48)

                def _bottom(nn):
                    b = _parse_bounds(nn.attrib.get("bounds", "")) or (0, 0, 0, 0)
                    return b[3]

                filtered = []
                for nn in text_nodes:
                    b = _parse_bounds(nn.attrib.get("bounds", ""))
                    if not b:
                        continue
                    cy = (b[1] + b[3]) // 2
                    tx = (nn.attrib.get("text") or "").replace(" ", "")
                    if cy < mid_y:
                        continue
                    if not any(k in tx for k in ("查询", "搜索")):
                        continue
                    filtered.append(nn)
                use_nodes = filtered if filtered else text_nodes
                use_nodes.sort(key=_bottom, reverse=True)
                _tap_nodes_center(device_factory, [use_nodes[0]], device_id)
                print("  - 已点击文本查询按钮（查询兜底）。")
                return True
            except Exception:
                text_nodes.sort(
                    key=lambda n: (_parse_bounds(n.attrib.get("bounds", "")) or (0, 0, 0, 0))[3],
                    reverse=True,
                )
                _tap_nodes_center(device_factory, [text_nodes[0]], device_id)
                print("  - 已点击文本查询按钮（查询兜底）。")
                return True
        # 4) 最后：底部大蓝钮「查询」固定区域（与日期行无关，约在屏高 90% 附近）
        try:
            sw, sh = _get_screen_size_via_adb(device_id)
            device_factory.tap(sw // 2, int(sh * 0.905), device_id=device_id)
            time.sleep(1.0)
            print("  - 已用底部相对坐标点击「查询」区域（避免点到日期行）。")
            return True
        except Exception:
            pass
        print("提示: 未找到『查询/搜索』按钮（包括 searchbut/picSearch），fill_search_conditions 暂时无法自动触发搜索。")
        return False


def open_hotel_from_result(device_factory, device_id: Optional[str], hotel_name: str):
    """
    在查询结果页（mtl/查询结果.xml）中点击目标酒店卡片。
    简单策略：查找 text / content-desc 包含指定酒店名称的节点，并点击其卡片区域。
    """
    print("[步骤] 查询结果页 → 进入酒店详情页")
    # 这里必须保证“不要卡住”：优先走 uiautomator2（比 adb dump 快），
    # 失败才走 adb 兜底，且将重试次数压到最低。
    xml = _safe_get_ui_xml_via_u2(device_id, retry=2, sleep_sec=0.2)
    if not xml:
        xml = _get_xml(device_factory, device_id, retry=1, sleep_sec=0.2)
    if not xml:
        print("未获取到查询结果页 UI 树，改用坐标兜底点击第一条酒店。")
        try:
            # mtl/查询结果.xml 第一条酒店卡片约为 [35,622][1080,1249]
            device_factory.tap(560, 935, device_id=device_id)
            time.sleep(1.0)
            return True
        except Exception:
            return False
    try:
        root = ET.fromstring(xml)
    except Exception:
        print("查询结果页 XML 解析失败。")
        return False

    # 若已在酒店详情页，则无需再点查询结果
    if (
        "htl_x_dtl_header_tab_exposure" in xml
        or "htl_x_dtl_rmlist" in xml
        or "查看房型" in xml
    ):
        print("当前已在酒店详情页，跳过结果页点击。")
        return True

    # 即使节点的 text/desc 里包含酒店名，也可能来自“热卖榜单/排名”卡片，
    # 这种卡片要跳过，避免点到榜单页。
    excluded_group_kw_for_target = (
        "热卖",
        "酒店热卖",
        "热卖排行",
        "榜",
        "排名",
        "NO.",
        "NO.1",
        "NO.2",
        "NO.3",
        "舒适型",
        "低价",
        "低价房",
    )

    def _subtree_text_for_target(n: ET.Element) -> str:
        parts: list[str] = []
        for it in n.iter():
            t = (it.attrib.get("text") or "").strip()
            d = (it.attrib.get("content-desc") or "").strip()
            if t:
                parts.append(t)
            if d and d != t:
                parts.append(d)
        return "".join(parts).replace(" ", "")

    target_nodes = []
    for node in _iter_nodes(root):
        text = (node.attrib.get("text") or "").strip()
        desc = (node.attrib.get("content-desc") or "").strip()
        clickable = (node.attrib.get("clickable") or "").strip().lower() == "true"
        b = _parse_bounds(node.attrib.get("bounds", ""))
        top = b[1] if b else 0
        # 只考虑列表区域（避开顶部搜索栏）且可点击节点
        if top < 300 or not clickable:
            continue
        if hotel_name and (hotel_name in text or hotel_name in desc):
            combo = _subtree_text_for_target(node)
            if any(kw in combo for kw in excluded_group_kw_for_target):
                continue
            target_nodes.append(node)

    def _adb_back() -> None:
        if not device_id:
            return
        try:
            subprocess.run(
                ["adb", "-s", device_id, "shell", "input", "keyevent", "4"],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception:
            pass

    def _looks_like_hot_ranking_page(xml_text: str) -> bool:
        if not xml_text:
            return False
        return any(
            k in xml_text
            for k in (
                "热卖排名",
                "热卖排行榜",
                "热卖排行",
                "热卖榜",
                "热卖",
                "NO.1",
                "NO.2",
                "NO.3",
            )
        )

    def _looks_like_hotel_detail(xml_text: str) -> bool:
        if not xml_text:
            return False
        return (
            "htl_x_dtl_header_tab_exposure" in xml_text
            or "htl_x_dtl_rmlist" in xml_text
            or "查看房型" in xml_text
            or "htl_x_dtl" in xml_text
        )

    if not target_nodes:
        print(f"提示: 查询结果中未通过文本找到酒店『{hotel_name}』，可在 open_hotel_from_result 中补充其他匹配方式。")
        # 兜底：从 UI 树中挑“像酒店卡片”的可点击节点（通常包含：价格 ¥...起 或 ¥ 数字 + 评分 4.x分）。
        try:
            candidates: list[ET.Element] = []
            # 这些词高度指向“榜单/热卖分组框”，不应该作为具体酒店卡片点击
            excluded_group_kw = (
                "热卖",
                "酒店热卖",
                "榜",
                "排名",
                "No.",
                "No.1",
                "NO.",
                "NO.1",
                "NO.2",
                "NO.3",
                "舒适型",
                "低价",
                "低价房",
            )
            def _subtree_text(n: ET.Element) -> str:
                parts: list[str] = []
                for it in n.iter():
                    t = (it.attrib.get("text") or "").strip()
                    d = (it.attrib.get("content-desc") or "").strip()
                    if t:
                        parts.append(t)
                    if d and d != t:
                        parts.append(d)
                return "".join(parts).replace(" ", "")

            for node in _iter_nodes(root):
                clickable = (node.attrib.get("clickable") or "").strip().lower() == "true"
                if not clickable:
                    continue
                b = _parse_bounds(node.attrib.get("bounds", ""))
                if not b:
                    continue
                l, t, r, bb = b
                w = r - l
                h = bb - t
                if t < 250 or h < 70 or w < 300:
                    continue
                combo = _subtree_text(node)
                # 排除分组/标题：通常没有价格，也没有评分“X.X分”
                if "¥" not in combo:
                    continue
                if "起" not in combo and "晚" not in combo and "间" not in combo:
                    continue
                if any(kw in combo for kw in excluded_group_kw):
                    continue
                if not re.search(r"\d\.\d分", combo):
                    # 有些卡片评分可能拆开显示，放宽一部分：至少出现“分”或“收藏/点评”关键字
                    if "分" not in combo:
                        continue
                candidates.append(node)

            candidates.sort(key=lambda n: (_parse_bounds(n.attrib.get("bounds", "")) or (0, 0, 0, 0))[1])

            # 依次尝试前几个候选，点完立刻验证是否进入详情页
            for c in candidates[:8]:
                center = _center_of(c.attrib.get("bounds", ""))
                if not center:
                    continue
                # 按你的要求：尽量点卡片右侧主体位置
                bbb = _parse_bounds(c.attrib.get("bounds", ""))
                if bbb:
                    l, t, r, bb = bbb
                    tap_x = int(l + (r - l) * 0.75)
                    tap_y = int((t + bb) / 2)
                else:
                    tap_x, tap_y = center

                device_factory.tap(tap_x, tap_y, device_id=device_id)
                time.sleep(1.2)
                xml_after = _safe_get_ui_xml_via_u2(device_id, retry=2, sleep_sec=0.2)
                if _looks_like_hot_ranking_page(xml_after) and not _looks_like_hotel_detail(xml_after):
                    # 点错了榜单页：直接返回，再换候选
                    print("  - 点到了热卖排名页，已自动返回，继续换候选。")
                    _adb_back()
                    time.sleep(1.0)
                    continue
                if _looks_like_hotel_detail(xml_after):
                    print("  - 兜底点击候选酒店卡片成功（已进入酒店详情页）。")
                    return True
            # 最后仍失败：不要无条件 return True（会导致你看到我们乱点“热卖榜单”）。
            # 这里先尝试一次旧坐标兜底并验证；仍失败就返回 False，交给上层停止或人工处理。
            try:
                device_factory.tap(560, 935, device_id=device_id)
                time.sleep(1.2)
                xml_after2 = _safe_get_ui_xml_via_u2(device_id, retry=2, sleep_sec=0.2)
                if _looks_like_hotel_detail(xml_after2):
                    print("  - 坐标兜底成功（已进入酒店详情页）。")
                    return True
                if _looks_like_hot_ranking_page(xml_after2) and not _looks_like_hotel_detail(xml_after2):
                    print("  - 坐标兜底点到了热卖排名页，已返回。")
                    _adb_back()
            except Exception:
                pass
            return False
        except Exception:
            try:
                device_factory.tap(560, 935, device_id=device_id)
                time.sleep(1.2)
                return True
            except Exception:
                return False

    # 选取屏幕上方的一个（通常是第一条搜索结果卡片）
    def _top(n):
        b = _parse_bounds(n.attrib.get("bounds", "")) or (9999, 9999, 9999, 9999)
        return b[1]

    target_nodes.sort(key=_top)
    # 不要无条件 return：点完必须验证是否进入酒店详情，否则要返回并尝试下一个
    for tn in target_nodes[:5]:
        b_tn = _parse_bounds(tn.attrib.get("bounds", ""))
        if b_tn:
            l, t, r, bb = b_tn
            tap_x = int(l + (r - l) * 0.75)  # 点右侧主体
            tap_y = int((t + bb) / 2)
        else:
            center = _center_of(tn.attrib.get("bounds", ""))
            if not center:
                continue
            tap_x, tap_y = center

        device_factory.tap(tap_x, tap_y, device_id=device_id)
        time.sleep(1.2)
        xml_after2 = _safe_get_ui_xml_via_u2(device_id, retry=2, sleep_sec=0.2)
        if _looks_like_hotel_detail(xml_after2):
            return True
        if _looks_like_hot_ranking_page(xml_after2) and not _looks_like_hotel_detail(xml_after2):
            print("  - 点到热卖排名页（非酒店详情），已返回并换候选。")
            _adb_back()
            time.sleep(1.0)
            continue
    return False


# ------------- 在房型页自动展开 -------------

def expand_all_sections_and_packages(
    device_factory,
    device_id: Optional[str] = None,
    max_rounds: int = 40,
    allow_geom_fallback: bool = True,
    allow_more_price_click: bool = True,
    allow_section_click: bool = False,
):
    """
    在酒店详情页 → 房型页（mtl/折叠房型.xml）中：
    1. 点击「酒店热卖！查看已订完房型」等折叠入口；
    2. 将当前屏及下方所有「折叠房型」从上到下依次点开，直到连续两轮无可点或达到轮数上限。

    每轮只点一次（已订完/展开一个房型/查看其他价格），避免跳点；几何兜底用「标题+价格+面积+id」稳定去重，
    不用 bounds（滑动后坐标会变，会导致同一房型被当成多张卡重复点）。另有几何兜底总次数上限。
    """
    min_rounds_before_stable = 32   # 至少滑过更多轮后再允许“连续 N 轮无可点”退出，减少过早停
    consecutive_no_click_to_exit = 10  # 需更长连续无可点才退出，避免漏掉前段/中段未展开房型
    print("[步骤] 房型页：展开折叠区 & 套餐")
    same_count = 0

    # 先尽量通过文本点击“房型”标签，避免死坐标在不同机型上失效
    try:
        # 房型页优先使用 uiautomator2 获取 UI 树（可见 WebView 内容）
        xml_pre = _safe_get_ui_xml_via_u2(device_id, retry=2, sleep_sec=0.2)
        if xml_pre:
            try:
                root_pre = ET.fromstring(xml_pre)
            except Exception:
                root_pre = None
            room_tab = None
            if root_pre is not None:
                for node in _iter_nodes(root_pre):
                    text = (node.attrib.get("text") or "").strip()
                    b = _parse_bounds(node.attrib.get("bounds", ""))
                    # 顶部导航区域通常在屏幕上方，限制一个较小的 top 范围，例如 < 420
                    if text == "房型" and b and b[1] < 420:
                        room_tab = node
                        break
            if room_tab is not None:
                _tap_nodes_center(device_factory, [room_tab], device_id, delay=0.8)
                print("  - 已点击顶部『房型』标签（按文本定位）。")
            else:
                # 若未找到顶部“房型”Tab，则优先尝试点击底部蓝色「查看房型」按钮
                clicked_room_entry = False
                if root_pre is not None:
                    candidates: list[ET.Element] = []
                    for node in _iter_nodes(root_pre):
                        text = (node.attrib.get("text") or "").strip()
                        b = _parse_bounds(node.attrib.get("bounds", ""))
                        if not text or not b:
                            continue
                        # 靠近底部区域的「查看房型」按钮
                        if "查看房型" in text and b[1] > 1600:
                            candidates.append(node)
                    if candidates:
                        # 选最靠下的一个按钮
                        candidates.sort(key=lambda n: (_parse_bounds(n.attrib.get("bounds", "")) or (0, 0, 0, 0))[1], reverse=True)
                        _tap_nodes_center(device_factory, [candidates[0]], device_id, delay=0.8)
                        print("  - 已点击底部『查看房型』按钮（按文本定位）。")
                        clicked_room_entry = True

                if not clicked_room_entry:
                    # 仍然兜底一次：用屏幕尺寸估算「查看房型」大按钮位置，不再点顶部箭头
                    try:
                        sw, sh = _get_screen_size_via_adb(device_id)
                        btn_x = int(sw * 0.85)
                        btn_y = int(sh * 0.90)
                        device_factory.tap(btn_x, btn_y, device_id=device_id)
                        time.sleep(0.8)
                        print("  - 未在 XML 中找到『房型』文本/按钮，使用底部坐标兜底点击『查看房型』。")
                    except Exception:
                        print("  - 未在 XML 中找到『房型』文本，且坐标兜底点击失败。")
    except Exception:
        print("  - 点击『房型』标签时出现异常（忽略，继续后续流程）。")

    # 按你提供的折叠套餐.xml / 展开房型.xml 固定元素特征定位
    section_signatures = [
        "htl_x_dtl_rmlist_mbRmCard_mbmore_exposure",  # 酒店热卖！查看已订完房型
    ]
    # 展开动作只针对 mbRmCard（房型标题行 + 展开箭头），
    # 不对 rmCard（套餐/价格块）做点击，避免误触“领券订/下单”流。
    room_card_signatures = [
        "htl_x_dtl_rmlist_mbRmCard_exposure",
    ]
    more_price_signatures = [
        "htl_x_dtl_rmlist_mbRmCard_more_exposure",  # 查看其他价格
    ]

    def _find_nodes_by_signatures(xml: str, signatures: list[str], min_top: int = 300) -> list[ET.Element]:
        if not xml:
            return []
        try:
            root = ET.fromstring(xml)
        except Exception:
            return []
        out: list[ET.Element] = []
        for node in _iter_nodes(root):
            rid = (node.attrib.get("resource-id") or "").strip()
            cdesc = (node.attrib.get("content-desc") or "").strip()
            combo = f"{rid} {cdesc}"
            if not any(sig in combo for sig in signatures):
                continue
            b = _parse_bounds(node.attrib.get("bounds", ""))
            if not b:
                continue
            if b[1] < min_top:
                continue
            out.append(node)
        return out

    def _text_has_codepoint(text: str, cp: int) -> bool:
        if not text:
            return False
        try:
            return any(ord(ch) == cp for ch in text)
        except Exception:
            return False

    def _card_flat_text(card: ET.Element) -> str:
        parts: list[str] = []
        for sub in card.iter():
            for attr in ("text", "content-desc"):
                t = (sub.attrib.get(attr) or "").strip()
                if t:
                    parts.append(t)
        return "\n".join(parts)

    def _card_seems_expanded_content(card: ET.Element) -> bool:
        """无私有字体图标时，用“强特征”判断卡片是否已展开，避免把折叠卡误判为已展开。"""
        txt = _card_flat_text(card)
        if _text_has_codepoint(txt, 990100):
            return True
        # 仅保留强信号：出现早餐分档 + 取消/支付组合，通常只在展开后的套餐块内
        meal_kw = ("无早餐", "1份早餐", "2份早餐", "双早", "含早餐")
        pay_cancel_kw = ("不可取消", "可取消", "在线付", "预付", "到店付")
        if any(k in txt for k in meal_kw) and any(k in txt for k in pay_cancel_kw):
            return True
        # 另一个强信号：同一房型块出现多条“领券订”按钮（多套餐）
        if txt.count("领券订") >= 2:
            return True
        return False

    def _geom_dedupe_key(card: ET.Element) -> str:
        """
        几何兜底去重：不依赖 bounds（列表滚动后同一房型坐标会变）。
        用房型标题 + 首价 + 面积 + resource-id 片段；信息过少时用正文摘要 hash。
        """
        txt = _card_flat_text(card)
        title = ""
        for sub in card.iter():
            t = (sub.attrib.get("text") or "").strip()
            if t and len(t) > 3 and "房" in t:
                title = t[:120].strip()
                break
        rid_tail = ""
        for sub in card.iter():
            rid = (sub.attrib.get("resource-id") or "").strip()
            if not rid:
                continue
            # 与 room_card_signatures 一致：mb 房型行 与 无 mb 的 rmCard 块（勿用裸子串 "rmCard" 误匹配 mbRmCard）
            if "mbRmCard_exposure" in rid or "rmlist_rmCard_exposure" in rid:
                rid_tail = rid.split("/")[-1][-40:]
                break
        prices = re.findall(r"[¥￥]\s*(\d+)", txt)
        price_part = prices[0] if prices else ""
        area_m = re.search(r"(\d+)\s*㎡", txt)
        area_part = area_m.group(1) if area_m else ""
        core = "|".join(x for x in (title, price_part, area_part, rid_tail) if x)
        if len(core) < 6:
            h = hashlib.sha256(re.sub(r"\s+", " ", txt[:320]).encode("utf-8", errors="ignore")).hexdigest()[:20]
            return f"fp:{h}"
        return core

    def _scroll_room_list_down_nudge(steps: int = 6) -> None:
        """
        手指上滑列表（内容下移），多段短滑：首张房型展开后占满屏时，
        把下方折叠房型 / 未露出的套餐行拉进视口，否则 UI 树里没有 990101 可点。
        """
        try:
            sw, sh = _get_screen_size_via_adb(device_id)
            sx = sw // 2
            y_from = int(sh * 0.82)
            y_to = int(sh * 0.38)
            for _ in range(max(1, steps)):
                device_factory.swipe(sx, y_from, sx, y_to, device_id=device_id, duration=220)
                time.sleep(0.22)
        except Exception:
            pass

    def _visible_room_cards_all_expanded_no_collapsed(xml: str) -> bool:
        """当前屏可见 mbRmCard 均显示已展开(990100)且无折叠(990101) → 可能被首卡撑满，需要下滑找下一张。"""
        cards = _find_nodes_by_signatures(xml, room_card_signatures, min_top=260)
        if not cards:
            return False
        for card in cards:
            has_exp = False
            has_col = False
            for sub in card.iter():
                t = (sub.attrib.get("text") or "").strip()
                d = (sub.attrib.get("content-desc") or "").strip()
                merged = f"{t} {d}".strip()
                if _text_has_codepoint(merged, 990100) or "990100" in merged:
                    has_exp = True
                if _text_has_codepoint(merged, 990101) or "990101" in merged:
                    has_col = True
            if has_col:
                return False
            if not has_exp:
                return False
        return True

    def _card_likely_collapsed_only_starting_price(card: ET.Element) -> bool:
        """
        部分机型 dump 里折叠态没有 990101 节点：仅显示「¥601起」等起价，无早餐/取消等套餐行。
        此时应仍点标题行右侧展开区。
        """
        txt = _card_flat_text(card)
        if _text_has_codepoint(txt, 990100) or "990100" in txt:
            return False
        if not re.search(r"[¥￥]\s*\d+", txt):
            return False
        if "起" not in txt:
            return False
        pkg_kw = ("无早餐", "份早餐", "含早", "不可取消", "免费取消", "在线付", "预付", "到店付", "领券订")
        if any(k in txt for k in pkg_kw):
            return False
        return True

    def _expand_room_cards_by_state_icon(xml: str) -> int:
        """
        通过房型卡片内的状态图标点击“未展开”项：
        - 未展开图标：codepoint 990101；已展开：990100（不点，避免重复展开）
        - 每轮只点当前屏从上到下第一个未展开的房型，实现顺序展开、不跳点。
        - 仅扫描 mbRmCard_exposure，避免把套餐块当成可展开房型去点击。
        """
        if not xml:
            return 0
        try:
            root = ET.fromstring(xml)
        except Exception:
            return 0

        # 找所有房型卡片容器，按从上到下、从左到右排序
        room_cards = _find_nodes_by_signatures(xml, room_card_signatures, min_top=260)
        room_cards.sort(key=lambda n: (_parse_bounds(n.attrib.get("bounds", "")) or (0, 0, 0, 0))[1:3])
        for card in room_cards:
            collapsed_icon_node = None
            expanded_icon_found = False
            for sub in card.iter():
                t = (sub.attrib.get("text") or "").strip()
                d = (sub.attrib.get("content-desc") or "").strip()
                merged = f"{t} {d}".strip()
                if _text_has_codepoint(merged, 990100) or "990100" in merged:
                    expanded_icon_found = True
                elif _text_has_codepoint(merged, 990101) or "990101" in merged:
                    collapsed_icon_node = sub

            if expanded_icon_found:
                continue

            if collapsed_icon_node is not None:
                center = _center_of(collapsed_icon_node.attrib.get("bounds", ""))
                if center:
                    try:
                        device_factory.tap(*center, device_id=device_id)
                        time.sleep(0.25)
                        return 1
                    except Exception:
                        pass
                continue

            # 无 990101/990100 时：若表现为「仅起价」折叠，点标题行右侧展开位（与几何兜底一致）
            if _card_likely_collapsed_only_starting_price(card):
                cb = _parse_bounds(card.attrib.get("bounds", ""))
                if cb:
                    l, t, r, b = cb
                    if r - l >= 400 and b - t >= 120:
                        try:
                            device_factory.tap(r - 32, t + 20, device_id=device_id)
                            time.sleep(0.28)
                            return 1
                        except Exception:
                            pass
        return 0

    def _expand_packages_without_xml(max_screens: int = 8):
        """
        无法获取 UI 树时的纯坐标遍历：
        - 只点击一次“查看已订完房型”（避免展开后又被点回收起）；
        - 之后只做滑动遍历，不再固定坐标乱点，避免误入订购页。
        """
        print("进入无 UI 树保守模式：仅展开已订完入口，随后只滑动遍历，避免误触订购页。")
        # 先确保在“房型”tab（坐标使用相对屏幕高度，以适配不同机型）
        try:
            sw, sh = _get_screen_size_via_adb(device_id)
            tab_x = int(sw * 0.16)   # 顶部左侧一小块区域
            tab_y = int(sh * 0.12)   # 靠近顶部导航栏
            device_factory.tap(tab_x, tab_y, device_id=device_id)
            time.sleep(0.6)
        except Exception:
            pass

        soldout_opened = False
        for i in range(max_screens):
            try:
                if not soldout_opened:
                    # “酒店热卖！查看已订完房型”入口（只点一次）
                    sw, sh = _get_screen_size_via_adb(device_id)
                    sold_x = sw // 2
                    sold_y = int(sh * 0.88)  # 靠近底部但不贴边
                    device_factory.tap(sold_x, sold_y, device_id=device_id)
                    time.sleep(0.8)
                    soldout_opened = True
                    print("  - 已点击『查看已订完房型』（一次性）。")

                # 不再固定坐标点击房型/套餐区域，防止误点“领券订/预订”进入下单页
                # 仅做滚动遍历，让后续 1.py 负责采集已展开/可见内容
                sw, sh = _get_screen_size_via_adb(device_id)
                sx = sw // 2
                sy1 = int(sh * 0.82)
                sy2 = int(sh * 0.36)
                device_factory.swipe(sx, sy1, sx, sy2, device_id=device_id, duration=260)
                time.sleep(0.6)
            except Exception:
                continue

    # 先回到列表顶部附近，避免从中段开始导致前几个房型漏展开
    try:
        sw, sh = _get_screen_size_via_adb(device_id)
        sx = sw // 2
        for _ in range(5):
            device_factory.swipe(sx, int(sh * 0.34), sx, int(sh * 0.84), device_id=device_id, duration=260)
            time.sleep(0.45)
    except Exception:
        pass

    no_xml_rounds = 0
    section_opened_once = False
    top_recheck_count = 0
    tapped_room_keys: set[str] = set()
    max_geom_taps_total = 28  # 几何兜底全局上限，避免无限滑屏+重复尝试
    geom_taps_done = 0
    geom_cap_warned = False
    for round_idx in range(max_rounds):
        expanded_count = 0
        nudge_after_room_expand = False
        # 房型页优先使用 uiautomator2 获取 UI 树
        xml = _safe_get_ui_xml_via_u2(device_id, retry=3, sleep_sec=0.25)
        if not xml:
            no_xml_rounds += 1
            print("未获取到房型页 UI 树，改用坐标兜底点击折叠入口。")
            # 第一次就进入“无 UI 树遍历模式”，避免反复点同一入口导致展开后又关闭
            if no_xml_rounds == 1:
                _expand_packages_without_xml(max_screens=max(6, max_rounds + 2))
            print("无 UI 树模式展开完成，直接进入抓取。")
            break
            continue

        clicked_this_round = False

        # 每轮只做一次点击：已订完 / 展开一个房型 / 查看其他价格 三选一，从上到下顺序、不跳点、不重复
        # 1) 已订完入口：只点一次（「酒店热卖！查看已订完房型」可能在屏中上部，min_top 过大永远找不到）
        if allow_section_click and not section_opened_once:
            section_nodes = _find_nodes_by_signatures(xml, section_signatures, min_top=120)
            if not section_nodes:
                try:
                    root_sec = ET.fromstring(xml)
                    for node in _iter_nodes(root_sec):
                        text = (node.attrib.get("text") or "").strip()
                        if "查看已订完房型" in text or ("酒店热卖" in text and "订完" in text):
                            b = _parse_bounds(node.attrib.get("bounds", ""))
                            if b and b[1] >= 80:
                                section_nodes.append(node)
                except Exception:
                    pass
            if section_nodes:
                section_nodes.sort(key=lambda n: (_parse_bounds(n.attrib.get("bounds", "")) or (0, 0, 0, 0))[1], reverse=True)
                _tap_nodes_center(device_factory, [section_nodes[0]], device_id, delay=0.5)
                section_opened_once = True
                clicked_this_round = True
                print(f"第 {round_idx + 1} 轮：点击『酒店热卖/查看已订完房型』入口 1 次。")

        if not clicked_this_round:
            # 2) 按房型卡片“展开状态图标”点当前屏从上到下第一个未展开项
            expanded_count = _expand_room_cards_by_state_icon(xml)
            if expanded_count > 0:
                print(f"第 {round_idx + 1} 轮：按状态图标展开房型 1 个（从上到下顺序）。")
                clicked_this_round = True
                nudge_after_room_expand = True

        if allow_geom_fallback and (not clicked_this_round) and geom_taps_done < max_geom_taps_total:
            # 2.1) 兜底：几何点右上角展开区。room_key 与 bounds 脱钩，避免滑动后同一房型反复点。
            room_cards = _find_nodes_by_signatures(xml, room_card_signatures, min_top=260)
            room_cards.sort(key=lambda n: (_parse_bounds(n.attrib.get("bounds", "")) or (0, 0, 0, 0))[1:3])
            for card in room_cards:
                cb = _parse_bounds(card.attrib.get("bounds", ""))
                if not cb:
                    continue
                l, t, r, b = cb
                if r - l < 400 or b - t < 120:
                    continue
                has_expanded_icon = False
                for sub in card.iter():
                    txt = (sub.attrib.get("text") or "").strip()
                    desc = (sub.attrib.get("content-desc") or "").strip()
                    merged = f"{txt} {desc}".strip()
                    if _text_has_codepoint(merged, 990100) or "990100" in merged:
                        has_expanded_icon = True
                        break
                if has_expanded_icon:
                    continue
                # 不再用“内容像已展开”跳过：该启发在当前酒店会把折叠卡误判为已展开，导致漏点。
                room_key = _geom_dedupe_key(card)
                if room_key in tapped_room_keys:
                    continue

                icon_x = r - 32
                icon_y = t + 20
                try:
                    device_factory.tap(icon_x, icon_y, device_id=device_id)
                    time.sleep(0.25)
                    tapped_room_keys.add(room_key)
                    geom_taps_done += 1
                    clicked_this_round = True
                    nudge_after_room_expand = True
                    print(
                        f"第 {round_idx + 1} 轮：几何兜底点击房型展开位 1 次（去重键已记录，本进程累计 {geom_taps_done}/{max_geom_taps_total}）。"
                    )
                except Exception:
                    pass
                break  # 每轮只点一个，下一轮再点下一个
        elif allow_geom_fallback and (not clicked_this_round) and geom_taps_done >= max_geom_taps_total and not geom_cap_warned:
            geom_cap_warned = True
            print(f"提示: 几何兜底已达上限（{max_geom_taps_total} 次），后续仅滑动与状态图标/查看其他价格，避免重复点同一批房型。")

        if allow_more_price_click and (not clicked_this_round):
            # 3) 点“查看其他价格”入口（每轮只点当前屏从上到下第一个，顺序展开、不跳点）
            more_nodes = _find_nodes_by_signatures(xml, more_price_signatures, min_top=350)
            more_nodes = [n for n in more_nodes if _parse_bounds(n.attrib.get("bounds", "")) and (_parse_bounds(n.attrib.get("bounds", ""))[3] - _parse_bounds(n.attrib.get("bounds", ""))[1]) <= 80]
            if more_nodes:
                more_nodes.sort(key=lambda n: (_parse_bounds(n.attrib.get("bounds", "")) or (0, 0, 0, 0))[1])
                _tap_nodes_center(device_factory, [more_nodes[0]], device_id, delay=0.25)
                print(f"第 {round_idx + 1} 轮：点击『查看其他价格』1 个（从上到下顺序）。")
                clicked_this_round = True

        # 首张房型展开后占满屏时，下方折叠 mbRmCard 不在视口 → 树里无 990101；多段小滑把后续房型/套餐拉进来。
        if nudge_after_room_expand:
            print("  - 已展开房型，追加小滑以露出下方折叠房型/未露出的套餐。")
            _scroll_room_list_down_nudge(7)
            time.sleep(0.35)

        if not clicked_this_round and _visible_room_cards_all_expanded_no_collapsed(xml):
            print("  - 当前屏可见房型均已展开且列表较高，追加小滑以寻找下方折叠房型。")
            _scroll_room_list_down_nudge(10)
            time.sleep(0.4)

        # 每轮固定做两次上滑，让列表真的在动、带出新内容，而不是只靠延时
        try:
            start_x = 540
            start_y = 1920
            end_x = 540
            end_y = 840
            device_factory.swipe(start_x, start_y, end_x, end_y, device_id=device_id, duration=260)
            time.sleep(0.35)
            device_factory.swipe(start_x, start_y, end_x, end_y, device_id=device_id, duration=260)
        except Exception:
            pass
        time.sleep(1.2)
        # 若本轮无可点，再多滑两次，明显多滚一截，触发懒加载后再 dump
        if not clicked_this_round:
            try:
                device_factory.swipe(start_x, start_y, end_x, end_y, device_id=device_id, duration=280)
                time.sleep(0.3)
                device_factory.swipe(start_x, start_y, end_x, end_y, device_id=device_id, duration=280)
            except Exception:
                pass
            time.sleep(1.0)

        # 至少完成 min_rounds_before_stable 轮后，且连续 consecutive_no_click_to_exit 轮无可点，才视为已全部展开并结束。
        if not clicked_this_round:
            same_count += 1
            if same_count >= consecutive_no_click_to_exit and (round_idx + 1) >= min_rounds_before_stable:
                # 退出前做一次“回滑复查”，避免前段房型漏展开
                if top_recheck_count < 2:
                    try:
                        sw, sh = _get_screen_size_via_adb(device_id)
                        sx = sw // 2
                        device_factory.swipe(sx, int(sh * 0.34), sx, int(sh * 0.84), device_id=device_id, duration=280)
                        time.sleep(0.7)
                        device_factory.swipe(sx, int(sh * 0.34), sx, int(sh * 0.84), device_id=device_id, duration=280)
                        time.sleep(0.7)
                    except Exception:
                        pass
                    top_recheck_count += 1
                    same_count = 0
                    print("检测到连续无可点：已执行回滑复查，继续下一轮，避免漏展开前段房型。")
                    continue
                print("已滑过多屏且连续多轮无可点展开位，认为已全部展开，结束展开步骤。")
                break
        else:
            same_count = 0
    else:
        # 达到 max_rounds 未 break 时提示
        if round_idx + 1 >= max_rounds:
            print("已达到最大展开轮数，若还有折叠项可适当增大 max_rounds。")


# ------------- 调用 1.py 抓取房型 -------------

def run_room_scrape_via_one_py(no_filter: bool = False) -> str:
    """
    以模块方式调用 1.py 的 collect_all_rooms + build_output_json。
    返回生成的 JSON 路径。
    """
    base = os.path.dirname(os.path.abspath(__file__))
    one_path = os.path.join(base, "1.py")
    if not os.path.isfile(one_path):
        raise FileNotFoundError(f"未找到 1.py: {one_path}")

    spec = importlib.util.spec_from_file_location("_one_script", one_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    print("[步骤] 调用 1.py 收集房型套餐")
    # OCR-only 采集：只从展开后的屏幕 OCR 解析套餐和价格
    rooms, page_info = mod.collect_all_rooms_ocr_only(no_filter=no_filter)
    data = mod.build_output_json(rooms, page_info, no_filter=no_filter)

    out_name = "1_nofilter.json" if no_filter else "1.json"
    out_path = os.path.join(base, out_name)
    import json

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已生成房型 JSON：{out_path}")
    return out_path


# ------------- 主流程 -------------

def main(expand_only: bool = False, no_filter: bool = False, aggressive_expand: bool = False):
    """
    从首页开始，一路到生成 1.json 的主入口。

    注意：
    - 运行前请确保手机已连接且当前在携程首页；
    - city / hotel_name 两个参数可以根据实际需要调整或改成命令行参数。
    """
    device_factory = get_device_factory()
    device_id = _resolve_device_id()
    if not device_id:
        print("未检测到可用设备，请先通过 adb 连接手机。")
        return
    print(f"使用设备: {device_id}")

    # 优先读取调度器传入的环境变量，未提供时才走默认值
    # test/app_scheduler.py 会写入 CTRIP_CITY / CTRIP_HOTEL_NAME
    city = (os.environ.get("CTRIP_CITY") or "上海").strip()
    hotel_name = (os.environ.get("CTRIP_HOTEL_NAME") or "丽呈美利居酒店").strip()
    print(f"搜索参数: city={city} hotel={hotel_name}")

    # 1. 首页 → 酒店搜索页
    entered = go_to_hotel_search(device_factory, device_id)
    if not entered:
        print("未能从首页进入酒店搜索页，主流程停止。")
        return
    time.sleep(1.0)

    # 2. 填写搜索条件并查询
    search_ok = fill_search_conditions(device_factory, device_id, city=city, hotel_keyword=hotel_name)
    if not search_ok:
        print("搜索步骤未完成，主流程停止。")
        return
    # 等查询结果/详情页切换：不要固定 sleep，避免你中断时误以为又点错了
    for _ in range(10):
        xml_now = _safe_get_ui_xml_via_u2(device_id, retry=1, sleep_sec=0.15)
        if xml_now and (
            "htl_x_dtl" in xml_now
            or "查看房型" in xml_now
            or "查询结果" in xml_now
            or "hotel_search_result" in xml_now
        ):
            break
        time.sleep(0.35)

    # 3. 在查询结果中点击目标酒店
    opened = open_hotel_from_result(device_factory, device_id, hotel_name=hotel_name)
    if not opened:
        print("未能从查询结果页进入酒店详情页，主流程停止。")
        return
    # 等详情页加载：不要固定 sleep 太久，改为短轮询确认页面已就绪，
    # 否则你手动 KeyboardInterrupt 会以为“又点错了”，但其实只是等加载。
    for attempt in range(5):
        xml_wait = _safe_get_ui_xml_via_u2(device_id, retry=1, sleep_sec=0.2)
        if xml_wait and (
            "htl_x_dtl_header_tab_exposure" in xml_wait
            or "htl_x_dtl_rmlist" in xml_wait
            or "查看房型" in xml_wait
            or "房型" in xml_wait
        ):
            break
        time.sleep(0.5)

    # 4. 抓取前强校验：允许纠偏点击一次，避免“进错页直接抓”。
    if not _ensure_room_page_before_scrape(device_factory, device_id, allow_tap_fix=True):
        return

    # 5. 由 Xiecheng.flow 串联：展开折叠区 -> OCR 识别套餐和价格 -> 导出 Android-/1.json
    from Xiecheng.flow import run as xiecheng_run

    xiecheng_run(
        device_factory,
        device_id,
        aggressive_expand=aggressive_expand,
        expand_only=expand_only,
        no_filter=no_filter,
        out_name="1.json",
    )


if __name__ == "__main__":
    import sys
    expand_only_flag = ("--expand-only" in sys.argv) or ("--expand" in sys.argv)
    no_filter_flag = ("--no-filter" in sys.argv) or ("--nofilter" in sys.argv)
    aggressive_expand_flag = ("--aggressive-expand" in sys.argv) or ("--expand-all" in sys.argv)
    main(
        expand_only=expand_only_flag,
        no_filter=no_filter_flag,
        aggressive_expand=aggressive_expand_flag,
    )


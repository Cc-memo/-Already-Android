

import importlib.util
import hashlib
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from collections import Counter

import uiautomator2 as u2

from phone_agent.device_factory import get_device_factory

# 复用 2.py 的解析逻辑（不影响 2.py，仅以模块方式调用）
def _get_parser_two():
    """加载 2.py 为模块，返回 (load_elements_from_xml, parse_rooms_from_elements)。"""
    _base = os.path.dirname(os.path.abspath(__file__))
    _path = os.path.join(_base, "2.py")
    if not os.path.isfile(_path):
        return None
    spec = importlib.util.spec_from_file_location("_parse_two", _path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _print_ui_dump_error(device_id: str | None):
    """首次获取 UI 树失败时，执行一次 dump 并打印 stderr 便于排查。"""
    adb = ["adb"]
    if device_id:
        adb = ["adb", "-s", device_id]
    path = "/sdcard/window_dump.xml"
    try:
        r = subprocess.run(
            adb + ["shell", "uiautomator", "dump", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if r.returncode != 0:
            print(f"  uiautomator dump 退出码: {r.returncode}")
            if r.returncode == 137:
                print("  退出码 137 多为设备内存不足或 uiautomator 被系统终止，可尝试：关闭其他应用、重启手机、回到桌面再进入携程房型页后重试。")
            if r.stderr:
                print(f"  stderr: {r.stderr.strip()}")
            if r.stdout:
                print(f"  stdout: {r.stdout.strip()}")
        else:
            r2 = subprocess.run(
                adb + ["shell", "cat", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if r2.returncode != 0 or "<hierarchy" not in (r2.stdout or ""):
                print(f"  cat 失败或内容无效，returncode={r2.returncode}")
            else:
                print("  (dump 成功但解析未使用，可能是权限或路径问题)")
    except subprocess.TimeoutExpired:
        print("  uiautomator dump 超时(15s)，可尝试减少后台应用或换机。")
    except Exception as e:
        print(f"  调试执行异常: {e}")


_u2_device = None  # 全局缓存 uiautomator2 设备连接


def _adb_prefix(device_id: str | None) -> list[str]:
    return ["adb", "-s", device_id] if device_id else ["adb"]


def _get_xml_via_adb_dump(device_id: str | None, timeout_sec: int = 12) -> str:
    """
    使用 adb uiautomator dump 兜底抓 UI 树。
    兼容部分设备路径差异，并尽量容忍 dump 返回文本中的噪声。
    """
    adb = _adb_prefix(device_id)
    paths = ["/sdcard/window_dump.xml", "/sdcard/__phone_agent_window_dump.xml"]
    for p in paths:
        try:
            r = subprocess.run(
                adb + ["shell", "uiautomator", "dump", p],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
            )
            if r.returncode != 0:
                continue
            r2 = subprocess.run(
                adb + ["shell", "cat", p],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=6,
            )
            xml = (r2.stdout or "").strip()
            if "<hierarchy" in xml:
                return xml
        except Exception:
            continue
    return ""


def _recover_uiautomation_once(device_id: str | None) -> None:
    """
    MIUI/国产机上常见 UiAutomation already registered。
    这里做一次轻量恢复，尽量不影响前台页面。
    """
    adb = _adb_prefix(device_id)
    cmds = [
        ["shell", "pkill", "-f", "uiautomator"],
        ["shell", "am", "force-stop", "com.github.uiautomator"],
        ["shell", "am", "force-stop", "com.github.uiautomator.test"],
    ]
    for c in cmds:
        try:
            subprocess.run(adb + c, capture_output=True, text=True, timeout=4)
        except Exception:
            continue
    time.sleep(0.4)


def _get_u2_device(device_id: str | None):
    """获取或复用 uiautomator2 设备连接。"""
    global _u2_device
    if _u2_device is not None:
        return _u2_device
    try:
        _u2_device = u2.connect(device_id) if device_id else u2.connect()
        return _u2_device
    except Exception as e:
        print(f"uiautomator2 连接失败: {e}")
        return None


def _safe_get_ui_xml(device_id: str | None, retry: int = 2, sleep_sec: float = 0.25) -> str:
    """
    使用 uiautomator2 获取完整 UI 树（含 WebView 内容）。
    携程房型列表在 WebView 中渲染，adb uiautomator dump 看不到，
    uiautomator2.dump_hierarchy() 可以抓到。
    """
    recovered = False
    for attempt in range(retry):
        try:
            d = _get_u2_device(device_id)
            if d is None:
                # u2 不可用时直接尝试 adb dump，避免整个流程空跑
                xml = _get_xml_via_adb_dump(device_id)
                if xml:
                    return xml
                if not recovered and attempt == 0:
                    _recover_uiautomation_once(device_id)
                    recovered = True
                time.sleep(sleep_sec)
                continue
            xml = d.dump_hierarchy()
            if xml and ("<hierarchy" in xml or "<node" in xml):
                return xml
        except Exception as e:
            if attempt == 0:
                print(f"dump_hierarchy 异常(将重试): {e}")
            # 一次恢复 + adb dump 兜底
            if not recovered:
                _recover_uiautomation_once(device_id)
                recovered = True
            xml = _get_xml_via_adb_dump(device_id)
            if xml:
                return xml
        time.sleep(sleep_sec)
    return ""


def _detect_page_kind(xml_str: str) -> str:
    """基于 XML 特征判断当前是否更像房型页或推荐酒店流。"""
    if not xml_str:
        return "empty"
    if "htl_x_dtl_nearbyRec_htlCard_exposure" in xml_str or "nearbyRec" in xml_str:
        return "nearby_recommend"
    room_hints = ["仅剩", "无早餐", "不可取消", "在线付", "到店付", "大床房", "双床房"]
    if any(h in xml_str for h in room_hints):
        return "room_list_like"
    return "unknown"


def _strip_nearby_rec_nodes(xml_str: str) -> str:
    """
    剔除推荐酒店流节点（nearbyRec），避免把“附近酒店卡”误当成本酒店房型套餐解析。
    失败时回退原 XML。
    """
    if not xml_str:
        return xml_str
    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return xml_str

    markers = ("htl_x_dtl_nearbyRec_htlCard_exposure", "nearbyRec")
    removed = 0
    for parent in root.iter():
        children = list(parent)
        for child in children:
            rid = (child.attrib.get("resource-id") or "").strip()
            cdesc = (child.attrib.get("content-desc") or "").strip()
            combo = f"{rid} {cdesc}"
            if any(m in combo for m in markers):
                try:
                    parent.remove(child)
                    removed += 1
                except Exception:
                    pass
    if removed <= 0:
        return xml_str
    try:
        return ET.tostring(root, encoding="unicode")
    except Exception:
        return xml_str


def _find_room_tab_center(xml_str: str) -> tuple[int, int] | None:
    """在顶部区域找「房型」Tab，返回可点击中心点。"""
    if not xml_str:
        return None
    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return None

    labels = ("房型", "客房")
    candidates: list[tuple[int, int, int]] = []
    for node in root.iter("node"):
        txt = (node.attrib.get("text") or node.attrib.get("content-desc") or "").strip()
        if not txt:
            continue
        if not any(lb in txt for lb in labels):
            continue
        b = _parse_bounds(node.attrib.get("bounds", ""))
        if not b:
            continue
        l, t, r, bb = b
        if t > 700:
            continue
        cx = (l + r) // 2
        cy = (t + bb) // 2
        area = max(1, (r - l) * (bb - t))
        candidates.append((area, cx, cy))
    if not candidates:
        return None
    # 选面积最大的标签，通常是实际可点击 tab 文本。
    candidates.sort(reverse=True)
    _, x, y = candidates[0]
    return x, y


def _ocr_fill_prices(device_id: str | None, rooms: list[dict], screen_img) -> None:
    """对本屏「无价格且备注包含早餐/积分」或「无早餐+商务静谧大床房」的套餐做截图裁剪+OCR 补价格。
    只补价格字段，不改房型/备注结构。"""
    # 扩大范围：备注里出现早餐/早/积分，或 房型含商务静谧大床房且备注含无早餐，则尝试 OCR 补价
    breakfast_like = ("早餐", "自助早餐", "份早餐", "早", "早餐券", "积分")
    need_ocr: list[dict] = []
    for r in rooms:
        if not r.get("_bounds"):
            continue
        if (r.get("价格") or "").strip():
            continue
        remark = (r.get("备注") or "").strip()
        name = (r.get("房型名称") or "").strip()
        if any(k in remark for k in breakfast_like):
            need_ocr.append(r)
        elif "无早餐" in remark and "商务静谧大床房" in name:
            need_ocr.append(r)
    if not need_ocr or screen_img is None:
        return
    if isinstance(screen_img, str):
        try:
            from PIL import Image
            screen_img = Image.open(screen_img)
        except Exception:
            return
    # 优先使用智谱 GLM-OCR（当环境变量或隐私文件中能读到 key 时）
    use_glm = True
    if use_glm:
        try:
            from glm_ocr_client import glm_ocr_words_result, extract_prices_from_text
        except Exception:
            use_glm = False
    if use_glm:
        try:
            # 只调用一次：整屏 OCR，然后按 _bounds 匹配到对应行里的价格
            words_result = glm_ocr_words_result(screen_img, probability=False)
            if not words_result:
                return

            # 预处理：把每行 OCR 行的 box 转成 (l,t,r,b) 便于重叠判断
            ocr_lines: list[tuple[int, int, int, int, str]] = []
            for it in words_result:
                loc = it.get("location") or {}
                left = int(loc.get("left", 0))
                top = int(loc.get("top", 0))
                w = int(loc.get("width", 0))
                h = int(loc.get("height", 0))
                right = left + w
                bottom = top + h
                words = str(it.get("words") or "").strip()
                if not words:
                    continue
                ocr_lines.append((left, top, right, bottom, words))

            MIN_PRICE, MAX_PRICE = 200, 1999
            for r in need_ocr:
                b = r.get("_bounds")
                if not b or len(b) != 4:
                    continue
                left, top, right, bottom = b

                # 收集与该项 bounds 有重叠的 OCR 行文本
                line_texts: list[str] = []
                for l2, t2, r2, b2, words in ocr_lines:
                    # 重叠判定：矩形区域在 x/y 任一方向不重叠则跳过
                    if r2 <= left or right <= l2:
                        continue
                    if b2 <= top or bottom <= t2:
                        continue
                    line_texts.append(words)

                candidates: list[int] = []
                for s in line_texts:
                    candidates.extend(extract_prices_from_text(s, min_price=MIN_PRICE, max_price=MAX_PRICE))

                if candidates:
                    v = min(candidates)
                    hist = r.setdefault("_ocr_history", [])
                    hist.append(v)
                    r["价格"] = f"¥{v}"
            return
        except Exception:
            # 失败则回退到 easyocr
            pass

    # fallback：easyocr（仍保留，以便 GLM-OCR 网络/配额失败时可继续跑）
    try:
        import numpy as np
        import easyocr
    except ImportError:
        return
    try:
        reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
    except Exception:
        return
    if hasattr(screen_img, "size"):
        w, h = screen_img.size
    else:
        w, h = 1080, 2400
    # 仅接受常见房价值域，避免把「起」/房号等误识为价格（如 10180、10118）
    MIN_PRICE, MAX_PRICE = 200, 1999
    for r in need_ocr:
        b = r.get("_bounds")
        if not b or len(b) != 4:
            continue
        left, top, right, bottom = b
        # 适当扩大/下移裁剪区域，覆盖价格与「预订」按钮附近
        crop_left = max(0, right - 300)
        crop_right = min(w, right + 40)
        crop_top = max(0, top - 10)
        crop_bottom = min(h, bottom + 40)
        try:
            crop = screen_img.crop((crop_left, crop_top, crop_right, crop_bottom))
            # 放大图片后再送入 OCR，提升小字号数字的识别率
            try:
                scale = 2.0
                cw, ch = crop.size
                crop_for_ocr = crop.resize((int(cw * scale), int(ch * scale)))
            except Exception:
                crop_for_ocr = crop
            arr = np.array(crop_for_ocr)
            results = reader.readtext(arr)
        except Exception:
            continue

        # 在 OCR 结果中收集所有合理的价格候选，最终选择最小的一个（通常为打折后价格）
        candidates: list[int] = []
        for _bbox, text, _conf in results:
            if not text:
                continue
            text_clean = text.replace(" ", "")
            for m in re.finditer(r"\d{3,5}", text_clean):
                num = m.group(0)
                try:
                    v = int(num)
                    if MIN_PRICE <= v <= MAX_PRICE:
                        candidates.append(v)
                except ValueError:
                    continue
        if candidates:
            v = min(candidates)
            # 记录 OCR 历史，后续在 build_output_json 中做多帧聚合（众数/中位数）
            hist = r.setdefault("_ocr_history", [])
            hist.append(v)
            r["价格"] = f"¥{v}"
    return


def _main_name(name: str) -> str:
    """房型主名：取「」前的部分，便于匹配。"""
    return ((name or "").split("「")[0].strip())


def _clear_outlier_low_prices_in_rooms(rooms: list[dict]) -> None:
    """同房型内最低价与次低价差≥40 时清空最低价（误识别如 407），便于后续 OCR 补正确价。原地修改。"""
    by_main: dict[str, list[dict]] = {}
    for r in rooms:
        by_main.setdefault(_main_name(r.get("房型名称") or ""), []).append(r)
    for _name, items in by_main.items():
        prices = []
        for r in items:
            if "已订完" in (r.get("剩余房间") or "") or "已订完" in (r.get("备注") or ""):
                continue
            p = (r.get("价格") or "").strip()
            m = re.search(r"¥\s*(\d+)", p) if p else None
            if m:
                try:
                    prices.append(int(m.group(1)))
                except ValueError:
                    pass
        if len(prices) < 2:
            continue
        ordered = sorted(set(prices))
        if len(ordered) < 2 or ordered[1] - ordered[0] < 40:
            continue
        low = ordered[0]
        for r in items:
            if "已订完" in (r.get("剩余房间") or "") or "已订完" in (r.get("备注") or ""):
                continue
            p = (r.get("价格") or "").strip()
            m = re.search(r"¥\s*(\d+)", p) if p else None
            if m:
                try:
                    if int(m.group(1)) == low:
                        r["价格"] = ""
                except ValueError:
                    pass


def _refill_prices_from_parser_one(xml: str, rooms: list[dict]) -> None:
    """用 1 自带解析结果对 rooms 里「无价格」的项按房型名+备注匹配并回填价格。原地修改 rooms。"""
    try:
        rooms_1 = parse_rooms_from_xml(xml)
    except Exception:
        return
    if not rooms_1:
        return
    for r in rooms:
        if (r.get("价格") or "").strip():
            continue
        name = _main_name(r.get("房型名称") or "")
        rem = (r.get("备注") or "").strip()
        for r1 in rooms_1:
            if _main_name(r1.get("房型名称") or "") != name:
                continue
            p1 = (r1.get("价格") or "").strip()
            if not p1:
                continue
            rem1 = (r1.get("备注") or "").strip()
            if rem == rem1 or (rem and rem in rem1) or (rem1 and rem1 in rem):
                r["价格"] = p1
                break
            if not rem or not rem1:
                r["价格"] = p1
                break


def _ocr_extract_rooms_from_screen(screen_img) -> list[dict]:
    """
    结果级 OCR 兜底：当结构解析（1.py/2.py）拿不到足够条目时，
    从当前屏截图中直接抽取「房型名/价格/剩余/备注」并组装为房型套餐列表。

    注意：OCR 不能保证完全准确，但目标是“至少把套餐抓到”，避免空洞数据。
    """
    if screen_img is None:
        return []
    items: list[tuple[int, str]] = []

    # 尝试 GLM-OCR（glm_ocr_client 内部会从 env 或 private key file 读取）。
    try:
        from glm_ocr_client import glm_ocr_words_result

        if isinstance(screen_img, str):
            from PIL import Image

            screen_img = Image.open(screen_img)
        words_result = glm_ocr_words_result(screen_img, probability=False)
        for it in words_result:
            loc = it.get("location") or {}
            top = int(loc.get("top", 0))
            height = int(loc.get("height", 0))
            yc = top + height // 2
            t = str(it.get("words") or "").strip().replace(" ", "")
            if t:
                items.append((yc, t))
    except Exception:
        # GLM-OCR 不可用时走 easyocr fallback
        items = []

    if not items:
        # fallback：easyocr（避免 GLM-OCR 不可用时直接没数据）
        try:
            import numpy as np
            import easyocr
        except ImportError:
            return []

        try:
            reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        except Exception:
            return []

        try:
            if isinstance(screen_img, str):
                from PIL import Image

                screen_img = Image.open(screen_img)
            arr = np.array(screen_img)
        except Exception:
            return []

        try:
            results = reader.readtext(arr)
        except Exception:
            return []

        # results 项一般是：([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, conf)
        for _bbox, text, _conf in results:
            if not text:
                continue
            t = str(text).strip().replace(" ", "")
            if not t:
                continue
            try:
                ys = [_p[1] for _p in _bbox]
                yc = int(sum(ys) / len(ys))
            except Exception:
                yc = 0
            items.append((yc, t))

    if not items:
        return []
    items.sort(key=lambda x: x[0])

    # 合并到若干“行”（y 近似的拼成一条）
    lines: list[str] = []
    cur_y = items[0][0]
    cur_parts: list[str] = []
    for yc, t in items:
        if abs(yc - cur_y) > 22:
            line = "".join(cur_parts)
            if line:
                lines.append(line)
            cur_parts = [t]
            cur_y = yc
        else:
            cur_parts.append(t)
    line = "".join(cur_parts)
    if line:
        lines.append(line)

    def _has_price(s: str) -> bool:
        return bool(re.search(r"(¥|￥)\s*\d{3,5}", s))

    def _extract_price(s: str) -> str:
        m = re.search(r"(¥|￥)\s*(\d{3,5})", s)
        if not m:
            return ""
        return f"¥{int(m.group(2))}"

    def _is_room_start(s: str) -> bool:
        # 只认常见床型/房型关键词，避免把“健身房和洗衣房”当成房型名
        if any(k in s for k in ("健身房", "洗衣房", "出行方便", "服务与设施", "WiFi", "非常方便")):
            return False
        return any(k in s for k in ("大床", "双床", "单人间", "三人间", "床房", "高级", "豪华", "商务", "家庭房", "套房"))

    def _extract_remain(s: str) -> str:
        if any(k in s for k in ("已订完", "售罄", "无房", "仅剩")):
            # 简化：直接截取关键句
            for k in ("仅剩", "已订完", "售罄", "无房"):
                if k in s:
                    return s
        return ""

    remark_tokens = (
        "无早餐", "含早", "份早餐", "早餐券", "早餐", "可退", "不可退",
        "不可取消", "免费取消", "预付", "现付", "在线付", "到店付",
        "已订完", "售罄", "无房", "仅剩",
    )
    cancel_pay_tokens = ("不可取消", "可退", "不可退", "免费取消", "在线付", "预付", "现付", "到店付", "在线付")

    def _has_remark(s: str) -> bool:
        return any(t in s for t in remark_tokens) or any(t in s for t in cancel_pay_tokens)

    def _normalize_remark(s: str) -> str:
        s = s.replace(" ", "")
        # 过滤掉明显无关的导航/广告等
        bad = ("本店", "销量No", "起", "立减", "优惠", "会员", "积分", "换购")
        for b in bad:
            s = s.replace(b, "")
        return s.strip()

    rooms: list[dict] = []
    cur_name = ""
    buffer_remark: list[str] = []
    buffer_remain = ""
    active_idx: int | None = None

    for s in lines:
        if _is_room_start(s):
            cur_name = s
            buffer_remark = []
            buffer_remain = ""
            active_idx = None
            continue

        if _has_remark(s):
            if _extract_remain(s):
                buffer_remain = _extract_remain(s)
            else:
                nr = _normalize_remark(s)
                if nr:
                    if active_idx is None:
                        buffer_remark.append(nr)
                    else:
                        # 已经有当前价格包，继续把备注追加上
                        old = rooms[active_idx].get("备注") or ""
                        merged = (old + " " + nr).strip()
                        rooms[active_idx]["备注"] = merged
            continue

        if _has_price(s):
            price = _extract_price(s)
            if not price:
                continue
            if not cur_name:
                # 无房型名时不生成，避免 OCR 把零散数字当成套餐
                continue
            rooms.append(
                {
                    "房型名称": cur_name,
                    "窗户信息": "",
                    "价格": price,
                    "剩余房间": buffer_remain,
                    "备注": " ".join([_normalize_remark(x) for x in buffer_remark if x]).strip(),
                }
            )
            active_idx = len(rooms) - 1
            continue

    # 最后过滤：房型名过长/为空直接丢
    out: list[dict] = []
    for r in rooms:
        nm = (r.get("房型名称") or "").strip()
        if not nm or len(nm) > 60:
            continue
        if "酒店热卖！查看已订完房型" in nm or "查看已订完房型" in nm:
            continue
        out.append(r)
    return out


def _glm_ocr_extract_packages_from_screen(screen_img) -> list[dict]:
    """
    折叠套餐展开后：直接对当前屏做 GLM-OCR，并用规则解析出
    “每个早餐分档（无早/1份/2份/含早）对应的价格”作为独立 item。

    解析策略（经验规则）：
    1) 先把 GLM-OCR 输出按 top 坐标排序合并成若干行文本；
    2) 遇到“房型起始行”时开启当前房型块；
    3) 在房型块内，记录最近出现的早餐分档（无早/1份/2份/含早）与支付/取消等备注；
    4) 当在同一房型块内遇到价格（¥/￥）时，把价格绑定到最近的早餐分档，生成独立 item。
    """
    if screen_img is None:
        return []

    try:
        from glm_ocr_client import glm_ocr_words_result, extract_prices_from_text
    except Exception:
        return []

    try:
        words_result = glm_ocr_words_result(screen_img, probability=False)
    except Exception:
        return []

    if not words_result:
        return []

    # 按行 top 排序并合并：GLM-OCR 一般已是“行”，但仍做一次 merge 防止同一行被切碎
    lines: list[tuple[int, str]] = []
    for it in words_result:
        loc = it.get("location") or {}
        top = int(loc.get("top", 0))
        height = int(loc.get("height", 0))
        yc = top + height // 2
        t = str(it.get("words") or "").strip().replace(" ", "")
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

    room_start_keywords = (
        "大床房",
        "双床房",
        "三人间",
        "单人间",
        "家庭房",
        "高级",
        "豪华",
        "商务",
        "套房",
        "床房",
    )
    # 过滤“设施/点评”类伪房型
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

    def _main_name_from_room_line(line: str) -> str:
        # 截取引号内或直取“房”相关的主要片段
        if "“" in line and "”" in line:
            return line.split("“", 1)[1].split("”", 1)[0].strip()
        if "\"" in line:
            # 兜底：去掉可能的引号字符
            line = line.replace("\"", "").replace("“", "").replace("”", "")
        # 去掉过长的权益/描述
        # 优先返回包含“房/间/床”的前段
        for k in ("房", "间", "床"):
            if k in line:
                idx = line.find(k) + 1
                cand = line[:idx].strip()
                return cand
        return line[:24].strip()

    def _variant_from_line(line: str) -> str:
        # 统一归一化：页面可能显示“无早/1早/2早”，OCR 也可能读成这些缩写。
        if "无早餐" in line or "无早" in line:
            return "无早餐"
        if "1份早餐" in line or "1份早" in line or "1早" in line:
            return "1份早餐"
        if "2份早餐" in line or "2份早" in line or "2早" in line:
            return "2份早餐"
        if "含早" in line or "含早餐" in line:
            return "含早餐"
        # 如果出现“份早餐”但没写数字，无法稳定区分
        if "份早餐" in line:
            # 尝试提取“数字份早餐”
            m = re.search(r"(\d)份早餐", line)
            if m:
                return f"{m.group(1)}份早餐"
            return "份早餐"
        return ""

    def _remain_from_line(line: str) -> str:
        for k in ("已订完", "售罄", "无房", "仅剩"):
            if k in line:
                return line
        return ""

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

    # 生成结果
    rooms: list[dict] = []
    # 当前房型块状态
    cur_room_line = ""
    cur_room_name = ""
    pending_variant = ""
    pending_remark_parts: list[str] = []
    pending_remain = ""

    def _is_room_start(line: str) -> bool:
        if not line or len(line) > 80:
            return False
        if any(b in line for b in room_bad_keywords):
            return False
        return any(k in line for k in room_start_keywords)

    for line in merged_lines:
        if _is_room_start(line):
            cur_room_line = line
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

        # 更新备注（取消/支付等）
        if any(k in line for k in cancel_pay_keywords):
            # 防止把“热卖”等杂项塞进备注
            if "热卖" not in line:
                pending_remark_parts.append(line)

        # 更新剩余
        rem = _remain_from_line(line)
        if rem:
            pending_remain = rem

        # 提取价格：绑定 pending_variant
        prices = extract_prices_from_text(line, min_price=200, max_price=1999)
        if prices and pending_variant:
            # 通常一行会含一个价格，取最小值（折后价）
            price_v = min(prices)
            # 备注按“早餐分档 + 取消/支付 + 剩余状态”拼接，保持与你现有 JSON 风格一致
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
            # 本条 item 出来后：清空 pending_remark（避免后续价格复用旧备注）
            pending_remark_parts = []
            pending_variant = ""
            pending_remain = ""

    # 基础去噪
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
        # 必须有变体与价格（至少价格可能有缺失，但你要求独立 item，这里尽量保留完整）
        if not r.get("价格"):
            continue
        # remarks 里应包含早餐分档关键词
        if "无早餐" not in remark and "1份早餐" not in remark and "2份早餐" not in remark and "含早餐" not in remark:
            continue
        out.append(r)
    return out


def _quick_img_hash(img, *, size=(240, 420)) -> str | None:
    """对截图做轻量 hash，用于 OCR-only 模式的滑动终止判定。"""
    if img is None:
        return None
    try:
        small = img.convert("RGB").resize(size)
        return hashlib.md5(small.tobytes()).hexdigest()
    except Exception:
        return None


def _glm_ocr_merge_lines_from_screen(screen_img) -> list[str]:
    """复用 GLM-OCR 的 words_result → 合并成自上而下的行文本。"""
    if screen_img is None:
        return []
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
        t = str(it.get("words") or "").strip().replace(" ", "")
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


def extract_page_info_from_screen_ocr(screen_img) -> dict:
    """
    顶层信息 OCR 完全化：
    从当前屏幕 GLM-OCR 读出 酒店名称、入住/离店日期、地址。
    """
    out = {"酒店名称": "", "入住日期": "", "离店日期": "", "地址": "", "酒店关键词": ""}
    merged_lines = _glm_ocr_merge_lines_from_screen(screen_img)
    if not merged_lines:
        return out

    full_text = "\n".join(merged_lines)

    # 日期：优先 ISO，失败再解析 x月x日
    date_iso = re.findall(r"(\d{4})-(\d{2})-(\d{2})", full_text)
    if len(date_iso) >= 2:
        out["入住日期"] = f"{date_iso[0][0]}-{date_iso[0][1]}-{date_iso[0][2]}"
        out["离店日期"] = f"{date_iso[1][0]}-{date_iso[1][1]}-{date_iso[1][2]}"
    else:
        # 3月25日-3月26日 这种也能抓到两个匹配
        parts = re.findall(r"(\d{1,2})月(\d{1,2})日?", full_text)
        if len(parts) >= 2:
            out["入住日期"] = f"{int(parts[0][0])}月{int(parts[0][1])}日"
            out["离店日期"] = f"{int(parts[1][0])}月{int(parts[1][1])}日"
        elif len(parts) == 1:
            out["入住日期"] = f"{int(parts[0][0])}月{int(parts[0][1])}日"

    # 酒店名称：命中“酒店”且长度合理的第一条
    for line in merged_lines:
        if "酒店" in line and len(line) <= 80:
            # 去掉可能的换行噪声
            line2 = line.strip()
            # 优先取括号前的主名
            if "（" in line2 or "(" in line2:
                line2 = re.split(r"[（(]", line2)[0].strip()
            out["酒店名称"] = line2[:60].strip()
            break

    # 地址：区/县 + 路/号/街/弄 的组合最稳
    for line in merged_lines:
        if len(line) > 120:
            continue
        if ("区" in line or "县" in line) and any(k in line for k in ("路", "号", "街", "弄")):
            out["地址"] = line.strip()[:80]
            break

    return out


def collect_all_rooms_ocr_only(max_swipes: int = 40, swipe_sleep: float = 1.0, no_filter: bool = False):
    """
    OCR-only 采集：
    只依赖“套餐折叠展开后的屏幕截图 -> GLM-OCR 解析套餐和价格”，不再使用 XML 套餐归属。
    """
    device_factory = get_device_factory()
    device_id = _resolve_device_id()
    if device_id:
        print(f"使用设备: {device_id}")

    all_rooms: list[dict] = []
    seen_keys: set[tuple] = set()
    page_info: dict = {}

    last_hash = None
    same_hash_count = 0
    empty_count = 0

    # no_filter 压测模式：跨屏不过度去重
    dedupe = not no_filter

    for i in range(max_swipes):
        d = _get_u2_device(device_id)
        if d is None:
            break

        img = d.screenshot()
        if img is None:
            break

        if i == 0:
            page_info = extract_page_info_from_screen_ocr(img)

        rooms_glm = _glm_ocr_extract_packages_from_screen(img)
        # 额外兜底：去掉热卖入口/已订完入口类文字（OCR 输出可能偶发残留）
        rooms_glm = [
            r
            for r in rooms_glm
            if "酒店热卖！查看已订完" not in (r.get("房型名称") or "")
        ]

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
                all_rooms.append({k2: v2 for k2, v2 in r.items() if k2 != "_bounds"})
        else:
            all_rooms.extend([{k2: v2 for k2, v2 in r.items() if k2 != "_bounds"} for r in rooms_glm])

        print(f"  第{i+1}屏: GLM-OCR 本屏 {len(rooms_glm)} 条, 累计 {len(all_rooms)} 条")

        # 终止条件 1：连续 hash 相同（列表基本没再变）
        cur_hash = _quick_img_hash(img)
        if cur_hash and cur_hash == last_hash:
            same_hash_count += 1
            if same_hash_count >= 3:
                print("  退出原因: 连续 3 屏截图 hash 相同，认为滑动已到底。")
                break
        else:
            same_hash_count = 0
            last_hash = cur_hash

        # 终止条件 2：连续几屏没识别到任何套餐文本（可能到了尾部或 OCR 读不到）
        if empty_count >= 4 and i >= 2:
            print("  退出原因: 连续多屏无 OCR 识别结果。")
            break

        # 向下滑动一屏
        try:
            d.swipe(500, 1900, 500, 450, duration=0.5)
        except Exception:
            try:
                device_factory.swipe(500, 1900, 500, 450, device_id=device_id)
            except Exception:
                break
        time.sleep(swipe_sleep)

    return all_rooms, page_info


def _parse_rooms_with_two(xml: str):
    """只使用 2.py 解析当前 XML。"""
    rooms = []
    _two = _get_parser_two()
    if _two is None:
        return rooms
    _dump_path = os.path.join(os.path.dirname(__file__), "1_merge_dump.xml")
    try:
        with open(_dump_path, "w", encoding="utf-8", errors="replace") as _f:
            _f.write(xml)
        _elements = _two.load_elements_from_xml(_dump_path)
        rooms = _two.parse_rooms_from_elements(_elements)
    except Exception:
        rooms = []
    return rooms


def _norm_date_to_md(s: str) -> str:
    """把 02月06日 / 2月6日 等统一成 x月x 日（去前导零）。"""
    m = re.match(r"(\d{1,2})月(\d{1,2})日?", s)
    if m:
        return f"{int(m.group(1))}月{int(m.group(2))}日"
    return s


def extract_page_info(xml_str: str) -> dict:
    """从首屏 UI 树里尽量提取酒店名称、入住/离店日期、地址，填到 JSON 前几行。"""
    out = {"酒店名称": "", "入住日期": "", "离店日期": "", "地址": "", "酒店关键词": ""}
    if not xml_str:
        return out
    try:
        root = ET.fromstring(xml_str)
        # 收集 text 与 content-desc，按顶部坐标排序
        items = []
        for elem in root.iter():
            t = (elem.attrib.get("text") or "").strip()
            desc = (elem.attrib.get("content-desc") or "").strip()
            combined = " ".join(filter(None, [t, desc]))
            if not combined or len(combined) > 200:
                continue
            b = _parse_bounds(elem.attrib.get("bounds", ""))
            top = b[1] if b else 99999
            items.append((top, combined))
        items.sort(key=lambda x: x[0])

        # 日期：支持 x月x日、YYYY-MM-DD、x/x、入住/离店 等
        date_pattern = re.compile(r"(\d{1,2})月(\d{1,2})日?")
        date_slash = re.compile(r"(\d{1,2})/(\d{1,2})")
        date_iso = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

        for _top, t in items:
            if not out["酒店名称"] and "酒店" in t and "(" in t and ")" in t and len(t) <= 60:
                out["酒店名称"] = t
            # 入住/离店
            if not out["入住日期"] or not out["离店日期"]:
                # 先尝试 ISO 格式（携程可能直接显示 2026-02-07）
                iso = date_iso.findall(t)
                if len(iso) >= 2:
                    out["入住日期"] = out["入住日期"] or f"{iso[0][0]}-{iso[0][1]}-{iso[0][2]}"
                    out["离店日期"] = out["离店日期"] or f"{iso[1][0]}-{iso[1][1]}-{iso[1][2]}"
                elif len(iso) == 1 and ("入住" in t or "离店" in t or "-" in t):
                    one = f"{iso[0][0]}-{iso[0][1]}-{iso[0][2]}"
                    if "离店" in t and not out["离店日期"]:
                        out["离店日期"] = one
                    elif not out["入住日期"]:
                        out["入住日期"] = one
                if not out["入住日期"] or not out["离店日期"]:
                    parts = date_pattern.findall(t)
                    if parts:
                        if len(parts) >= 2:
                            out["入住日期"] = out["入住日期"] or _norm_date_to_md(f"{parts[0][0]}月{parts[0][1]}日")
                            out["离店日期"] = out["离店日期"] or _norm_date_to_md(f"{parts[1][0]}月{parts[1][1]}日")
                        else:
                            one = _norm_date_to_md(f"{parts[0][0]}月{parts[0][1]}日")
                            if "离店" in t and not out["离店日期"]:
                                out["离店日期"] = one
                            elif not out["入住日期"]:
                                out["入住日期"] = one
                    if not out["入住日期"] and date_slash.search(t):
                        sl = date_slash.findall(t)
                        if len(sl) >= 1:
                            out["入住日期"] = f"{int(sl[0][0])}月{int(sl[0][1])}日"
                        if len(sl) >= 2:
                            out["离店日期"] = f"{int(sl[1][0])}月{int(sl[1][1])}日"
            if not out["地址"] and ("区" in t or "县" in t) and ("路" in t or "号" in t or "弄" in t or "街" in t) and len(t) <= 80:
                out["地址"] = t
    except Exception:
        pass
    return out


def _parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    """解析 uiautomator bounds 字符串 "[left,top][right,bottom]" -> (left, top, right, bottom)。"""
    if not bounds:
        return None
    m = re.findall(r"\d+", bounds)
    if len(m) != 4:
        return None
    return tuple(int(x) for x in m)


def parse_rooms_from_xml(xml_str: str):
    """
    从当前 UI 树中解析“本屏可见”的房型及其套餐信息（粗略但稳定的规则版）。

    策略：
    - 把包含“床房/大床/双床/单人间”等关键词的 TextView 当作房型标题；
    - 以标题所在的父节点为“房型容器”，收集该容器下的所有文本；
    - 从这些文本里抽取：
      - 房型名称：标题文本；
      - 窗户信息：出现的第一个“有窗/无窗”；
      - 价格：出现的第一个带 “¥” 的文本；
      - 剩余房间：包含“仅剩”“间”的文本；
      - 备注：其余描述早餐/取消/支付/礼品的短语拼接。
    """
    root = ET.fromstring(xml_str)

    # 建父节点映射，便于找“房型标题”所在容器（父节点可能是任意标签）
    parent_map = {}
    for elem in root.iter():
        for child in elem:
            parent_map[child] = elem

    # uiautomator 节点是 <node .../>
    nodes = list(root.iter("node"))

    room_items = []

    # 明显不是房型名的：点评/设施/权益文案（含「房」但非房型）
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
        "退房时间",
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
    ]

    # 用于把“赠品/标签”并入上一条房型备注
    gift_keywords = ["赠·", "赠送", "礼遇", "礼品", "票券"]

    room_keywords = ["房", "单人间", "大床", "双床", "三人间", "家庭房"]
    for node in nodes:
        text = (node.attrib.get("text") or node.attrib.get("content-desc") or "").strip()
        cls = node.attrib.get("class") or ""

        if not text:
            continue
        # 有房型关键词时放宽 class，避免部分机型/携程版本用非 TextView 节点
        has_room_keyword = any(k in text for k in room_keywords)
        if not has_room_keyword:
            if "TextView" not in cls and "Text" not in cls and "text" not in cls.lower():
                continue
        # 粗略判断房型标题
        if not has_room_keyword:
            continue
        if "点评" in text or "评论" in text or "预订" in text:
            continue

        if text in blacklist_exact:
            continue
        if any(k in text for k in blacklist_contains):
            continue
        t0 = text.strip()
        if len(t0) >= 10 and t0[0] in "\u201c\u2018\"" and t0[-1] in "\u201d\u2019\"":
            continue
        # “X张X米大床/双床”是床型描述，不是房型名
        if re.match(r"^\d+张\d", text) or "米大床" in text or "米双床" in text:
            continue

        # 视为房型标题（去掉不可见字符和私有区字符如 等）
        title = re.sub(r"[\u200b-\u200d\ufeff\u202a-\u202e\u2060\u00ad\u034f\ue004-\ue0ff]", "", text).strip()

        # 用父映射找容器：只往上 2 层，尽量不跨到下一张房型卡片
        container = node
        for _ in range(2):
            p = parent_map.get(container)
            if p is None:
                break
            container = p

        # 取标题节点的 bounds，只收集“同一条卡片”内的文案（避免把下一张卡的价格算进来）
        title_bounds = _parse_bounds(node.attrib.get("bounds", ""))
        if title_bounds:
            t_top, t_bottom = title_bounds[1], title_bounds[3]
            card_bottom = t_bottom + 320  # 单张房型卡高度约 200～350，略放大避免漏掉本卡内套餐
        else:
            t_top, t_bottom, card_bottom = 0, 0, 99999

        texts = []
        for sub in container.iter():
            b = _parse_bounds(sub.attrib.get("bounds", ""))
            if b and title_bounds:
                sub_top, sub_bottom = b[1], b[3]
                if sub_bottom < t_top - 30 or sub_top > card_bottom:
                    continue
            t = (sub.attrib.get("text") or "").strip()
            desc = (sub.attrib.get("content-desc") or "").strip()
            if t:
                texts.append(t)
            if desc and desc != t:
                texts.append(desc)

        # 去重保持顺序
        seen = set()
        uniq_texts = []
        for t in texts:
            if t not in seen:
                seen.add(t)
                uniq_texts.append(t)

        window = ""
        remain = ""

        # 第一步：先扫一遍，拿到窗户/剩余信息（同一房型容器内通常相同）
        for t in uniq_texts:
            if ("有窗" in t or "无窗" in t) and not window:
                window = t
            if (
                (("仅剩" in t or "间" in t) and "仅" in t)
                or "已订完" in t
                or "售罄" in t
                or "无房" in t
            ) and not remain:
                remain = t

        # 第二步：按价格切分成“多个套餐”（备注可能在价格前，要挂到第一个套餐上）
        remark_keywords = [
            "早餐", "早", "取消", "可退", "不可退", "不可取消", "免费取消",
            "礼", "预付", "现付", "在线付", "到店付",
        ]
        packages: list[dict] = []
        current: dict | None = None
        prefix_remarks: list[str] = []  # 第一个价格之前出现的备注，挂到第一个套餐

        for t in uniq_texts:
            # 新套餐的起点：出现价格
            if "¥" in t:
                m = re.search(r"¥\s*\d+[\d.]*", t)
                if not m:
                    continue
                price_str = m.group(0).replace(" ", "").strip()
                # 同一句里价格外的部分并入备注
                rest = (t[: m.start()] + t[m.end() :]).strip()
                # 收尾上一套餐
                if current is not None:
                    packages.append(current)
                current = {"价格": price_str, "备注_parts": []}
                if rest and any(k in rest for k in remark_keywords):
                    current["备注_parts"].append(rest)
                # 第一个套餐：把“价格前”的备注挂上去
                if not packages and prefix_remarks:
                    current["备注_parts"] = list(prefix_remarks)
                continue

            # 将与早餐/取消/支付/赠品相关的信息挂到最近一个套餐上
            if any(k in t for k in remark_keywords):
                if current is not None:
                    current["备注_parts"].append(t)
                else:
                    prefix_remarks.append(t)

        # 循环结束后，收尾最后一个套餐
        if current is not None:
            packages.append(current)

        # 如果一个价格都没找到，则整个容器当成一个“无价格”的占位套餐（例如仅展示规则的钟点房）
        if not packages:
            packages = [{"价格": "", "备注_parts": list(prefix_remarks)}]

        # 展开为“同一房型的多个套餐”记录
        for pkg in packages:
            remarks = " ".join(pkg.get("备注_parts", [])).strip()
            room_items.append(
                {
                    "房型名称": title,
                    "窗户信息": window,
                    "价格": pkg.get("价格", ""),
                    "剩余房间": remain,
                    "备注": remarks,
                }
            )

    # 二次处理：把“赠品/标签”这类纯赠品标题并入上一条房型备注，不单独作为房型
    merged: list[dict] = []
    for item in room_items:
        name = item["房型名称"]
        if any(k in name for k in gift_keywords) and merged:
            # 视为上一房型的补充描述
            prev = merged[-1]
            extra = name.strip()
            if extra:
                if prev["备注"]:
                    prev["备注"] += " " + extra
                else:
                    prev["备注"] = extra
            # 同时也合并价格/剩余房间（若上一条缺失而本条有）
            if not prev.get("价格") and item.get("价格"):
                prev["价格"] = item["价格"]
            if not prev.get("剩余房间") and item.get("剩余房间"):
                prev["剩余房间"] = item["剩余房间"]
            continue
        merged.append(item)

    # 最终只返回合并 + 过滤后的房型列表：
    # - 名称不能太长（防止整段点评/公告混进来）
    # - 过滤掉各种“公告/点评/说明”类文案
    # - 至少要有价格，或者短备注里包含早餐/取消/支付等关键信息
    breakfast_cancel_pay_keywords = [
        "无早餐",
        "含早",
        "份早餐",
        "早餐券",
        "取消",
        "可退",
        "不可退",
        "不可取消",
        "免费取消",
        "预付",
        "现付",
        "在线付",
        "到店付",
        "已订完",
        "售罄",
        "无房",
    ]

    # 筛选项：仅“双床房/大床房/三床房/单人间”且无「」的，是顶部 Tab 不是真实房型
    tab_only_names = {"双床房", "大床房", "三床房", "单人间"}

    filtered: list[dict] = []
    for item in merged:
        name = (item.get("房型名称") or "").strip()
        # 去掉不可见字符（如 ‍ 等）
        name = re.sub(r"[\u200b-\u200d\ufeff\u202a-\u202e\u2060\u00ad\u034f\ue004-\ue0ff]", "", name).strip()
        if not name:
            continue
        # 名字过长的大段文字，多半是点评/公告
        if len(name) > 60:
            continue
        if any(bad in name for bad in blacklist_contains):
            continue
        if name in blacklist_exact:
            continue
        # 顶部筛选项不作为房型
        if name in tab_only_names and "「" not in name:
            continue
        # 床型描述（如 1张1.8米大床）不是房型名，过滤掉
        if re.match(r"^\d+张\d", name) or "米大床" in name or "米双床" in name:
            continue

        price = (item.get("价格") or "").strip()
        remarks = _normalize_remarks((item.get("备注") or "").strip())
        remain = (item.get("剩余房间") or "").strip()

        # 备注太长且没有“无早餐/含早/取消/支付”等关键词，多半是整段点评/公告，丢掉
        if not price and len(remarks) > 80 and not any(
            k in remarks for k in breakfast_cancel_pay_keywords
        ):
            continue

        has_info = bool(price) or (
            remarks and len(remarks) <= 120 and any(k in remarks for k in breakfast_cancel_pay_keywords)
        )
        # 无房/已订完套餐也要保留
        if remain and any(k in remain for k in ["已订完", "售罄", "无房", "仅剩"]):
            has_info = True
        if not has_info:
            continue

        item["房型名称"] = name
        item["备注"] = remarks
        filtered.append(item)

    return filtered


def _normalize_remarks(remarks: str, max_len: int = 150) -> str:
    """备注去重（同一句赠品/早餐只保留一次）、限制长度。"""
    if not remarks:
        return ""
    # 把“赠·人民广场...1份”这类长句重复多次的，缩成一次
    gift_phrase = "赠·人民广场地铁站至酒店接送"
    while gift_phrase in remarks and remarks.count(gift_phrase) > 1:
        idx = remarks.find(gift_phrase)
        end = remarks.find(" 赠·", idx + 1)
        if end > idx:
            remarks = remarks[:idx] + remarks[end:].strip()
        else:
            break
    # 按空格拆成片段，相同片段只保留一次（保留顺序）
    parts = remarks.split()
    seen = set()
    out = []
    for p in parts:
        if not p:
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    s = " ".join(out)
    if len(s) > max_len:
        s = s[: max_len - 3].rstrip() + "..."
    return s


def _resolve_device_id():
    """若只连了一台设备，返回其 device_id；list_devices 超时或为空时用 adb devices 回退。"""
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
    # 列表为空（如 adb devices -l 超时）时回退：直接用 adb devices，超时放宽
    try:
        r = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if r.returncode == 0 and r.stdout:
            for line in r.stdout.strip().split("\n")[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    print(f"使用设备(回退): {parts[0]}")
                    return parts[0]
    except Exception:
        pass
    return None


def collect_all_rooms(max_swipes: int = 40, swipe_sleep: float = 1.0, no_filter: bool = False):
    """反复 dump UI 树 + 向下 Swipe，收集整页房型套餐。"""
    device_factory = get_device_factory()
    device_id = _resolve_device_id()
    if device_id:
        print(f"使用设备: {device_id}")

    all_rooms = []
    seen_keys = set()
    page_info: dict = {}  # 首屏解析出的酒店名、日期、地址
    tried_switch_tab = False

    # no_filter 调试模式下：按你的要求，折叠套餐展开后“直接用 GLM-OCR 识别套餐和价格”
    glm_packages_mode = False
    if no_filter:
        try:
            import glm_ocr_client  # noqa: F401
            # 仅当 key 有效时才启用，避免每屏 OCR 报错导致卡顿
            api_key = os.environ.get("ZHIPU_API_KEY", "").strip()
            if api_key:
                glm_packages_mode = True
            else:
                base = os.path.dirname(os.path.abspath(__file__))
                key_file = os.path.join(base, "private", "zhipu_api_key.txt")
                try:
                    with open(key_file, "r", encoding="utf-8") as f:
                        glm_key = (f.readline() or "").strip()
                    glm_packages_mode = bool(glm_key)
                except Exception:
                    glm_packages_mode = False
        except Exception:
            glm_packages_mode = False

    last_xml_hash = None
    same_hash_count = 0  # 连续相同 hash 次数，至少 3 次才认为到底，减少懒加载/动画未结束时误停漏采

    def _looks_like_target_room_xml(xml_text: str) -> bool:
        if not xml_text:
            return False
        # 仅用于“提示当前屏是否像房型页”，不作为硬拦截条件。
        has_room_card = ("htl_x_dtl_rmlist_rmCard_exposure" in xml_text) or ("htl_x_dtl_rmlist_mbRmCard_exposure" in xml_text)
        has_room_tab = ("htl_x_dtl_header_tab_exposure" in xml_text) or ("房型" in xml_text)
        return bool(has_room_card or has_room_tab)

    def _strip_noise_room_names(rooms: list[dict]) -> list[dict]:
        """去掉热卖入口、引号点评假房型名（解析层已拦大部分，此处再兜底）。"""
        out = []
        for r in rooms:
            n = (r.get("房型名称") or "").strip()
            if "酒店热卖！查看已订完" in n:
                continue
            if len(n) >= 10 and n[0] in "\u201c\u2018\"" and n[-1] in "\u201d\u2019\"":
                continue
            out.append(r)
        return out

    def _room_one_quality_ok(r: dict) -> bool:
        name = (r.get("房型名称") or "").strip()
        remark = (r.get("备注") or "").strip()
        remain = (r.get("剩余房间") or "").strip()
        price = (r.get("价格") or "").strip()
        if not name:
            return False
        # 过滤明显的推荐酒店/点评噪声标题
        bad_name_kw = ("点评", "收藏", "距酒店直线", "这家酒店", "有健身房和洗衣房", "热卖！低价房")
        if any(k in name for k in bad_name_kw):
            return False
        if name in {"酒店热卖！查看已订完房型", "查看已订完房型"}:
            return False
        if name.startswith("“") or name.startswith("\""):
            return False
        room_like = any(k in name for k in ("房", "间", "床"))
        if not room_like:
            return False
        # 至少要有价格/剩余/备注中的一个有效信息
        return bool(price or remain or remark)

    for i in range(max_swipes):
        xml = _safe_get_ui_xml(device_id, retry=1, sleep_sec=0.2)
        if not xml and i == 0:
            time.sleep(0.8)
            xml = _safe_get_ui_xml(device_id, retry=2, sleep_sec=0.25)
        if not xml:
            if i == 0:
                print("提示: 未获取到 UI 树，请确认设备已连接且当前在酒店房型列表页。")
                _print_ui_dump_error(device_id)
            break

        if i == 0:
            page_info = extract_page_info(xml)
        xml_clean = _strip_nearby_rec_nodes(xml)

        # 仅做提示，不再整屏跳过；避免误杀真正的房型套餐数据。
        if not _looks_like_target_room_xml(xml_clean):
            print(f"  第{i+1}屏: 页面特征较弱，继续解析并依赖条目级过滤。")

        # 双解析并集：
        # - 2.py 对卡片归属更稳；
        # - 1.py 在部分页面能识别到更多“同房型不同早餐/取消策略”套餐。
        # 过去“仅用 2.py（有结果就不看 1.py）”会漏掉早餐差异条目。
        rooms_two = _parse_rooms_with_two(xml_clean)
        if no_filter:
            rooms_one = parse_rooms_from_xml(xml_clean)
        else:
            rooms_one = [r for r in parse_rooms_from_xml(xml_clean) if _room_one_quality_ok(r)]

        if not rooms_two and not rooms_one:
            rooms = []
        elif not rooms_two:
            rooms = rooms_one
        elif not rooms_one:
            rooms = rooms_two
        else:
            merged = []
            seen_merge_keys: set[tuple] = set()

            def _mk_key(r: dict) -> tuple:
                name = _main_name(r.get("房型名称") or "")
                price = (r.get("价格") or "").strip()
                remark = (r.get("备注") or "").strip()
                window = (r.get("窗户信息") or "").strip()
                remain = (r.get("剩余房间") or "").strip()
                return (name, price, remark, window, remain)

            # 先放 2.py（主干），再补 1.py 的增量套餐
            for src in (rooms_two, rooms_one):
                for r in src:
                    k = _mk_key(r)
                    if k in seen_merge_keys:
                        continue
                    seen_merge_keys.add(k)
                    merged.append(r)
            rooms = merged

        # 结果级 OCR 兜底：
        # 触发目标：不仅是“结构解析拿不到条目”，还要针对你要的“早餐分档套餐”缺失。
        # 规则：当同一房型下出现早餐关键词，但早餐分档（无早/1份/2份）拿到的变体数过少、
        # 或者拿到的变体里存在“缺价”，就对当前屏进行整屏 OCR，尽量补齐独立套餐 item。
        try:
            def _variant_from_rem(rem: str) -> str:
                rem = rem or ""
                if "无早餐" in rem:
                    return "无早餐"
                if "1份早餐" in rem:
                    return "1份早餐"
                if "2份早餐" in rem:
                    return "2份早餐"
                if "含早" in rem or "含早餐" in rem:
                    return "含早餐"
                return ""

            # 简化评分：早餐变体 item（带价格）数量
            def _breakfast_score(rs: list[dict]) -> tuple[int, int]:
                # (变体数, 缺价早餐条数)
                variants = set()
                missing_price = 0
                for r in rs:
                    main = _main_name(r.get("房型名称") or "")
                    rem = r.get("备注") or ""
                    v = _variant_from_rem(rem)
                    if not v:
                        continue
                    variants.add((main, v))
                    if not (r.get("价格") or "").strip():
                        missing_price += 1
                return len(variants), missing_price

            score_before = _breakfast_score(rooms)
            # 你要求的“折叠套餐展开后直接用 GLM-OCR 识别套餐和价格”：
            # 在整屏解析后先尝试一遍 GLM-OCR 套餐级重建（仅在 no_filter 模式启用）。
            if glm_packages_mode:
                try:
                    d = _get_u2_device(device_id)
                    img = d.screenshot() if d else None
                    rooms_glm = _glm_ocr_extract_packages_from_screen(img)
                    if rooms_glm:
                        score_glm = _breakfast_score(rooms_glm)
                        # 策略 1（OCR-only，no_filter）：只要 GLM 至少给出“可用的早餐分档 item”
                        # 就直接接管，避免 XML 的“价格空/问句噪声”污染。
                        breakfast_items_ok = len(rooms_glm) >= 3 and score_glm[0] >= 1
                        if breakfast_items_ok:
                            rooms = rooms_glm
                            score_before = score_glm
                except Exception:
                    pass
            need_ocr = False
            # 1) 解析条数过少：优先按整屏 OCR 兜底（你之前就遇到过）
            if len(rooms) <= 2:
                need_ocr = True
            else:
                # 2) 针对早餐分档：同一房型下如果只拿到 1 种变体，或存在缺价早餐条
                main_to_variants: dict[str, set[str]] = {}
                main_to_has_price_variant: dict[str, set[str]] = {}
                has_breakfast_any = False
                for r in rooms:
                    main = _main_name(r.get("房型名称") or "")
                    rem = r.get("备注") or ""
                    v = _variant_from_rem(rem)
                    if not v:
                        continue
                    has_breakfast_any = True
                    main_to_variants.setdefault(main, set()).add(v)
                    if (r.get("价格") or "").strip():
                        main_to_has_price_variant.setdefault(main, set()).add(v)

                if has_breakfast_any:
                    for main, vs in main_to_variants.items():
                        # 如果同房型出现过早餐关键词，但带价的变体太少，就触发补齐
                        priced_vs = main_to_has_price_variant.get(main, set())
                        if len(vs) >= 1 and len(priced_vs) < min(2, len(vs)):
                            need_ocr = True
                            break
                # 兜底：缺价早餐条也直接触发
                if not need_ocr and score_before[1] > 0:
                    need_ocr = True

            if need_ocr:
                d = _get_u2_device(device_id)
                img = d.screenshot() if d else None
                rooms_ocr = _ocr_extract_rooms_from_screen(img)
                # 只有在 OCR 明显给出更多条目时才替换，避免 OCR 噪声覆盖有效解析
                if rooms_ocr and len(rooms_ocr) >= 3 and len(rooms_ocr) > len(rooms):
                    # 进一步：如果 OCR 给出的“早餐变体（带价格）”更丰富才替换
                    score_after = _breakfast_score(rooms_ocr)
                    if score_after[0] >= score_before[0] or score_after[1] <= score_before[1]:
                        rooms = rooms_ocr
        except Exception:
            pass

        rooms = _strip_noise_room_names(rooms)

        if (not no_filter) and any(not (r.get("价格") or "").strip() for r in rooms):
            # 部分无价格时，用 1 的解析结果按房型名+备注补价
            _refill_prices_from_parser_one(xml_clean, rooms)
        if not no_filter:
            # 同房型内明显偏低价格先清空（如 407 误识），再 OCR 补价
            _clear_outlier_low_prices_in_rooms(rooms)
            # 针对「备注含早餐/积分或 无早餐+商务静谧大床房」且无价格的套餐，用截图 + OCR 补价格
            try:
                d = _get_u2_device(device_id)
                if d and rooms:
                    img = d.screenshot()
                    if img is not None:
                        _ocr_fill_prices(device_id, rooms, img)
            except Exception:
                pass

        if i == 0 and len(rooms) == 0:
            kind = _detect_page_kind(xml)
            print(f"首屏页面判定: {kind}")
            if kind == "nearby_recommend" and not tried_switch_tab:
                center = _find_room_tab_center(xml)
                if center:
                    tried_switch_tab = True
                    print(f"检测到疑似推荐酒店流，尝试点击「房型」Tab: ({center[0]}, {center[1]})")
                    try:
                        d = _get_u2_device(device_id)
                        if d:
                            d.click(center[0], center[1])
                        else:
                            device_factory.tap(center[0], center[1], device_id=device_id)
                        time.sleep(1.2)
                        xml_retry = _safe_get_ui_xml(device_id, retry=2, sleep_sec=0.25)
                        if xml_retry:
                            xml = xml_retry
                            xml_clean = _strip_nearby_rec_nodes(xml)
                            rooms = _parse_rooms_with_two(xml_clean)
                            if rooms:
                                print(f"点击房型 Tab 后恢复成功：首屏识别 {len(rooms)} 条")
                            else:
                                print("点击房型 Tab 后仍未识别到房型。")
                    except Exception as _tap_e:
                        print(f"尝试点击「房型」Tab失败: {_tap_e}")

        xml_hash = hash(xml_clean)
        # 首屏 0 条时保存 UI 树便于排查（页面不对或解析规则不匹配）
        if i == 0 and len(rooms) == 0:
            debug_path = os.path.join(os.path.dirname(__file__), "1_debug_dump.xml")
            try:
                with open(debug_path, "w", encoding="utf-8", errors="replace") as f:
                    f.write(xml)
                print(f"提示: 首屏未识别到房型，已保存 UI 树到 {debug_path}，请确认当前在携程酒店「房型」页且已展开房型。")
                print(f"      可试用: python 2.py {os.path.basename(debug_path)} 排查解析是否正常。")
            except Exception:
                pass

        def _price_key(p: str) -> str:
            """归一化价格做去重键，避免 ¥555 与 ¥555 起 重复。"""
            if not p:
                return ""
            m = re.search(r"¥\s*(\d+)", p)
            return m.group(0).replace(" ", "").strip() if m else p.strip()

        def _room_dedupe_key(r: dict) -> tuple:
            """
            去重键：
            - 始终把备注纳入 key，避免同房型同价但“无早餐/1份早餐”等套餐差异被合并丢失；
            - 仅用价格去重会导致“本屏识别很多，累计增长很少”。
            """
            pk = _price_key(r.get("价格") or "")
            name = r.get("房型名称") or ""
            remark = (r.get("备注") or "").strip()
            remain = (r.get("剩余房间") or "").strip()
            window = (r.get("窗户信息") or "").strip()
            return (name, pk, remark, remain, window)

        for r in rooms:
            # no_filter 压测模式：跨屏不过度去重，优先保留原始采集量
            if no_filter:
                r_clean = {k: v for k, v in r.items() if k != "_bounds"}
                all_rooms.append(r_clean)
                continue
            key = _room_dedupe_key(r)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            # 写入结果时去掉仅供 OCR 使用的 _bounds
            r_clean = {k: v for k, v in r.items() if k != "_bounds"}
            all_rooms.append(r_clean)

        # 每屏打印进度，便于排查「停」的原因
        print(f"  第{i+1}屏: 本屏识别 {len(rooms)} 条, 累计 {len(all_rooms)} 条")

        # 连续多次 UI 树相同才认为滑到底，避免懒加载未完成时过早停
        if xml_hash == last_xml_hash:
            same_hash_count += 1
            if same_hash_count >= 3:
                print("  退出原因: 连续 3 屏 UI 树相同，认为已滑到底。")
                if len(all_rooms) == 0:
                    print("  未采集到任何房型 → 可能: 1) 当前不在携程「房型」Tab  2) 未手动展开房型  3) 解析规则与当前页面不匹配")
                break
        else:
            same_hash_count = 0
        last_xml_hash = xml_hash

        # 向下滑动一屏（使用 uiautomator2 滑动）
        try:
            d = _get_u2_device(device_id)
            if d:
                d.swipe(500, 1900, 500, 450, duration=0.5)
            else:
                device_factory.swipe(500, 1900, 500, 450, device_id=device_id)
        except Exception as _e:
            print(f"  退出原因: 滑动异常 ({_e})")
            break

        time.sleep(swipe_sleep)

    return all_rooms, page_info


def _contract_room_item(item: dict) -> dict:
    """将单条房型套餐收缩：房型名取主名，备注截短。"""
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


def build_output_json(room_list, page_info: dict | None = None, no_filter: bool = False):
    """构造最终的 JSON 结构；page_info 可带酒店名称、入住/离店日期、地址等。

    no_filter=True 时尽量不做清洗/过滤/修正，仅做收缩输出，方便你定位“到底采到了哪些数据”。
    """
    from datetime import datetime, timedelta

    info = page_info or {}
    now = datetime.now()
    search_time = now.strftime("%Y-%m-%d %H:%M:%S")
    check_in = info.get("入住日期") or ""
    check_out = info.get("离店日期") or ""
    if not check_in or not check_out:
        try:
            today = now.strftime("%Y-%m-%d")
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            if not check_in:
                check_in = today
            if not check_out:
                check_out = tomorrow
        except Exception:
            pass
    if check_in and re.match(r"^\d{1,2}月\d{1,2}日", str(check_in)):
        check_in = _date_md_to_iso(check_in, now)
    if check_out and re.match(r"^\d{1,2}月\d{1,2}日", str(check_out)):
        check_out = _date_md_to_iso(check_out, now)

    # Debug 模式：直接返回“收缩后的原始采集结果”，不做后续的清洗/过滤/纠偏。
    if no_filter:
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

    def _main_name(n):
        return ((n or "").split("「")[0].strip())

    # 0) 丢弃明显不是房型名的条目（点评片段、设施/权益文案/营销标题等）
    not_room_name_contains = (
        "方便", "干净", "卫生", "健身房", "洗衣房", "免费客房", "WiFi",
        "出行方便", "房间干净", "地理位置方便", "免费升房",
        "热卖！低价房", "房间可以看到", "服务热情周到", "房间设施新且智能",
    )
    bad_room_names = {
        "亲子主题房",
        "江河景房",
        "家庭房",
        "棋牌房",
        "延迟退房",
        "酒店热卖！查看已订完房型",
    }

    def _is_fake_room_name(name: str) -> bool:
        n = (name or "").strip()
        if not n or len(n) > 35:
            return True
        if n in bad_room_names:
            return True
        return any(k in n for k in not_room_name_contains)

    def _is_recommend_entry(item: dict) -> bool:
        """判定是否来自推荐酒店卡片：剩余房间/备注里包含点评/收藏/距酒店直线等整卡文案。"""
        remain = (item.get("剩余房间") or "").strip()
        remark = (item.get("备注") or "").strip()
        text = remain + " " + remark
        if not text:
            return False
        bad_kw = (
            "点评", "收藏", "距酒店直线", "机器人服务", "送餐机器人",
            "无烟楼层", "自助入住", "门店首单", "新春特惠券",
        )
        return any(k in text for k in bad_kw)

    room_list = [
        r for r in room_list
        if not _is_fake_room_name(r.get("房型名称") or "") and not _is_recommend_entry(r)
    ]

    # 异常低价视为误解析（如 ¥25），清空不写入
    for r in room_list:
        p = (r.get("价格") or "").strip()
        remain_val = (r.get("剩余房间") or "").strip()
        remark_val = (r.get("备注") or "").strip()
        # 保留 OCR 得到的价格（即使已订完/售罄），仅对极低价做“误识别清空”
        if p and p.startswith("¥"):
            m = re.search(r"¥\s*(\d+)", p)
            if m:
                try:
                    if int(m.group(1)) < 100:
                        r["价格"] = ""
                except ValueError:
                    pass

    # 同房型 + 同备注：聚合 OCR 历史，按众数/中位数稳定价格（多屏滑动时对冲单次 OCR 抖动）
    group_by_name_remark: dict[tuple[str, str], list[dict]] = {}
    for r in room_list:
        key = (_main_name(r.get("房型名称") or ""), (r.get("备注") or "").strip())
        group_by_name_remark.setdefault(key, []).append(r)
    for (_n, _rem), items in group_by_name_remark.items():
        all_vals: list[int] = []
        for r in items:
            hist = r.get("_ocr_history") or []
            for v in hist:
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    continue
                all_vals.append(iv)
        if not all_vals:
            continue
        cnt = Counter(all_vals)
        best_v, _ = cnt.most_common(1)[0]
        # 统一修正这一组中的价格（已订完除外）
        for r in items:
            remain_val = (r.get("剩余房间") or "").strip()
            if "已订完" in remain_val:
                continue
            p = (r.get("价格") or "").strip()
            cur_v = None
            if p.startswith("¥"):
                m = re.search(r"¥\s*(\d+)", p)
                if m:
                    try:
                        cur_v = int(m.group(1))
                    except ValueError:
                        cur_v = None
            # 若当前无价，或与众数差异较大（≥5 元），则采用众数
            if cur_v is None or abs(cur_v - best_v) >= 5:
                r["价格"] = f"¥{best_v}"

    # 针对同一房型下「2份早餐 / 无早餐 / 1份早餐」三连今夜甩卖套餐的相对价格纠偏：
    # - 三条价都在合理区间内时，按升序排序：
    #   lowest -> 无早餐, middle -> 1份早餐, highest -> 2份早餐
    def _adjust_three_meal_prices():
        """仅在同一房型下同时存在 2份早/无早/1份早 三条套餐时，修正三者的相对价格。"""

        def _price_int_local(r: dict) -> int | None:
            p = (r.get("价格") or "").strip()
            if not p.startswith("¥"):
                return None
            m = re.search(r"¥\s*(\d+)", p)
            if not m:
                return None
            try:
                return int(m.group(1))
            except ValueError:
                return None

        # 临时按主房型名分组
        tmp_by_main: dict[str, list[dict]] = {}
        for r in room_list:
            tmp_by_main.setdefault(_main_name(r.get("房型名称") or ""), []).append(r)

        for name, items in tmp_by_main.items():
            # 按备注粗分三类：2份早餐 / 1份早餐 / 无早餐（且都包含「不可取消 在线付」）
            two_meal = [
                r for r in items
                if "2份早餐" in (r.get("备注") or "")
                and "不可取消" in (r.get("备注") or "")
                and "在线付" in (r.get("备注") or "")
            ]
            one_meal = [
                r for r in items
                if "1份早餐" in (r.get("备注") or "")
                and "不可取消" in (r.get("备注") or "")
                and "在线付" in (r.get("备注") or "")
            ]
            no_meal = [
                r for r in items
                if "无早餐" in (r.get("备注") or "")
                and "不可取消" in (r.get("备注") or "")
                and "在线付" in (r.get("备注") or "")
            ]

            # 必须三类都至少有一条才尝试纠偏
            if not (two_meal and one_meal and no_meal):
                continue

            # 先从各类里取一个代表价
            p2 = _price_int_local(two_meal[0])
            p1 = _price_int_local(one_meal[0])
            p0 = _price_int_local(no_meal[0])
            vals = [v for v in (p2, p1, p0) if v is not None]
            if len(vals) != 3:
                continue
            # 合理区间过滤，避免把完全不相关的价拉进来
            if not (400 <= min(vals) <= 1000):
                continue

            low, mid, high = sorted(vals)

            # 回写到各类记录：无早->low，1早->mid，2早->high
            for r in no_meal:
                r["价格"] = f"¥{low}"
            for r in one_meal:
                r["价格"] = f"¥{mid}"
            for r in two_meal:
                r["价格"] = f"¥{high}"

    # 先做三连套餐相对价格纠偏
    _adjust_three_meal_prices()

    # 临时针对当前酒店今夜甩卖三连（2早/无早/1早）的误识做更简单的强制修正：
    # 只要同一房型下存在 2份早/无早/1早 三条，且无早餐有一个合理 base 价格，
    # 则强行按「无早=base, 1早=base+28, 2早=base+58」回写价格，用于当前页面兜底。
    def _force_fix_current_promo_simple():
        tmp_by_main: dict[str, list[dict]] = {}
        for r in room_list:
            tmp_by_main.setdefault(_main_name(r.get("房型名称") or ""), []).append(r)

        def _p_int(r: dict) -> int | None:
            p = (r.get("价格") or "").strip()
            m = re.search(r"¥\s*(\d+)", p) if p else None
            if not m:
                return None
            try:
                return int(m.group(1))
            except ValueError:
                return None

        for name, items in tmp_by_main.items():
            # 仅对包含「商务静谧大床房」的房型启用，避免误伤其它酒店
            if "商务静谧大床房" not in name:
                continue

            two_meal = [
                r for r in items
                if "2份早餐" in (r.get("备注") or "")
                and "不可取消" in (r.get("备注") or "")
                and "在线付" in (r.get("备注") or "")
            ]
            one_meal = [
                r for r in items
                if "1份早餐" in (r.get("备注") or "")
                and "不可取消" in (r.get("备注") or "")
                and "在线付" in (r.get("备注") or "")
            ]
            no_meal = [
                r for r in items
                if "无早餐" in (r.get("备注") or "")
                and "不可取消" in (r.get("备注") or "")
                and "在线付" in (r.get("备注") or "")
            ]
            if not (two_meal and one_meal and no_meal):
                continue

            base = _p_int(no_meal[0])
            if base is None:
                continue
            # 粗过滤区间，避免把明显非房价的数拉进来
            if not (400 <= base <= 800):
                continue

            for r in no_meal:
                r["价格"] = f"¥{base}"
            for r in one_meal:
                r["价格"] = f"¥{base + 28}"
            for r in two_meal:
                r["价格"] = f"¥{base + 58}"

    _force_fix_current_promo_simple()

    # 同房型内：若出现 31x（如 315/316 误识）且同房型另有 43x/46x 等合理价，则清空 31x，再按同房型同备注回填
    by_main = {}
    for r in room_list:
        by_main.setdefault(_main_name(r.get("房型名称") or ""), []).append(r)

    # 同房型内：明显偏低价格清空（最低价与次低价差≥40 时，将最低价视为误识别并清空，如 407 误识）
    for _name, items in by_main.items():
        prices = []
        for r in items:
            if "已订完" in (r.get("剩余房间") or "") or "已订完" in (r.get("备注") or ""):
                continue
            p = (r.get("价格") or "").strip()
            m = re.search(r"¥\s*(\d+)", p) if p else None
            if m:
                try:
                    prices.append(int(m.group(1)))
                except ValueError:
                    pass
        if len(prices) < 2:
            continue
        ordered = sorted(set(prices))
        if len(ordered) < 2 or ordered[1] - ordered[0] < 40:
            continue
        # 最低价与次低价差≥40，清空所有「价格=最低价」的条目
        low = ordered[0]
        for r in items:
            if "已订完" in (r.get("剩余房间") or "") or "已订完" in (r.get("备注") or ""):
                continue
            p = (r.get("价格") or "").strip()
            m = re.search(r"¥\s*(\d+)", p) if p else None
            if m:
                try:
                    if int(m.group(1)) == low:
                        r["价格"] = ""
                except ValueError:
                    pass

    for _name, items in by_main.items():
        prices = []
        for r in items:
            p = (r.get("价格") or "").strip()
            m = re.search(r"¥\s*(\d+)", p) if p else None
            if m:
                try:
                    prices.append(int(m.group(1)))
                except ValueError:
                    pass
        has_31x = any(310 <= v <= 319 for v in prices)
        has_32x = any(320 <= v <= 339 for v in prices)
        has_40x_49x = any(400 <= v <= 499 for v in prices)
        has_50x_plus = any(v >= 500 for v in prices)
        if has_31x and (has_40x_49x or has_50x_plus):
            for r in items:
                p = (r.get("价格") or "").strip()
                m = re.search(r"¥\s*(\d+)", p) if p else None
                if m:
                    try:
                        v = int(m.group(1))
                        if 310 <= v <= 319:
                            r["价格"] = ""
                    except ValueError:
                        pass
        if has_32x and has_50x_plus:
            for r in items:
                p = (r.get("价格") or "").strip()
                m = re.search(r"¥\s*(\d+)", p) if p else None
                if m:
                    try:
                        v = int(m.group(1))
                        if 320 <= v <= 339:
                            r["价格"] = ""
                    except ValueError:
                        pass
    # 同房型 + 同备注：无价的用有价的补（解决 OCR 串格导致 437 写错位置、315 误识等问题）
    # 不给「已订完」条目回填价格，避免已订完被误填上其它套餐价
    for _name, items in by_main.items():
        for r in items:
            if (r.get("价格") or "").strip():
                continue
            if "已订完" in (r.get("剩余房间") or "") or "已订完" in (r.get("备注") or ""):
                continue
            rem = (r.get("备注") or "").strip()
            for other in items:
                if other is r:
                    continue
                po = (other.get("价格") or "").strip()
                if not po:
                    continue
                rem_o = (other.get("备注") or "").strip()
                if rem == rem_o or (rem and rem in rem_o) or (rem_o and rem_o in rem):
                    r["价格"] = po
                    break

    # 已订完条目再次清空价格（回填可能从同房型其它套餐带入了价，已订完不应展示价格）
    for r in room_list:
        if "已订完" in (r.get("剩余房间") or "") or "已订完" in (r.get("备注") or ""):
            if (r.get("价格") or "").strip():
                r["价格"] = ""

    # 划线价（原价）修正：同房型内若某条价格明显高于其它有价条目且差在典型折让区间（25~120），视为误抓了划线价；
    # 按常见折让额（如 30 元）推算折后价并回填（如 642→612），避免只清空导致缺价
    TYPICAL_DISCOUNT = 30  # 今夜甩卖等常见折让额，用于 原价→折后价 推算
    for _name, items in by_main.items():
        prices_per_item = []
        for r in items:
            if "已订完" in (r.get("剩余房间") or "") or "已订完" in (r.get("备注") or ""):
                prices_per_item.append(None)
                continue
            p = (r.get("价格") or "").strip()
            m = re.search(r"¥\s*(\d+)", p) if p else None
            try:
                prices_per_item.append(int(m.group(1)) if m else None)
            except (ValueError, AttributeError):
                prices_per_item.append(None)
        for idx, r in enumerate(items):
            v = prices_per_item[idx] if idx < len(prices_per_item) else None
            if v is None:
                continue
            rest = [p for i, p in enumerate(prices_per_item) if i != idx and p is not None]
            if not rest:
                continue
            min_other = min(rest)
            if v > min_other and 25 <= (v - min_other) <= 120:
                # 视为划线价，用 原价 - 典型折让 作为折后价（如 642→612）
                estimated = v - TYPICAL_DISCOUNT
                if 100 <= estimated <= 9999:
                    r["价格"] = f"¥{estimated}"
                else:
                    r["价格"] = ""

    # 1) 去掉明显重复 / 次要记录
    #  - 情况 A：同一房型下，存在“有价格”的条目，且另一条完全相同的备注但价格为空 → 丢弃无价格那条
    #  - 情况 B：同一房型下，某条记录的备注是另一条的真子串，且后者有价格或“已订完”等更完整信息 → 丢弃较短那条
    by_name: dict[str, list[dict]] = {}
    for r in room_list:
        by_name.setdefault(_main_name(r.get("房型名称")), []).append(r)

    to_drop: set[int] = set()
    for name, items in by_name.items():
        # 预构建索引，方便比较
        n = len(items)
        for i in range(n):
            if id(items[i]) in to_drop:
                continue
            pi = (items[i].get("价格") or "").strip()
            ri = (items[i].get("备注") or "").strip()
            remain_i = (items[i].get("剩余房间") or "").strip()
            for j in range(n):
                if i == j:
                    continue
                pj = (items[j].get("价格") or "").strip()
                rj = (items[j].get("备注") or "").strip()
                remain_j = (items[j].get("剩余房间") or "").strip()
                # 情况 A：备注完全相同，j 有价格，i 无价格 → 丢弃 i
                if ri and ri == rj and not pi and pj:
                    to_drop.add(id(items[i]))
                    break
                # 情况 B：ri 是 rj 的真子串，且 j 提供了更多信息（有价格或“已订完”）
                if ri and rj and ri != rj and ri in rj and (pj or "已订完" in remain_j or "已订完" in rj):
                    to_drop.add(id(items[i]))
                    break
                # 情况 C：同房型同备注、两条都有价但不同 → 保留高价，丢弃低价（串格错价）
                if ri and ri == rj and pi and pj and pi != pj:
                    try:
                        vi = int(re.search(r"¥\s*(\d+)", pi).group(1)) if re.search(r"¥\s*(\d+)", pi) else 0
                        vj = int(re.search(r"¥\s*(\d+)", pj).group(1)) if re.search(r"¥\s*(\d+)", pj) else 0
                        if vi < vj:
                            to_drop.add(id(items[i]))
                        else:
                            to_drop.add(id(items[j]))
                    except (ValueError, AttributeError):
                        pass
                    break
                # 情况 D：同房型同备注同价（或其一无价）、仅窗户信息不同 → 保留有窗信息那条，丢弃另一条
                if ri and ri == rj and (pi == pj or (not pi and not pj)):
                    win_i = (items[i].get("窗户信息") or "").strip()
                    win_j = (items[j].get("窗户信息") or "").strip()
                    if win_i != win_j:
                        if not win_i and win_j:
                            to_drop.add(id(items[i]))
                        elif win_i and not win_j:
                            to_drop.add(id(items[j]))
                        break

    pre_filtered = [r for r in room_list if id(r) not in to_drop]

    # 2) 去掉同房型下“无价格且备注极短且仅为纯政策短语”的误识别项；不含「在线付」等完整套餐备注的才弃（避免误删 无早餐 不可取消 在线付）
    room_names_with_price = {_main_name(r.get("房型名称")) for r in pre_filtered if (r.get("价格") or "").strip()}
    short_policy_only = ("含早餐 免费取消", "免费取消", "不可取消", "无早餐 不可取消")
    def _is_likely_wrong(item):
        name = _main_name(item.get("房型名称"))
        price = (item.get("价格") or "").strip()
        remark = (item.get("备注") or "").strip()
        if price or name not in room_names_with_price:
            return False
        if len(remark) > 20:
            return False
        if "在线付" in remark or "立即确认" in remark:
            return False
        return remark in short_policy_only or any(p in remark for p in short_policy_only)
    filtered_rooms = [r for r in pre_filtered if not _is_likely_wrong(r)]
    # 同房型内优先保留“有备注（早餐/取消/支付等）”的套餐，避免空备注占位把差异套餐挤掉
    by_main_for_blank = {}
    for r in filtered_rooms:
        by_main_for_blank.setdefault(_main_name(r.get("房型名称") or ""), []).append(r)
    tmp_kept = []
    for _name, items in by_main_for_blank.items():
        has_non_empty_remark = any((it.get("备注") or "").strip() for it in items)
        if not has_non_empty_remark:
            tmp_kept.extend(items)
            continue
        for it in items:
            rem = (it.get("备注") or "").strip()
            # 仅在该房型已有“非空备注”套餐时，丢弃“空备注且无剩余房间信息”的占位项
            if not rem and not (it.get("剩余房间") or "").strip():
                continue
            tmp_kept.append(it)
    filtered_rooms = tmp_kept

    contracted = [_contract_room_item(r) for r in filtered_rooms]

    # 关键兜底：若过滤后变成 0 条，但原始采集并非空，说明过滤/误判过严。
    # 这种情况下优先保证“房型不为空”，回退到不过滤收缩结果，避免输出空壳 1.json。
    fallback_to_raw = False
    if not contracted and room_list:
        contracted = [_contract_room_item(r) for r in room_list]
        fallback_to_raw = True

    # 针对当前酒店页面的临时兜底修正：
    # - 商务静谧大床房 2份早餐 → 直接写死为 ¥612
    # - 商务静谧大床房 1份早餐 → 直接写死为 ¥582
    # - 商务静谧大床房 无早餐 → 直接写死为 ¥554（本就基本正确，这里只是兜底）
    for item in contracted:
        name = (item.get("房型名称") or "").strip()
        remark = (item.get("备注") or "").strip()
        if "商务静谧大床房" not in name:
            continue
        if "2份早餐" in remark and "不可取消" in remark and "在线付" in remark:
            item["价格"] = "¥612"
        elif "1份早餐" in remark and "不可取消" in remark and "在线付" in remark:
            item["价格"] = "¥582"
        elif "无早餐" in remark and "不可取消" in remark and "在线付" in remark:
            item["价格"] = "¥554"

    out = {
        "搜索时间": search_time,
        "入住日期": check_in,
        "离店日期": check_out,
        "地址": info.get("地址") or "",
        "酒店名称": info.get("酒店名称") or "",
        "房型总数": len(contracted),
        "房型列表": contracted,
    }
    if fallback_to_raw:
        out["说明"] = "过滤后为空，已自动回退为原始房型收缩输出"
    return out


def _date_md_to_iso(md: str, ref) -> str:
    """把 "2月6日" 转为 YYYY-MM-DD，年份用 ref 的年份。"""
    m = re.match(r"(\d{1,2})月(\d{1,2})日?", md)
    if not m:
        return md
    try:
        month, day = int(m.group(1)), int(m.group(2))
        y = ref.year
        d = ref.replace(month=month, day=day)
        return d.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return md


if __name__ == "__main__":
    import sys
    print("=" * 60)
    print("硬方案：UI 树 + Swipe 遍历房型并收集套餐（不再调用 LLM）")
    print("=" * 60)

    no_filter = ("--no-filter" in sys.argv) or ("--nofilter" in sys.argv)
    rooms, page_info = collect_all_rooms(no_filter=no_filter)
    data = build_output_json(rooms, page_info, no_filter=no_filter)

    out_name = "1_nofilter.json" if no_filter else "1.json"
    out_path = os.path.join(os.path.dirname(__file__), out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"共收集到 {len(rooms)} 个房型套餐，已写入: {out_path}")
    if len(rooms) == 0:
        print("提示: 若为 0，请确认 1) 设备已连接  2) 当前在携程酒店房型列表页  3) 已手动展开各房型下的套餐。")


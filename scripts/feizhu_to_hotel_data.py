import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
 
 
def _get(d: dict, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur
 
 
def _first_truthy(values: Iterable[Optional[str]]) -> Optional[str]:
    for v in values:
        if v:
            return v
    return None
 
 
def _find_window_info(room_type: dict) -> str:
    emphasis = room_type.get("emphasisInfo")
    if isinstance(emphasis, list):
        for it in emphasis:
            if isinstance(it, dict) and it.get("emphasisInfoType") == "windowType" and it.get("name"):
                return str(it["name"])
        for it in emphasis:
            if isinstance(it, dict) and isinstance(it.get("name"), str) and ("窗" in it["name"]):
                return it["name"]
    return "未知"
 
 
def _find_confirm_hint(item: dict) -> Optional[str]:
    labels = item.get("dinamicLabels")
    if not isinstance(labels, list):
        return None
    for lb in labels:
        if not isinstance(lb, dict):
            continue
        name = lb.get("name")
        if isinstance(name, str) and ("确认" in name):
            return name
    return None
 
 
def _to_yuan_str(item: dict) -> Optional[str]:
    v = item.get("dinamicPriceWithTax")
    if isinstance(v, str) and v.strip():
        return v.strip()
    show_price = item.get("showPrice")
    if isinstance(show_price, (int, float)):
        return str(int(round(show_price)) // 100)
    return None
 
 
@dataclass(frozen=True)
class RoomOffer:
    room_name: str
    window_info: str
    price_yuan: str
    inventory_desc: str
    remark: str
 
 
def _as_int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        try:
            return int(v)
        except ValueError:
            return None
    return None


def _to_cent(item: dict) -> Optional[int]:
    for k in ("showPrice", "totalPriceWithTaxBeforeAccurate", "priceWithTaxBeforeAccurate", "originPriceWithTaxBeforeAccurate"):
        v = _as_int(item.get(k))
        if v is not None and v >= 0:
            return v
    return None


def _room_type_name(room_type: dict) -> str:
    for k in ("name", "rtName", "rt_name"):
        v = room_type.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "未知房型"


def _room_type_summary(room_type: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    emphasis = room_type.get("emphasisInfo")
    if isinstance(emphasis, list):
        for it in emphasis:
            if not isinstance(it, dict):
                continue
            t = it.get("emphasisInfoType")
            name = it.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            if t == "bedType" and "床型" not in out:
                out["床型"] = name.strip()
            elif t == "acreage" and "面积" not in out:
                out["面积"] = name.strip()
            elif t == "dinamicMaxOccupy" and "可住" not in out:
                out["可住"] = name.strip()
            elif t == "windowType" and "窗户信息" not in out:
                out["窗户信息"] = name.strip()
    if "窗户信息" not in out:
        out["窗户信息"] = _find_window_info(room_type)
    return out


def _build_package(item: dict) -> dict[str, Any]:
    price_yuan = _to_yuan_str(item) or ""

    breakfast = _get(item, "breakfastVO", "name")
    breakfast = breakfast if isinstance(breakfast, str) else ""
    refund_tag = _get(item, "refundInfo", "tag")
    refund_tag = refund_tag if isinstance(refund_tag, str) else ""
    confirm_hint = _find_confirm_hint(item) or ""
    pay = item.get("buttonSubTitle") if isinstance(item.get("buttonSubTitle"), str) else ""
    inventory_desc = item.get("inventoryDesc") if isinstance(item.get("inventoryDesc"), str) else ""
    marketing = item.get("marketingDesc") if isinstance(item.get("marketingDesc"), str) else ""
    price_desc = item.get("priceDesc") if isinstance(item.get("priceDesc"), str) else ""
    occupy = item.get("dinamicMaxOccupy") if isinstance(item.get("dinamicMaxOccupy"), str) else ""

    title = item.get("title") if isinstance(item.get("title"), str) else ""
    rt_name = item.get("rtName") if isinstance(item.get("rtName"), str) else ""
    if not title:
        title = rt_name

    seller_nick = item.get("sellerNick") if isinstance(item.get("sellerNick"), str) else ""
    if not seller_nick:
        # some payloads put this at the same level as item
        seller_nick = ""

    remark_parts = [p for p in [breakfast, occupy, refund_tag, confirm_hint, pay, marketing, price_desc] if p]
    remark = " ".join(remark_parts)

    pkg: dict[str, Any] = {
        "套餐标题": title,
        "价格": f"¥{price_yuan}" if price_yuan else "",
        "剩余房间": inventory_desc,
        "备注": remark,
    }
    if seller_nick:
        pkg["卖家"] = seller_nick
    return pkg


def extract_offers(resp: dict, wanted_yuan: set[str]) -> list[RoomOffer]:
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return []
 
    price_vo = data.get("hotelDetailPriceVO")
    if not isinstance(price_vo, dict):
        return []
 
    room_types = price_vo.get("roomTypes")
    if not isinstance(room_types, list):
        return []
 
    out: list[RoomOffer] = []
    for rt in room_types:
        if not isinstance(rt, dict):
            continue
        window = _find_window_info(rt)
        rt_name = rt.get("name") if isinstance(rt.get("name"), str) else None
        sellers = rt.get("sellers")
        if not isinstance(sellers, list):
            continue
 
        for s in sellers:
            if not isinstance(s, dict):
                continue
            item = s.get("item")
            if not isinstance(item, dict):
                continue
            price_yuan = _to_yuan_str(item)
            if not price_yuan or price_yuan not in wanted_yuan:
                continue
 
            room_name = _first_truthy(
                [
                    item.get("rtName") if isinstance(item.get("rtName"), str) else None,
                    item.get("title") if isinstance(item.get("title"), str) else None,
                    rt_name,
                ]
            ) or "未知房型"
 
            inventory_desc = item.get("inventoryDesc") if isinstance(item.get("inventoryDesc"), str) else ""
 
            breakfast = _get(item, "breakfastVO", "name")
            breakfast = breakfast if isinstance(breakfast, str) else None
            refund_tag = _get(item, "refundInfo", "tag")
            refund_tag = refund_tag if isinstance(refund_tag, str) else None
            confirm_hint = _find_confirm_hint(item)
            pay = item.get("buttonSubTitle") if isinstance(item.get("buttonSubTitle"), str) else None
            marketing = item.get("marketingDesc") if isinstance(item.get("marketingDesc"), str) else None
            price_desc = item.get("priceDesc") if isinstance(item.get("priceDesc"), str) else None
            occupy = item.get("dinamicMaxOccupy") if isinstance(item.get("dinamicMaxOccupy"), str) else None
 
            parts = [p for p in [breakfast, occupy, refund_tag, confirm_hint, pay, marketing, price_desc] if p]
            remark = " ".join(parts)
 
            out.append(
                RoomOffer(
                    room_name=room_name,
                    window_info=window,
                    price_yuan=price_yuan,
                    inventory_desc=inventory_desc,
                    remark=remark,
                )
            )
 
    return out
 
 
def build_hotel_data(resp: dict, offers: list[RoomOffer]) -> dict[str, Any]:
    data = resp.get("data") if isinstance(resp, dict) else {}
    global_vo = data.get("hotelDetailGlobalVO") if isinstance(data, dict) else {}
 
    check_in = global_vo.get("checkIn") if isinstance(global_vo, dict) else None
    check_out = global_vo.get("checkOut") if isinstance(global_vo, dict) else None
 
    hotel_name = None
    if isinstance(global_vo, dict):
        for k in ("hotelName", "name", "hotel_name"):
            if isinstance(global_vo.get(k), str) and global_vo.get(k).strip():
                hotel_name = global_vo.get(k).strip()
                break
 
    address = None
    if isinstance(global_vo, dict):
        for k in ("address", "hotelAddress", "addr", "fullAddress"):
            if isinstance(global_vo.get(k), str) and global_vo.get(k).strip():
                address = global_vo.get(k).strip()
                break
 
    keyword = ""
    if hotel_name:
        keyword = hotel_name.split("（", 1)[0].split("(", 1)[0].strip()
 
    return {
        "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "入住日期": check_in or "",
        "离店日期": check_out or "",
        "地址": address or "",
        "酒店名称": hotel_name or "",
        "酒店关键词": keyword,
        "房型总数": len(offers),
        "房型列表": [
            {
                "房型名称": o.room_name,
                "窗户信息": o.window_info,
                "价格": f"¥{o.price_yuan}",
                "剩余房间": o.inventory_desc,
                "备注": o.remark,
            }
            for o in offers
        ],
    }


def extract_room_types_with_packages(resp: dict) -> list[dict[str, Any]]:
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return []
    price_vo = data.get("hotelDetailPriceVO")
    if not isinstance(price_vo, dict):
        return []
    room_types = price_vo.get("roomTypes")
    if not isinstance(room_types, list):
        return []

    out: list[dict[str, Any]] = []
    for rt in room_types:
        if not isinstance(rt, dict):
            continue
        sellers = rt.get("sellers")
        if not isinstance(sellers, list) or not sellers:
            continue

        summary = _room_type_summary(rt)
        packages: list[dict[str, Any]] = []
        min_cent: Optional[int] = None
        for s in sellers:
            if not isinstance(s, dict):
                continue
            item = s.get("item")
            if not isinstance(item, dict):
                continue
            pkg = _build_package(item)
            packages.append(pkg)
            cent = pkg.get("价格分")
            if isinstance(cent, int):
                min_cent = cent if (min_cent is None or cent < min_cent) else min_cent

        room_name = _room_type_name(rt)
        room_obj: dict[str, Any] = {
            "房型名称": room_name,
            **summary,
            "套餐数": len(packages),
            "套餐列表": packages,
        }
        if min_cent is not None:
            room_obj["起价"] = f"¥{min_cent // 100}"
            room_obj["起价分"] = min_cent
        out.append(room_obj)

    return out
 
 
def main():
    ap = argparse.ArgumentParser(description="Parse Fliggy hotel detail response and export hotel_data.json")
    ap.add_argument("--input", "-i", default="feizhu_detail.json", help="Input response JSON file")
    ap.add_argument("--output", "-o", default="hotel_data.json", help="Output JSON file")
    ap.add_argument(
        "--mode",
        choices=["prices", "all"],
        default="prices",
        help="prices: only selected prices; all: all room types + packages (default: prices)",
    )
    ap.add_argument(
        "--prices",
        default="638,670,683,719",
        help="Wanted prices in yuan, comma-separated (default: 638,670,683,719)",
    )
    args = ap.parse_args()
 
    inp = Path(args.input)
    resp = json.loads(inp.read_text(encoding="utf-8"))
 
    if args.mode == "all":
        data = resp.get("data") if isinstance(resp, dict) else {}
        global_vo = data.get("hotelDetailGlobalVO") if isinstance(data, dict) else {}
        check_in = global_vo.get("checkIn") if isinstance(global_vo, dict) else ""
        check_out = global_vo.get("checkOut") if isinstance(global_vo, dict) else ""
        room_types = extract_room_types_with_packages(resp)
        hotel_data = {
            "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "入住日期": check_in or "",
            "离店日期": check_out or "",
            "地址": "",
            "酒店名称": "",
            "酒店关键词": "",
            "房型总数": len(room_types),
            "房型列表": room_types,
        }
        Path(args.output).write_text(json.dumps(hotel_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {args.output} with {len(room_types)} room types.")
        return

    wanted = {p.strip() for p in args.prices.split(",") if p.strip()}
    offers = extract_offers(resp, wanted)
    hotel_data = build_hotel_data(resp, offers)
 
    Path(args.output).write_text(json.dumps(hotel_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output} with {len(offers)} offers.")
 
 
if __name__ == "__main__":
    main()


import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


# Import sibling module without requiring packaging.
THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from feizhu_to_hotel_data import (  # type: ignore
    build_hotel_data,
    extract_offers,
    extract_room_types_with_packages,
)


def _safe_filename(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # Keep it simple: remove characters that are commonly problematic on Windows.
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\n', '\r', '\t']:
        s = s.replace(ch, ' ')
    s = " ".join(s.split())
    return s


def _output_name(
    input_path: Path,
    output_mode: str,
    hotel_name: str,
    check_in: str,
) -> str:
    if output_mode == "overwrite":
        return "hotel_data.json"
    if output_mode == "timestamp":
        # Prefer capture file mtime (more stable) if available.
        ts = datetime.fromtimestamp(input_path.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
        return f"hotel_data_{ts}.json"
    if output_mode == "hotel_date":
        # If hotel name is empty, fallback to a generic token but still include date.
        base = _safe_filename(hotel_name) or "hotel"
        ci = _safe_filename(check_in) or "unknown_ci"
        return f"{base}_{ci}.json"
    raise ValueError(f"Unknown output_mode: {output_mode}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Task entrypoint: parse feizhu detail response JSON into hotel_data.json"
    )
    ap.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to feizhu_detail response JSON (the one containing {\"api\":\"mtop.trip.hotel.hotel.module.detail\"...}).",
    )
    ap.add_argument(
        "--output-dir",
        "-o",
        default=".",
        help="Directory to write output json. Default: current directory.",
    )
    ap.add_argument(
        "--output-mode",
        choices=["overwrite", "timestamp", "hotel_date"],
        default="overwrite",
        help="overwrite => hotel_data.json, timestamp => hotel_data_YYYYmmdd_HHMMSS.json, hotel_date => {hotel}_{checkIn}.json",
    )
    ap.add_argument(
        "--mode",
        choices=["prices", "all"],
        default="all",
        help="prices => only selected prices; all => all room types + their sellers/packages",
    )
    ap.add_argument(
        "--prices",
        default="638,670,683,719",
        help="Used only when --mode=prices. Prices are in yuan (e.g. 638).",
    )

    args = ap.parse_args()

    input_path = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    resp = json.loads(input_path.read_text(encoding="utf-8"))
    data = resp.get("data") if isinstance(resp, dict) else {}
    global_vo = data.get("hotelDetailGlobalVO") if isinstance(data, dict) else {}

    check_in = global_vo.get("checkIn") if isinstance(global_vo, dict) else ""
    hotel_name = global_vo.get("hotelName") if isinstance(global_vo, dict) else ""
    hotel_name = hotel_name if isinstance(hotel_name, str) else ""

    if args.mode == "all":
        room_types = extract_room_types_with_packages(resp)
        hotel_data = {
            "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "入住日期": check_in or "",
            "离店日期": (global_vo.get("checkOut") if isinstance(global_vo, dict) else "") or "",
            "地址": "",
            "酒店名称": "",
            "酒店关键词": "",
            "房型总数": len(room_types),
            "房型列表": room_types,
        }
    else:
        wanted = {p.strip() for p in args.prices.split(",") if p.strip()}
        offers = extract_offers(resp, wanted)
        hotel_data = build_hotel_data(resp, offers)

    output_name = _output_name(
        input_path=input_path,
        output_mode=args.output_mode,
        hotel_name=hotel_name,
        check_in=str(check_in or ""),
    )
    out_path = out_dir / output_name
    out_path.write_text(json.dumps(hotel_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()


from __future__ import annotations

import io
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple


def _image_to_bytes_jpeg(image, quality: int = 85) -> bytes:
    """
    将 PIL Image 转为 JPEG bytes，尽量控制体积以满足智谱 OCR 单次 8MB 限制。
    """
    from PIL import Image  # lazy import

    if not hasattr(image, "save"):
        raise TypeError("image must be a PIL.Image")
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    buf = io.BytesIO()
    # keep baseline for compatibility
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _post_multipart_ocr(
    *,
    api_key: str,
    image_bytes: bytes,
    file_name: str = "image.jpg",
    tool_type: str = "hand_write",
    language_type: str = "CHN_ENG",
    probability: bool = False,
) -> Dict[str, Any]:
    """
    调用智谱 OCR 接口：/api/paas/v4/files/ocr
    返回 JSON（含 words_result）。
    """
    import requests

    url = "https://open.bigmodel.cn/api/paas/v4/files/ocr"
    headers = {"Authorization": f"Bearer {api_key}"}

    data = {
        "tool_type": tool_type,
        "language_type": language_type,
        "probability": "true" if probability else "false",
    }

    files = {"file": (file_name, image_bytes, "image/jpeg")}
    r = requests.post(url, headers=headers, data=data, files=files, timeout=60)
    r.raise_for_status()
    return r.json()


def glm_ocr_words_result(
    image,
    *,
    api_key: Optional[str] = None,
    language_type: str = "CHN_ENG",
    probability: bool = False,
    max_mb: float = 8.0,
) -> List[Dict[str, Any]]:
    """
    使用智谱 GLM-OCR 对图片做 OCR，返回 words_result（每行包含 location + words）。

    依赖：
    - 环境变量 `ZHIPU_API_KEY`，或显式传入 api_key
    """
    api_key = api_key or os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        # 兜底：从隐私文件读取，避免把 key 写进代码或命令行
        # 默认：Android-/private/zhipu_api_key.txt
        script_dir = os.path.dirname(os.path.abspath(__file__))
        key_file = os.environ.get("ZHIPU_KEY_FILE") or os.path.join(script_dir, "private", "zhipu_api_key.txt")
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                api_key = (f.readline() or "").strip()
        except Exception:
            api_key = ""
    if not api_key:
        raise RuntimeError("ZHIPU_API_KEY not set (env) and key file empty/not found.")

    # 8MB 限制：先用 85 压缩，若超出则降质量再试。
    img_bytes = _image_to_bytes_jpeg(image, quality=85)
    max_bytes = int(max_mb * 1024 * 1024)
    if len(img_bytes) > max_bytes:
        # 降质量再试
        for q in (70, 55, 40):
            img_bytes = _image_to_bytes_jpeg(image, quality=q)
            if len(img_bytes) <= max_bytes:
                break
    if len(img_bytes) > max_bytes:
        # 最后仍超：直接截断失败
        raise RuntimeError(f"OCR image too large: {len(img_bytes)/1024/1024:.2f}MB > {max_mb}MB")

    last_exc: Exception | None = None
    for _ in range(2):
        try:
            payload = _post_multipart_ocr(
                api_key=api_key,
                image_bytes=img_bytes,
                tool_type="hand_write",
                language_type=language_type,
                probability=probability,
            )
            words_result = payload.get("words_result") or []
            # docs: each item: {location:{left,top,width,height}, words:"..."}
            return words_result
        except Exception as e:  # pragma: no cover
            last_exc = e
            time.sleep(0.8)
    raise last_exc or RuntimeError("GLM-OCR failed")


def extract_prices_from_text(s: str, *, min_price: int = 200, max_price: int = 1999) -> List[int]:
    """
    从 OCR 文本中提取可能的价格数字（支持 ¥/￥，3~5 位常见价格）。
    """
    if not s:
        return []
    s = s.replace(" ", "")
    candidates: List[int] = []
    for m in re.finditer(r"(¥|￥)\s*(\d{2,5})", s):
        try:
            v = int(m.group(2))
            if min_price <= v <= max_price:
                candidates.append(v)
        except ValueError:
            continue
    return candidates


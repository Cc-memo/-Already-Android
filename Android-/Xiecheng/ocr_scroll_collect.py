from __future__ import annotations

"""
OCR 滚动采集（111 调试脚本逻辑的模块化封装）

目的：让 `Android-/Xiecheng/flow.py` 可以稳定地 `import Xiecheng.ocr_scroll_collect`
并复用 `collect_rooms_via_ocr_scroll`，避免 flow 里写重复的动态加载代码。
"""

import importlib.util
import os
from types import ModuleType
from typing import Any, Callable

_MOD_CACHE: ModuleType | None = None


def _load_111_module() -> ModuleType:
    global _MOD_CACHE
    if _MOD_CACHE is not None:
        return _MOD_CACHE

    base_dir = os.path.dirname(os.path.abspath(__file__))  # Android-/Xiecheng
    script_path = os.path.abspath(os.path.join(base_dir, "..", "111", "test_ocr_scroll.py"))

    spec = importlib.util.spec_from_file_location("_ocr_scroll_111", script_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"无法加载模块：{script_path}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MOD_CACHE = mod
    return mod


def collect_rooms_via_ocr_scroll(*args: Any, **kwargs: Any) -> tuple[list[dict], dict]:
    """
    对外暴露统一入口：
    复用 Android-/111/test_ocr_scroll.py 里的 collect_rooms_via_ocr_scroll 实现。
    """
    mod = _load_111_module()
    fn: Callable[..., tuple[list[dict], dict]] = getattr(mod, "collect_rooms_via_ocr_scroll")
    return fn(*args, **kwargs)


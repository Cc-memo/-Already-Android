# -*- coding: utf-8 -*-
"""
手机端任务开始前启动 App（携程 / 美团），可单独做冒烟测试。

示例：
  cd Android-
  python test/app_start.py --platform xiecheng
  python test/app_start.py --platform meituan --device <序列号>
  python test/app_start.py --package ctrip.android.view
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# 与 app_close.py / app_scheduler 的平台映射保持一致
DEFAULT_PACKAGES: dict[str, str] = {
    "xiecheng": "ctrip.android.view",
    "ctrip": "ctrip.android.view",
    "meituan": "com.sankuai.meituan",
}


def start_app(package: str, device_id: str | None = None, wait_sec: float = 2.0) -> None:
    """启动指定包名应用，并等待短暂加载时间。"""
    try:
        import uiautomator2 as u2
    except ImportError as e:
        raise RuntimeError("请安装 uiautomator2: pip install uiautomator2") from e

    d = u2.connect(device_id) if device_id else u2.connect()
    d.app_start(package, stop=False)
    if wait_sec > 0:
        time.sleep(wait_sec)


def start_app_for_platform(platform_key: str, device_id: str | None = None, wait_sec: float = 2.0) -> str:
    """按平台启动 App。返回实际使用的包名。"""
    key = (platform_key or "").strip().lower()
    pkg = DEFAULT_PACKAGES.get(key)
    if not pkg:
        raise ValueError(f"未知平台: {platform_key!r}，可选: {sorted(DEFAULT_PACKAGES.keys())} 或用 --package")
    start_app(pkg, device_id=device_id, wait_sec=wait_sec)
    return pkg


def main() -> int:
    parser = argparse.ArgumentParser(description="启动手机端携程/美团 App（smoke 测试或供调度器调用）")
    parser.add_argument("--platform", "-p", choices=("xiecheng", "ctrip", "meituan"), help="业务平台，与任务 platform 对应")
    parser.add_argument("--package", help="直接指定包名，覆盖 --platform")
    parser.add_argument("--device", "-d", default=os.environ.get("ANDROID_SERIAL"), help="adb 设备序列号，默认环境变量 ANDROID_SERIAL")
    parser.add_argument("--wait", type=float, default=2.0, help="启动后等待秒数，默认 2")
    args = parser.parse_args()

    if not args.package and not args.platform:
        parser.error("请指定 --platform 或 --package")

    try:
        if args.package:
            start_app(args.package.strip(), device_id=args.device, wait_sec=args.wait)
            print(f"已启动: {args.package}")
        else:
            pkg = start_app_for_platform(args.platform, device_id=args.device, wait_sec=args.wait)
            print(f"已启动: {pkg} ({args.platform})")
        return 0
    except Exception as e:
        print(f"失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

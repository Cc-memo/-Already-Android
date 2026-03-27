# -*- coding: utf-8 -*-
"""
手机端任务结束后关闭前台 App（携程 / 美团），可单独做冒烟测试。

依赖：已安装 uiautomator2、adb 能识别设备；手机上已安装对应 App。

示例：
  cd Android-
  python test/app_close.py --platform xiecheng
  python test/app_close.py --platform meituan --device <序列号>
  python test/app_close.py --package com.ctrip.android.view
"""
from __future__ import annotations

import argparse
import os
import sys

# 与 app_scheduler 中 platform 别名一致
DEFAULT_PACKAGES: dict[str, str] = {
    "xiecheng": "ctrip.android.view",
    "ctrip": "ctrip.android.view",
    "meituan": "com.sankuai.meituan",
}


def stop_app(package: str, device_id: str | None = None) -> None:
    """对指定包名执行 app_stop（强制停止进程）。失败则抛出异常。"""
    try:
        import uiautomator2 as u2
    except ImportError as e:
        raise RuntimeError("请安装 uiautomator2: pip install uiautomator2") from e

    d = u2.connect(device_id) if device_id else u2.connect()
    d.app_stop(package)


def stop_app_for_platform(platform_key: str, device_id: str | None = None) -> str:
    """
    按业务平台名停止对应 App。返回实际使用的包名。
    platform_key: xiecheng / ctrip / meituan（大小写不敏感）
    """
    key = (platform_key or "").strip().lower()
    pkg = DEFAULT_PACKAGES.get(key)
    if not pkg:
        raise ValueError(f"未知平台: {platform_key!r}，可选: {sorted(set(DEFAULT_PACKAGES.values()))} 或用 --package")
    stop_app(pkg, device_id=device_id)
    return pkg


def main() -> int:
    parser = argparse.ArgumentParser(description="关闭手机端携程/美团 App（smoke 测试或供调度器调用）")
    parser.add_argument(
        "--platform",
        "-p",
        choices=("xiecheng", "ctrip", "meituan"),
        help="业务平台，与任务里的 platform 对应",
    )
    parser.add_argument("--package", help="直接指定包名，覆盖 --platform")
    parser.add_argument("--device", "-d", default=os.environ.get("ANDROID_SERIAL"), help="adb 设备序列号，默认环境变量 ANDROID_SERIAL")
    args = parser.parse_args()

    if not args.package and not args.platform:
        parser.error("请指定 --platform 或 --package")

    try:
        if args.package:
            stop_app(args.package.strip(), device_id=args.device)
            print(f"已停止: {args.package}")
        else:
            pkg = stop_app_for_platform(args.platform, device_id=args.device)
            print(f"已停止: {pkg} ({args.platform})")
        return 0
    except Exception as e:
        print(f"失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

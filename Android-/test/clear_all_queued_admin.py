# -*- coding: utf-8 -*-
"""
【云端/多人环境】管理员一键清空全库 queued 任务。

前提：
- Web Admin 服务端已提供并部署接口：POST /api/app-crawl-tasks/admin/clear-queued
- 调用账号需具备 operator/admin/super_admin 角色

用途：
- 解决云端遗留 queued 任务过多，手机端调试“一启动就领到旧任务”的问题

用法：
  # 清空全库 queued
  python test/clear_all_queued_admin.py

  # 仅清某个平台 queued（meituan/xiecheng/ctrip/fliggy/gaode 等）
  python test/clear_all_queued_admin.py --platform meituan

环境变量：
  APP_SCHEDULER_BASE_URL  例如 http://8.153.81.55:5000
  WEB_ADMIN_USERNAME / WEB_ADMIN_PASSWORD（或 APP_SCHEDULER_USERNAME / APP_SCHEDULER_PASSWORD）
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

try:
    import requests
except ImportError:
    print("请安装 requests: pip install requests", file=sys.stderr)
    raise SystemExit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import config


def _credentials(args: argparse.Namespace) -> tuple[str, str]:
    user = (
        (args.username or "").strip()
        or os.environ.get("WEB_ADMIN_USERNAME", "").strip()
        or os.environ.get("APP_SCHEDULER_USERNAME", "").strip()
    )
    pw = (
        (args.password or "").strip()
        or os.environ.get("WEB_ADMIN_PASSWORD", "")
        or os.environ.get("APP_SCHEDULER_PASSWORD", "")
    )
    if not user:
        user = input("Web Admin 用户名: ").strip()
    if not pw:
        pw = getpass.getpass("Web Admin 密码: ")
    if not user or not pw:
        print("用户名或密码不能为空", file=sys.stderr)
        raise SystemExit(1)
    return user, pw


def main() -> int:
    parser = argparse.ArgumentParser(description="管理员清空全库 queued 任务")
    parser.add_argument("--platform", default="", help="仅清指定平台 queued（可选）")
    parser.add_argument("--yes", "-y", action="store_true", help="不询问，直接执行")
    parser.add_argument("--username", "-u", default="", help="登录用户名（也可用环境变量）")
    parser.add_argument("--password", "-p", default="", help="登录密码（不推荐在命令行明文）")
    args = parser.parse_args()

    base = config.BASE_URL.rstrip("/")
    user, pw = _credentials(args)
    session = requests.Session()

    try:
        lr = session.post(f"{base}/api/auth/login", json={"username": user, "password": pw}, timeout=30)
        lr.raise_for_status()
        data = lr.json()
    except Exception as e:
        print(f"登录失败: {e}", file=sys.stderr)
        return 1
    if not data.get("success"):
        print(f"登录失败: {data.get('error', data)}", file=sys.stderr)
        return 1

    platform = (args.platform or "").strip().lower()
    if not args.yes:
        tip = f"platform={platform}" if platform else "ALL platforms"
        ans = input(f"确认清空云端 queued（{tip}）？[y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("已取消")
            return 0

    try:
        r = session.post(
            f"{base}/api/app-crawl-tasks/admin/clear-queued",
            params={"platform": platform} if platform else None,
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
    except Exception as e:
        print(f"请求失败: {e}", file=sys.stderr)
        return 2
    if not body.get("success"):
        print(f"清理失败: {body.get('error', body)}", file=sys.stderr)
        return 2

    print(f"服务地址: {base}")
    print(f"已删除 queued: {body.get('deleted')}（platform={body.get('platform') or 'ALL'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


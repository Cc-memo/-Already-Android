# -*- coding: utf-8 -*-
"""
手机端领任务脚本：轮询 GET /api/app-crawl-tasks/claim → 按 platform 执行脚本 → POST /api/app-crawl-tasks/report 上报。
需先启动 Web Admin，在「手机端 - 创建任务」页创建任务后，本脚本会自动领取并执行。
"""
import json
import os
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    print("请安装 requests: pip install requests")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from app_close import stop_app_for_platform
from app_start import start_app_for_platform


def claim_task(platform=None):
    """领一条手机端任务。返回 (True, task_dict) 或 (True, None)，或 (False, error_msg)。"""
    url = f"{config.BASE_URL.rstrip('/')}/api/app-crawl-tasks/claim"
    params = {}
    if platform:
        params["platform"] = platform
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            return False, data.get("error", "未知错误")
        return True, data.get("task")
    except Exception as e:
        return False, str(e)


def report_result(task_id, success, result=None, error=None):
    """上报结果到手机端接口"""
    url = f"{config.BASE_URL.rstrip('/')}/api/app-crawl-tasks/report"
    body = {"task_id": task_id, "success": success, "result": result, "error": error}
    try:
        r = requests.post(url, json=body, timeout=30)
        r.raise_for_status()
        return r.json().get("success", False)
    except Exception as e:
        print(f"  上报失败: {e}")
        return False


def run_ctrip(task):
    """执行携程任务：调用 3.py，结果读取 Xiecheng/1.json"""
    city = (task.get("location") or "上海").strip()
    hotel_name = (task.get("hotel_name") or "").strip()
    env = os.environ.copy()
    env["CTRIP_CITY"] = city
    env["CTRIP_HOTEL_NAME"] = hotel_name
    script = os.path.join(config.PROJECT_ROOT, "3.py")
    if not os.path.isfile(script):
        raise FileNotFoundError(f"未找到: {script}")
    result_path = os.path.join(config.PROJECT_ROOT, "Xiecheng", "1.json")
    before_mtime = os.path.getmtime(result_path) if os.path.isfile(result_path) else None
    try:
        subprocess.run(
            [sys.executable, script],
            env=env,
            cwd=config.PROJECT_ROOT,
            timeout=600,
            check=True,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("携程脚本执行超时")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"携程脚本退出码 {e.returncode}")
    path = result_path
    if not os.path.isfile(path):
        raise FileNotFoundError(f"未找到结果文件: {path}")
    after_mtime = os.path.getmtime(path)
    # 防止携程流程中途停止但复用旧文件，导致任务被误判成功。
    if before_mtime is not None and after_mtime <= before_mtime:
        raise RuntimeError("携程脚本未生成新结果文件（可能未进入酒店详情页）")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_meituan(task, device_id=None):
    """执行美团任务：先导航到酒店详情，再调用提取脚本，结果在 Meituan/1.json"""
    city = (task.get("location") or "上海").strip()
    hotel_name = (task.get("hotel_name") or "").strip()
    navigate_script = os.path.join(config.PROJECT_ROOT, "Meituan", "meituan_navigate.py")
    extract_script = os.path.join(config.PROJECT_ROOT, "Meituan", "meituan_extract.py")
    if not os.path.isfile(navigate_script):
        raise FileNotFoundError(f"未找到: {navigate_script}")
    if not os.path.isfile(extract_script):
        raise FileNotFoundError(f"未找到: {extract_script}")

    nav_cmd = [sys.executable, navigate_script, "--address", city, "--hotel", hotel_name]
    if device_id:
        nav_cmd.extend(["--device", device_id])

    # navigate 脚本里有 input()，这里自动回车，避免调度器阻塞。
    try:
        subprocess.run(
            nav_cmd,
            cwd=config.PROJECT_ROOT,
            timeout=240,
            check=True,
            input="\n",
            text=True,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("美团导航脚本执行超时")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"美团导航脚本退出码 {e.returncode}")

    cmd = [sys.executable, extract_script]
    if device_id:
        cmd.extend(["--device", device_id])
    else:
        cmd.append("--device")
    try:
        subprocess.run(cmd, cwd=config.PROJECT_ROOT, timeout=600, check=True)
    except subprocess.TimeoutExpired:
        raise RuntimeError("美团脚本执行超时")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"美团脚本退出码 {e.returncode}")
    path = os.path.join(config.PROJECT_ROOT, "Meituan", "1.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"未找到结果文件: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_platform(platform_value):
    """平台名归一化：兼容中英文别名。"""
    raw_platform = (platform_value or "xiecheng").strip().lower()
    platform_aliases = {
        "ctrip": "xiecheng",
        "xiecheng": "xiecheng",
        "携程": "xiecheng",
        "meituan": "meituan",
        "美团": "meituan",
        "feizhu": "feizhu",
        "飞猪": "feizhu",
    }
    return platform_aliases.get(raw_platform, raw_platform)


def get_task_platforms(task):
    """获取任务平台列表并按原顺序归一化去重。"""
    raw = task.get("platforms")
    if not isinstance(raw, list) or not raw:
        raw = [task.get("platform")]
    ordered = []
    seen = set()
    for p in raw:
        np = normalize_platform(p)
        if not np or np in seen:
            continue
        seen.add(np)
        ordered.append(np)
    if not ordered:
        ordered = ["xiecheng"]
    return ordered


def run_platform(task, platform, device_id=None):
    """按指定平台执行并返回结果 JSON。"""
    if platform == "xiecheng":
        return run_ctrip(task)
    if platform == "meituan":
        return run_meituan(task, device_id)
    if platform == "feizhu":
        raise NotImplementedError("飞猪执行尚未接入")
    raise ValueError(f"不支持的 platform: {platform}")


def should_manage_mobile_app(platform):
    """是否需要在调度层做启动/关闭 App 管理。"""
    return platform in {"xiecheng", "meituan"}


def main():
    print("=" * 60)
    print("  手机端调度：领任务 → 执行 → 上报（app_crawl_tasks）")
    print("  云端地址:", config.BASE_URL)
    print("  轮询间隔:", config.POLL_INTERVAL, "秒")
    print("=" * 60)

    while True:
        ok, task = claim_task()
        if not ok:
            print(f"[错误] 领任务失败: {task}")
            time.sleep(config.POLL_INTERVAL)
            continue
        if not task:
            print("[无任务] 等待下次轮询...（请在「手机端 - 创建任务」页创建任务）")
            time.sleep(config.POLL_INTERVAL)
            continue

        task_id = task.get("task_id", "")
        hotel_name = task.get("hotel_name", "")
        platforms = get_task_platforms(task)
        device_id = (task.get("device_id") or "").strip() or None
        print(f"[已领取任务] task_id={task_id} 酒店={hotel_name} 平台={','.join(platforms)}")

        platform_results = {}
        platform_errors = {}
        try:
            for platform in platforms:
                print(f"  开始执行平台: {platform}")
                app_started = False
                try:
                    if should_manage_mobile_app(platform):
                        pkg = start_app_for_platform(platform, device_id=device_id, wait_sec=2.0)
                        app_started = True
                        print(f"    已启动 App: {pkg}")
                    result = run_platform(task, platform, device_id=device_id)
                    platform_results[platform] = result
                    print(f"    平台执行完成: {platform}")
                except Exception as platform_err:
                    platform_errors[platform] = str(platform_err)
                    print(f"    平台执行失败: {platform} -> {platform_err}")
                finally:
                    if app_started and should_manage_mobile_app(platform):
                        try:
                            pkg = stop_app_for_platform(platform, device_id=device_id)
                            print(f"    已关闭 App: {pkg}")
                        except Exception as close_err:
                            print(f"    关闭 App 失败（忽略）: {close_err}")

            all_success = not platform_errors and bool(platform_results)
            final_result = {
                "task_id": task_id,
                "hotel_name": task.get("hotel_name"),
                "location": task.get("location"),
                "platforms": platforms,
                "platform_results": platform_results,
                "platform_errors": platform_errors,
            }

            if report_result(task_id, all_success, result=final_result, error="; ".join(platform_errors.values()) or None):
                print(f"  任务 {task_id} 已上报成功")
            else:
                print(f"  任务 {task_id} 上报失败")
        except Exception as e:
            print(f"  执行失败: {e}")
            fail_result = {
                "hotel_name": task.get("hotel_name"),
                "location": task.get("location"),
                "platform": task.get("platform"),
                "status": "failed",
                "error": str(e),
            }
            report_result(task_id, False, result=fail_result, error=str(e))
            print("  已上报失败状态")

        time.sleep(1)


if __name__ == "__main__":
    main()

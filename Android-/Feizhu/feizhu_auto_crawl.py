# -*- coding: utf-8 -*-
"""
飞猪自动打开并进入酒店详情，触发 Fiddler 抓包。
依赖: pip install uiautomator2
首次使用可执行: python -m uiautomator2 init
"""
import sys
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
IN_DIR = REPO_ROOT / "Android-" / "json" / "in"
OUT_DIR = REPO_ROOT / "Android-" / "json" / "out"

# ---------- 写死的参数 ----------
HOTEL_NAME = "杭州西湖国宾馆"
FLIGGY_PACKAGE = "com.taobao.trip"
WAIT_AFTER_LAUNCH = 3
WAIT_AFTER_SEARCH = 2
WAIT_AFTER_TAP_FIRST = 2
MAX_RETRIES = 2
OUTPUT_MODE = "overwrite"  # overwrite => hotel_data.json；timestamp => 带时间戳保留历史
AUTO_PARSE_AFTER_CAPTURE = True

# 由于飞猪是 Flutter，自绘控件对 uiautomator2 的可访问树不一定完整，
# 因此在关键步骤上保留坐标兜底（只用于“点哪里触发接口”）。
HOME_HOTEL_TILE_XY = (160, 645)          # 首页红框“酒店”入口大致中心
SEARCH_BAR_XY = (540, 105)             # 搜索框区域大致中心（键盘页顶部）
FIRST_HOTEL_CANDIDATE_YS = [720, 760, 800]  # 点第一个酒店时，y 候选值（从上到下微调）

CAPTURE_TIMEOUT_S = 60                  # 点击第一个酒店后，最多等多久落盘
# ------------------------------

def _wait_file_stable(p: Path, timeout_s: float = 15.0, interval_s: float = 0.5) -> None:
    """
    等文件写入完成（避免解析时读到半截内容）。
    判断标准：文件大小在连续两次检查中保持不变。
    """
    deadline = time.time() + timeout_s
    last_size = None
    stable_rounds = 0
    while time.time() < deadline:
        if not p.exists():
            stable_rounds = 0
            last_size = None
            time.sleep(interval_s)
            continue

        size = p.stat().st_size
        if last_size is not None and size == last_size:
            stable_rounds += 1
            if stable_rounds >= 2:
                return
        else:
            stable_rounds = 0

        last_size = size
        time.sleep(interval_s)

    # 超时仍返回，由后续解析脚本自己处理报错


def _set_input_ime(d, enable: bool) -> None:
    """uiautomator2 在不同版本里方法名可能不同；做一次兼容。"""
    for fn in ("set_input_ime", "set_fastinput_ime"):
        try:
            getattr(d, fn)(enable)
            return
        except Exception:
            pass
    # 如果两种都不可用，就退回不切 IME（仍可能能输入）
    return


def _wait_for_new_feizhu_detail(before: set[Path], timeout_s: float) -> Path | None:
    """轮询 Android-/json/in 目录，新文件落盘后返回其路径。"""
    deadline = time.time() + timeout_s
    latest: Path | None = None
    while time.time() < deadline:
        if IN_DIR.exists():
            after = set(IN_DIR.glob("feizhu_detail_*.json"))
        else:
            after = set()
        new_files = after - before
        if new_files:
            latest = max(new_files, key=lambda p: p.stat().st_mtime)
            return latest
        time.sleep(1.0)
    return None

def main() -> None:
    try:
        import uiautomator2 as u2
    except ImportError:
        print("请先安装: pip install uiautomator2", file=sys.stderr)
        sys.exit(1)

    # 连设备（USB 一台时空字符串即可）
    d = u2.connect()

    for attempt in range(MAX_RETRIES):
        try:
            before = set(IN_DIR.glob("feizhu_detail_*.json")) if IN_DIR.exists() else set()
            # 启动飞猪
            d.app_stop(FLIGGY_PACKAGE)
            time.sleep(0.5)
            d.app_start(FLIGGY_PACKAGE)
            time.sleep(WAIT_AFTER_LAUNCH)

            # 1) 首页：点“酒店”入口（匹配你的手动流程图第 1 步）
            clicked = (
                d(text="酒店").click_exists(timeout=3)
                or d(textContains="酒店").click_exists(timeout=3)
            )
            if not clicked:
                # 坐标兜底（只要画面分辨率不至于变太夸张）
                d.click(*HOME_HOTEL_TILE_XY)
            time.sleep(2)

            # 2) 搜索页：聚焦搜索框 -> IME 注入酒店名 -> 触发搜索
            focused = (
                d(resourceId="com.taobao.trip:id/search_box").click_exists(timeout=2)
                or d(resourceId="com.taobao.trip:id/home_frg_searchbar").click_exists(timeout=2)
                or d(text="搜索").click_exists(timeout=2)
            )
            if not focused:
                d.click(*SEARCH_BAR_XY)
            time.sleep(1)

            _set_input_ime(d, True)
            d.send_keys(HOTEL_NAME)
            time.sleep(0.2)
            _set_input_ime(d, False)

            # 用回车触发（比找“搜索”按钮 text 更稳）
            try:
                d.press("enter")
            except Exception:
                try:
                    d.send_action("search")
                except Exception:
                    pass
            time.sleep(WAIT_AFTER_SEARCH)

            # 3) 结果页：点第一个酒店（只要第 1 条触发 detail 即可）
            got_capture = False
            for y in FIRST_HOTEL_CANDIDATE_YS:
                d.click(540, y)
                time.sleep(WAIT_AFTER_TAP_FIRST)
                latest_file = _wait_for_new_feizhu_detail(before, timeout_s=CAPTURE_TIMEOUT_S)
                if latest_file is not None:
                    got_capture = True

                    print("Captured =>", latest_file.name)

                    # 方案 A：抓到文件后立刻解析房型/套餐
                    _wait_file_stable(latest_file)
                    parser_script = REPO_ROOT / "scripts" / "feizhu_task_export.py"
                    OUT_DIR.mkdir(parents=True, exist_ok=True)

                    cmd = [
                        sys.executable,
                        str(parser_script),
                        "-i",
                        str(latest_file),
                        "-o",
                        str(OUT_DIR),
                        "--output-mode",
                        OUTPUT_MODE,
                        "--mode",
                        "all",
                    ]
                    print("Parsing =>", " ".join(cmd))
                    res = subprocess.run(cmd, capture_output=True, text=True)
                    if res.returncode != 0:
                        print("Parse failed (stdout):\n", res.stdout, file=sys.stderr)
                        print("Parse failed (stderr):\n", res.stderr, file=sys.stderr)
                        raise RuntimeError("feizhu_task_export.py failed")
                    if OUTPUT_MODE == "overwrite":
                        print("Parse done =>", str(OUT_DIR / "hotel_data.json"))
                    else:
                        print("Parse done => output in", str(OUT_DIR))
                    return

                # 未捕获则尝试下一 y；如果页面已进入详情，后续点可能无效
                # 因此 y 候选应尽量少，先保证命中接口。

            if not got_capture:
                print("Timeout: no new feizhu_detail_*.json captured after clicking first hotel.", file=sys.stderr)
        except Exception as e:
            print(f"Attempt {attempt + 1} error: {e}", file=sys.stderr)
            if attempt >= MAX_RETRIES - 1:
                raise

    print("未检测到新 feizhu_detail_*.json，请确认 Fiddler 已开且代理正确。", file=sys.stderr)
    print(f"抓包目录: {IN_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()

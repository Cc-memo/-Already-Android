# -*- coding: utf-8 -*-
"""
流程编排模块 (Pipeline)
负责模块调用顺序，不实现任何爬虫或具体业务逻辑

流程：
1. 第一次搜索 -> 获取价格数据
2. 执行比价逻辑
3. 第二次搜索 -> 获取最新价格数据
4. 对比两次搜索结果，检测价格变动
"""

import os
import sys
import json
import copy
import time
from typing import Dict, List, Tuple, Optional

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# 尝试导入可视化库
try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # 定义空颜色类，避免报错
    class Fore:
        GREEN = YELLOW = RED = BLUE = CYAN = MAGENTA = RESET = ""
    class Style:
        BRIGHT = DIM = RESET_ALL = ""

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据文件路径
MEITUAN_DATA_FILE = os.path.join(SCRIPT_DIR, "meituan", "meituan_hotel.json")
XIECHENG_DATA_FILE = os.path.join(SCRIPT_DIR, "xiecheng", "hotel_data.json")

# 价格变动阈值
PRICE_CHANGE_THRESHOLD = 30.0       # 绝对变动阈值（元）
PRICE_CHANGE_PERCENT = 5.0          # 相对变动阈值（百分比）

# ==================== 可视化工具函数 ====================

def print_colored(text: str, color: str = Fore.RESET, style: str = Style.RESET_ALL):
    """打印彩色文本"""
    if COLORAMA_AVAILABLE:
        print(f"{style}{color}{text}{Style.RESET_ALL}")
    else:
        print(text)


def print_step_header(step_num: int, total_steps: int, title: str):
    """打印步骤标题（带颜色和进度）"""
    progress = f"[{step_num}/{total_steps}]"
    bar_length = 30
    filled = int(bar_length * step_num / total_steps)
    bar = "█" * filled + "░" * (bar_length - filled)
    percentage = int(100 * step_num / total_steps)
    
    print_colored("\n" + "=" * 70, Fore.CYAN)
    print_colored(f"  {progress} {title}", Fore.CYAN, Style.BRIGHT)
    print_colored(f"  进度: [{bar}] {percentage}%", Fore.CYAN)
    print_colored("=" * 70, Fore.CYAN)


def print_success(message: str):
    """打印成功消息"""
    print_colored(f"✅ {message}", Fore.GREEN, Style.BRIGHT)


def print_warning(message: str):
    """打印警告消息"""
    print_colored(f"⚠️  {message}", Fore.YELLOW, Style.BRIGHT)


def print_error(message: str):
    """打印错误消息"""
    print_colored(f"❌ {message}", Fore.RED, Style.BRIGHT)


def print_info(message: str):
    """打印信息消息"""
    print_colored(f"ℹ️  {message}", Fore.BLUE)


def print_flowchart():
    """打印流程图（ASCII 艺术）"""
    flowchart = f"""
{Fore.CYAN}{Style.BRIGHT}
╔══════════════════════════════════════════════════════════════════╗
║                    Pipeline 流程图                                ║
╚══════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}
{Fore.GREEN}    [开始]{Style.RESET_ALL}
         │
         ▼
{Fore.YELLOW}    ┌─────────────────────────────────┐{Style.RESET_ALL}
{Fore.YELLOW}    │  步骤 1: 第一次搜索              │{Style.RESET_ALL}
{Fore.YELLOW}    │  ┌──────────┐  ┌──────────┐     │{Style.RESET_ALL}
{Fore.YELLOW}    │  │ 携程爬虫 │  │ 美团爬虫 │     │{Style.RESET_ALL}
{Fore.YELLOW}    │  └──────────┘  └──────────┘     │{Style.RESET_ALL}
{Fore.YELLOW}    └─────────────────────────────────┘{Style.RESET_ALL}
         │
         ▼
{Fore.MAGENTA}    ┌─────────────────────────────────┐{Style.RESET_ALL}
{Fore.MAGENTA}    │  步骤 2: 执行比价分析            │{Style.RESET_ALL}
{Fore.MAGENTA}    │  • 加载数据                      │{Style.RESET_ALL}
{Fore.MAGENTA}    │  • 价格比较                      │{Style.RESET_ALL}
{Fore.MAGENTA}    │  • 生成报告                      │{Style.RESET_ALL}
{Fore.MAGENTA}    └─────────────────────────────────┘{Style.RESET_ALL}
         │
         ▼
{Fore.YELLOW}    ┌─────────────────────────────────┐{Style.RESET_ALL}
{Fore.YELLOW}    │  步骤 3: 第二次搜索              │{Style.RESET_ALL}
{Fore.YELLOW}    │  ┌──────────┐  ┌──────────┐     │{Style.RESET_ALL}
{Fore.YELLOW}    │  │ 携程爬虫 │  │ 美团爬虫 │     │{Style.RESET_ALL}
{Fore.YELLOW}    │  └──────────┘  └──────────┘     │{Style.RESET_ALL}
{Fore.YELLOW}    └─────────────────────────────────┘{Style.RESET_ALL}
         │
         ▼
{Fore.BLUE}    ┌─────────────────────────────────┐{Style.RESET_ALL}
{Fore.BLUE}    │  步骤 4: 价格变动检测            │{Style.RESET_ALL}
{Fore.BLUE}    │  • 对比两次搜索结果              │{Style.RESET_ALL}
{Fore.BLUE}    │  • 检测价格变化                  │{Style.RESET_ALL}
{Fore.BLUE}    │  • 输出变动警告                  │{Style.RESET_ALL}
{Fore.BLUE}    └─────────────────────────────────┘{Style.RESET_ALL}
         │
         ▼
{Fore.GREEN}    [完成]{Style.RESET_ALL}
"""
    print(flowchart)


def generate_mermaid_flowchart(output_file: str = "pipeline_flowchart.md"):
    """生成 Mermaid 流程图文件"""
    mermaid_content = """# Pipeline 流程图

```mermaid
flowchart TD
    Start([开始]) --> Step1[步骤 1: 第一次搜索]
    Step1 --> Search1_1[携程爬虫]
    Step1 --> Search1_2[美团爬虫]
    Search1_1 --> Save1[保存第一次搜索结果]
    Search1_2 --> Save1
    Save1 --> Step2[步骤 2: 执行比价分析]
    Step2 --> Load[加载数据]
    Load --> Compare[价格比较]
    Compare --> Report[生成比价报告]
    Report --> Step3[步骤 3: 第二次搜索]
    Step3 --> Search2_1[携程爬虫]
    Step3 --> Search2_2[美团爬虫]
    Search2_1 --> Save2[保存第二次搜索结果]
    Search2_2 --> Save2
    Save2 --> Step4[步骤 4: 价格变动检测]
    Step4 --> Detect[对比两次搜索结果]
    Detect --> Check{价格是否变动?}
    Check -->|是| Alert[输出变动警告]
    Check -->|否| Stable[价格稳定提示]
    Alert --> End([完成])
    Stable --> End
    
    style Start fill:#90EE90
    style End fill:#90EE90
    style Step1 fill:#FFD700
    style Step2 fill:#DDA0DD
    style Step3 fill:#FFD700
    style Step4 fill:#87CEEB
    style Alert fill:#FF6B6B
    style Stable fill:#90EE90
```

## 说明

- **步骤 1**: 第一次搜索，获取初始价格数据
- **步骤 2**: 执行比价分析，生成比价报告
- **步骤 3**: 第二次搜索，获取最新价格数据
- **步骤 4**: 对比两次搜索结果，检测价格变动

## 查看方式

1. 在 VS Code 中安装 "Markdown Preview Mermaid Support" 插件
2. 在 GitHub/GitLab 等平台查看（自动渲染）
3. 使用在线工具：https://mermaid.live/
"""
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, output_file)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(mermaid_content)
        print_info(f"流程图已保存到: {output_file}")
        return output_path
    except Exception as e:
        print_error(f"保存流程图失败: {e}")
        return None


# ==================== 数据加载函数 ====================

def load_hotel_data(file_path: str) -> Optional[Dict]:
    """
    加载酒店数据 JSON 文件
    
    参数:
        file_path: JSON 文件路径
    
    返回:
        加载的数据字典，失败返回 None
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[警告] 文件不存在: {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"[警告] JSON 格式错误: {file_path}")
        return None


def load_all_data() -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    加载美团和携程的酒店数据
    
    返回:
        (美团数据, 携程数据) 元组
    """
    meituan_data = load_hotel_data(MEITUAN_DATA_FILE)
    xiecheng_data = load_hotel_data(XIECHENG_DATA_FILE)
    return meituan_data, xiecheng_data


def deep_copy_data(meituan_data: Optional[Dict], xiecheng_data: Optional[Dict]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    深拷贝数据，用于保存第一次搜索结果
    
    参数:
        meituan_data: 美团数据
        xiecheng_data: 携程数据
    
    返回:
        深拷贝后的数据元组
    """
    meituan_copy = copy.deepcopy(meituan_data) if meituan_data else None
    xiecheng_copy = copy.deepcopy(xiecheng_data) if xiecheng_data else None
    return meituan_copy, xiecheng_copy


# ==================== 搜索调用函数 ====================

def run_search(search_input: str) -> Tuple[bool, bool]:
    """
    调用 search.py 执行搜索（黑盒调用）
    
    参数:
        search_input: 搜索输入，格式为 "城市/地址,酒店关键词"
    
    返回:
        (携程成功标志, 美团成功标志) 元组
    """
    # 导入 search 模块的函数
    from search import run_parallel
    
    print_colored("\n" + "─" * 70, Fore.CYAN)
    print_colored("  🔍 执行搜索...", Fore.CYAN, Style.BRIGHT)
    print_colored("─" * 70, Fore.CYAN)
    
    ctrip_ok, meituan_ok = run_parallel(search_input)
    
    # 显示搜索结果状态
    if ctrip_ok:
        print_success("携程搜索成功")
    else:
        print_error("携程搜索失败")
    
    if meituan_ok:
        print_success("美团搜索成功")
    else:
        print_error("美团搜索失败")
    
    return ctrip_ok, meituan_ok


# ==================== 比价调用函数 ====================

def run_price_comparison():
    """
    调用 price_comparison.py 执行比价逻辑（黑盒调用）
    """
    # 导入 price_comparison 模块的 main 函数
    from price_comparison import main as price_comparison_main
    
    print_colored("\n" + "─" * 70, Fore.MAGENTA)
    print_colored("  📊 执行比价分析...", Fore.MAGENTA, Style.BRIGHT)
    print_colored("─" * 70, Fore.MAGENTA)
    
    price_comparison_main()


# ==================== 价格变动检测函数 ====================

def parse_price(price_str: str) -> float:
    """
    解析价格字符串，提取数值
    
    参数:
        price_str: 价格字符串，如 "¥540"
    
    返回:
        价格数值
    """
    import re
    price_clean = re.sub(r'[^\d.]', '', price_str)
    try:
        return float(price_clean)
    except ValueError:
        return 0.0


def extract_room_prices(data: Optional[Dict]) -> Dict[str, float]:
    """
    从酒店数据中提取房型价格映射
    
    参数:
        data: 酒店数据字典
    
    返回:
        {房型名称: 价格} 字典
    """
    if not data:
        return {}
    
    prices = {}
    room_list = data.get("房型列表", [])
    
    for room in room_list:
        room_name = room.get("房型名称", "")
        price_str = room.get("价格", "¥0")
        remaining = room.get("剩余房间", "")
        
        # 如果房间满房，跳过（不参与价格比较和变动检测）
        if remaining and ("满房" in remaining or "全部订完" in remaining):
            continue
        
        price = parse_price(price_str)
        
        # 如果价格为0或无效，也跳过
        if price <= 0:
            continue
        
        # 使用房型名称作为唯一标识
        # 如果有重复的房型名称，保留价格最低的
        if room_name not in prices or price < prices[room_name]:
            prices[room_name] = price
    
    return prices


def extract_room_status(data: Optional[Dict]) -> Dict[str, str]:
    """
    从酒店数据中提取房型状态映射（用于检测满房状态变化）
    
    参数:
        data: 酒店数据字典
    
    返回:
        {房型名称: 状态} 字典，状态为"有房"或"满房"
    """
    if not data:
        return {}
    
    statuses = {}
    room_list = data.get("房型列表", [])
    
    for room in room_list:
        room_name = room.get("房型名称", "")
        remaining = room.get("剩余房间", "")
        
        # 判断房间状态
        if remaining and ("满房" in remaining or "全部订完" in remaining):
            status = "满房"
        else:
            status = "有房"
        
        statuses[room_name] = status
    
    return statuses


def check_price_changes(
    first_meituan: Optional[Dict],
    first_xiecheng: Optional[Dict],
    second_meituan: Optional[Dict],
    second_xiecheng: Optional[Dict]
) -> Tuple[List[Dict], List[Dict]]:
    """
    检测两次搜索之间的价格变动和房间状态变化
    
    参数:
        first_meituan: 第一次搜索的美团数据
        first_xiecheng: 第一次搜索的携程数据
        second_meituan: 第二次搜索的美团数据
        second_xiecheng: 第二次搜索的携程数据
    
    返回:
        (价格变动列表, 房间状态变化列表)
        价格变动列表：每项包含平台、房型、原价、新价、变动幅度等信息
        房间状态变化列表：每项包含平台、房型、原状态、新状态等信息
    """
    price_changes = []
    status_changes = []
    
    # 检测美团价格变动和状态变化
    first_meituan_prices = extract_room_prices(first_meituan)
    second_meituan_prices = extract_room_prices(second_meituan)
    first_meituan_statuses = extract_room_status(first_meituan)
    second_meituan_statuses = extract_room_status(second_meituan)
    
    # 检测价格变动
    for room_name, first_price in first_meituan_prices.items():
        if room_name in second_meituan_prices:
            second_price = second_meituan_prices[room_name]
            change = detect_single_price_change("美团", room_name, first_price, second_price)
            if change:
                price_changes.append(change)
    
    # 检测状态变化（从有房变为满房）
    for room_name, first_status in first_meituan_statuses.items():
        if room_name in second_meituan_statuses:
            second_status = second_meituan_statuses[room_name]
            if first_status == "有房" and second_status == "满房":
                status_changes.append({
                    "platform": "美团",
                    "room_name": room_name,
                    "first_status": first_status,
                    "second_status": second_status,
                    "change_type": "变为满房"
                })
    
    # 检测携程价格变动和状态变化
    first_xiecheng_prices = extract_room_prices(first_xiecheng)
    second_xiecheng_prices = extract_room_prices(second_xiecheng)
    first_xiecheng_statuses = extract_room_status(first_xiecheng)
    second_xiecheng_statuses = extract_room_status(second_xiecheng)
    
    # 检测价格变动
    for room_name, first_price in first_xiecheng_prices.items():
        if room_name in second_xiecheng_prices:
            second_price = second_xiecheng_prices[room_name]
            change = detect_single_price_change("携程", room_name, first_price, second_price)
            if change:
                price_changes.append(change)
    
    # 检测状态变化（从有房变为满房）
    for room_name, first_status in first_xiecheng_statuses.items():
        if room_name in second_xiecheng_statuses:
            second_status = second_xiecheng_statuses[room_name]
            if first_status == "有房" and second_status == "满房":
                status_changes.append({
                    "platform": "携程",
                    "room_name": room_name,
                    "first_status": first_status,
                    "second_status": second_status,
                    "change_type": "变为满房"
                })
    
    return price_changes, status_changes


def detect_single_price_change(
    platform: str,
    room_name: str,
    first_price: float,
    second_price: float
) -> Optional[Dict]:
    """
    检测单个房源的价格变动
    
    价格变动判断规则:
    - 价格变化 ≥ 30 元 或 变化比例 ≥ 5%，则认为"价格发生变动"
    
    参数:
        platform: 平台名称
        room_name: 房型名称
        first_price: 第一次价格
        second_price: 第二次价格
    
    返回:
        价格变动信息字典，无变动返回 None
    """
    if first_price <= 0 or second_price <= 0:
        return None
    
    # 计算价格变化
    price_diff = second_price - first_price
    price_diff_abs = abs(price_diff)
    price_change_percent = (price_diff_abs / first_price) * 100
    
    # 判断是否达到变动阈值
    is_changed = (price_diff_abs >= PRICE_CHANGE_THRESHOLD or 
                  price_change_percent >= PRICE_CHANGE_PERCENT)
    
    if not is_changed:
        return None
    
    # 构建变动信息
    direction = "上涨" if price_diff > 0 else "下降"
    
    return {
        "platform": platform,
        "room_name": room_name,
        "first_price": first_price,
        "second_price": second_price,
        "price_diff": price_diff,
        "price_diff_abs": price_diff_abs,
        "price_change_percent": price_change_percent,
        "direction": direction
    }


# ==================== 结果输出函数 ====================

def print_price_changes(price_changes: List[Dict], status_changes: List[Dict]):
    """
    输出价格变动和房间状态变化提示（带颜色）
    
    参数:
        price_changes: 价格变动列表
        status_changes: 房间状态变化列表
    """
    has_changes = len(price_changes) > 0 or len(status_changes) > 0
    
    if not has_changes:
        print_colored("\n" + "=" * 70, Fore.GREEN)
        print_success("价格稳定：两次搜索之间没有检测到显著价格变动")
        print_success("房间状态稳定：没有检测到房间状态变化")
        print_info(f"   (变动阈值: ≥{PRICE_CHANGE_THRESHOLD}元 或 ≥{PRICE_CHANGE_PERCENT}%)")
        print_colored("=" * 70, Fore.GREEN)
        return
    
    # 输出价格变动
    if price_changes:
        print_colored("\n" + "=" * 70, Fore.YELLOW, Style.BRIGHT)
        print_warning(f"价格变动警告 - 检测到 {len(price_changes)} 个房源价格发生变动")
        print_colored("=" * 70, Fore.YELLOW)
        print()
        
        for i, change in enumerate(price_changes, 1):
            direction_color = Fore.RED if change['direction'] == '上涨' else Fore.GREEN
            print_colored(f"【{i}】{change['platform']} - {change['room_name']}", Fore.CYAN, Style.BRIGHT)
            print(f"    原价: {Fore.YELLOW}¥{change['first_price']:.0f}{Style.RESET_ALL}")
            print(f"    新价: {Fore.YELLOW}¥{change['second_price']:.0f}{Style.RESET_ALL}")
            print_colored(f"    变动: {change['direction']} ¥{change['price_diff_abs']:.0f} ({change['price_change_percent']:.1f}%)", 
                         direction_color, Style.BRIGHT)
            print()
        
        print_colored("=" * 70, Fore.YELLOW)
        print_info("提示: 价格已发生变动，请根据实际情况决定是否重新比价")
        print_colored("=" * 70, Fore.YELLOW)
    
    # 输出房间状态变化（满房警告）
    if status_changes:
        print_colored("\n" + "=" * 70, Fore.RED, Style.BRIGHT)
        print_warning(f"⚠️  房间状态变化警告 - 检测到 {len(status_changes)} 个房源变为满房")
        print_colored("=" * 70, Fore.RED)
        print()
        
        for i, change in enumerate(status_changes, 1):
            print_colored(f"【{i}】{change['platform']} - {change['room_name']}", Fore.CYAN, Style.BRIGHT)
            print_colored(f"    状态变化: {change['first_status']} → {change['second_status']}", Fore.RED, Style.BRIGHT)
            print_colored(f"    ⚠️  该房间在第二次搜索时已满房，无法预订", Fore.RED)
            print()
        
        print_colored("=" * 70, Fore.RED)
        print_warning("提示: 部分房间已满房，请检查其他可用房型或重新搜索")
        print_colored("=" * 70, Fore.RED)


def popup_price_change_alert(changes: List[Dict]):
    """
    弹窗提示价格变动（可选功能）
    
    参数:
        changes: 价格变动列表
    """
    if not changes:
        return
    
    try:
        import tkinter as tk
        from tkinter import messagebox
        
        # 创建隐藏的主窗口
        root = tk.Tk()
        root.withdraw()
        
        # 构建消息内容
        msg_lines = [f"检测到 {len(changes)} 个房源价格发生变动：\n"]
        for change in changes[:5]:  # 最多显示5条
            msg_lines.append(
                f"• {change['platform']} - {change['room_name'][:20]}...\n"
                f"  {change['first_price']:.0f}元 → {change['second_price']:.0f}元 "
                f"({change['direction']}{change['price_diff_abs']:.0f}元)"
            )
        
        if len(changes) > 5:
            msg_lines.append(f"\n...还有 {len(changes) - 5} 条变动")
        
        message = "\n".join(msg_lines)
        
        # 显示弹窗
        messagebox.showwarning("价格变动警告", message)
        
        root.destroy()
        
    except ImportError:
        # tkinter 不可用，跳过弹窗
        print("[提示] 无法显示弹窗，已在控制台输出价格变动信息")
    except Exception as e:
        print(f"[提示] 弹窗显示失败: {e}")


# ==================== 主流程函数 ====================

def run_pipeline(search_input: str, enable_popup: bool = False, show_flowchart: bool = True):
    """
    执行完整的流程编排
    
    流程：
    1. 第一次搜索 -> 获取价格数据
    2. 执行比价逻辑
    3. 第二次搜索 -> 获取最新价格数据
    4. 对比两次搜索结果，检测价格变动（只执行一次，不循环）
    
    参数:
        search_input: 搜索输入，格式为 "城市/地址,酒店关键词"
        enable_popup: 是否启用弹窗提示
        show_flowchart: 是否显示流程图
    """
    # 显示流程图
    if show_flowchart:
        print_flowchart()
        time.sleep(1)  # 暂停1秒，让用户看清流程图
    
    print_colored("\n" + "=" * 70, Fore.CYAN, Style.BRIGHT)
    print_colored("  🚀 Pipeline 流程启动", Fore.CYAN, Style.BRIGHT)
    print_colored("=" * 70, Fore.CYAN)
    print_info(f"搜索参数: {search_input}")
    print_info(f"价格变动阈值: ≥{PRICE_CHANGE_THRESHOLD}元 或 ≥{PRICE_CHANGE_PERCENT}%")
    
    # ========== 步骤1: 第一次搜索 ==========
    print_step_header(1, 4, "第一次搜索")
    
    ctrip_ok_1, meituan_ok_1 = run_search(search_input)
    
    if not (ctrip_ok_1 or meituan_ok_1):
        print_error("第一次搜索失败，流程终止")
        print_warning("提示：如果浏览器启动卡住，请尝试：")
        print_info("  1. 手动关闭所有 Chrome/Chromium 窗口")
        print_info("  2. 检查网络连接")
        print_info("  3. 检查 ChromeDriver 版本是否匹配")
        return
    
    # 加载并保存第一次搜索结果
    print_info("正在保存第一次搜索结果...")
    first_meituan, first_xiecheng = load_all_data()
    first_meituan, first_xiecheng = deep_copy_data(first_meituan, first_xiecheng)
    
    print_success("第一次搜索完成，数据已保存")
    
    # ========== 步骤2: 执行比价 ==========
    print_step_header(2, 4, "执行比价分析")
    
    run_price_comparison()
    
    print_success("比价分析完成")
    
    # ========== 步骤3: 第二次搜索 ==========
    print_step_header(3, 4, "第二次搜索（价格确认）")
    
    ctrip_ok_2, meituan_ok_2 = run_search(search_input)
    
    if not (ctrip_ok_2 or meituan_ok_2):
        print_error("第二次搜索失败，流程终止")
        print_warning("提示：如果浏览器启动卡住，请尝试：")
        print_info("  1. 手动关闭所有 Chrome/Chromium 窗口")
        print_info("  2. 检查网络连接")
        print_info("  3. 检查 ChromeDriver 版本是否匹配")
        return
    
    # 加载第二次搜索结果
    print_info("正在加载第二次搜索结果...")
    second_meituan, second_xiecheng = load_all_data()
    
    print_success("第二次搜索完成")
    
    # ========== 步骤4: 价格变动检测 ==========
    print_step_header(4, 4, "价格变动检测")
    
    # 对比两次搜索结果（只执行一次，不循环）
    print_info("正在对比两次搜索结果...")
    price_changes, status_changes = check_price_changes(
        first_meituan, first_xiecheng,
        second_meituan, second_xiecheng
    )
    
    # 输出价格变动和状态变化提示
    print_price_changes(price_changes, status_changes)
    
    # 如果启用弹窗且有价格变动或状态变化，显示弹窗
    if enable_popup and (price_changes or status_changes):
        popup_price_change_alert(price_changes)
    
    # ========== 流程结束 ==========
    print_colored("\n" + "=" * 70, Fore.GREEN, Style.BRIGHT)
    print_colored("  🎯 Pipeline 流程完成", Fore.GREEN, Style.BRIGHT)
    print_colored("=" * 70, Fore.GREEN)
    
    # 生成 Mermaid 流程图文件
    generate_mermaid_flowchart()


def main():
    """主函数 - 交互式入口"""
    print_colored("=" * 70, Fore.CYAN, Style.BRIGHT)
    print_colored("  🏨 酒店价格监控流程 (Pipeline)", Fore.CYAN, Style.BRIGHT)
    print_colored("=" * 70, Fore.CYAN)
    print("\n流程说明:")
    print("  1. 第一次搜索 → 获取初始价格")
    print("  2. 执行比价分析 → 生成比价报告")
    print("  3. 第二次搜索 → 获取最新价格")
    print("  4. 价格变动检测 → 检查是否有显著变化")
    print()
    
    # 检查可视化库
    if not COLORAMA_AVAILABLE:
        print_warning("未安装 colorama，将使用普通文本输出")
        print_info("安装命令: pip install colorama")
    if not TQDM_AVAILABLE:
        print_info("提示: 安装 tqdm 可获得更好的进度条显示 (pip install tqdm)")
    print()
    
    # 获取用户输入
    search_input = input("请输入查询条件（格式: 城市/地址,酒店关键词）: ").strip()
    
    if not search_input:
        print("输入为空，使用默认值: 上海,如家")
        search_input = "上海,如家"
    
    # 验证输入格式
    parts = search_input.replace('，', ',').split(',')
    if len(parts) < 2:
        print_error("输入格式错误！请使用格式: 城市/地址,酒店关键词")
        return
    
    # 是否启用弹窗提示
    enable_popup_input = input("\n是否启用弹窗提示? (y/n, 默认n): ").strip().lower()
    enable_popup = enable_popup_input == 'y'
    
    # 是否显示流程图
    show_flowchart_input = input("是否显示流程图? (y/n, 默认y): ").strip().lower()
    show_flowchart = show_flowchart_input != 'n'
    
    # 执行流程
    run_pipeline(search_input, enable_popup=enable_popup, show_flowchart=show_flowchart)


if __name__ == "__main__":
    main()

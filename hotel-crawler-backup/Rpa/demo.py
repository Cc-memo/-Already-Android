# -*- coding: utf-8 -*-
"""
酒店价格监控与自动上架系统 - 演示 Demo

【演示目的】
1. 能搜 - 搜索携程和美团
2. 能对齐 - 确认是同一家酒店
3. 能看出哪个平台便宜 - 价格对比
4. 自动上架 - 在代理通上架
5. 购买前验证 - 二次搜索确认价格

【使用方式】
  # 完整演示（使用真实搜索）
  python demo.py
  
  # 演示模式（使用已有数据，不启动浏览器）
  python demo.py --dry-run
  
  # 指定酒店
  python demo.py --hotel "上海,美利居酒店"
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据文件路径
XIECHENG_FILE = os.path.join(SCRIPT_DIR, "xiecheng", "hotel_data.json")
MEITUAN_FILE = os.path.join(SCRIPT_DIR, "meituan", "meituan_hotel.json")


# ==================== 显示工具函数 ====================

def print_title(title: str):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_step(step_num: int, total: int, title: str):
    """打印步骤标题"""
    print("\n" + "-" * 60)
    print(f"【步骤{step_num}/{total}】{title}")
    print("-" * 60)


def print_success(message: str):
    """打印成功消息"""
    print(f"  ✅ {message}")


def print_error(message: str):
    """打印错误消息"""
    print(f"  ❌ {message}")


def print_info(message: str):
    """打印信息"""
    print(f"  ℹ️  {message}")


def print_warning(message: str):
    """打印警告"""
    print(f"  ⚠️  {message}")


def print_result(label: str, value: str):
    """打印结果"""
    print(f"  → {label}: {value}")


def wait_for_confirm(message: str = "按回车继续..."):
    """等待用户确认"""
    try:
        input(f"\n  {message}")
    except (EOFError, KeyboardInterrupt):
        pass


# ==================== 步骤1: 搜索功能 ====================

def step1_search(search_input: str, dry_run: bool = False) -> bool:
    """
    步骤1: 搜索功能
    
    参数:
        search_input: 搜索条件（格式: 城市,酒店关键词）
        dry_run: 是否演示模式（不实际搜索）
    
    返回:
        是否成功
    """
    print_step(1, 5, "搜索功能")
    
    print_info(f"搜索条件: {search_input}")
    
    if dry_run:
        print_info("演示模式：使用已有数据，跳过实际搜索")
        # 检查是否有已有数据
        if os.path.exists(XIECHENG_FILE) and os.path.exists(MEITUAN_FILE):
            print_success("携程数据已存在")
            print_success("美团数据已存在")
            return True
        else:
            print_error("未找到已有数据，请先运行完整搜索")
            return False
    
    # 实际搜索
    print_info("正在搜索携程...")
    print_info("正在搜索美团...")
    
    try:
        from search import run_parallel
        ctrip_ok, meituan_ok = run_parallel(search_input)
        
        if ctrip_ok:
            print_success("携程搜索成功")
        else:
            print_error("携程搜索失败")
        
        if meituan_ok:
            print_success("美团搜索成功")
        else:
            print_error("美团搜索失败")
        
        return ctrip_ok or meituan_ok
        
    except Exception as e:
        print_error(f"搜索出错: {e}")
        return False


# ==================== 步骤2: 酒店对齐 ====================

def step2_match_hotel() -> Tuple[bool, Dict, Dict]:
    """
    步骤2: 酒店对齐
    
    返回:
        (是否匹配, 携程数据, 美团数据)
    """
    print_step(2, 5, "酒店对齐")
    
    # 加载数据
    if not os.path.exists(XIECHENG_FILE):
        print_error(f"携程数据不存在: {XIECHENG_FILE}")
        return False, {}, {}
    
    if not os.path.exists(MEITUAN_FILE):
        print_error(f"美团数据不存在: {MEITUAN_FILE}")
        return False, {}, {}
    
    with open(XIECHENG_FILE, 'r', encoding='utf-8') as f:
        xiecheng_data = json.load(f)
    
    with open(MEITUAN_FILE, 'r', encoding='utf-8') as f:
        meituan_data = json.load(f)
    
    # 显示酒店信息
    xiecheng_hotel = xiecheng_data.get("酒店名称", "未知")
    meituan_hotel = meituan_data.get("酒店关键词", "未知")
    xiecheng_time = xiecheng_data.get("搜索时间", "未知")
    meituan_time = meituan_data.get("搜索时间", "未知")
    
    print_result("携程酒店", xiecheng_hotel)
    print_result("携程搜索时间", xiecheng_time)
    print_result("美团酒店", meituan_hotel)
    print_result("美团搜索时间", meituan_time)
    
    # 判断是否匹配
    # 简单匹配逻辑：关键词包含
    xiecheng_key = xiecheng_hotel.replace("酒店", "").replace("（", "").replace("(", "").split("）")[0].split(")")[0]
    meituan_key = meituan_hotel.replace("酒店", "")
    
    is_match = False
    if xiecheng_key and meituan_key:
        # 检查是否有共同关键词
        if meituan_key in xiecheng_hotel or xiecheng_key in meituan_hotel:
            is_match = True
        # 或者都包含相同的酒店名称
        elif any(word in xiecheng_hotel and word in meituan_hotel for word in ["美利居", "如家", "汉庭", "全季"]):
            is_match = True
    
    if is_match:
        print_success("确认是同一家酒店")
    else:
        print_warning("酒店名称不完全匹配，请人工确认")
    
    return True, xiecheng_data, meituan_data


# ==================== 步骤3: 价格对比 ====================

def step3_compare_price(xiecheng_data: Dict, meituan_data: Dict) -> List[Dict]:
    """
    步骤3: 价格对比
    
    参数:
        xiecheng_data: 携程数据
        meituan_data: 美团数据
    
    返回:
        有利润的房型列表
    """
    print_step(3, 5, "价格对比")
    
    try:
        from price_comparison import DataLoader, PriceComparator
        
        # 解析房间数据
        xiecheng_rooms = DataLoader.parse_room_data(xiecheng_data, "携程")
        meituan_rooms = DataLoader.parse_room_data(meituan_data, "美团")
        
        print_info(f"携程房型数: {len(xiecheng_rooms)}")
        print_info(f"美团房型数: {len(meituan_rooms)}")
        
        # 执行比价
        comparator = PriceComparator(
            threshold=50.0, 
            threshold_percent=10.0, 
            profit_threshold_percent=20.0
        )
        comparisons = comparator.compare_all_rooms(xiecheng_rooms, meituan_rooms)
        
        print_info(f"可比较的房型数: {len(comparisons)}")
        
        if not comparisons:
            print_warning("没有找到可比较的房型")
            return []
        
        # 按房间类型分组显示
        grouped = {}
        for comp in comparisons:
            key = f"{comp.room_type.value} | {comp.window_type.value} | {comp.breakfast_type.value}"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(comp)
        
        print("\n  📊 价格对比结果:")
        print("  " + "-" * 50)
        
        profitable_rooms = []
        
        for room_desc, comps in sorted(grouped.items()):
            # 找出最便宜的
            best_comp = min(comps, key=lambda c: min(c.price_a, c.price_b))
            
            if best_comp.price_a < best_comp.price_b:
                cheaper = "携程"
                cheaper_price = best_comp.price_a
                other_price = best_comp.price_b
            elif best_comp.price_b < best_comp.price_a:
                cheaper = "美团"
                cheaper_price = best_comp.price_b
                other_price = best_comp.price_a
            else:
                cheaper = "价格相同"
                cheaper_price = best_comp.price_a
                other_price = best_comp.price_b
            
            save = abs(other_price - cheaper_price)
            save_percent = (save / cheaper_price) * 100 if cheaper_price > 0 else 0
            
            print(f"\n  【{room_desc}】")
            print(f"     携程: {best_comp.price_a:.0f}元")
            print(f"     美团: {best_comp.price_b:.0f}元")
            
            if save > 0:
                print(f"     → {cheaper} 更便宜，节省 {save:.0f}元 ({save_percent:.1f}%)")
                
                if best_comp.has_profit:
                    print(f"     💰 有利润空间（价差>{20}%）")
                    profitable_rooms.append({
                        "room_desc": room_desc,
                        "cheaper_platform": cheaper,
                        "cheaper_price": cheaper_price,
                        "other_price": other_price,
                        "save": save,
                        "save_percent": save_percent,
                        "room_name": best_comp.room_name_a if cheaper == "携程" else best_comp.room_name_b
                    })
                else:
                    print(f"     ⚠️  无利润空间（价差≤{20}%）")
            else:
                print(f"     → 价格相同")
        
        print("\n  " + "-" * 50)
        
        if profitable_rooms:
            print_success(f"发现 {len(profitable_rooms)} 个有利润的房型")
        else:
            print_warning("没有发现有利润的房型（价差都≤20%）")
        
        return profitable_rooms
        
    except Exception as e:
        print_error(f"比价出错: {e}")
        import traceback
        traceback.print_exc()
        return []


# ==================== 步骤4: 自动上架 ====================

def step4_auto_shangjia(profitable_rooms: List[Dict], dry_run: bool = False) -> bool:
    """
    步骤4: 自动上架
    
    参数:
        profitable_rooms: 有利润的房型列表
        dry_run: 是否演示模式（不实际上架）
    
    返回:
        是否成功
    """
    print_step(4, 5, "自动上架")
    
    if not profitable_rooms:
        print_warning("没有可上架的房型（无利润空间）")
        return False
    
    print_info("将要上架的房型:")
    for i, room in enumerate(profitable_rooms, 1):
        print(f"\n  {i}. {room['room_desc']}")
        print(f"     来源: {room['cheaper_platform']} ({room['cheaper_price']:.0f}元)")
        print(f"     利润空间: {room['save_percent']:.1f}%")
    
    if dry_run:
        print("\n")
        print_info("演示模式：以下是将要执行的操作")
        for room in profitable_rooms:
            print(f"  → 在代理通上架: {room['room_desc']}, 价格 {room['cheaper_price']:.0f}元")
        print_success("演示完成（未实际执行）")
        return True
    
    # 实际上架
    print("\n")
    print_info("正在执行自动上架...")
    
    try:
        # 获取当天日期
        today = datetime.now().strftime("%m.%d")
        
        from auto_shangjia import AutoShangjia
        auto = AutoShangjia(
            hotel_name="美利居",  # 可以从参数传入
            target_date=today,
            dry_run=False
        )
        success = auto.run()
        
        if success:
            print_success("自动上架完成")
        else:
            print_error("自动上架失败")
        
        return success
        
    except Exception as e:
        print_error(f"上架出错: {e}")
        return False


# ==================== 步骤5: 购买前验证 ====================

def step5_verify_before_purchase(search_input: str, dry_run: bool = False) -> bool:
    """
    步骤5: 购买前验证（二次搜索确认价格）
    
    参数:
        search_input: 搜索条件
        dry_run: 是否演示模式
    
    返回:
        是否通过验证
    """
    print_step(5, 5, "购买前验证（二次搜索确认价格）")
    
    print_info("目的: 支付前再次搜索，确认价格是否变动")
    
    if dry_run:
        print_info("演示模式：模拟二次搜索")
        print_info("二次搜索结果: 价格未变动")
        print_success("验证通过，可以继续支付")
        return True
    
    # 保存第一次搜索结果
    print_info("保存当前价格数据...")
    
    with open(XIECHENG_FILE, 'r', encoding='utf-8') as f:
        first_xiecheng = json.load(f)
    
    with open(MEITUAN_FILE, 'r', encoding='utf-8') as f:
        first_meituan = json.load(f)
    
    # 执行二次搜索
    print_info("执行二次搜索...")
    
    try:
        from search import run_parallel
        ctrip_ok, meituan_ok = run_parallel(search_input)
        
        if not (ctrip_ok or meituan_ok):
            print_error("二次搜索失败")
            return False
        
        # 加载二次搜索结果
        with open(XIECHENG_FILE, 'r', encoding='utf-8') as f:
            second_xiecheng = json.load(f)
        
        with open(MEITUAN_FILE, 'r', encoding='utf-8') as f:
            second_meituan = json.load(f)
        
        # 检测价格变动
        from pipeline import check_price_changes
        price_changes, status_changes = check_price_changes(
            first_meituan, first_xiecheng,
            second_meituan, second_xiecheng
        )
        
        if price_changes or status_changes:
            print_error("检测到价格变动！")
            for change in price_changes:
                print(f"  ⚠️  {change['platform']} - {change['room_name']}")
                print(f"      {change['first_price']:.0f}元 → {change['second_price']:.0f}元")
            print_error("建议停止支付，重新比价")
            return False
        else:
            print_success("价格稳定，未检测到变动")
            print_success("验证通过，可以继续支付")
            return True
        
    except Exception as e:
        print_error(f"验证出错: {e}")
        return False


# ==================== 主函数 ====================

def run_demo(search_input: str, dry_run: bool = False, skip_verify: bool = False):
    """
    运行完整演示
    
    参数:
        search_input: 搜索条件
        dry_run: 是否演示模式
        skip_verify: 是否跳过购买前验证
    """
    print_title("酒店价格监控与自动上架系统 - 演示")
    
    print(f"\n  📅 演示时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  🔍 搜索条件: {search_input}")
    print(f"  🎭 演示模式: {'是（不实际执行）' if dry_run else '否（实际执行）'}")
    
    wait_for_confirm()
    
    # 步骤1: 搜索
    if not step1_search(search_input, dry_run):
        print_error("搜索失败，演示终止")
        return
    
    wait_for_confirm()
    
    # 步骤2: 酒店对齐
    success, xiecheng_data, meituan_data = step2_match_hotel()
    if not success:
        print_error("酒店对齐失败，演示终止")
        return
    
    wait_for_confirm()
    
    # 步骤3: 价格对比
    profitable_rooms = step3_compare_price(xiecheng_data, meituan_data)
    
    wait_for_confirm()
    
    # 步骤4: 自动上架
    step4_auto_shangjia(profitable_rooms, dry_run)
    
    wait_for_confirm()
    
    # 步骤5: 购买前验证
    if not skip_verify:
        step5_verify_before_purchase(search_input, dry_run)
    else:
        print_step(5, 5, "购买前验证（已跳过）")
        print_info("跳过购买前验证")
    
    # 演示完成
    print_title("演示完成")
    
    print("\n  📋 演示总结:")
    print("  " + "-" * 50)
    print("  1️⃣  搜索功能 - 搜索携程和美团")
    print("  2️⃣  酒店对齐 - 确认是同一家酒店")
    print("  3️⃣  价格对比 - 发现哪个平台更便宜")
    print("  4️⃣  自动上架 - 在代理通上架低价房型")
    print("  5️⃣  购买前验证 - 二次搜索确认价格稳定")
    print("  " + "-" * 50)
    
    print("\n  💡 系统价值:")
    print("  → 自动化比价，节省人工成本")
    print("  → 实时发现价格差异，抓住利润机会")
    print("  → 三维匹配（房型+窗户+早餐），确保比价准确")
    print("  → 购买前二次验证，降低价格波动风险")
    print("  → 全流程自动化，从搜索到上架一键完成")
    
    print("\n  🎯 核心能力:")
    print("  → 能搜：同时搜索携程和美团，获取实时价格")
    print("  → 能对齐：智能匹配同一家酒店，避免比价错误")
    print("  → 能比价：清晰展示价格差异，标注利润空间")
    print("  → 能上架：发现低价后自动上架，快速抢占商机")
    print("  → 能验证：支付前再次确认，确保价格稳定")
    
    print("\n  📈 预期效果:")
    print("  → 人工比价时间：从30分钟/酒店 → 1分钟/酒店")
    print("  → 价格监控覆盖：从人工抽查 → 全量自动监控")
    print("  → 利润机会捕获：实时发现价差>20%的房型")
    print("  → 风险控制：购买前验证，避免价格变动损失")
    print()
    



def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='酒店价格监控与自动上架系统 - 演示 Demo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 完整演示（使用真实搜索）
  python demo.py --hotel "上海,美利居酒店"
  
  # 演示模式（使用已有数据，不启动浏览器）
  python demo.py --dry-run
  
  # 跳过购买前验证
  python demo.py --dry-run --skip-verify
        '''
    )
    
    parser.add_argument('--hotel', '-H', default='上海,美利居酒店', 
                        help='搜索条件（格式: 城市,酒店关键词）')
    parser.add_argument('--dry-run', action='store_true', 
                        help='演示模式：使用已有数据，不实际执行')
    parser.add_argument('--skip-verify', action='store_true', 
                        help='跳过购买前验证步骤')
    
    args = parser.parse_args()
    
    try:
        run_demo(
            search_input=args.hotel,
            dry_run=args.dry_run,
            skip_verify=args.skip_verify
        )
    except KeyboardInterrupt:
        print("\n\n  用户中断演示")
    except Exception as e:
        print(f"\n\n  ❌ 演示出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


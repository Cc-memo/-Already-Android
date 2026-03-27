# -*- coding: utf-8 -*-
"""
订单处理快捷启动脚本
从项目根目录运行订单处理模块

使用方式:
    # 从代理通获取订单并处理
    python run_order.py --fetch
    
    # 演示模式（不实际下单）
    python run_order.py --fetch --dry-run
    
    # 查看所有订单
    python run_order.py --list
    
    # 测试携程下单（演示模式）
    python run_order.py --test-ctrip --dry-run
    
    # 测试携程下单（真实操作）
    python run_order.py --test-ctrip
    
    # 测试美团下单（演示模式）
    python run_order.py --test-meituan --dry-run
    
    # 测试美团下单（真实操作）
    python run_order.py --test-meituan
"""

import sys
import os
import argparse

# 添加项目根目录和 orders 目录到路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ORDERS_DIR = os.path.join(PROJECT_ROOT, "orders")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if ORDERS_DIR not in sys.path:
    sys.path.insert(0, ORDERS_DIR)


def test_ctrip(dry_run: bool = False):
    """测试携程下单"""
    from orders.ctrip_order import CtripOrderPlacer
    
    print("="*50)
    print("  测试携程下单模块")
    print("="*50)
    
    placer = CtripOrderPlacer()
    try:
        if not placer.setup_browser():
            print("启动浏览器失败")
            return
        
        success, result = placer.place_order(
            hotel_name="美利居酒店（上海城市中心人民广场店）",
            room_type="商务大床房",
            check_in="2026-01-10",
            check_out="2026-01-11",
            guest_name="张三",
            phone="13800138000",
            dry_run=dry_run
        )
        
        print(f"\n结果: {'成功' if success else '失败'}")
        print(f"订单号/信息: {result}")
    finally:
        try:
            input("\n按回车键关闭浏览器...")
        except EOFError:
            print("\n自动关闭浏览器...")
        placer.close_browser()


def test_meituan(dry_run: bool = False):
    """测试美团下单"""
    from orders.meituan_order import MeituanOrderPlacer
    
    print("="*50)
    print("  测试美团下单模块")
    print("="*50)
    
    placer = MeituanOrderPlacer()
    try:
        if not placer.setup_browser():
            print("启动浏览器失败")
            return
        
        success, result = placer.place_order(
            hotel_name="美利居酒店（上海城市中心人民广场店）",
            room_type="商务大床房",
            check_in="2026-01-10",
            check_out="2026-01-11",
            guest_name="张三",
            phone="13800138000",
            dry_run=dry_run
        )
        
        print(f"\n结果: {'成功' if success else '失败'}")
        print(f"订单号/信息: {result}")
    finally:
        try:
            input("\n按回车键关闭浏览器...")
        except EOFError:
            print("\n自动关闭浏览器...")
        placer.close_browser()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="订单处理工具")
    parser.add_argument("--fetch", action="store_true", help="从代理通获取订单并处理")
    parser.add_argument("--list", action="store_true", help="列出所有订单")
    parser.add_argument("--test-ctrip", action="store_true", help="测试携程下单")
    parser.add_argument("--test-meituan", action="store_true", help="测试美团下单")
    parser.add_argument("--dry-run", action="store_true", help="演示模式（不实际操作）")
    parser.add_argument("--order-index", type=int, default=0, help="订单索引（默认0）")
    
    args = parser.parse_args()
    
    if args.test_ctrip:
        test_ctrip(dry_run=args.dry_run)
    elif args.test_meituan:
        test_meituan(dry_run=args.dry_run)
    elif args.fetch or args.list:
        # 使用 order_processor 的 main 函数
        from orders.order_processor import main
        main()
    else:
        parser.print_help()


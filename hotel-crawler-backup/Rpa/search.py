# -*- coding: utf-8 -*-
"""
统一搜索入口程序
同时调用携程和美团的酒店搜索爬虫
"""

import sys
import os
import subprocess
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 子程序路径
CTRIP_SCRIPT = os.path.join(SCRIPT_DIR, "xiecheng", "ctrip_crawler.py")
MEITUAN_SCRIPT = os.path.join(SCRIPT_DIR, "meituan", "meituan_rpa.py")

# 强制使用 UTF-8 编码（通过环境变量让子进程也使用 UTF-8）
ENCODING = 'utf-8'

# 创建子进程环境变量，强制使用 UTF-8
SUBPROCESS_ENV = os.environ.copy()
SUBPROCESS_ENV['PYTHONIOENCODING'] = 'utf-8'


def run_ctrip(search_input):
    """
    运行携程爬虫
    
    参数:
        search_input: 搜索输入，格式为 "城市,酒店关键词"
    """
    print("\n" + "=" * 50)
    print("🚀 启动携程爬虫...")
    print("=" * 50)
    
    try:
        print("  正在启动子进程...")
        # 使用 subprocess 运行携程爬虫，通过 stdin 传递输入
        process = subprocess.Popen(
            [sys.executable, CTRIP_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,  # Python 3.7+支持，升级后可用
            encoding=ENCODING,
            errors='replace',  # 遇到无法解码的字符时用?替换
            cwd=os.path.dirname(CTRIP_SCRIPT),  # 切换到脚本所在目录
            env=SUBPROCESS_ENV  # 强制子进程使用 UTF-8
        )
        
        print("  子进程已启动，正在等待输出...")
        print("  (如果长时间无响应，可能是浏览器启动卡住)")
        
        # 传递搜索参数和回车确认
        stdout, _ = process.communicate(input=f"{search_input}\n\n", timeout=300)
        
        print("\n[携程爬虫输出]")
        print(stdout)
        
        # 检查输出中是否有错误信息
        if "超时" in stdout or "失败" in stdout or "错误" in stdout:
            return False, "携程爬虫执行失败"
        
        return True, "携程爬虫完成"
        
    except subprocess.TimeoutExpired:
        print("\n❌ 携程爬虫超时（超过5分钟）")
        print("  可能原因：")
        print("    1. 浏览器启动卡住")
        print("    2. 网络连接问题")
        print("    3. 页面加载过慢")
        try:
            process.kill()
            print("  已终止超时进程")
        except:
            pass
        return False, "携程爬虫超时"
    except Exception as e:
        print(f"\n❌ 携程爬虫出错: {str(e)}")
        return False, f"携程爬虫出错: {str(e)}"


def run_meituan(search_input):
    """
    运行美团爬虫
    
    参数:
        search_input: 搜索输入，格式为 "地址关键词,酒店关键词"
    """
    print("\n" + "=" * 50)
    print("🚀 启动美团爬虫...")
    print("=" * 50)
    
    try:
        print("  正在启动子进程...")
        # 使用 subprocess 运行美团爬虫，通过 stdin 传递输入
        process = subprocess.Popen(
            [sys.executable, MEITUAN_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,  # Python 3.7+支持，升级后可用
            encoding=ENCODING,
            errors='replace',  # 遇到无法解码的字符时用?替换
            cwd=os.path.dirname(MEITUAN_SCRIPT),  # 切换到脚本所在目录
            env=SUBPROCESS_ENV  # 强制子进程使用 UTF-8
        )
        
        print("  子进程已启动，正在等待输出...")
        print("  (如果长时间无响应，可能是浏览器启动卡住)")
        
        # 传递搜索参数和回车确认
        stdout, _ = process.communicate(input=f"{search_input}\n\n", timeout=300)
        
        print("\n[美团爬虫输出]")
        print(stdout)
        
        # 检查输出中是否有错误信息
        if "超时" in stdout or "失败" in stdout or "错误" in stdout:
            return False, "美团爬虫执行失败"
        
        return True, "美团爬虫完成"
        
    except subprocess.TimeoutExpired:
        print("\n❌ 美团爬虫超时（超过5分钟）")
        print("  可能原因：")
        print("    1. 浏览器启动卡住")
        print("    2. 网络连接问题")
        print("    3. 页面加载过慢")
        try:
            process.kill()
            print("  已终止超时进程")
        except:
            pass
        return False, "美团爬虫超时"
    except Exception as e:
        print(f"\n❌ 美团爬虫出错: {str(e)}")
        return False, f"美团爬虫出错: {str(e)}"


def run_sequential(search_input):
    """
    串行运行两个爬虫（一个接一个）
    """
    print("\n📋 模式: 串行执行（先携程后美团）")
    
    # 运行携程
    ctrip_success, ctrip_msg = run_ctrip(search_input)
    print(f"\n✅ {ctrip_msg}" if ctrip_success else f"\n❌ {ctrip_msg}")
    
    # 运行美团
    meituan_success, meituan_msg = run_meituan(search_input)
    print(f"\n✅ {meituan_msg}" if meituan_success else f"\n❌ {meituan_msg}")
    
    return ctrip_success, meituan_success


def run_parallel(search_input):
    """
    并行运行两个爬虫（同时启动）
    注意：并行模式下两个浏览器会同时打开
    """
    print("\n📋 模式: 并行执行（同时启动）")
    
    results = {}
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(run_ctrip, search_input): "携程",
            executor.submit(run_meituan, search_input): "美团"
        }
        
        for future in as_completed(futures):
            name = futures[future]
            try:
                success, msg = future.result()
                results[name] = (success, msg)
                print(f"\n✅ {msg}" if success else f"\n❌ {msg}")
            except Exception as e:
                results[name] = (False, f"{name}爬虫异常: {str(e)}")
                print(f"\n❌ {name}爬虫异常: {str(e)}")
    
    return results.get("携程", (False, ""))[0], results.get("美团", (False, ""))[0]


def main():
    """主函数"""
    print("=" * 60)
    print("  🏨 酒店信息统一搜索工具")
    print("  同时搜索携程和美团的酒店房型信息")
    print("=" * 60)
    
    # 检查子程序是否存在
    if not os.path.exists(CTRIP_SCRIPT):
        print(f"\n❌ 携程爬虫脚本不存在: {CTRIP_SCRIPT}")
        return
    
    if not os.path.exists(MEITUAN_SCRIPT):
        print(f"\n❌ 美团爬虫脚本不存在: {MEITUAN_SCRIPT}")
        return
    
    print("\n✓ 已找到携程爬虫脚本")
    print("✓ 已找到美团爬虫脚本")
    
    # 获取用户输入
    print("\n" + "-" * 60)
    search_input = input("请输入查询条件（格式: 城市/地址,酒店关键词）: ").strip()
    
    if not search_input:
        print("输入为空，使用默认值: 上海,如家")
        search_input = "上海,如家"
    
    # 验证输入格式
    parts = search_input.replace('，', ',').split(',')
    if len(parts) < 2:
        print("\n❌ 输入格式错误！请使用格式: 城市/地址,酒店关键词")
        return
    
    city = parts[0].strip()
    hotel_keyword = parts[1].strip()
    
    print(f"\n📍 搜索参数:")
    print(f"   城市/地址: {city}")
    print(f"   酒店关键词: {hotel_keyword}")
    
    print("\n" + "=" * 60)
    print("开始搜索（并发模式）...")
    print("=" * 60)
    
    # 直接使用并发模式
    ctrip_ok, meituan_ok = run_parallel(search_input)
    
    # 打印汇总
    print("\n" + "=" * 60)
    print("🎯 搜索完成！结果汇总:")
    print("=" * 60)
    
    if ctrip_ok is not None:
        status = "✅ 成功" if ctrip_ok else "❌ 失败"
        print(f"  携程: {status}")
        if ctrip_ok:
            print(f"        数据保存在: xiecheng/hotel_data.json")
    
    if meituan_ok is not None:
        status = "✅ 成功" if meituan_ok else "❌ 失败"
        print(f"  美团: {status}")
        if meituan_ok:
            print(f"        数据保存在: meituan/meituan_hotel.json")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

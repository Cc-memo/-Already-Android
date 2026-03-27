# -*- coding: utf-8 -*-
"""
飞猪登录态检查工具

使用本地Chromium用户数据目录 + Cookies文件双重保持登录态
"""

import os
import time
import pickle
import tempfile
import uuid
import shutil
import platform
import subprocess
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.core.os_manager import ChromeType
    os.environ['WDM_LOCAL'] = '1'  # 优先使用本地缓存
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(SCRIPT_DIR, "feizhu_cookies.pkl")

# 飞猪相关URL
FEIZHU_HOME = "https://www.fliggy.com/"
FEIZHU_HOTEL = "https://hotel.fliggy.com/"


def kill_chrome_processes():
    """
    清理浏览器相关进程，避免启动冲突。
    
    安全策略（默认）：
    - Windows 下默认 **只杀 chromedriver.exe**，避免把用户正在使用的 chrome.exe 误杀。
    - 如确实需要连 chrome.exe 一并清理，可设置环境变量 KILL_CHROME_PROCESS=1。
    """
    if platform.system() != "Windows":
        return
    # Web Admin / 后台任务场景：可能会并发跑多个平台任务。
    # 如果这里强行 taskkill chromedriver.exe，会把"另一个任务"的 driver 会话直接杀掉，
    # 从而出现 urllib3 的 WinError 10061（连接被拒绝）重试日志。
    #
    # 因此：当 NON_INTERACTIVE=1（Web Admin 会设置）时默认不清理 chromedriver.exe，
    # 需要强制清理可设置 KILL_CHROMEDRIVER_PROCESS=1。
    if os.getenv("NON_INTERACTIVE", "") == "1" and os.getenv("KILL_CHROMEDRIVER_PROCESS", "0") != "1":
        return
    try:
        allow_kill_chrome = os.getenv("KILL_CHROME_PROCESS", "0") == "1"
        if allow_kill_chrome:
            subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'],
                          capture_output=True, timeout=5)
        # 杀掉 chromedriver.exe
        subprocess.run(['taskkill', '/F', '/IM', 'chromedriver.exe', '/T'],
                      capture_output=True, timeout=5)
        if allow_kill_chrome:
            subprocess.run(['taskkill', '/F', '/IM', 'chromium.exe', '/T'],
                          capture_output=True, timeout=5)
    except Exception:
        pass


def setup_browser(use_local_profile=True):
    """
    配置并启动Chromium浏览器（与携程保持一致）
    
    参数:
        use_local_profile: 是否使用本地用户数据（会使用独立临时目录，支持并发）
    """
    chrome_options = Options()

    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin and not os.path.exists(chrome_bin):
        print(f"  ⚠️  CHROME_BIN 指向的文件不存在: {chrome_bin}")
        chrome_bin = None
    
    # 如果没有设置 CHROME_BIN，优先使用 Chromium（与 meituan_cookies.py 保持一致）
    if not chrome_bin:
        if os.name == "nt":
            # Windows: 直接使用 Chromium 路径（与 meituan_cookies.py 保持一致）
            chrome_bin = r"D:\yingyong\tool\chrome-win\chrome.exe"
            if not os.path.exists(chrome_bin):
                # 如果自定义路径不存在，再查找系统安装的 Chromium
                candidates = [
                    os.path.join(os.getenv("LOCALAPPDATA", ""), "Chromium", "Application", "chrome.exe"),
                    os.path.join(os.getenv("PROGRAMFILES", ""), "Chromium", "Application", "chrome.exe"),
                    os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Chromium", "Application", "chrome.exe"),
                ]
                for c in candidates:
                    if c and os.path.exists(c):
                        chrome_bin = c
                        break
                else:
                    # 如果 Chromium 都不存在，才考虑 Chrome（但不推荐）
                    chrome_candidates = [
                        os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
                        os.path.join(os.getenv("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
                        os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                    ]
                    for c in chrome_candidates:
                        if c and os.path.exists(c):
                            chrome_bin = c
                            print(f"  ⚠️  未找到 Chromium，使用 Chrome: {chrome_bin}")
                            break
        else:
            # Linux: 查找 Chromium
            for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
                if os.path.exists(candidate):
                    chrome_bin = candidate
                    break
    if chrome_bin and os.path.exists(chrome_bin):
        chrome_options.binary_location = chrome_bin
        # 判断是 Chromium 还是 Chrome
        browser_name = "Chromium" if any(k in chrome_bin.lower() for k in ("chromium", "chrome-win")) else "Chrome"
        print(f"  使用浏览器: {browser_name} ({chrome_bin})")
    else:
        chrome_bin = None
        print("  使用系统默认浏览器（未指定 CHROME_BIN）")

    chrome_driver_path = os.getenv("CHROME_DRIVER_PATH")
    if chrome_driver_path and not os.path.exists(chrome_driver_path):
        print(f"  ⚠️  CHROME_DRIVER_PATH 指向的文件不存在: {chrome_driver_path}")
        chrome_driver_path = None
    is_chromium = bool(chrome_bin) and any(k in chrome_bin.lower() for k in ("chromium", "chrome-win"))
    
    if platform.system() != "Windows":
        use_local_profile = False
    
    if use_local_profile:
        # 为并发支持：每个实例使用独立的用户数据目录（与携程保持一致）
        # 如果使用固定的用户数据目录，多个并发实例会冲突，导致只打开一个窗口
        temp_dir = tempfile.gettempdir()
        # 创建独立的用户数据目录，避免并发冲突
        user_data_dir = os.path.join(temp_dir, f"feizhu_chromium_profile_{uuid.uuid4().hex[:8]}")
        os.makedirs(user_data_dir, exist_ok=True)
        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
        chrome_options.add_argument('--profile-directory=Default')
        print(f"  使用独立用户数据目录（支持并发）: {user_data_dir}")
    
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    # 关闭Chrome的错误和警告输出
    chrome_options.add_argument('--log-level=3')  # 只显示FATAL级别日志
    chrome_options.add_argument('--disable-logging')
    chrome_options.add_argument('--disable-gpu-logging')
    chrome_options.add_argument('--silent')
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])  # 禁用日志记录
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # 在启动浏览器前，先清理可能冲突的进程
    kill_chrome_processes()
    
    # 启动浏览器（与携程保持一致）
    max_retries = 3
    driver = None
    
    for attempt in range(max_retries):
        try:
            print(f"  尝试启动浏览器... (尝试 {attempt + 1}/{max_retries})")
            if chrome_driver_path:
                service = Service(executable_path=chrome_driver_path)
                print("  使用 CHROME_DRIVER_PATH 指定的 ChromeDriver")
                print("  正在启动Chrome浏览器...")
                driver = webdriver.Chrome(service=service, options=chrome_options)
            elif USE_WEBDRIVER_MANAGER:
                try:
                    # 使用缓存，避免每次联网检查版本
                    print("  正在获取ChromeDriver...")
                    if is_chromium:
                        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
                    else:
                        service = Service(ChromeDriverManager().install())
                    print("  正在启动Chrome浏览器...")
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                except Exception as e:
                    print(f"  webdriver_manager失败: {str(e)[:50]}")
                    print("  尝试使用本地chromedriver...")
                    # 回退到本地驱动或系统PATH中的驱动
                    try:
                        service = Service()
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                    except Exception as e2:
                        if attempt < max_retries - 1:
                            print(f"  本地驱动也失败，清理进程后重试...")
                            kill_chrome_processes()
                            time.sleep(2)
                            continue
                        print(f"  本地驱动也失败: {str(e2)[:50]}")
                        raise
            else:
                print("  正在启动Chrome浏览器...")
                driver = webdriver.Chrome(options=chrome_options)
            
            print("  浏览器启动成功")
            break  # 成功后跳出循环
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  启动失败，正在清理进程后重试... ({attempt + 1}/{max_retries})")
                print(f"  错误信息: {str(e)[:100]}")
                kill_chrome_processes()
                time.sleep(2)
            else:
                print(f"\n❌ 浏览器启动失败: {e}")
                print("\n请尝试以下解决方案:")
                print("  1. 手动关闭所有 Chrome/Chromium 窗口")
                print("  2. 设置环境变量 CHROME_DRIVER_PATH 指向 chromedriver.exe（推荐）")
                print("  3. 或设置环境变量 USE_WDM=1 让脚本自动下载匹配的 ChromeDriver")
                print("  4. 检查 ChromeDriver 版本是否与 Chrome/Chromium 主版本一致")
                print("  5. 或尝试: pip install --upgrade selenium webdriver-manager")
                raise
    
    if driver is None:
        raise Exception("浏览器启动失败：所有重试均失败")
    
    # 防止被检测为自动化程序
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })
    except:
        pass
    
    return driver


def save_cookies(driver):
    """保存cookies到文件"""
    try:
        cookies = driver.get_cookies()
        cookie_data = {
            'cookies': cookies,
            'save_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(COOKIES_FILE, 'wb') as f:
            pickle.dump(cookie_data, f)
        print(f"✓ Cookies已保存 (共 {len(cookies)} 个)")
        return True
    except Exception as e:
        print(f"⚠️ 保存Cookies失败: {e}")
        return False


def load_cookies(driver):
    """从文件加载cookies"""
    if not os.path.exists(COOKIES_FILE):
        return False
    
    try:
        with open(COOKIES_FILE, 'rb') as f:
            cookie_data = pickle.load(f)
        
        if isinstance(cookie_data, list):
            cookies = cookie_data
            save_time = "未知"
        else:
            cookies = cookie_data.get('cookies', [])
            save_time = cookie_data.get('save_time', '未知')
        
        print(f"  发现已保存的Cookies（保存于: {save_time}）")
        
        # 加载cookies（需要先在同域名下）
        loaded_count = 0
        for cookie in cookies:
            try:
                # 处理可能的问题
                if 'expiry' in cookie:
                    cookie['expiry'] = int(cookie['expiry'])
                # 移除sameSite如果有问题
                if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                    del cookie['sameSite']
                driver.add_cookie(cookie)
                loaded_count += 1
            except:
                pass
        
        print(f"✓ 已加载 {loaded_count}/{len(cookies)} 个cookie")
        return loaded_count > 0
    except Exception as e:
        print(f"⚠️ 加载Cookies失败: {e}")
        return False


def check_login_status(driver, debug=True):
    """
    检查飞猪登录状态
    
    返回: (is_logged_in: bool, status_info: str)
    
    飞猪/淘宝登录检测逻辑：
    - 未登录：顶部显示"请登录" "免费注册" 或 "登录"按钮
    - 已登录：顶部显示用户昵称
    """
    try:
        time.sleep(2)
        
        # ========== 方法1: 检查顶部导航栏的登录按钮（未登录标志） ==========
        # 飞猪未登录时，顶部会有明显的"请登录"文字
        not_logged_selectors = [
            # 顶部导航栏的登录链接
            '//div[contains(@class,"header")]//a[contains(text(),"请登录")]',
            '//div[contains(@class,"header")]//a[contains(text(),"登录")]',
            '//div[contains(@class,"nav")]//a[contains(text(),"请登录")]',
            '//div[contains(@class,"nav")]//a[contains(text(),"登录")]',
            # 淘宝登录相关
            '//a[@class="h" and contains(text(),"请登录")]',
            '//a[contains(@href,"login") and contains(text(),"登录")]',
            # 通用选择器
            '//div[contains(@class,"site-nav")]//a[contains(text(),"登录")]',
        ]
        
        for selector in not_logged_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for el in elements:
                    if el.is_displayed():
                        text = el.text.strip()
                        if debug:
                            print(f"    [检测] 发现未登录标志: '{text}'")
                        return False, f"未登录 (发现: {text})"
            except:
                pass
        
        # ========== 方法2: 检查页面文本中的"请登录"（更宽泛） ==========
        try:
            # 获取页面顶部区域的文本
            header_elements = driver.find_elements(By.XPATH, 
                '//header | //div[contains(@class,"header")] | //div[contains(@class,"nav")] | //div[contains(@class,"top")]')
            
            for header in header_elements[:5]:  # 只检查前5个
                try:
                    header_text = header.text
                    if '请登录' in header_text or '免费注册' in header_text:
                        if debug:
                            print(f"    [检测] 顶部区域发现: '请登录' 或 '免费注册'")
                        return False, "未登录 (顶部显示请登录)"
                except:
                    pass
        except:
            pass
        
        # ========== 方法3: 检查是否有用户昵称（已登录标志） ==========
        logged_in_selectors = [
            # 用户昵称元素
            '//a[contains(@class,"site-nav-user")]',
            '//span[contains(@class,"site-nav-user")]',
            '//div[contains(@class,"member-nick")]//a',
            '//a[contains(@class,"member-nick")]',
            # 淘宝用户
            '//a[contains(@href,"taobao.com/home")]',
        ]
        
        for selector in logged_in_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for el in elements:
                    if el.is_displayed():
                        text = el.text.strip()
                        # 排除"登录"等文字
                        if text and '登录' not in text and '注册' not in text and len(text) > 0:
                            if debug:
                                print(f"    [检测] 发现用户昵称: '{text}'")
                            return True, f"已登录 (用户: {text})"
            except:
                pass
        
        # ========== 方法4: 检查整个页面的body文本 ==========
        try:
            body_text = driver.find_element(By.TAG_NAME, 'body').text
            
            # 先检查未登录标志（优先级更高）
            if '请登录' in body_text[:500]:  # 只检查前500字符（通常是顶部）
                if debug:
                    print(f"    [检测] 页面顶部包含 '请登录'")
                return False, "未登录 (页面显示请登录)"
            
            # 检查已登录标志
            # 注意：这些文字可能在页面其他位置出现，所以放在最后作为兜底
            if '退出' in body_text[:500] and '登录' not in body_text[:200]:
                if debug:
                    print(f"    [检测] 页面顶部包含 '退出' 且无 '登录'")
                return True, "已登录 (发现退出按钮)"
                
        except:
            pass
        
        # ========== 默认：无法确定 ==========
        if debug:
            print(f"    [检测] 无法确定登录状态")
        return False, "状态不确定 (建议手动检查浏览器)"
        
    except Exception as e:
        print(f"  检查登录状态时出错: {e}")
        return False, f"检查失败: {e}"


def check_login():
    """
    主函数：检查飞猪登录态
    
    流程：
    1. 启动浏览器（使用本地用户数据目录）
    2. 尝试加载保存的Cookies
    3. 检查登录状态
    4. 未登录则引导用户登录并保存Cookies
    """
    print("="*60)
    print("  飞猪登录态检查工具")
    print("="*60)
    
    # 检查是否有保存的Cookies
    has_cookies = os.path.exists(COOKIES_FILE)
    if has_cookies:
        print(f"\n[发现] 已保存的Cookies文件: {COOKIES_FILE}")
    
    print("\n[1] 正在启动浏览器...")
    print("    ⚠️  请确保已关闭所有Chromium浏览器窗口")
    
    driver = None
    try:
        driver = setup_browser(use_local_profile=True)
        
        print("\n[2] 正在访问飞猪首页...")
        driver.get(FEIZHU_HOME)
        time.sleep(2)
        
        # 尝试加载保存的Cookies
        if has_cookies:
            print("\n[3] 尝试加载保存的Cookies...")
            load_cookies(driver)
            # 刷新页面以应用Cookies
            driver.refresh()
            time.sleep(3)
        else:
            time.sleep(1)
        
        print("\n[4] 检查登录状态...")
        is_logged_in, status = check_login_status(driver, debug=True)
        
        if is_logged_in:
            print("\n" + "="*60)
            print("✅ 登录态检查结果: 已登录")
            print(f"   状态: {status}")
            print("="*60)
            
            # 更新保存的Cookies
            print("\n正在更新Cookies...")
            save_cookies(driver)
            
            input("\n按回车关闭浏览器...")
            return True, status
        else:
            print("\n" + "="*60)
            print("❌ 当前未登录")
            print("="*60)
            
            print("\n📌 请在浏览器中登录飞猪（使用淘宝账号）")
            print("   登录完成后，回到这里按回车保存登录态")
            
            input("\n>>> 登录完成后按回车 <<< ")
            
            # 再次检查登录状态
            print("\n正在验证登录状态...")
            time.sleep(2)
            is_logged_in, status = check_login_status(driver, debug=True)
            
            if is_logged_in:
                # 保存Cookies
                print("\n正在保存Cookies...")
                save_cookies(driver)
                
                print("\n" + "="*60)
                print("✅ 登录成功！Cookies已保存")
                print("   下次运行将自动使用保存的登录态")
                print("="*60)
                
                input("\n按回车关闭浏览器...")
                return True, status
            else:
                print("\n❌ 登录验证失败，请确保已成功登录")
                input("\n按回车关闭浏览器...")
                return False, status
        
    except Exception as e:
        print(f"\n❌ 出错: {e}")
        input("\n按回车退出...")
        return False, str(e)
        
    finally:
        if driver:
            driver.quit()


def test_login_status():
    """快速测试登录状态"""
    print("="*60)
    print("  快速测试飞猪登录状态")
    print("="*60)
    
    has_cookies = os.path.exists(COOKIES_FILE)
    if has_cookies:
        print(f"\n[发现] Cookies文件存在")
    else:
        print(f"\n[提示] 无Cookies文件，请先运行 python feizhu_rpa.py 登录")
    
    driver = None
    try:
        print("\n正在启动浏览器...")
        driver = setup_browser(use_local_profile=True)
        
        print("正在访问飞猪...")
        driver.get(FEIZHU_HOME)
        time.sleep(2)
        
        # 加载Cookies
        if has_cookies:
            print("正在加载Cookies...")
            load_cookies(driver)
            driver.refresh()
            time.sleep(3)
        
        print("\n检测登录状态...")
        is_logged_in, status = check_login_status(driver, debug=True)
        
        print("\n" + "-"*40)
        if is_logged_in:
            print(f"✅ 已登录 ({status})")
        else:
            print(f"❌ 未登录 ({status})")
            if not has_cookies:
                print("\n请运行 python feizhu_rpa.py 进行登录")
        print("-"*40)
        
        input("\n按回车关闭浏览器...")
        return is_logged_in
        
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "test":
            test_login_status()
        else:
            print(f"未知命令: {cmd}")
            print("可用命令:")
            print("  python feizhu_rpa.py        - 检查登录态")
            print("  python feizhu_rpa.py test   - 快速测试")
    else:
        check_login()

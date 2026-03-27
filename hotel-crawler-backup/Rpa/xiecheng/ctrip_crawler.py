# -*- coding: utf-8 -*-


import re
import json
import time
import random
import os
import platform
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class TaskCancelled(Exception):
    """Web Admin 删除/取消任务时用于中断执行。"""


# 由 Web Admin 注入（run_non_interactive 设置），用于脚本内部轮询取消
_CANCEL_EVENT = None


def _cancel_requested() -> bool:
    try:
        return bool(_CANCEL_EVENT) and _CANCEL_EVENT.is_set()
    except Exception:
        return False


def _check_cancelled() -> None:
    if _cancel_requested():
        raise TaskCancelled("任务已取消")

try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.core.os_manager import ChromeType
    # 设置缓存有效期为7天，避免每次联网检查
    os.environ['WDM_LOCAL'] = '1'  # 优先使用本地缓存
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

# 默认禁用webdriver_manager以避免联网检查延迟，除非设置环境变量 USE_WDM=1
if os.getenv("USE_WDM", "0") != "1":
    USE_WEBDRIVER_MANAGER = False

# 导入数据库工具
import sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from database.db_utils import save_to_database
except ImportError:
    try:
        # 兼容旧路径
        from db_utils import save_to_database
    except ImportError:
        save_to_database = None
        print("[警告] 无法导入 save_to_database，数据库保存功能将不可用")

# 导入cookies管理模块
try:
    from ctrip_cookies import load_cookies, cookies_exist, COOKIES_FILE
except ImportError:
    # 如果从其他目录运行，尝试相对导入
    try:
        from xiecheng.ctrip_cookies import load_cookies, cookies_exist, COOKIES_FILE
    except ImportError:
        load_cookies = None
        cookies_exist = None
        COOKIES_FILE = None


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
    # 如果这里强行 taskkill chromedriver.exe，会把“另一个任务”的 driver 会话直接杀掉，
    # 从而出现 urllib3 的 WinError 10061（连接被拒绝）重试日志。
    #
    # 因此：当 NON_INTERACTIVE=1（Web Admin 会设置）时默认不清理 chromedriver.exe，
    # 需要强制清理可设置 KILL_CHROMEDRIVER_PROCESS=1。
    if os.getenv("NON_INTERACTIVE", "") == "1" and os.getenv("KILL_CHROMEDRIVER_PROCESS", "0") != "1":
        return
    import subprocess
    try:
        allow_kill_chrome = os.getenv("KILL_CHROME_PROCESS", "0") == "1"
        if allow_kill_chrome:
            subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'],
                          capture_output=True, timeout=5)
        # 杀掉 chromedriver.exe
        subprocess.run(['taskkill', '/F', '/IM', 'chromedriver.exe', '/T'], 
                      capture_output=True, timeout=5)
        time.sleep(1)
        if allow_kill_chrome:
            print("  已清理Chrome/ChromeDriver进程")
        else:
            print("  已清理ChromeDriver进程（安全模式：未清理chrome.exe）")
    except:
        pass


def setup_browser(use_local_profile=True, use_cookies=True):
    """
    配置并启动Chromium浏览器
    
    参数:
        use_local_profile: 是否使用本地用户数据（包含登录态）
        use_cookies: 是否使用保存的cookies文件登录（优先于use_local_profile）
    """
    chrome_options = Options()
    _check_cancelled()
    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin and not os.path.exists(chrome_bin):
        print(f"  ⚠️  CHROME_BIN 指向的文件不存在: {chrome_bin}")
        chrome_bin = None

    if not chrome_bin:
        if platform.system() == "Linux":
            for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
                if os.path.exists(candidate):
                    chrome_bin = candidate
                    break
        elif platform.system() == "Windows":
            # 优先查找Chromium，然后才是Chrome
            candidates = [
                r"D:\yingyong\tool\chrome-win\chrome.exe",  # 优先使用这个（Chromium）
                os.path.join(os.getenv("PROGRAMFILES", ""), "Chromium", "Application", "chrome.exe"),
                os.path.join(os.getenv("LOCALAPPDATA", ""), "Chromium", "Application", "chrome.exe"),
                os.path.join(os.getenv("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            for candidate in candidates:
                if candidate and os.path.exists(candidate):
                    chrome_bin = candidate
                    # 检查是否是Chromium
                    is_chromium = any(k in candidate.lower() for k in ("chromium", "chrome-win"))
                    if is_chromium:
                        print(f"  找到Chromium: {candidate}")
                    else:
                        print(f"  找到Chrome（非Chromium）: {candidate}，建议使用Chromium")
                    break

    if chrome_bin and os.path.exists(chrome_bin):
        chrome_options.binary_location = chrome_bin
        is_chromium = any(k in chrome_bin.lower() for k in ("chromium", "chrome-win"))
        if is_chromium:
            print(f"  使用Chromium浏览器: {chrome_bin}")
        else:
            print(f"  使用Chrome浏览器: {chrome_bin}（建议使用Chromium）")
    else:
        chrome_bin = None
        print("  使用系统默认浏览器（未指定 CHROME_BIN）")
    
    # 如果使用cookies文件登录，则不需要本地profile
    if use_cookies and cookies_exist and cookies_exist():
        use_local_profile = False
        print("  将使用保存的Cookies文件登录")
    
    if platform.system() != "Windows":
        use_local_profile = False

    if use_local_profile:
        # 为并发支持：每个实例使用独立的用户数据目录
        # 如果使用固定的用户数据目录，多个并发实例会冲突，导致只打开一个窗口
        import tempfile
        import uuid
        temp_dir = tempfile.gettempdir()
        # 创建独立的用户数据目录，避免并发冲突
        user_data_dir = os.path.join(temp_dir, f"ctrip_chromium_profile_{uuid.uuid4().hex[:8]}")
        os.makedirs(user_data_dir, exist_ok=True)
        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
        chrome_options.add_argument('--profile-directory=Default')
        print(f"  使用独立用户数据目录（支持并发）: {user_data_dir}")
    
    headless_env = os.getenv("HEADLESS")
    if headless_env is None:
        headless_env = "1" if platform.system() == "Linux" else "0"
    if headless_env.lower() in ("1", "true", "yes", "on"):
        chrome_options.add_argument("--headless=new")

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
    
    # 代理配置（如果启用）
    use_proxy = os.getenv("USE_PROXY", "").strip()
    if use_proxy and use_proxy.lower() in ("1", "true", "yes", "on"):
        http_proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        if http_proxy:
            chrome_options.add_argument(f'--proxy-server={http_proxy}')
            print(f"  已启用代理: {http_proxy}")
        else:
            print("  ⚠️  已启用代理但未配置 HTTP_PROXY 或 HTTPS_PROXY 环境变量")
    
    # 关闭Python日志输出
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('WDM').setLevel(logging.WARNING)
    
    # 在启动浏览器前，先清理可能冲突的进程
    print("  正在清理可能冲突的Chrome进程...")
    kill_chrome_processes()
    _check_cancelled()
    
    # 优先使用显式指定的 ChromeDriver（Windows 最稳）
    chrome_driver_path = os.getenv("CHROME_DRIVER_PATH")
    if chrome_driver_path and not os.path.exists(chrome_driver_path):
        print(f"  ⚠️  CHROME_DRIVER_PATH 指向的文件不存在: {chrome_driver_path}")
        chrome_driver_path = None

    is_chromium = bool(chrome_bin) and any(k in chrome_bin.lower() for k in ("chromium", "chrome-win"))

    # 使用chromedriver（需要与Chromium版本匹配）
    # 读取系统设置：最大重试次数
    max_retries = int(os.getenv("MAX_RETRIES", "2"))
    driver = None
    for attempt in range(max_retries):
        try:
            _check_cancelled()
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
                # 让 Selenium 自己通过 Selenium Manager 寻找/下载驱动（可能受网络/权限影响）
                driver = webdriver.Chrome(options=chrome_options)
            
            print("  浏览器启动成功")
            break  # 成功后跳出循环
        except Exception as e:
            if isinstance(e, TaskCancelled):
                raise
            # 如果 Selenium Manager 无法获取驱动，自动兜底尝试 webdriver-manager（即便未显式开启 USE_WDM）
            if (
                driver is None
                and (not chrome_driver_path)
                and (not USE_WEBDRIVER_MANAGER)
                and ("Unable to obtain driver for chrome" in str(e) or "obtain driver for chrome" in str(e))
            ):
                try:
                    print("  Selenium Manager 未能获取驱动，尝试用 webdriver-manager 兜底获取...")
                    service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()) if is_chromium else Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    print("  浏览器启动成功（webdriver-manager 兜底）")
                    break
                except Exception as e3:
                    e = e3

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
    _check_cancelled()
    
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
    
    # 如果使用cookies文件登录，加载cookies
    if use_cookies and load_cookies and cookies_exist and cookies_exist():
        print("  正在加载保存的Cookies...")
        try:
            load_cookies(driver)
            print("  ✓ Cookies加载成功")
        except Exception as e:
            print(f"  ⚠️  Cookies加载失败: {e}")
    
    return driver


def random_sleep(min_sec=1, max_sec=3):
    """随机等待，模拟人工操作"""
    total = random.uniform(min_sec, max_sec)
    # 分片睡眠：允许尽快响应取消
    step = 0.2
    slept = 0.0
    while slept < total:
        _check_cancelled()
        time.sleep(min(step, total - slept))
        slept += step


def simulate_typing(element, text, delay=0.1):
    """模拟人工输入"""
    for char in text:
        _check_cancelled()
        element.send_keys(char)
        time.sleep(random.uniform(delay * 0.5, delay * 1.5))


def select_dates(driver, wait, checkin_date=None, checkout_date=None):
    """
    选择入住和离店日期
    
    参数:
        driver: Selenium WebDriver对象
        wait: WebDriverWait对象
        checkin_date: 入住日期，格式 "YYYY-MM-DD"
        checkout_date: 离店日期，格式 "YYYY-MM-DD"
    """
    from datetime import datetime, timedelta
    
    # 如果没有指定日期，使用默认值（今天和明天）
    today = datetime.now()
    if not checkin_date:
        checkin_date = today.strftime("%Y-%m-%d")
    if not checkout_date:
        # 默认离店日期为入住日期后一天
        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
        checkout_date = (checkin_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"  入住日期: {checkin_date}")
    print(f"  离店日期: {checkout_date}")
    
    # 解析目标日期
    checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
    checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d")
    
    try:
        # 点击入住日期元素打开日历
        # 携程首页的日期选择器: <p id="checkIn" class="focus-input ...">1月5日<span>(今天)</span></p>
        checkin_selectors = [
            '//p[@id="checkIn"]',
            '//*[@id="checkIn"]',
            '//p[contains(@class, "in-time")]',
            '//p[contains(@class, "focus-input") and contains(text(), "月")]',
            '//*[@id="kakxi"]/li[2]/div[2]/div',
            '//div[contains(@class, "date-wrap")]//p[1]',
        ]
        
        date_picker_opened = False
        for selector in checkin_selectors:
            try:
                date_element = driver.find_element(By.XPATH, selector)
                if date_element.is_displayed():
                    driver.execute_script("arguments[0].click();", date_element)
                    print(f"  已点击入住日期选择器")
                    date_picker_opened = True
                    random_sleep(1, 1.5)
                    break
            except:
                continue
        
        if not date_picker_opened:
            print("  未找到日期选择区域，跳过日期选择")
            return
        
        # 选择入住日期
        if _click_date_in_calendar(driver, checkin_dt):
            print(f"  ✓ 已选择入住日期: {checkin_date}")
            random_sleep(0.8, 1.2)
        else:
            print(f"  ⚠ 入住日期选择可能失败")
        
        # 选择离店日期（日历通常会自动等待选择离店日期）
        if _click_date_in_calendar(driver, checkout_dt):
            print(f"  ✓ 已选择离店日期: {checkout_date}")
            random_sleep(0.5, 1)
        else:
            print(f"  ⚠ 离店日期选择可能失败")
        
    except Exception as e:
        print(f"  日期选择失败: {str(e)[:50]}")


def _click_date_in_calendar(driver, target_date):
    """
    在携程日历中点击指定日期
    
    参数:
        driver: Selenium WebDriver对象
        target_date: datetime对象，目标日期
    
    返回:
        bool: 是否成功点击
    """
    target_year = target_date.year
    target_month = target_date.month
    target_day = target_date.day
    
    # 携程日历的日期格式: "YYYY-MM-DD" 或 "YYYY-M-D"
    date_str_full = target_date.strftime("%Y-%m-%d")  # 2026-01-05
    date_str_short = f"{target_year}-{target_month}-{target_day}"  # 2026-1-5
    
    # 方式1: 通过data-date属性查找（携程常用方式）
    date_selectors = [
        f'//td[@data-date="{date_str_full}"]',
        f'//td[@data-date="{date_str_short}"]',
        f'//div[@data-date="{date_str_full}"]',
        f'//div[@data-date="{date_str_short}"]',
        f'//*[@data-date="{date_str_full}"]',
        f'//*[@data-date="{date_str_short}"]',
    ]
    
    for selector in date_selectors:
        try:
            date_el = driver.find_element(By.XPATH, selector)
            if date_el.is_displayed():
                # 滚动到元素可见
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_el)
                random_sleep(0.2, 0.3)
                driver.execute_script("arguments[0].click();", date_el)
                return True
        except:
            continue
    
    # 方式2: 先确保正确的月份可见，然后点击日期
    try:
        # 携程日历通常显示多个月份，需要找到正确月份的日期
        # 查找包含目标月份的日历面板
        month_str_cn = f"{target_year}年{target_month}月"  # 2026年1月
        month_str_cn2 = f"{target_month}月{target_year}"   # 1月2026
        
        # 查找月份标题，确定日历是否显示目标月份
        month_panels = driver.find_elements(By.XPATH, '//div[contains(@class, "calendar") or contains(@class, "month")]')
        
        target_panel = None
        for panel in month_panels:
            try:
                panel_text = panel.text
                if month_str_cn in panel_text or f"{target_month}月" in panel_text:
                    target_panel = panel
                    break
            except:
                continue
        
        # 如果没找到目标月份面板，尝试切换月份
        if not target_panel:
            max_switches = 12
            for _ in range(max_switches):
                # 点击下一个月按钮
                next_btn_selectors = [
                    '//div[contains(@class, "next") or contains(@class, "arrow-right")]',
                    '//span[contains(@class, "next")]',
                    '//button[contains(@class, "next")]',
                    '//i[contains(@class, "next") or contains(@class, "right")]',
                    '//*[contains(@class, "calendar")]//div[contains(@class, "arrow")][last()]',
                ]
                
                clicked = False
                for selector in next_btn_selectors:
                    try:
                        next_btn = driver.find_element(By.XPATH, selector)
                        if next_btn.is_displayed():
                            driver.execute_script("arguments[0].click();", next_btn)
                            clicked = True
                            random_sleep(0.3, 0.5)
                            break
                    except:
                        continue
                
                if not clicked:
                    break
                
                # 再次检查是否有目标月份
                for selector in date_selectors:
                    try:
                        date_el = driver.find_element(By.XPATH, selector)
                        if date_el.is_displayed():
                            driver.execute_script("arguments[0].click();", date_el)
                            return True
                    except:
                        continue
        
        # 方式3: 在日历中查找匹配日期数字的元素
        # 携程日历中日期通常是 <td> 或 <div> 包含日期数字
        day_selectors = [
            # 携程特定选择器
            f'//td[contains(@class, "day") and normalize-space(text())="{target_day}"]',
            f'//td[normalize-space(.)="{target_day}" and not(contains(@class, "disabled"))]',
            f'//div[contains(@class, "day") and normalize-space(text())="{target_day}"]',
            f'//span[contains(@class, "day") and normalize-space(text())="{target_day}"]',
            # 更通用的选择器
            f'//div[contains(@class, "calendar")]//td[normalize-space(.)="{target_day}"]',
            f'//div[contains(@class, "calendar")]//div[normalize-space(.)="{target_day}"]',
        ]
        
        for selector in day_selectors:
            try:
                day_elements = driver.find_elements(By.XPATH, selector)
                for day_el in day_elements:
                    if day_el.is_displayed():
                        class_attr = day_el.get_attribute("class") or ""
                        # 排除禁用、过去的日期
                        if "disabled" not in class_attr.lower() and "past" not in class_attr.lower() and "invalid" not in class_attr.lower():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", day_el)
                            random_sleep(0.1, 0.2)
                            driver.execute_script("arguments[0].click();", day_el)
                            return True
            except:
                continue
                
    except Exception as e:
        print(f"    点击日期失败: {str(e)[:50]}")
    
    return False


def search_hotel(driver, city, hotel_keyword, checkin_date=None, checkout_date=None):
    """
    在携程搜索酒店
    
    参数:
        driver: Selenium WebDriver对象
        city: 城市名称
        hotel_keyword: 酒店关键词
        checkin_date: 入住日期，格式 "YYYY-MM-DD"，默认为今天
        checkout_date: 离店日期，格式 "YYYY-MM-DD"，默认为明天
    
    返回:
        bool: 是否成功进入酒店详情页
    """
    _check_cancelled()
    print(f"\n[步骤1] 打开携程网站...")
    driver.get("https://www.ctrip.com/")
    random_sleep(3, 5)
    
    # 等待页面加载
    # 读取系统设置：请求超时时间
    request_timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))
    wait = WebDriverWait(driver, request_timeout)
    
    try:
        # [步骤2] 输入目的地城市
        _check_cancelled()
        print(f"[步骤2] 输入目的地: {city}")
        
        # 尝试多种方式找到目的地输入框
        destination_selectors = [
            '//*[@id="hotels-destination"]',
            '//input[@id="destination"]',
            '//input[contains(@placeholder, "目的地")]',
            '//input[contains(@placeholder, "城市")]',
            '//div[contains(@class, "destination")]//input'
        ]
        
        destination_input = None
        for selector in destination_selectors:
            try:
                destination_input = wait.until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                break
            except:
                continue
        
        if not destination_input:
            # 尝试点击酒店入口再查找
            print("  尝试点击酒店入口...")
            hotel_entry = driver.find_element(By.XPATH, '//a[contains(text(), "酒店")]')
            hotel_entry.click()
            random_sleep(2, 3)
            
            for selector in destination_selectors:
                try:
                    destination_input = wait.until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    break
                except:
                    continue
        
        if destination_input:
            _check_cancelled()
            # 先点击输入框
            destination_input.click()
            random_sleep(0.5, 1)
            # 全选并删除原有内容
            destination_input.send_keys(Keys.CONTROL + 'a')
            random_sleep(0.2, 0.3)
            destination_input.send_keys(Keys.DELETE)
            random_sleep(0.3, 0.5)
            # 再次确保清空
            destination_input.clear()
            random_sleep(0.3, 0.5)
            # 输入新城市
            simulate_typing(destination_input, city)
            print(f"  已输入目的地: {city}")
            random_sleep(1, 2)
        else:
            raise Exception("无法找到目的地输入框")
        
        # [步骤3] 等待并点击搜索建议的第一个结果
        _check_cancelled()
        print(f"[步骤3] 等待搜索建议并点击第一个结果...")
        random_sleep(2, 3)
        
        # 点击下拉建议中的第一个城市选项
        suggestion_selector = '//*[@id="kakxi"]/li[1]/div/div[2]/div[2]/div[1]/div'
        try:
            suggestion = wait.until(
                EC.element_to_be_clickable((By.XPATH, suggestion_selector))
            )
            suggestion.click()
            print("  已点击城市建议选项")
        except:
            print("  未找到建议选项，尝试按回车")
            destination_input.send_keys(Keys.ENTER)
        
        random_sleep(1, 2)
        
        # [步骤3.5] 选择入住和离店日期
        if checkin_date or checkout_date:
            print(f"[步骤3.5] 选择日期...")
            select_dates(driver, wait, checkin_date, checkout_date)
            random_sleep(1, 2)
        
        # [步骤4] 输入酒店关键词
        print(f"[步骤4] 输入酒店关键词: {hotel_keyword}")
        
        keyword_selectors = [
            '//*[@id="keyword"]',
            '//input[contains(@placeholder, "关键词")]',
            '//input[contains(@placeholder, "酒店")]',
            '//div[contains(@class, "keyword")]//input'
        ]
        
        keyword_input = None
        for selector in keyword_selectors:
            try:
                keyword_input = driver.find_element(By.XPATH, selector)
                if keyword_input.is_displayed():
                    break
            except:
                continue
        
        if keyword_input:
            keyword_input.clear()
            simulate_typing(keyword_input, hotel_keyword)
            random_sleep(1, 2)
        
        # [步骤5] 点击搜索按钮
        print("[步骤5] 点击搜索按钮...")
        search_selectors = [
            '//button[contains(text(), "搜索")]',
            '//div[contains(@class, "search-btn")]',
            '//a[contains(@class, "search-btn")]',
            '//button[contains(@class, "search")]'
        ]
        
        for selector in search_selectors:
            try:
                search_btn = driver.find_element(By.XPATH, selector)
                if search_btn.is_displayed():
                    search_btn.click()
                    break
            except:
                continue
        
        random_sleep(3, 5)
        
        # [步骤6] 在搜索结果中点击第一个酒店
        print("[步骤6] 点击搜索结果中的第一个酒店...")
        random_sleep(2, 3)
        
        # 点击第一个酒店名称
        hotel_name_selector = '//span[@class="hotelName"]'
        try:
            hotel_names = driver.find_elements(By.XPATH, hotel_name_selector)
            print(f"  找到 {len(hotel_names)} 个酒店")
            if hotel_names:
                hotel_name = hotel_names[0].text
                print(f"  点击酒店: {hotel_name}")
                hotel_names[0].click()
                random_sleep(2, 3)
                
                # 切换到新打开的标签页
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    print("  已切换到酒店详情页")
                
                random_sleep(3, 5)
                return True
        except Exception as e:
            print(f"  点击酒店名称失败: {str(e)[:50]}")
        
        # 备用方案：点击查看详情按钮
        try:
            detail_btn = driver.find_element(By.XPATH, '//div[@class="book-btn"]//span[contains(text(), "查看详情")]')
            detail_btn.click()
            random_sleep(2, 3)
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
            return True
        except:
            pass
            
        print("  未能点击酒店")
        return False
        
    except Exception as e:
        print(f"搜索过程出错: {str(e)}")
        return False


def extract_hotel_info(driver):
    """
    从酒店详情页提取酒店基本信息
    
    参数:
        driver: Selenium WebDriver对象
    
    返回:
        dict: 包含酒店名称、地址等信息的字典
    """
    hotel_info = {
        "酒店名称": "",
        "地址": ""
    }
    
    try:
        # 提取酒店名称
        name_selectors = [
            '//h1[@class="hotel-name"]',
            '//h1[contains(@class, "name")]',
            '//div[contains(@class, "hotel-name")]',
            '//h1',
            '//div[@class="hotel-info"]//h1',
            '//span[@class="hotel-name"]'
        ]
        
        for selector in name_selectors:
            try:
                name_element = driver.find_element(By.XPATH, selector)
                if name_element and name_element.text.strip():
                    hotel_info["酒店名称"] = name_element.text.strip()
                    print(f"  酒店名称: {hotel_info['酒店名称']}")
                    break
            except:
                continue
        
        # 提取地址
        address_selectors = [
            '//div[contains(@class, "address")]',
            '//span[contains(@class, "address")]',
            '//div[contains(text(), "地址")]',
            '//*[contains(text(), "地址：")]',
            '//*[contains(text(), "地址:")]'
        ]
        
        for selector in address_selectors:
            try:
                addr_element = driver.find_element(By.XPATH, selector)
                addr_text = addr_element.text.strip()
                if addr_text and len(addr_text) > 3:
                    # 清理地址文本
                    addr_text = addr_text.replace("地址：", "").replace("地址:", "").strip()
                    # 移除换行符和"显示地图"等无关文本
                    addr_text = addr_text.replace("\n显示地图", "").replace("显示地图", "").strip()
                    # 移除所有换行符
                    addr_text = addr_text.replace("\n", " ").strip()
                    hotel_info["地址"] = addr_text
                    print(f"  地址: {hotel_info['地址']}")
                    break
            except:
                continue
        
    except Exception as e:
        print(f"  提取酒店信息时出错: {str(e)[:50]}")
    
    return hotel_info


def extract_room_data(driver):
    """
    从酒店详情页提取房型数据
    
    参数:
        driver: Selenium WebDriver对象
    
    返回:
        list: 房型数据列表
    """
    print("\n[数据提取] 开始提取房型数据...")
    
    # 设置较短的隐式等待时间，加快元素查找速度
    # 读取系统设置：请求超时时间（用于隐式等待）
    request_timeout = int(os.getenv("REQUEST_TIMEOUT", "10"))
    driver.implicitly_wait(min(request_timeout / 20, 0.5))  # 隐式等待使用较小的值
    
    # 等待页面加载
    random_sleep(2, 3)
    
    # 滚动页面以加载更多内容
    driver.execute_script("window.scrollTo(0, 500);")
    random_sleep(0.5, 1)
    
    # [新增1] 点击"展示其余X个房型"按钮，展开所有隐藏的房型
    print("  正在展开所有隐藏房型...")
    room_expand_count = 0
    max_attempts = 5  # 最多尝试5次，因为点击后可能还会出现新的按钮
    clicked_button_ids = set()  # 记录已点击的按钮ID，避免重复点击
    
    for attempt in range(max_attempts):
        try:
            # 使用多种选择器查找"展示其余"按钮
            expand_selectors = [
                '//*[contains(text(), "展示其余")]',
                '//a[contains(text(), "展示其余")]',
                '//span[contains(text(), "展示其余")]',
                '//div[contains(text(), "展示其余")]',
                '//*[@class][contains(text(), "展示其余")]',
            ]
            
            room_expand_buttons = []
            for selector in expand_selectors:
                try:
                    buttons = driver.find_elements(By.XPATH, selector)
                    room_expand_buttons.extend(buttons)
                except:
                    continue
            
            # 去重（同一个元素可能被多个选择器找到）
            unique_buttons = []
            seen_elements = set()
            for btn in room_expand_buttons:
                try:
                    element_id = btn.id
                    if element_id not in seen_elements:
                        seen_elements.add(element_id)
                        unique_buttons.append(btn)
                except:
                    # 如果无法获取ID，尝试通过位置去重
                    try:
                        location = btn.location
                        size = btn.size
                        key = (location['x'], location['y'], size['width'], size['height'])
                        if key not in seen_elements:
                            seen_elements.add(key)
                            unique_buttons.append(btn)
                    except:
                        unique_buttons.append(btn)
            
            # 过滤掉已点击的按钮
            new_buttons = []
            for btn in unique_buttons:
                try:
                    btn_id = btn.id
                    if btn_id not in clicked_button_ids:
                        new_buttons.append(btn)
                except:
                    # 如果无法获取ID，尝试通过文本和位置判断
                    try:
                        btn_text = btn.text[:50] if btn.text else ""
                        location = btn.location
                        btn_key = (btn_text, location.get('x', 0), location.get('y', 0))
                        if btn_key not in clicked_button_ids:
                            new_buttons.append(btn)
                            clicked_button_ids.add(btn_key)
                    except:
                        new_buttons.append(btn)
            
            unique_buttons = new_buttons
            print(f"  第{attempt + 1}次尝试，找到 {len(unique_buttons)} 个未点击的房型展开按钮")
            
            if not unique_buttons:
                if attempt == 0:
                    print("  未找到房型展开按钮")
                else:
                    print("  所有按钮已点击或已不存在")
                break
            
            clicked_any = False
            for btn in unique_buttons:
                try:
                    # 记录按钮ID，避免重复点击
                    try:
                        btn_id = btn.id
                        clicked_button_ids.add(btn_id)
                    except:
                        try:
                            btn_text = btn.text[:50] if btn.text else ""
                            location = btn.location
                            btn_key = (btn_text, location.get('x', 0), location.get('y', 0))
                            clicked_button_ids.add(btn_key)
                        except:
                            pass
                    
                    # 先滚动到元素可见位置（即使is_displayed返回False也尝试）
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", btn)
                    random_sleep(0.3, 0.5)
                    
                    # 尝试多种点击方式（优先使用JavaScript点击，避免可见性问题）
                    click_success = False
                    try:
                        # 方式1: JavaScript点击（最可靠，不受遮挡影响）
                        driver.execute_script("arguments[0].click();", btn)
                        click_success = True
                    except:
                        try:
                            # 方式2: 直接点击
                            btn.click()
                            click_success = True
                        except:
                            try:
                                # 方式3: 模拟鼠标事件
                                from selenium.webdriver.common.action_chains import ActionChains
                                ActionChains(driver).move_to_element(btn).click().perform()
                                click_success = True
                            except:
                                print(f"    无法点击按钮: {btn.text[:30] if btn.text else '未知'}")
                    
                    if click_success:
                        clicked_any = True
                        room_expand_count += 1
                        print(f"    已点击: {btn.text[:50] if btn.text else '展开按钮'}")
                        random_sleep(1, 1.5)
                except Exception as e:
                    print(f"    点击房型展开按钮失败: {str(e)[:50]}")
            
            if not clicked_any:
                print("  本轮未点击任何按钮，停止尝试")
                break  # 如果没有点击任何按钮，停止尝试
            
            # 短暂等待，让页面更新
            random_sleep(0.5, 1)
            
        except Exception as e:
            print(f"  查找房型展开按钮时出错: {str(e)[:50]}")
            break
    
    if room_expand_count > 0:
        print(f"  已展开 {room_expand_count} 个隐藏房型区域")
        random_sleep(1, 1.5)  # 缩短等待时间
    else:
        print("  未找到或无法点击房型展开按钮")
    
    # 点击所有"展示额外"按钮，展开隐藏的套餐
    try:
        pkg_expand_buttons = driver.find_elements(By.XPATH, '//*[contains(text(), "展示额外")]')
        for btn in pkg_expand_buttons:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                driver.execute_script("arguments[0].click();", btn)  # 直接用JS点击，更快
                random_sleep(0.2, 0.3)
            except:
                pass
        if pkg_expand_buttons:
            random_sleep(0.5, 1)
    except:
        pass
    
    # 回到页面顶部
    driver.execute_script("window.scrollTo(0, 0);")
    random_sleep(0.2, 0.3)
    
    all_rooms = []
    
    room_ids = []
    try:
        all_divs = driver.find_elements(By.XPATH, '//div[@id]')
        for div in all_divs:
            try:
                div_id = div.get_attribute("id")
                # 检查ID是否为纯数字且长度大于5（房型ID特征）
                if div_id and div_id.isdigit() and len(div_id) > 5:
                    room_ids.append(div_id)
            except:
                pass
    except Exception as e:
        pass
    
    if not room_ids:
        try:
            room_containers = driver.find_elements(By.XPATH, '//div[contains(@class, "room-list")]//div[contains(@class, "room-item")]')
        except:
            pass
        return []
    
    # 遍历每个房型ID
    for room_id in room_ids:
        # 检查容器是否存在
        try:
            container = driver.find_element(By.XPATH, f'//*[@id="{room_id}"]')
            if not container:
                continue
        except:
            continue
        
        # 获取房型名称
        room_name = ""
        try:
            name_xpath = f'//*[@id="{room_id}"]/div[1]/span'
            name_element = driver.find_element(By.XPATH, name_xpath)
            room_name = name_element.text.strip()
        except:
            pass
        
        if not room_name:
            room_name = f"房型_{room_id}"
        
        # 获取窗户信息
        window_info = ""
        try:
            # 窗户信息XPath: //*[@id="房型ID"]/div[2]/div[1]/div[3]/div[1]/span
            window_xpath = f'//*[@id="{room_id}"]/div[2]/div[1]/div[3]/div[1]/span'
            window_element = driver.find_element(By.XPATH, window_xpath)
            window_info = window_element.text.strip()
        except:
            pass
        
        # 如果上面的XPath没找到，尝试备用XPath（只用一个通用选择器）
        if not window_info:
            try:
                # 备用XPath：在房型信息区域查找包含"窗"字的元素
                window_element = driver.find_element(By.XPATH, f'//*[@id="{room_id}"]/div[2]/div[1]//span[contains(text(), "窗")]')
                window_info = window_element.text.strip()
            except:
                pass
        
        room_data = {
            "房型名称": room_name,
            "窗户信息": window_info,
            "套餐列表": []
        }
        
        # 获取该房型下的所有套餐（展开后可能更多，扩大搜索范围）
        empty_count = 0
        for pkg_idx in range(2, 20):
            summary_xpath = f'//*[@id="{room_id}"]/div[2]/div[2]/div[{pkg_idx}]/div[1]'
            price_xpath = f'//*[@id="{room_id}"]/div[2]/div[2]/div[{pkg_idx}]/div[3]'
            
            pkg_info = {
                "套餐摘要": "",
                "价格": "",
                "剩余房间": "",
                "房量状态": ""
            }
            
            # 提取套餐摘要
            try:
                summary_el = driver.find_element(By.XPATH, summary_xpath)
                pkg_info["套餐摘要"] = summary_el.text.strip()
            except:
                pass
            
            # 提取价格和剩余房间数
            try:
                price_el = driver.find_element(By.XPATH, price_xpath)
                price_text = price_el.text.strip()
                
                # 提取剩余房间数（如"仅剩4间"）
                remain_match = re.search(r'仅剩(\d+)间', price_text)
                if remain_match:
                    pkg_info["剩余房间"] = f"仅剩{remain_match.group(1)}间"
                
                # 找出所有价格数字
                all_prices = re.findall(r'[¥￥]\s*(\d+(?:,\d{3})*)', price_text)
                if all_prices:
                    actual_price = all_prices[-1]
                    pkg_info["价格"] = f"¥{actual_price}"
                else:
                    pkg_info["价格"] = price_text
            except:
                pass
            
            # 提取房量状态（如"房量紧张"）
            try:
                status_xpath = f'//*[@id="{room_id}"]/div[2]/div[2]/div[{pkg_idx}]/div[3]/div/div/div[2]/div'
                status_el = driver.find_element(By.XPATH, status_xpath)
                status_text = status_el.text.strip()
                if status_text:
                    pkg_info["房量状态"] = status_text
                    # 如果没有剩余房间信息，将房量状态显示在剩余房间字段中
                    if not pkg_info["剩余房间"]:
                        pkg_info["剩余房间"] = status_text
            except:
                pass
            
            # 如果连续2个空摘要，说明没有更多套餐了
            if not pkg_info["套餐摘要"]:
                empty_count += 1
                if empty_count >= 2:
                    break
                continue
            else:
                empty_count = 0
            
            # 过滤无效内容（按钮、展开收起等）
            invalid_keywords = ["展示额外", "收起", "查看更多", "展开", "房型价格"]
            is_valid = True
            for keyword in invalid_keywords:
                if keyword in pkg_info["套餐摘要"]:
                    is_valid = False
                    break
            
            # 有效套餐应该包含早餐、取消、确认等关键词
            valid_keywords = ["早餐", "取消", "确认", "在线付", "到店付"]
            has_valid_keyword = any(kw in pkg_info["套餐摘要"] for kw in valid_keywords)
            
            if is_valid and has_valid_keyword:
                room_data["套餐列表"].append(pkg_info)
        
        # 只有获取到套餐的房型才添加
        if room_data["套餐列表"]:
            all_rooms.append(room_data)
            print(f"  ✓ {room_name} - {len(room_data['套餐列表'])}个套餐")
    
    # 恢复默认隐式等待时间
    # 读取系统设置：请求超时时间（用于隐式等待）
    request_timeout = int(os.getenv("REQUEST_TIMEOUT", "10"))
    driver.implicitly_wait(min(request_timeout, 10))
    
    print(f"  提取完成，共 {len(all_rooms)} 个房型")
    return all_rooms


def print_summary(all_rooms):
    """打印汇总信息"""
    print(f"\n{'='*50}")
    print(f"{'汇总':^48}")
    print(f"{'='*50}")
    print(f"共提取到 {len(all_rooms)} 个房型\n")
    
    for room in all_rooms:
        window_info = room.get('窗户信息', '')
        window_display = f" [{window_info}]" if window_info else ""
        print(f"【{room['房型名称']}】{window_display} - {len(room['套餐列表'])} 个套餐")
        for pkg in room['套餐列表']:
            summary_short = pkg['套餐摘要'][:40] if len(pkg['套餐摘要']) > 40 else pkg['套餐摘要']
            remain_info = f" | {pkg['剩余房间']}" if pkg.get('剩余房间') else ""
            print(f"    {summary_short} | {pkg['价格']}{remain_info}")
        print()


def save_to_json(data, filename="hotel_data.json"):
    """保存数据到JSON文件"""
    filepath = os.path.join(os.path.dirname(__file__), filename) if hasattr(os.path, 'dirname') else filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n数据已保存到: {filepath}")


def main():
    """主函数"""
    print("=" * 50)
    print("  携程酒店房型数据爬取工具")
    print("=" * 50)
    
    # 获取用户输入
    print("\n输入格式说明:")
    print("  基本格式: 城市,酒店关键词")
    print("  带日期格式: 城市,酒店关键词,入住日期,离店日期")
    print("  日期格式: YYYY-MM-DD (如 2026-01-10)")
    print("  示例: 上海,如家,2026-01-10,2026-01-12")
    
    input_str = input("\n请输入查询条件: ").strip()
    
    if not input_str:
        print("输入为空，使用默认值: 上海,如家")
        input_str = "上海,如家"
    
    # 分割输入
    parts = input_str.split(',')
    if len(parts) < 2:
        parts = input_str.split('，')  # 支持中文逗号
    
    if len(parts) < 2:
        print("输入格式错误！请使用格式: 城市,酒店关键词")
        return
    
    city = parts[0].strip()
    hotel_keyword = parts[1].strip()
    checkin_date = parts[2].strip() if len(parts) > 2 else None
    checkout_date = parts[3].strip() if len(parts) > 3 else None
    
    # 验证日期格式
    if checkin_date:
        try:
            datetime.strptime(checkin_date, "%Y-%m-%d")
        except ValueError:
            print(f"入住日期格式错误: {checkin_date}，应为 YYYY-MM-DD")
            return
    
    if checkout_date:
        try:
            datetime.strptime(checkout_date, "%Y-%m-%d")
        except ValueError:
            print(f"离店日期格式错误: {checkout_date}，应为 YYYY-MM-DD")
            return
    
    print(f"\n搜索参数:")
    print(f"  城市: {city}")
    print(f"  酒店关键词: {hotel_keyword}")
    if checkin_date:
        print(f"  入住日期: {checkin_date}")
    if checkout_date:
        print(f"  离店日期: {checkout_date}")
    
    driver = None
    try:
        # 启动浏览器
        print("\n正在启动浏览器...")
        driver = setup_browser()
        
        # 搜索酒店
        success = search_hotel(driver, city, hotel_keyword, checkin_date, checkout_date)
        
        if success:
            # 提取酒店基本信息
            hotel_info = extract_hotel_info(driver)
            
            # 提取房型数据
            room_data = extract_room_data(driver)
            
            if room_data:
                # 构建完整的数据结构（类似meituan格式）
                # 计算实际使用的日期
                from datetime import timedelta
                actual_checkin = checkin_date if checkin_date else datetime.now().strftime("%Y-%m-%d")
                actual_checkout = checkout_date if checkout_date else (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                
                complete_data = {
                    "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "入住日期": actual_checkin,
                    "离店日期": actual_checkout,
                    "地址": hotel_info.get("地址", ""),
                    "酒店名称": hotel_info.get("酒店名称", ""),
                    "酒店关键词": hotel_keyword,
                    "房型总数": len(room_data),
                    "房型列表": []
                }
                
                # 转换房型数据格式（从嵌套的套餐列表转为扁平列表，类似meituan格式）
                for room in room_data:
                    room_name = room.get("房型名称", "")
                    window_info = room.get("窗户信息", "")
                    for pkg in room.get("套餐列表", []):
                        # 将套餐信息转换为房型项
                        room_item = {
                            "房型名称": room_name,
                            "窗户信息": window_info,
                            "价格": pkg.get("价格", ""),
                            "剩余房间": pkg.get("剩余房间", ""),
                            "备注": pkg.get("套餐摘要", "").replace("\n", " ")
                        }
                        # 如果剩余房间字段为空但有房量状态，使用房量状态
                        if not room_item["剩余房间"] and pkg.get("房量状态"):
                            room_item["剩余房间"] = pkg.get("房量状态")
                        complete_data["房型列表"].append(room_item)
                
                # 更新房型总数为实际房型项数量
                complete_data["房型总数"] = len(complete_data["房型列表"])
                
                # 打印汇总
                print_summary(room_data)
                
                # 保存到文件
                save_to_json(complete_data, "hotel_data.json")
                
                # 保存到数据库
                if save_to_database:
                    try:
                        save_to_database("ctrip", complete_data)
                    except Exception as e:
                        print(f"\n⚠️  数据库保存失败: {e}")
                else:
                    print("\n⚠️  数据库模块不可用，跳过数据库保存")
            else:
                print("\n未能提取到房型数据")
        else:
            print("\n未能成功进入酒店详情页")
        
        # 等待用户确认后关闭
        input("\n按回车键关闭浏览器...")
        
    except Exception as e:
        print(f"\n程序出错: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        if driver:
            driver.quit()
            print("浏览器已关闭")


if __name__ == "__main__":
    main()


# ==================== 供 Web 管理平台调用：非交互运行 ====================

def run_non_interactive(city: str, hotel_keyword: str, checkin_date: str = None, checkout_date: str = None, cancel_event=None):
    """
    供 Web 管理平台后台任务调用的入口。
    - 不会等待 input()
    - 返回结构化数据（并沿用原逻辑写 json/db）
    """
    driver = None
    try:
        global _CANCEL_EVENT
        _CANCEL_EVENT = cancel_event
        _check_cancelled()
        driver = setup_browser(use_local_profile=True, use_cookies=True)
        success = search_hotel(driver, city, hotel_keyword, checkin_date, checkout_date)

        if not success:
            return {
                "ok": False,
                "error": "未能成功进入酒店详情页",
                "city": city,
                "hotel_keyword": hotel_keyword,
            }

        hotel_info = extract_hotel_info(driver)
        room_data = extract_room_data(driver)
        if not room_data:
            return {
                "ok": False,
                "error": "未能提取到房型数据",
                "city": city,
                "hotel_keyword": hotel_keyword,
                "hotel_info": hotel_info,
            }

        from datetime import timedelta

        actual_checkin = checkin_date if checkin_date else datetime.now().strftime("%Y-%m-%d")
        actual_checkout = checkout_date if checkout_date else (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        complete_data = {
            "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "入住日期": actual_checkin,
            "离店日期": actual_checkout,
            "地址": hotel_info.get("地址", ""),
            "酒店名称": hotel_info.get("酒店名称", ""),
            "酒店关键词": hotel_keyword,
            "房型总数": 0,
            "房型列表": [],
        }

        for room in room_data:
            room_name = room.get("房型名称", "")
            window_info = room.get("窗户信息", "")
            for pkg in room.get("套餐列表", []):
                room_item = {
                    "房型名称": room_name,
                    "窗户信息": window_info,
                    "价格": pkg.get("价格", ""),
                    "剩余房间": pkg.get("剩余房间", ""),
                    "备注": (pkg.get("套餐摘要", "") or "").replace("\n", " "),
                }
                if not room_item["剩余房间"] and pkg.get("房量状态"):
                    room_item["剩余房间"] = pkg.get("房量状态")
                complete_data["房型列表"].append(room_item)

        complete_data["房型总数"] = len(complete_data["房型列表"])

        try:
            save_to_json(complete_data, "hotel_data.json")
        except Exception:
            pass

        if save_to_database:
            try:
                save_to_database("ctrip", complete_data)
            except Exception:
                pass

        return {"ok": True, "data": complete_data}
    except TaskCancelled:
        return {"ok": False, "error": "任务已取消"}
    finally:
        _CANCEL_EVENT = None
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

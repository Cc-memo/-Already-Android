import random
import time
import json
import pickle
import os
import platform
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service

class TaskCancelled(Exception):
    """Web Admin 删除/取消任务时用于中断执行。"""


# 由 Web Admin 注入（run 设置），用于脚本内部轮询取消
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
    os.environ['WDM_LOCAL'] = '1'  # 优先使用本地缓存
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

if platform.system() == "Linux" and os.getenv("USE_WDM", "0") != "1":
    USE_WEBDRIVER_MANAGER = False

# 获取脚本所在目录，确保cookies文件路径正确
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(SCRIPT_DIR, "meituan_h5_cookies.pkl")

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
    except:
        pass


def setup_browser():
    """
    配置并启动Chromium浏览器（纯净模式，使用Cookies保存登录态）
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
    
    # 不使用用户数据目录，避免冲突
    # 登录态通过 Cookies 文件管理
    
    # 防止崩溃和检测的参数
    headless_env = os.getenv("HEADLESS")
    if headless_env is None:
        headless_env = "1" if platform.system() == "Linux" else "0"
    if headless_env.lower() in ("1", "true", "yes", "on"):
        chrome_options.add_argument("--headless=new")

    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=430,900')
    
    # 抑制警告信息
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # 代理配置（如果启用）
    use_proxy = os.getenv("USE_PROXY", "").strip()
    if use_proxy and use_proxy.lower() in ("1", "true", "yes", "on"):
        http_proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        if http_proxy:
            chrome_options.add_argument(f'--proxy-server={http_proxy}')
            print(f"  已启用代理: {http_proxy}")
        else:
            print("  ⚠️  已启用代理但未配置 HTTP_PROXY 或 HTTPS_PROXY 环境变量")
    
    # 尝试启动浏览器
    # 读取系统设置：最大重试次数
    max_retries = int(os.getenv("MAX_RETRIES", "2"))
    driver = None
    chrome_driver_path = os.getenv("CHROME_DRIVER_PATH")
    if chrome_driver_path and not os.path.exists(chrome_driver_path):
        print(f"  ⚠️  CHROME_DRIVER_PATH 指向的文件不存在: {chrome_driver_path}")
        chrome_driver_path = None
    is_chromium = bool(chrome_bin) and any(k in chrome_bin.lower() for k in ("chromium", "chrome-win"))

    for attempt in range(max_retries):
        try:
            _check_cancelled()
            # 在Linux服务器上，尝试使用webdriver-manager（优先，可能使用缓存）
            if platform.system() == 'Linux':
                # Linux服务器：优先使用webdriver-manager（可能使用本地缓存）
                if USE_WEBDRIVER_MANAGER:
                    try:
                        print("  尝试使用webdriver-manager获取chromedriver...")
                        service = Service(ChromeDriverManager().install())
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        print("  使用webdriver-manager成功")
                    except Exception as e:
                        print(f"  webdriver-manager失败: {e}")
                        print("  尝试直接使用系统chromedriver...")
                        # 如果webdriver-manager失败，尝试直接使用系统chromedriver
                        try:
                            driver = webdriver.Chrome(options=chrome_options)
                            print("  使用系统chromedriver成功")
                        except Exception as e2:
                            raise Exception(f"无法启动Chrome: webdriver-manager失败({e})，系统chromedriver也失败({e2})。请手动安装chromedriver到/usr/local/bin/chromedriver")
                else:
                    # 如果没有webdriver-manager，尝试直接使用系统chromedriver
                    try:
                        driver = webdriver.Chrome(options=chrome_options)
                    except Exception as e:
                        raise Exception(f"无法启动Chrome: 未找到chromedriver。请安装: sudo yum install -y chromium-driver 或手动下载chromedriver到/usr/local/bin/chromedriver")
            elif USE_WEBDRIVER_MANAGER:
                # Windows本地：使用webdriver-manager
                print("  使用 webdriver-manager 管理 ChromeDriver")
                try:
                    if chrome_driver_path:
                        service = Service(executable_path=chrome_driver_path)
                    else:
                        service = Service(
                            ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
                            if is_chromium
                            else ChromeDriverManager().install()
                        )
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                except Exception as e:
                    print(f"  webdriver-manager失败，尝试直接启动: {e}")
                    driver = webdriver.Chrome(options=chrome_options)
            else:
                if chrome_driver_path:
                    service = Service(executable_path=chrome_driver_path)
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                else:
                    driver = webdriver.Chrome(options=chrome_options)
            print("  浏览器启动成功")
            break  # 成功后跳出循环，不要直接return
        except Exception as e:
            if isinstance(e, TaskCancelled):
                raise
            if attempt < max_retries - 1:
                print(f"  启动失败，正在清理进程后重试... ({attempt + 1}/{max_retries})")
                kill_chrome_processes()
                time.sleep(2)
            else:
                print(f"\n❌ 浏览器启动失败: {e}")
                print("\n请尝试以下解决方案:")
                print("  1. 手动关闭所有 Chrome/Chromium 窗口")
                print("  2. 运行测试脚本: python test_browser.py")
                print("  3. 或尝试: pip install --upgrade selenium webdriver-manager")
                raise
    
    # 防止被检测为自动化程序
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })
        print("  已添加反检测脚本")
    except:
        pass
    
    return driver


def random_sleep(min_s=0.8, max_s=1.6):
    total = random.uniform(min_s, max_s)
    step = 0.2
    slept = 0.0
    while slept < total:
        _check_cancelled()
        time.sleep(min(step, total - slept))
        slept += step


def type_slowly(element, text):
    for ch in text:
        _check_cancelled()
        element.send_keys(ch)
        time.sleep(random.uniform(0.05, 0.12))


def click_first(driver, xpaths, timeout=None):
    """依次尝试一组 XPath，点击第一个可点击的元素。"""
    # 读取系统设置：请求超时时间
    if timeout is None:
        timeout = int(os.getenv("REQUEST_TIMEOUT", "8"))
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            el.click()
            return el
        except Exception:
            continue
    return None


def choose_first_suggestion(driver, suggestion_xpaths):
    """选择下拉列表中的第一个建议项。"""
    # 读取系统设置：请求超时时间（使用较短超时，因为这是快速操作）
    timeout = min(int(os.getenv("REQUEST_TIMEOUT", "6")), 6)
    for xp in suggestion_xpaths:
        try:
            elems = WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located((By.XPATH, xp))
            )
            for el in elems:
                if el.is_displayed():
                    el.click()
                    return True
        except TimeoutException:
            continue
        except Exception:
            continue
    return False


def choose_first_suggestion_by_keyboard(input_el):
    """用键盘选择第一个建议（部分页面下拉项 XPath 不稳定时的兜底）。"""
    try:
        input_el.send_keys(Keys.ARROW_DOWN)
        time.sleep(0.15)
        input_el.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def select_dates(driver, wait, checkin_date=None, checkout_date=None):
    """
    选择入住和离店日期
    
    参数:
        driver: Selenium WebDriver对象
        wait: WebDriverWait对象
        checkin_date: 入住日期，格式 "YYYY-MM-DD"
        checkout_date: 离店日期，格式 "YYYY-MM-DD"
    """
    from datetime import timedelta
    
    # 如果没有指定日期，使用默认值（今天和明天）
    today = datetime.now()
    if not checkin_date:
        checkin_date = today.strftime("%Y-%m-%d")
    if not checkout_date:
        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
        checkout_date = (checkin_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"  入住日期: {checkin_date}")
    print(f"  离店日期: {checkout_date}")
    
    try:
        # 点击日期区域打开日历
        # 美团H5页面的日期入口: //*[@id="search"]/div/div[1]/div[3] 或 div[4]
        date_entry_selectors = [
            '//*[@id="search"]/div/div[1]/div[3]',
            '//*[@id="search"]/div/div[1]/div[4]',
            '//div[contains(text(), "入住")]/..',
            '//div[contains(text(), "今天")]/..',
            '//div[contains(@class, "date")]',
        ]
        
        date_picker_opened = False
        for selector in date_entry_selectors:
            try:
                date_entry = driver.find_element(By.XPATH, selector)
                if date_entry.is_displayed():
                    date_entry.click()
                    print("  已点击日期选择入口")
                    date_picker_opened = True
                    random_sleep(1, 1.5)
                    break
            except:
                continue
        
        if not date_picker_opened:
            print("  未找到日期选择入口，跳过日期选择")
            return False
        
        # 等待日历弹出
        try:
            wait.until(EC.presence_of_element_located((By.ID, "vueCalendarTemplate")))
            random_sleep(0.5, 1)
        except:
            print("  日历未弹出")
            return False
        
        # 选择入住日期（通过 data-date-format 属性定位）
        if _click_meituan_date(driver, checkin_date):
            print(f"  ✓ 已选择入住日期: {checkin_date}")
            random_sleep(0.5, 0.8)
        else:
            print(f"  ⚠ 入住日期选择可能失败")
        
        # 选择离店日期
        if _click_meituan_date(driver, checkout_date):
            print(f"  ✓ 已选择离店日期: {checkout_date}")
            random_sleep(0.5, 0.8)
        else:
            print(f"  ⚠ 离店日期选择可能失败")
        
        # 点击"完成"按钮确认日期选择
        try:
            complete_btn_selectors = [
                '//a[contains(text(), "完成")]',
                '//div[contains(@class, "complete")]//a',
                '//div[contains(@class, "calendar-complete")]//a',
            ]
            for selector in complete_btn_selectors:
                try:
                    complete_btn = driver.find_element(By.XPATH, selector)
                    if complete_btn.is_displayed():
                        complete_btn.click()
                        print("  ✓ 已点击完成按钮")
                        random_sleep(0.5, 1)
                        break
                except:
                    continue
        except:
            pass
        
        return True
        
    except Exception as e:
        print(f"  日期选择失败: {str(e)[:50]}")
        return False


def _click_meituan_date(driver, date_str):
    """
    在美团日历中点击指定日期
    
    参数:
        driver: Selenium WebDriver对象
        date_str: 日期字符串，格式 "YYYY-MM-DD"
    
    返回:
        bool: 是否成功点击
    """
    # 美团日历使用 data-date-format 属性存储日期
    # 例如: <li class="_day" data-date-format="2026-01-10">
    date_selectors = [
        f'//li[@data-date-format="{date_str}"]',
        f'//*[@data-date-format="{date_str}"]',
    ]
    
    for selector in date_selectors:
        try:
            date_elements = driver.find_elements(By.XPATH, selector)
            for date_el in date_elements:
                # 检查是否可点击（排除 disabled 状态）
                class_attr = date_el.get_attribute("class") or ""
                if "disabled" in class_attr:
                    continue
                
                # 滚动到元素可见
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_el)
                random_sleep(0.2, 0.3)
                
                # 点击日期
                driver.execute_script("arguments[0].click();", date_el)
                return True
        except:
            continue
    
    return False


def load_cookies(driver):
    """从文件加载cookies"""
    if not os.path.exists(COOKIES_FILE):
        return False
    
    try:
        with open(COOKIES_FILE, 'rb') as f:
            cookies = pickle.load(f)
        
        # 先访问域名
        driver.get("https://i.meituan.com")
        time.sleep(1)
        
        # 加载cookies
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except:
                pass
        
        print(f"✓ 已加载保存的Cookies（共 {len(cookies)} 个）")
        return True
    except Exception as e:
        print(f"⚠️  加载Cookies失败: {e}")
        return False


def save_cookies(driver):
    """保存cookies到文件"""
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'wb') as f:
            pickle.dump(cookies, f)
        print(f"✓ Cookies已保存（共 {len(cookies)} 个）")
    except Exception as e:
        print(f"⚠️  保存Cookies失败: {e}")


def check_and_wait_login(driver):
    """检测H5页面登录状态，未登录则引导用户使用登录工具。"""
    random_sleep(1, 2)
    
    # 检测页面中是否有"登录"和"注册"文字（说明未登录）
    try:
        page_text = driver.find_element(By.TAG_NAME, 'body').text
    except:
        page_text = ""
    
    # 页面底部有"登录 注册"说明未登录
    if '登录' in page_text and '注册' in page_text:
        # 非交互模式：直接失败，避免后台任务卡在 input()
        if os.getenv("NON_INTERACTIVE", "0") == "1":
            raise RuntimeError("美团H5未登录：请先运行 python meituan_cookies.py 生成登录态，再重试任务")

        print("\n" + "="*50)
        print("⚠️  H5页面未登录！")
        print("")
        print("请使用登录工具完成登录：")
        print("  python meituan_cookies.py")
        print("")
        print("登录后再运行本程序即可自动使用保存的登录态")
        print("="*50)
        
        # 等待用户手动登录
        print("\n或者现在在浏览器中登录...")
        input("登录完成后，按回车键继续 >>> ")
        
        # 保存cookies
        save_cookies(driver)
        
        # 刷新页面
        print("正在刷新页面...")
        driver.get("https://i.meituan.com/awp/h5/hotel/search/search.html")
        random_sleep(3, 4)
        
        print("✓ 登录完成，继续执行...\n")
    else:
        print("✓ 已登录，继续执行...")


def run(address_keyword, hotel_keyword, checkin_date=None, checkout_date=None, cancel_event=None):
    global _CANCEL_EVENT
    _CANCEL_EVENT = cancel_event
    _check_cancelled()
    driver = setup_browser()
    # 读取系统设置：请求超时时间
    request_timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))
    wait = WebDriverWait(driver, request_timeout)
    
    # 尝试加载保存的cookies
    cookies_loaded = load_cookies(driver)
    
    # 访问美团H5移动端酒店搜索页
    driver.get("https://i.meituan.com/awp/h5/hotel/search/search.html")
    random_sleep(3, 4)

    # 检测是否需要登录
    check_and_wait_login(driver)

    # H5移动端 XPath 定位
    ADDRESS_ENTRY = '//*[@id="search"]/div/div[1]/div[2]'
    ADDRESS_INPUT = '//*[@id="search"]/div/div[3]/div[1]/div/label/input'
    KEYWORD_ENTRY = '//*[@id="search"]/div/div[1]/div[5]'
    KEYWORD_INPUT = '//*[@id="search"]/div/div[4]/div[1]/label/input'
    SEARCH_BUTTON = '//*[@id="search"]/div/div[1]/div[7]/button'
    
    # [0] 选择日期（如果指定了日期）
    _check_cancelled()
    if checkin_date or checkout_date:
        print("[0] 选择入住/离店日期")
        select_dates(driver, wait, checkin_date, checkout_date)
        random_sleep(1, 1.5)

    # [1] 点击地址搜索框入口
    _check_cancelled()
    print("[1] 点击地址搜索框入口")
    try:
        addr_entry = wait.until(EC.element_to_be_clickable((By.XPATH, ADDRESS_ENTRY)))
        addr_entry.click()
        random_sleep()
    except Exception as e:
        print(f"点击地址入口失败: {e}")
        driver.quit()
        return

    # [2] 在地址输入框输入并选择第一个建议
    _check_cancelled()
    print(f"[2] 输入地址关键词: {address_keyword}")
    try:
        addr_input = wait.until(EC.element_to_be_clickable((By.XPATH, ADDRESS_INPUT)))
        addr_input.click()
        addr_input.send_keys(Keys.CONTROL, 'a')
        addr_input.send_keys(Keys.DELETE)
        type_slowly(addr_input, address_keyword)
        random_sleep(1.2, 1.8)
        # 选择第一个建议
        ok = choose_first_suggestion(driver, [
            '//ul/li[1]',
            '//li[contains(@class,"item")][1]',
            '//div[contains(@class,"result-item")][1]'
        ])
        if not ok:
            choose_first_suggestion_by_keyboard(addr_input)
        random_sleep(1, 1.5)
    except Exception as e:
        print(f"输入地址失败: {e}")
        driver.quit()
        return

    # [3] 点击关键词入口
    _check_cancelled()
    print("[3] 点击关键词入口")
    try:
        kw_entry = wait.until(EC.element_to_be_clickable((By.XPATH, KEYWORD_ENTRY)))
        kw_entry.click()
        random_sleep()
    except Exception as e:
        print(f"点击关键词入口失败: {e}")
        driver.quit()
        return

    # [4] 在关键词输入框输入
    print(f"[4] 输入酒店关键词: {hotel_keyword}")
    try:
        kw_input = wait.until(EC.element_to_be_clickable((By.XPATH, KEYWORD_INPUT)))
        kw_input.click()
        kw_input.send_keys(Keys.CONTROL, 'a')
        kw_input.send_keys(Keys.DELETE)
        type_slowly(kw_input, hotel_keyword)
        random_sleep(1.2, 1.8)
    except Exception as e:
        print(f"输入关键词失败: {e}")
        driver.quit()
        return

    # [5] 点击关键词搜索建议的第一项
    print("[5] 点击关键词搜索建议")
    KEYWORD_FIRST_SUGGESTION = '//*[@id="search"]/div/div[4]/div[1]/div'
    try:
        first_suggestion = wait.until(EC.element_to_be_clickable((By.XPATH, KEYWORD_FIRST_SUGGESTION)))
        first_suggestion.click()
        random_sleep(1, 1.5)
    except Exception as e:
        print(f"点击关键词建议失败: {e}，尝试直接搜索")

    # [6] 点击搜索按钮
    print("[6] 点击搜索按钮")
    try:
        search_btn = wait.until(EC.element_to_be_clickable((By.XPATH, SEARCH_BUTTON)))
        search_btn.click()
        random_sleep(3, 4)
    except Exception as e:
        print(f"点击搜索按钮失败: {e}")
        driver.quit()
        return

    # 点击搜索结果中的第一个酒店（静默执行）
    FIRST_HOTEL = '//*[@id="app"]/div[5]/div[1]/div[1]/a/div[2]'
    try:
        hotel = wait.until(EC.element_to_be_clickable((By.XPATH, FIRST_HOTEL)))
        hotel.click()
        random_sleep(3, 4)
    except Exception as e:
        print(f"点击第一个酒店失败: {e}")
        driver.quit()
        return

    # 提取酒店名称
    hotel_name = hotel_keyword  # 默认使用酒店关键词
    HOTEL_NAME_XPATH = '//*[@id="main"]/section/section[1]/div[3]/div'
    try:
        hotel_name_element = driver.find_element(By.XPATH, HOTEL_NAME_XPATH)
        extracted_name = hotel_name_element.text.strip()
        if extracted_name:
            hotel_name = extracted_name
            print(f"  酒店名称: {hotel_name}")
        else:
            print(f"  未找到酒店名称，使用关键词: {hotel_keyword}")
    except Exception as e:
        print(f"  提取酒店名称失败: {e}，使用关键词: {hotel_keyword}")

    # 点击"查看全部房型"（静默执行）
    VIEW_ALL_ROOMS = '//div[contains(text(),"查看全部") or contains(text(),"全部房型")]'
    VIEW_ALL_ROOMS_ALT = '//span[contains(text(),"查看全部")]'
    try:
        view_all = click_first(driver, [VIEW_ALL_ROOMS, VIEW_ALL_ROOMS_ALT], timeout=8)
        if view_all:
            random_sleep(2, 3)
    except Exception as e:
        print(f"点击查看全部房型失败: {e}，继续获取当前显示的房型")

    # [7] 获取房间信息
    print("[7] 获取房间信息")
    room_data = get_room_info(driver)
    
    # 打印房间信息
    print("\n" + "="*50)
    print("房间信息汇总:")
    print("="*50)
    for i, room in enumerate(room_data, 1):
        print(f"{i}. {room['name']}")
        print(f"   价格: {room['price']}")
        print(f"   剩余: {room['remaining']}")
        if room.get('tags'):
            print(f"   标签: {room['tags']}")
        print("-"*30)
    
    print(f"\n共找到 {len(room_data)} 个房型")
    
    # [10] 保存到 JSON 文件
    # 计算实际使用的日期
    from datetime import timedelta
    actual_checkin = checkin_date if checkin_date else datetime.now().strftime("%Y-%m-%d")
    actual_checkout = checkout_date if checkout_date else (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    result = {
        "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "入住日期": actual_checkin,
        "离店日期": actual_checkout,
        "地址": address_keyword,
        "酒店关键词": hotel_keyword,
        "酒店名称": hotel_name,  # 添加酒店名称字段
        "房型总数": len(room_data),
        "房型列表": [
            {
                "房型名称": room['name'],
                "价格": room['price'],
                "剩余房间": room['remaining'],
                "备注": room.get('tags', '')
            }
            for room in room_data
        ]
    }
    
    json_file = os.path.join(SCRIPT_DIR, "meituan_hotel.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[10] 数据已保存到 {json_file}")
    
    # 保存到数据库
    if save_to_database:
        try:
            save_to_database("meituan", result)
            print("[11] 数据已保存到数据库")
        except Exception as e:
            print(f"[11] 数据库保存失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("[11] 警告: save_to_database未导入，跳过数据库保存")

    # 非交互模式：不要阻塞等待输入
    if os.getenv("NON_INTERACTIVE", "0") != "1":
        try:
            input("\n按回车后关闭浏览器...")
        finally:
            driver.quit()
    else:
        driver.quit()
    
    return room_data


def get_room_info(driver):
    """获取所有房间的名称、价格、剩余房间数（使用精确XPath）"""
    import re
    room_data = []
    random_sleep(1, 2)
    
    # 使用用户提供的 XPath 规律：//*[@id="main"]/section/section[7]/ul/li[n]
    ROOM_LIST_XPATH = '//*[@id="main"]/section/section[7]/ul/li'
    
    try:
        # 获取所有房型 li 元素
        room_elements = driver.find_elements(By.XPATH, ROOM_LIST_XPATH)
        print(f"  找到 {len(room_elements)} 个房型元素")
        
        for idx, room_el in enumerate(room_elements, 1):
            try:
                room_text = room_el.text
                lines = [l.strip() for l in room_text.split('\n') if l.strip()]
                
                name = ""
                price = ""
                remaining = ""
                tags = ""
                
                for line in lines:
                    # 房型名（包含"房"或"间"字）
                    if ('房' in line or '间' in line) and '¥' not in line and '剩' not in line and '预订' not in line and '满房' not in line:
                        if not name:
                            # 去掉"代理"标签
                            name = line.replace('代理', '').strip()
                    
                    # 价格
                    price_match = re.search(r'¥\s*(\d+)', line)
                    if price_match:
                        price = f"¥{price_match.group(1)}"
                    
                    # 剩余房间数（包括"满房"）
                    if '仅剩' in line or '剩' in line:
                        remaining = line
                    elif '满房' in line:
                        remaining = "满房"
                    
                    # 标签信息
                    if '不含早' in line or '无窗' in line or '不可取消' in line:
                        if not tags:
                            tags = line
                
                # 添加房型信息（即使满房也要添加）
                if name:
                    room_data.append({
                        'name': name,
                        'price': price or '暂无报价',
                        'remaining': remaining or '有房',
                        'tags': tags
                    })
                    print(f"    {idx}. {name} | {price or '暂无报价'} | {remaining or '有房'}")
                    
            except Exception as e:
                print(f"    解析第 {idx} 个房型时出错: {e}")
                continue
                
    except Exception as e:
        print(f"获取房型列表失败: {e}")
        # 备用方案：尝试其他选择器
        try:
            print("  尝试备用方案...")
            body_text = driver.find_element(By.TAG_NAME, 'body').text
            # 按满房或预订分割
            sections = re.split(r'(预订|满房)\n', body_text)
            # ... 简化处理
        except:
            pass
    
    return room_data


if __name__ == "__main__":
    print("=" * 50)
    print("  美团酒店房型数据爬取工具")
    print("=" * 50)
    
    # 检查是否有保存的 Cookies
    if not os.path.exists(COOKIES_FILE):
        print("\n⚠️  未找到登录态！请先运行登录工具:")
        print("     python meituan_cookies.py\n")
        input("按回车退出...")
        exit(1)
    
    print("\n✓ 发现已保存的登录态\n")
    
    print("输入格式说明:")
    print("  基本格式: 地址关键词,酒店关键词")
    print("  带日期格式: 地址关键词,酒店关键词,入住日期,离店日期")
    print("  日期格式: YYYY-MM-DD (如 2026-01-10)")
    print("  示例: 上海黄浦区,美利居,2026-01-10,2026-01-12")
    
    user_input = input("\n请输入查询条件（默认为 上海黄浦区,美利居）：").strip()
    if not user_input:
        user_input = "上海黄浦区,美利居"
    parts = [p.strip() for p in user_input.replace('，', ',').split(',')]
    while len(parts) < 2:
        parts.append(parts[-1] if parts else "上海黄浦区")
    
    address_keyword = parts[0]
    hotel_keyword = parts[1]
    checkin_date = parts[2] if len(parts) > 2 else None
    checkout_date = parts[3] if len(parts) > 3 else None
    
    # 验证日期格式
    if checkin_date:
        try:
            datetime.strptime(checkin_date, "%Y-%m-%d")
        except ValueError:
            print(f"入住日期格式错误: {checkin_date}，应为 YYYY-MM-DD")
            input("按回车退出...")
            exit(1)
    
    if checkout_date:
        try:
            datetime.strptime(checkout_date, "%Y-%m-%d")
        except ValueError:
            print(f"离店日期格式错误: {checkout_date}，应为 YYYY-MM-DD")
            input("按回车退出...")
            exit(1)
    
    print(f"\n搜索参数:")
    print(f"  地址: {address_keyword}")
    print(f"  酒店关键词: {hotel_keyword}")
    if checkin_date:
        print(f"  入住日期: {checkin_date}")
    if checkout_date:
        print(f"  离店日期: {checkout_date}")
    print("\n正在启动浏览器...")
    
    run(address_keyword, hotel_keyword, checkin_date, checkout_date)

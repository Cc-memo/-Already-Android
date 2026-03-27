# -*- coding: utf-8 -*-
"""携程 Cookies 管理工具"""

import pickle
import os
import platform
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    from webdriver_manager.chrome import ChromeDriverManager
    os.environ['WDM_LOCAL'] = '1'
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

if platform.system() == "Linux" and os.getenv("USE_WDM", "0") != "1":
    USE_WEBDRIVER_MANAGER = False

# 获取脚本所在目录，确保cookies文件保存在正确位置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(SCRIPT_DIR, "ctrip_cookies.pkl")


def setup_browser():
    """启动浏览器"""
    chrome_options = Options()
    chrome_bin = os.getenv("CHROME_BIN")
    if not chrome_bin:
        if platform.system() == "Linux":
            for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
                if os.path.exists(candidate):
                    chrome_bin = candidate
                    break
        elif platform.system() == "Windows":
            # Windows: 自动检测 Chrome 路径
            candidates = [
                os.path.join(os.getenv("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.getenv("PROGRAMFILES", ""), "Chromium", "Application", "chrome.exe"),
                os.path.join(os.getenv("LOCALAPPDATA", ""), "Chromium", "Application", "chrome.exe"),
            ]
            for candidate in candidates:
                if candidate and os.path.exists(candidate):
                    chrome_bin = candidate
                    break
    if chrome_bin:
        chrome_options.binary_location = chrome_bin
    
    headless_env = os.getenv("HEADLESS")
    if headless_env and headless_env.lower() in ("1", "true", "yes", "on"):
        chrome_options.add_argument("--headless=new")

    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # 优先使用项目下的 chromedriver.exe
    project_root = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    local_chromedriver = os.path.join(project_root, "bin", "chromedriver.exe")
    chrome_driver_path = os.getenv("CHROME_DRIVER_PATH")
    
    if chrome_driver_path and os.path.exists(chrome_driver_path):
        # 使用环境变量指定的路径
        service = Service(executable_path=chrome_driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    elif os.path.exists(local_chromedriver):
        # 使用项目下的 chromedriver.exe
        service = Service(executable_path=local_chromedriver)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    elif USE_WEBDRIVER_MANAGER:
        # 回退到 webdriver_manager
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except:
            # 最后回退到 Selenium Manager
            driver = webdriver.Chrome(options=chrome_options)
    else:
        # 回退到 Selenium Manager 自动管理
        driver = webdriver.Chrome(options=chrome_options)
    
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
    cookies = driver.get_cookies()
    with open(COOKIES_FILE, 'wb') as f:
        pickle.dump(cookies, f)
    print(f"✓ Cookies已保存到 {COOKIES_FILE}")
    print(f"  共 {len(cookies)} 个cookie")


def load_cookies(driver):
    """从文件加载cookies"""
    if not os.path.exists(COOKIES_FILE):
        return False
    
    with open(COOKIES_FILE, 'rb') as f:
        cookies = pickle.load(f)
    
    # 先访问携程域名
    driver.get("https://www.ctrip.com")
    time.sleep(1)
    
    # 加载cookies
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            pass
    
    print(f"✓ 已加载 {len(cookies)} 个cookie")
    return True


def cookies_exist():
    """检查cookies文件是否存在"""
    return os.path.exists(COOKIES_FILE)


def get_cookies_file_path():
    """获取cookies文件路径"""
    return COOKIES_FILE


def check_login_status(driver):
    """
    检查当前页面的登录状态
    
    返回:
        bool: True表示已登录，False表示未登录
    """
    try:
        page_text = driver.find_element(By.TAG_NAME, 'body').text
        # 携程登录后通常不会显示"登录"和"注册"按钮
        # 而是显示用户昵称或头像
        if '登录' in page_text and '注册' in page_text:
            return False
        return True
    except:
        return False


def login_and_save():
    """登录并保存cookies"""
    print("="*50)
    print("  携程登录工具（保存Cookies）")
    print("="*50)
    
    driver = setup_browser()
    
    try:
        # 先尝试加载已有的cookies
        if os.path.exists(COOKIES_FILE):
            print("\n发现已保存的Cookies，正在加载...")
            load_cookies(driver)
        
        print("\n正在打开携程网站...")
        driver.get("https://www.ctrip.com/")
        time.sleep(3)
        
        # 检查是否需要登录
        is_logged_in = check_login_status(driver)
        
        if not is_logged_in:
            print("\n⚠️  检测到未登录状态")
        else:
            print("\n✓ 检测到已登录状态")
        
        # 始终让用户确认，避免误判
        print("\n请在浏览器中查看：")
        print("  - 如果页面右上角显示'登录/注册'，请先完成登录")
        print("  - 如果已显示用户昵称或头像，说明已登录")
        print("  - 可以点击右上角'登录/注册'按钮进行登录")
        input("\n确认已登录后，按回车保存Cookies >>> ")
        
        # 保存cookies
        save_cookies(driver)
        print("\n✅ Cookies已保存！")
        
        input("\n按回车关闭浏览器...")
        
    finally:
        driver.quit()


def test_cookies():
    """测试保存的cookies是否有效"""
    print("="*50)
    print("  测试保存的Cookies")
    print("="*50)
    
    if not os.path.exists(COOKIES_FILE):
        print("\n❌ 未找到cookies文件")
        print("   请先运行登录工具: python ctrip_cookies.py")
        return False
    
    driver = setup_browser()
    
    try:
        print("\n正在加载cookies...")
        load_cookies(driver)
        
        print("正在访问携程网站...")
        driver.get("https://www.ctrip.com/")
        time.sleep(3)
        
        is_logged_in = check_login_status(driver)
        
        if not is_logged_in:
            print("\n❌ Cookies已失效")
            print("   请重新运行登录工具")
            return False
        else:
            print("\n✅ Cookies有效！登录成功")
            return True
        
    finally:
        input("\n按回车关闭浏览器...")
        driver.quit()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_cookies()
    else:
        login_and_save()


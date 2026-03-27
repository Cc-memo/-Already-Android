# -*- coding: utf-8 -*-
"""美团H5 Cookies 管理工具"""

import pickle
import os
import platform
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# 获取脚本所在目录，确保cookies文件保存在正确位置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(SCRIPT_DIR, "meituan_h5_cookies.pkl")

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
    chrome_options.add_argument('--window-size=430,900')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
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
    else:
        # 回退到 Selenium Manager 自动管理（可能失败）
        driver = webdriver.Chrome(options=chrome_options)
    
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
    
    # 先访问域名
    driver.get("https://i.meituan.com")
    time.sleep(1)
    
    # 加载cookies
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            pass
    
    print(f"✓ 已加载 {len(cookies)} 个cookie")
    return True

def login_and_save():
    """登录并保存cookies"""
    print("="*50)
    print("  美团H5登录工具（保存Cookies）")
    print("="*50)
    
    driver = setup_browser()
    
    try:
        # 先尝试加载已有的cookies
        if os.path.exists(COOKIES_FILE):
            print("\n发现已保存的Cookies，正在加载...")
            load_cookies(driver)
        
        print("\n正在打开美团H5页面...")
        driver.get("https://i.meituan.com/awp/h5/hotel/search/search.html")
        time.sleep(3)
        
        page_text = driver.find_element(By.TAG_NAME, 'body').text
        
        # 检查是否需要登录（页面中有"登录"和"注册"按钮）
        needs_login = '登录' in page_text and '注册' in page_text
        
        if needs_login:
            print("\n⚠️  检测到未登录状态")
        else:
            print("\n✓ 检测到已登录状态")
        
        # 始终让用户确认，避免误判
        print("\n请在浏览器中查看：")
        print("  - 如果页面底部显示'登录/注册'，请先完成登录")
        print("  - 如果已显示用户信息，说明已登录")
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
        print("   请先运行登录工具: python meituan_cookies.py")
        return
    
    driver = setup_browser()
    
    try:
        print("\n正在加载cookies...")
        load_cookies(driver)
        
        print("正在访问页面...")
        driver.get("https://i.meituan.com/awp/h5/hotel/search/search.html")
        time.sleep(3)
        
        page_text = driver.find_element(By.TAG_NAME, 'body').text
        
        if '登录' in page_text and '注册' in page_text:
            print("\n❌ Cookies已失效")
            print("   请重新运行登录工具")
        else:
            print("\n✅ Cookies有效！登录成功")
        
        input("\n按回车关闭浏览器...")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_cookies()
    else:
        login_and_save()


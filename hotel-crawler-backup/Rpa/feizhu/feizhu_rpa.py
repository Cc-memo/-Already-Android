# -*- coding: utf-8 -*-
"""
飞猪酒店房型数据爬取工具

使用本地Chromium用户数据目录 + Cookies文件保持登录态
"""

import random
import time
import json
import pickle
import os
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
FEIZHU_HOME = "https://www.fliggy.com/?_er_static=true"


def setup_browser(use_local_profile=True):
    """
    配置并启动Chromium浏览器
    """
    chrome_options = Options()

    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin and not os.path.exists(chrome_bin):
        print(f"  ⚠️  CHROME_BIN 指向的文件不存在: {chrome_bin}")
        chrome_bin = None
    if not chrome_bin and os.name == "nt":
        candidates = [
            os.path.join(os.getenv("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.getenv("PROGRAMFILES", ""), "Chromium", "Application", "chrome.exe"),
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Chromium", "Application", "chrome.exe"),
            r"D:\yingyong\tool\chrome-win\chrome.exe",
        ]
        for c in candidates:
            if c and os.path.exists(c):
                chrome_bin = c
                break
    if chrome_bin and os.path.exists(chrome_bin):
        chrome_options.binary_location = chrome_bin
        print(f"  使用浏览器: {chrome_bin}")
    else:
        chrome_bin = None
        print("  使用系统默认 Chrome（未指定 CHROME_BIN）")

    chrome_driver_path = os.getenv("CHROME_DRIVER_PATH")
    if chrome_driver_path and not os.path.exists(chrome_driver_path):
        print(f"  ⚠️  CHROME_DRIVER_PATH 指向的文件不存在: {chrome_driver_path}")
        chrome_driver_path = None
    is_chromium = bool(chrome_bin) and any(k in chrome_bin.lower() for k in ("chromium", "chrome-win"))
    
    if use_local_profile:
        # 使用Chromium的用户数据目录（与携程保持一致）
        user_data_dir = r'C:\Users\武sir\AppData\Local\Chromium\User Data'
        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
        chrome_options.add_argument('--profile-directory=Default')
        print("  使用本地Chromium用户数据（含登录态）")
    
    # 防止崩溃和检测的参数
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # 抑制警告信息
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # 启动浏览器
    try:
        if chrome_driver_path:
            print("  使用 CHROME_DRIVER_PATH 指定的 ChromeDriver")
            service = Service(executable_path=chrome_driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        elif USE_WEBDRIVER_MANAGER:
            print("  使用 webdriver-manager 管理 ChromeDriver")
            service = Service(
                ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
                if is_chromium
                else ChromeDriverManager().install()
            )
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(options=chrome_options)
        print("  浏览器启动成功")
    except Exception as e:
        print(f"\n❌ 浏览器启动失败: {e}")
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
    except:
        pass
    
    return driver


def random_sleep(min_s=0.8, max_s=1.6):
    """随机等待，模拟人工操作"""
    time.sleep(random.uniform(min_s, max_s))


def type_slowly(element, text):
    """模拟人工输入"""
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(0.05, 0.12))


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
        else:
            cookies = cookie_data.get('cookies', [])
        
        # 加载cookies
        loaded_count = 0
        for cookie in cookies:
            try:
                if 'expiry' in cookie:
                    cookie['expiry'] = int(cookie['expiry'])
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


def select_dates(driver, check_in_days=1, nights=1):
    """
    选择入住和离店日期
    
    参数:
        driver: WebDriver实例
        check_in_days: 从今天起第几天入住（1表示明天）
        nights: 住几晚
    
    飞猪日历特点：
    - 双月显示（当前月+下个月）
    - 结构：td元素，包含日期数字
    - 可能有节日标记（平安夜、圣诞等）
    """
    print(f"[选择日期] 入住：今天+{check_in_days}天，住{nights}晚")
    
    try:
        # 计算日期
        today = datetime.now()
        check_in_date = today + timedelta(days=check_in_days)
        check_out_date = check_in_date + timedelta(days=nights)
        
        print(f"  入住日期: {check_in_date.strftime('%Y-%m-%d')} ({check_in_date.day}日)")
        print(f"  离店日期: {check_out_date.strftime('%Y-%m-%d')} ({check_out_date.day}日)")
        
        # 点击日期选择器区域（显示日历）
        date_picker_xpaths = [
            '//div[contains(@class,"domestic_RangePicker_show")]',
            '//div[contains(@class,"domestic_RangePicker_Div")]//div[contains(@class,"CustomizedCalendar_Div")]',
            '//div[contains(@class,"ant-picker-range")]',
            '//input[@placeholder="开始日期"]/..',
        ]
        
        clicked = False
        for xpath in date_picker_xpaths:
            try:
                date_picker = driver.find_element(By.XPATH, xpath)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_picker)
                random_sleep(0.3, 0.5)
                date_picker.click()
                print("  已点击日期选择器，等待日历弹出...")
                clicked = True
                random_sleep(1.5, 2)
                break
            except Exception as e:
                continue
        
        if not clicked:
            print("  ⚠️ 未找到日期选择器，尝试直接选择日期...")
            random_sleep(1, 1.5)
        
        # === 选择入住日期 ===
        # 飞猪日历结构：<td><div>日期数字</div></td>
        # 需要考虑：可能有两个月份显示，需要选择正确月份的日期
        
        check_in_month = check_in_date.month
        check_in_day = check_in_date.day
        check_out_month = check_out_date.month
        check_out_day = check_out_date.day
        
        selected_checkin = False
        
        # 策略1：通过月份标题定位到正确的月份，然后选择日期
        try:
            # 查找所有月份标题（如"2025年 12月"）
            month_headers = driver.find_elements(By.XPATH, 
                f'//div[contains(text(),"{check_in_date.year}年") and contains(text(),"{check_in_month}月")]')
            
            if month_headers:
                month_header = month_headers[0]
                print(f"  找到入住月份: {check_in_date.year}年{check_in_month}月")
                
                # 在该月份下查找对应的日期单元格
                # 使用following-sibling或following来定位后续的表格
                parent_calendar = month_header.find_element(By.XPATH, './ancestor::div[contains(@class,"CustomizedCalendar_Div") or contains(@class,"ant-picker-panel")]')
                
                # 在这个日历容器内查找日期
                date_cells = parent_calendar.find_elements(By.XPATH, 
                    f'.//td[not(contains(@class,"ant-picker-cell-disabled"))]//div[text()="{check_in_day}"]')
                
                for cell in date_cells:
                    if cell.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell)
                        random_sleep(0.3, 0.5)
                        cell.click()
                        print(f"  ✓ 已选择入住日期: {check_in_month}月{check_in_day}日")
                        selected_checkin = True
                        random_sleep(0.8, 1.2)
                        break
        except Exception as e:
            print(f"  策略1失败: {e}")
        
        # 策略2：使用XPath直接查找所有可点击的日期，按顺序尝试
        if not selected_checkin:
            try:
                all_date_cells = driver.find_elements(By.XPATH, 
                    f'//td[not(contains(@class,"ant-picker-cell-disabled")) and contains(@class,"ant-picker-cell")]//div[text()="{check_in_day}"]')
                
                print(f"  找到 {len(all_date_cells)} 个{check_in_day}日的日期单元格")
                
                # 如果当前月份还没过，选第一个；如果过了，选第二个（下个月）
                for idx, cell in enumerate(all_date_cells):
                    if cell.is_displayed():
                        # 检查这个日期是否在正确的月份
                        # 简单判断：如果入住日期在当前月，选第一个；否则选第二个
                        if check_in_month == today.month:
                            target_idx = 0
                        elif check_in_month == (today.month % 12) + 1:
                            target_idx = 1 if len(all_date_cells) > 1 else 0
                        else:
                            target_idx = idx
                        
                        if idx == target_idx:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell)
                            random_sleep(0.3, 0.5)
                            cell.click()
                            print(f"  ✓ 已选择入住日期: {check_in_day}日")
                            selected_checkin = True
                            random_sleep(0.8, 1.2)
                            break
            except Exception as e:
                print(f"  策略2失败: {e}")
        
        if not selected_checkin:
            print("  ⚠️ 未能自动选择入住日期，可能需要手动选择")
            print("     提示：请在浏览器中点击入住日期")
            random_sleep(3, 5)  # 给用户时间手动选择
        
        # === 选择离店日期 ===
        selected_checkout = False
        
        # 同样的策略选择离店日期
        try:
            # 先尝试找到离店月份标题
            month_headers = driver.find_elements(By.XPATH, 
                f'//div[contains(text(),"{check_out_date.year}年") and contains(text(),"{check_out_month}月")]')
            
            if month_headers:
                # 可能有两个月份，选择正确的那个
                for month_header in month_headers:
                    try:
                        parent_calendar = month_header.find_element(By.XPATH, 
                            './ancestor::div[contains(@class,"CustomizedCalendar_Div") or contains(@class,"ant-picker-panel")]')
                        
                        date_cells = parent_calendar.find_elements(By.XPATH, 
                            f'.//td[not(contains(@class,"ant-picker-cell-disabled"))]//div[text()="{check_out_day}"]')
                        
                        for cell in date_cells:
                            if cell.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell)
                                random_sleep(0.3, 0.5)
                                cell.click()
                                print(f"  ✓ 已选择离店日期: {check_out_month}月{check_out_day}日")
                                selected_checkout = True
                                random_sleep(0.8, 1.2)
                                break
                        if selected_checkout:
                            break
                    except:
                        continue
        except Exception as e:
            print(f"  离店日期策略1失败: {e}")
        
        # 备用策略
        if not selected_checkout:
            try:
                all_date_cells = driver.find_elements(By.XPATH, 
                    f'//td[not(contains(@class,"ant-picker-cell-disabled")) and contains(@class,"ant-picker-cell")]//div[text()="{check_out_day}"]')
                
                for idx, cell in enumerate(all_date_cells):
                    if cell.is_displayed():
                        # 离店日期通常在入住日期之后，所以选择后面的日期
                        if check_out_month == check_in_month:
                            # 同月，选第一个
                            target_idx = 0
                        else:
                            # 跨月，选第二个
                            target_idx = 1 if len(all_date_cells) > 1 else 0
                        
                        if idx == target_idx or len(all_date_cells) == 1:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell)
                            random_sleep(0.3, 0.5)
                            cell.click()
                            print(f"  ✓ 已选择离店日期: {check_out_day}日")
                            selected_checkout = True
                            random_sleep(0.8, 1.2)
                            break
            except Exception as e:
                print(f"  离店日期策略2失败: {e}")
        
        if not selected_checkout:
            print("  ⚠️ 未能自动选择离店日期，可能需要手动选择")
            print("     提示：请在浏览器中点击离店日期")
            random_sleep(3, 5)  # 给用户时间手动选择
        
        return selected_checkin and selected_checkout
        
    except Exception as e:
        print(f"  选择日期出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def run(address_keyword, hotel_keyword, check_in_days=1, nights=1):
    """
    主运行函数
    
    参数:
        address_keyword: 地址关键词（如"杭州"）
        hotel_keyword: 酒店关键词（如"西湖"）
        check_in_days: 从今天起第几天入住（默认1，即明天）
        nights: 住几晚（默认1晚）
    """
    driver = setup_browser(use_local_profile=True)
    wait = WebDriverWait(driver, 15)
    
    try:
        # [步骤1] 访问飞猪首页
        print("[步骤1] 访问飞猪首页...")
        driver.get(FEIZHU_HOME)
        random_sleep(2, 3)
        
        # 尝试加载Cookies
        if os.path.exists(COOKIES_FILE):
            print("  发现Cookies文件，正在加载...")
            load_cookies(driver)
            driver.refresh()
            random_sleep(2, 3)
            # 加载Cookies后需要点击页面激活
            try:
                body = driver.find_element(By.TAG_NAME, 'body')
                body.click()
                print("  已点击页面激活")
                random_sleep(0.5, 1)
            except:
                pass
        
        # [步骤2] 点击酒店菜单
        print("[步骤2] 点击酒店菜单...")
        hotel_menu_xpath = '//*[@id="fly-menu"]/li[2]'
        
        try:
            hotel_menu = wait.until(
                EC.element_to_be_clickable((By.XPATH, hotel_menu_xpath))
            )
            hotel_menu.click()
            print("  已点击酒店菜单")
            random_sleep(2, 3)  # 等待页面切换
        except Exception as e:
            print(f"  点击酒店菜单失败: {e}")
            print("  尝试继续...")
        
        # [步骤3] 输入目的地地址
        # 注意：飞猪只支持城市名（如"上海"），不支持具体区域（如"上海黄浦区"）
        # 如果输入包含区域，自动提取城市名
        city_name = address_keyword
        
        # 提取城市名（去除区、县等后缀，只保留主要城市名）
        # 常见城市列表（用于判断）
        major_cities = ['北京', '上海', '广州', '深圳', '杭州', '南京', '成都', '重庆', 
                       '武汉', '西安', '苏州', '天津', '长沙', '郑州', '青岛', '大连',
                       '厦门', '昆明', '无锡', '宁波', '佛山', '东莞', '合肥', '福州']
        
        # 如果输入包含"区"或"县"，尝试提取城市名
        if '区' in address_keyword or '县' in address_keyword:
            # 方法1: 按"区"或"县"分割，取第一部分
            parts_by_qu = address_keyword.split('区')[0] if '区' in address_keyword else address_keyword
            parts_by_xian = parts_by_qu.split('县')[0] if '县' in parts_by_qu else parts_by_qu
            
            # 方法2: 检查是否是已知城市名
            for city in major_cities:
                if address_keyword.startswith(city):
                    city_name = city
                    break
            else:
                # 如果不在已知城市列表中，使用分割方法
                city_name = parts_by_xian
            
            if city_name != address_keyword:
                print(f"  提示: 自动提取城市名 '{city_name}' (原输入: {address_keyword})")
        
        print(f"[步骤3] 输入目的地: {city_name}")
        
        try:
            # 定位输入框（使用ID或XPath）
            address_input = None
            try:
                address_input = wait.until(EC.element_to_be_clickable((By.ID, 'form_depCity')))
            except:
                address_input = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="J_HomeContainer"]/div/div[1]/div[1]/div[1]/div/div/div[2]/div[1]/div[2]/input')))
            
            # 点击并清空输入框
            address_input.click()
            random_sleep(0.5, 0.8)
            address_input.clear()
            address_input.send_keys(Keys.CONTROL + 'a')
            address_input.send_keys(Keys.DELETE)
            random_sleep(0.3, 0.5)
            
            # 输入城市名
            type_slowly(address_input, city_name)
            random_sleep(1.5, 2)
            
            print(f"  已输入: {city_name}")
            print("  等待下拉建议出现...")
            
            # 直接查找包含城市名的第一个可点击建议项
            # 建议项可能显示为"XX市,XX"格式，如"上海市,上海"
            suggestion_xpaths = [
                f'//li[contains(text(),"{city_name}")][1]',
                f'//div[contains(text(),"{city_name}")][1]',
                f'//span[contains(text(),"{city_name}")][1]',
                '//*[@id="form_depCity_list"]//li[1]',
                '//ul[contains(@class,"ant-select-dropdown")]//li[1]',
            ]
            
            clicked = False
            for xpath in suggestion_xpaths:
                try:
                    suggestion = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    if suggestion.is_displayed():
                        suggestion.click()
                        text = suggestion.text[:30] if suggestion.text else "未知"
                        print(f"  ✓ 已点击建议项: {text}")
                        clicked = True
                        random_sleep(0.8, 1.2)
                        break
                except:
                    continue
            
            if not clicked:
                print("  ⚠️ 未能自动点击建议，请手动点击下拉建议的第一项")
                random_sleep(3, 5)
            
        except Exception as e:
            print(f"  输入目的地失败: {e}")
        
        random_sleep(1, 1.5)
        
        # [步骤4] 选择日期
        print(f"[步骤4] 选择入住和离店日期")
        select_dates(driver, check_in_days, nights)
        random_sleep(1, 1.5)
        
        # [步骤5] 输入酒店关键词
        print(f"[步骤5] 输入酒店关键词: {hotel_keyword}")
        
        keyword_xpath = '//*[@id="J_HomeContainer"]/div/div[1]/div[1]/div[1]/div/div/div[2]/div[2]/input'
        
        try:
            keyword_input = wait.until(
                EC.element_to_be_clickable((By.XPATH, keyword_xpath))
            )
            keyword_input.click()
            random_sleep(0.3, 0.5)
            
            # 清空并输入关键词
            keyword_input.send_keys(Keys.CONTROL + 'a')
            keyword_input.send_keys(Keys.DELETE)
            random_sleep(0.2, 0.3)
            
            type_slowly(keyword_input, hotel_keyword)
            print(f"  已输入关键词: {hotel_keyword}")
            random_sleep(1.5, 2)
            
            # 点击第一个建议项
            print("  等待关键词建议出现...")
            suggestion_xpaths = [
                f'//li[contains(text(),"{hotel_keyword}")][1]',
                f'//div[contains(text(),"{hotel_keyword}")][1]',
                f'//span[contains(text(),"{hotel_keyword}")][1]',
                '//ul[contains(@class,"ant-select-dropdown")]//li[1]',
                '//div[contains(@class,"suggestion")]//li[1]',
            ]
            
            clicked = False
            for xpath in suggestion_xpaths:
                try:
                    suggestion = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    if suggestion.is_displayed():
                        suggestion.click()
                        text = suggestion.text[:50] if suggestion.text else "未知"
                        print(f"  ✓ 已点击第一个建议项: {text}")
                        clicked = True
                        random_sleep(0.8, 1.2)
                        break
                except:
                    continue
            
            if not clicked:
                print("  ⚠️ 未能自动点击建议，请手动点击下拉建议的第一项")
                random_sleep(3, 5)
            
        except Exception as e:
            print(f"  输入关键词失败: {e}")
        
        # [步骤6] 点击搜索按钮
        print("[步骤6] 点击搜索按钮...")
        
        search_xpath = '//*[@id="J_HomeContainer"]/div/div[1]/div[1]/div[1]/div/div/div[2]/div[4]'
        
        # 记录当前窗口数量
        original_windows = driver.window_handles
        
        try:
            search_btn = wait.until(
                EC.element_to_be_clickable((By.XPATH, search_xpath))
            )
            search_btn.click()
            print("  已点击搜索按钮...")
        except Exception as e:
            print(f"  点击搜索按钮失败: {e}")
            try:
                search_btn = driver.find_element(By.XPATH, '//button[contains(text(),"搜索")]')
                if search_btn.is_displayed():
                    search_btn.click()
                    print("  已使用备用方式点击搜索按钮")
            except:
                print("  ⚠️ 未能点击搜索按钮，请手动点击")
                random_sleep(3, 5)
        
        # [步骤7] 等待新标签页打开并切换
        print("[步骤7] 等待搜索结果页面...")
        
        # 等待新标签页打开
        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.window_handles) > len(original_windows)
            )
            # 切换到新标签页
            new_window = [w for w in driver.window_handles if w not in original_windows][0]
            driver.switch_to.window(new_window)
            print(f"  已切换到新标签页")
        except:
            print("  未检测到新标签页，检查当前页面...")
        
        # 等待搜索结果页面加载
        random_sleep(3, 5)
        print(f"  当前页面: {driver.current_url[:80]}...")
        
        # 等待搜索结果列表容器出现
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="J_List"]'))
            )
            print("  搜索结果列表已加载")
        except:
            print("  ⚠️ 未找到搜索结果列表，继续尝试...")
        
        random_sleep(2, 3)
        
        # [步骤8] 点击"查看详情"按钮进入酒店详情页
        print("[步骤8] 点击第一个酒店的'查看详情'...")
        
        # 记录当前窗口
        search_windows = driver.window_handles
        
        # 点击"查看详情"按钮
        detail_btn_xpaths = [
            '//*[@id="J_List"]/div[1]//a[contains(text(),"查看详情")]',
            '//*[@id="J_List"]/div[1]//button[contains(text(),"查看详情")]',
            '//a[contains(text(),"查看详情")][1]',
            '//button[contains(text(),"查看详情")][1]',
        ]
        
        clicked = False
        for xpath in detail_btn_xpaths:
            try:
                detail_btn = wait.until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                print(f"  找到'查看详情'按钮")
                detail_btn.click()
                clicked = True
                random_sleep(3, 5)
                break
            except:
                continue
        
        if not clicked:
            raise Exception("无法点击'查看详情'按钮")
        
        # 等待新标签页打开（酒店详情页）
        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.window_handles) > len(search_windows)
            )
            # 切换到最新的标签页（酒店详情页）
            driver.switch_to.window(driver.window_handles[-1])
            print(f"  已切换到酒店详情页")
            print(f"  当前页面: {driver.current_url[:60]}...")
        except:
            print("  未检测到新标签页，使用当前页面...")
        
        random_sleep(3, 5)
        
        # [步骤9] 逐个点击报价列表按钮并获取房间信息
        print("[步骤9] 逐个点击报价列表按钮并获取房间信息...")
        room_data = get_room_info(driver)
        
        if room_data:
            # 打印房间信息
            print_summary(room_data)
            
            # 保存到JSON
            result = {
                "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "地址": address_keyword,
                "酒店关键词": hotel_keyword,
                "入住日期": (datetime.now() + timedelta(days=check_in_days)).strftime("%Y-%m-%d"),
                "离店日期": (datetime.now() + timedelta(days=check_in_days + nights)).strftime("%Y-%m-%d"),
                "房型总数": len(room_data),
                "房型列表": room_data
            }
            
            json_file = os.path.join(SCRIPT_DIR, "feizhu_hotel.json")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n数据已保存到: {json_file}")
        
        input("\n按回车键关闭浏览器...")
        return room_data
        
    except Exception as e:
        print(f"\n程序出错: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键关闭浏览器...")
    
    finally:
        driver.quit()


def click_all_quote_buttons(driver):
    """
    点击所有报价列表按钮
    报价列表按钮的XPath模式：
    - 第一个：//*[@id="J_RoomList"]/div[1]/div/div[1]/div[1]/div/button
    - 第二个：//*[@id="J_RoomList"]/div[2]/div/div/div[1]/div/button
    - 后续：//*[@id="J_RoomList"]/div[n]/div/div/div[1]/div/button
    """
    try:
        # 等待房型列表容器出现
        room_list = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="J_RoomList"]'))
        )
        print("  找到房型列表容器")
        
        # 查找所有房型div
        room_divs = driver.find_elements(By.XPATH, '//*[@id="J_RoomList"]/div')
        print(f"  找到 {len(room_divs)} 个房型")
        
        clicked_count = 0
        
        # 遍历每个房型，点击报价列表按钮
        for idx in range(1, len(room_divs) + 1):
            try:
                # 尝试多种XPath模式
                quote_button_xpaths = [
                    f'//*[@id="J_RoomList"]/div[{idx}]/div/div[1]/div[1]/div/button',  # 第一个房型的格式
                    f'//*[@id="J_RoomList"]/div[{idx}]/div/div/div[1]/div/button',      # 后续房型的格式
                    f'//*[@id="J_RoomList"]/div[{idx}]//button[contains(text(),"报价列表")]',  # 包含"报价列表"文字的按钮
                ]
                
                clicked = False
                for xpath in quote_button_xpaths:
                    try:
                        button = driver.find_element(By.XPATH, xpath)
                        if button.is_displayed() and '报价列表' in button.text:
                            # 滚动到按钮位置
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                            random_sleep(0.3, 0.5)
                            button.click()
                            clicked_count += 1
                            print(f"    ✓ 已点击第 {idx} 个房型的报价列表按钮")
                            clicked = True
                            random_sleep(0.5, 1)  # 等待报价列表展开
                            break
                    except:
                        continue
                
                if not clicked:
                    print(f"    ⚠️ 第 {idx} 个房型未找到报价列表按钮（可能已全部订完）")
                    
            except Exception as e:
                print(f"    处理第 {idx} 个房型时出错: {e}")
                continue
        
        print(f"  共点击了 {clicked_count} 个报价列表按钮")
        
    except Exception as e:
        print(f"  点击报价列表按钮失败: {e}")


def get_room_info(driver):
    """
    从酒店详情页获取房间信息
    提取每个房型的名称、卖家和价格
    """
    random_sleep(2, 3)
    
    room_data = []
    
    try:
        # 等待房型列表容器
        room_list = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="J_RoomList"]'))
        )
        
        # 获取所有房型div
        room_divs = driver.find_elements(By.XPATH, '//*[@id="J_RoomList"]/div')
        print(f"  找到 {len(room_divs)} 个房型")
        
        # 解析每个房型
        for idx in range(1, len(room_divs) + 1):
            try:
                # 获取房型容器
                room_xpath = f'//*[@id="J_RoomList"]/div[{idx}]'
                room_div = driver.find_element(By.XPATH, room_xpath)
                
                # 滚动到房型位置，确保可见
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", room_div)
                random_sleep(0.5, 1)
                
                # === 提取房间名称（优先使用指定的XPath） ===
                room_name = ""
                
                # 优先使用用户提供的精确XPath
                precise_name_xpath = f'{room_xpath}/div/div/div[3]/div/p[1]/span'
                try:
                    name_el = room_div.find_element(By.XPATH, precise_name_xpath)
                    name_text = name_el.text.strip()
                    if name_text:
                        # 清理名称：移除换行符、多余空格，只保留第一行
                        name_text = name_text.split('\n')[0].strip()
                        # 如果名称太长，尝试提取关键部分
                        if len(name_text) > 30:
                            # 尝试提取包含"间"或"房"的简短部分
                            short_match = re.search(r'([^\n]{2,20}(?:间|房))', name_text)
                            if short_match:
                                name_text = short_match.group(1).strip()
                        room_name = name_text
                except:
                    pass
                
                # 如果精确XPath没找到，尝试其他方法
                if not room_name:
                    room_name_xpaths = [
                        f'{room_xpath}/div/div/div[3]/div/p[1]/span',  # 再次尝试（可能路径略有不同）
                        f'{room_xpath}//p[1]/span',
                        f'{room_xpath}//span[contains(text(),"间") or contains(text(),"房")][1]',
                        f'{room_xpath}//h3',
                        f'{room_xpath}//h4',
                        f'{room_xpath}//div[contains(@class,"room-name")]',
                    ]
                    
                    for name_xpath in room_name_xpaths:
                        try:
                            name_el = room_div.find_element(By.XPATH, name_xpath)
                            name_text = name_el.text.strip()
                            # 清理名称：移除换行符，只保留第一行
                            name_text = name_text.split('\n')[0].strip()
                            # 过滤掉太短或不符合房间名称格式的文本
                            if name_text and len(name_text) > 2 and len(name_text) <= 30 and ('间' in name_text or '房' in name_text):
                                room_name = name_text
                                break
                        except:
                            continue
                
                # 获取房型div的完整文本，用于提取所有信息
                room_text = room_div.text
                
                # 如果还没找到房间名称，尝试从文本中提取（但只取简短名称）
                if not room_name:
                    # 尝试匹配房间名称模式（如"优选单人间"、"商务静谧三人间"）
                    # 优先匹配较短的名称
                    name_patterns = [
                        r'([^\n]{2,20}(?:间|房))',  # 2-20个字符，以"间"或"房"结尾
                        r'([^\n]+(?:间|房))',  # 备用：任意长度
                    ]
                    
                    for pattern in name_patterns:
                        name_match = re.search(pattern, room_text)
                        if name_match:
                            candidate = name_match.group(1).strip()
                            # 清理：移除换行符，只保留第一行
                            candidate = candidate.split('\n')[0].strip()
                            # 只保留较短的名称（避免包含太多额外信息）
                            if len(candidate) <= 30:
                                room_name = candidate
                                break
                
                # 最终清理：确保名称干净简洁
                if room_name:
                    # 移除换行符和多余空格
                    room_name = ' '.join(room_name.split())
                    # 如果名称仍然太长，尝试提取关键部分
                    if len(room_name) > 30:
                        # 尝试提取前30个字符，但确保以"间"或"房"结尾
                        match = re.search(r'^(.{1,30}(?:间|房))', room_name)
                        if match:
                            room_name = match.group(1)
                        else:
                            # 如果找不到，就截取前30个字符
                            room_name = room_name[:30]
                
                # === 提取房间详细信息（床型、面积、楼层、窗型） ===
                bed_type = ""
                area = ""
                floor = ""
                window_type = ""
                start_price = ""
                
                # 床型
                bed_match = re.search(r'床型[：:]\s*([^\n]+)', room_text)
                if bed_match:
                    bed_type = bed_match.group(1).strip()
                else:
                    # 备用：直接匹配床型描述
                    bed_match = re.search(r'(\d+张[^\n]+床[^\n]*)', room_text)
                    if bed_match:
                        bed_type = bed_match.group(1).strip()
                
                # 面积
                area_match = re.search(r'面积[：:]\s*([^\n]+)', room_text)
                if area_match:
                    area = area_match.group(1).strip()
                else:
                    # 备用：匹配面积模式（如"15-18㎡"）
                    area_match = re.search(r'(\d+[-\d]*\s*[㎡m²])', room_text)
                    if area_match:
                        area = area_match.group(1).strip()
                
                # 楼层
                floor_match = re.search(r'楼层[：:]\s*([^\n]+)', room_text)
                if floor_match:
                    floor = floor_match.group(1).strip()
                else:
                    # 备用：匹配楼层模式（如"1-4"）
                    floor_match = re.search(r'楼层[：:]\s*(\d+[-\d]*)', room_text)
                    if floor_match:
                        floor = floor_match.group(1).strip()
                
                # 窗型
                window_match = re.search(r'窗型[：:]\s*([^\n]+)', room_text)
                if window_match:
                    window_type = window_match.group(1).strip()
                else:
                    # 备用：匹配窗型（如"无窗"、"暗窗"）
                    window_match = re.search(r'(无窗|暗窗|有窗)', room_text)
                    if window_match:
                        window_type = window_match.group(1).strip()
                
                # 起始价格
                price_match = re.search(r'[¥￥]\s*(\d+)\s*起', room_text)
                if price_match:
                    start_price = f"¥{price_match.group(1)}"
                else:
                    # 备用：匹配价格模式
                    price_match = re.search(r'[¥￥]\s*(\d+)', room_text)
                    if price_match:
                        start_price = f"¥{price_match.group(1)}"
                
                # === 检测"全部订完"状态 ===
                is_all_booked = False
                try:
                    # 查找"全部订完"按钮或文本
                    all_booked_selectors = [
                        f'{room_xpath}//button[contains(text(),"全部订完")]',
                        f'{room_xpath}//div[contains(text(),"全部订完")]',
                        f'{room_xpath}//span[contains(text(),"全部订完")]',
                    ]
                    for selector in all_booked_selectors:
                        try:
                            booked_el = room_div.find_element(By.XPATH, selector)
                            if booked_el.is_displayed():
                                is_all_booked = True
                                break
                        except:
                            continue
                    
                    # 也从文本中检测
                    if not is_all_booked and '全部订完' in room_text:
                        is_all_booked = True
                except:
                    pass
                
                # === 如果有"报价列表"按钮，点击它展开报价 ===
                if not is_all_booked:
                    try:
                        # 查找"报价列表"按钮
                        quote_button_xpaths = [
                            f'{room_xpath}/div/div[1]/div[1]/div/button',
                            f'{room_xpath}/div/div/div[1]/div/button',
                            f'{room_xpath}//button[contains(text(),"报价列表")]',
                        ]
                        
                        quote_button_clicked = False
                        for button_xpath in quote_button_xpaths:
                            try:
                                quote_button = driver.find_element(By.XPATH, button_xpath)
                                if quote_button.is_displayed() and '报价列表' in quote_button.text:
                                    # 滚动到按钮位置
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", quote_button)
                                    random_sleep(0.3, 0.5)
                                    quote_button.click()
                                    print(f"    ✓ 已点击第 {idx} 个房型的报价列表按钮")
                                    quote_button_clicked = True
                                    random_sleep(1, 1.5)  # 等待报价列表展开
                                    break
                            except:
                                continue
                        
                        if not quote_button_clicked:
                            print(f"    ⚠️ 第 {idx} 个房型未找到报价列表按钮")
                    except Exception as e:
                        print(f"    点击第 {idx} 个房型报价列表按钮时出错: {e}")
                
                # === 提取报价列表信息 ===
                quotes = []
                
                try:
                    # 查找报价表格行（可能是tr或div）
                    # 尝试多种选择器来定位报价行
                    quote_selectors = [
                        f'{room_xpath}//tr[contains(@class,"quote") or contains(@class,"offer")]',
                        f'{room_xpath}//div[contains(@class,"quote")]//tr',
                        f'{room_xpath}//table//tr[position()>1]',  # 跳过表头
                        f'{room_xpath}//div[contains(@class,"quote-row")]',
                        f'{room_xpath}//div[contains(@class,"offer-row")]',
                    ]
                    
                    quote_rows = []
                    for selector in quote_selectors:
                        try:
                            rows = room_div.find_elements(By.XPATH, selector)
                            if rows:
                                quote_rows = rows
                                break
                        except:
                            continue
                    
                    # 如果没找到表格行，尝试查找包含卖家信息的div
                    if not quote_rows:
                        # 查找包含"专营店"或"酒店"的div
                        seller_divs = room_div.find_elements(By.XPATH, 
                            f'.//div[contains(text(),"专营店") or contains(text(),"酒店")]')
                        if seller_divs:
                            quote_rows = seller_divs
                    
                    # 解析每个报价行
                    for quote_row in quote_rows:
                        try:
                            quote_text = quote_row.text
                            
                            # 提取卖家名称
                            seller = ""
                            seller_patterns = [
                                r'([^\n]+(?:专营店|酒店))',
                                r'([^\n]+专营店)',
                                r'([^\n]+酒店)',
                            ]
                            
                            for pattern in seller_patterns:
                                seller_match = re.search(pattern, quote_text)
                                if seller_match:
                                    seller = seller_match.group(1).strip()
                                    # 清理卖家名称（移除可能的图标字符）
                                    seller = re.sub(r'[^\w\u4e00-\u9fa5]', '', seller)
                                    if seller:
                                        break
                            
                            # 提取价格
                            price = ""
                            price_patterns = [
                                r'[¥￥]\s*(\d+)',
                                r'¥\s*(\d+)',
                                r'￥\s*(\d+)',
                            ]
                            
                            for pattern in price_patterns:
                                price_match = re.search(pattern, quote_text)
                                if price_match:
                                    price = f"¥{price_match.group(1)}"
                                    break
                            
                            # 只有当找到卖家或价格时才添加报价
                            if seller or price:
                                quotes.append({
                                    "卖家": seller,
                                    "价格": price
                                })
                                
                        except Exception as e:
                            continue
                    
                except Exception as e:
                    print(f"    提取报价信息失败: {e}")
                
                # 如果找到了房间名称或报价，就添加到结果中
                if room_name or quotes or bed_type or area:
                    room_info = {
                        "房型名称": room_name or f"房型{idx}",
                        "床型": bed_type,
                        "面积": area,
                        "楼层": floor,
                        "窗型": window_type,
                        "起始价格": start_price,
                        "报价列表": quotes,
                        "状态": "全部订完" if is_all_booked else ("有报价" if quotes else "暂无报价")
                    }
                    room_data.append(room_info)
                    status_text = "全部订完" if is_all_booked else f"{len(quotes)}个报价"
                    print(f"    {idx}. {room_name or f'房型{idx}'} | {start_price or '价格未知'} | {status_text}")
                    
            except Exception as e:
                print(f"    解析第 {idx} 个房型失败: {e}")
                continue
    
    except Exception as e:
        print(f"  获取房型信息失败: {e}")
        import traceback
        traceback.print_exc()
    
    return room_data


def print_summary(room_data):
    """打印房间信息汇总（房间名称、卖家、价格）"""
    print(f"\n{'='*60}")
    print(f"{'房型信息汇总':^56}")
    print(f"{'='*60}")
    print(f"共找到 {len(room_data)} 个房型\n")
    
    for idx, room in enumerate(room_data, 1):
        room_name = room.get('房型名称', '未知房型')
        print(f"【{idx}. {room_name}】")
        
        # 显示房间详细信息
        details = []
        if room.get('床型'):
            details.append(f"床型: {room['床型']}")
        if room.get('面积'):
            details.append(f"面积: {room['面积']}")
        if room.get('楼层'):
            details.append(f"楼层: {room['楼层']}")
        if room.get('窗型'):
            details.append(f"窗型: {room['窗型']}")
        if details:
            print(f"   详细信息: {' | '.join(details)}")
        
        if room.get('起始价格'):
            print(f"   起始价格: {room['起始价格']}")
        
        # 显示报价列表（卖家、价格）
        room_status = room.get('状态', '')
        if room_status == '全部订完':
            print("   状态: 全部订完")
        elif room.get('报价列表'):
            print(f"   报价数量: {len(room['报价列表'])} 个")
            for quote_idx, quote in enumerate(room['报价列表'], 1):
                seller = quote.get('卖家', '未知卖家')
                price = quote.get('价格', '价格未知')
                print(f"      {quote_idx}. 卖家: {seller} | 价格: {price}")
        else:
            print("   报价: 暂无报价或未展开")
        
        print("-"*60)


if __name__ == "__main__":
    print("=" * 50)
    print("  飞猪酒店房型数据爬取工具")
    print("=" * 50)
    print("\n提示: 地址只需输入城市名（如'上海'），不需要具体区域")
    print("      如果输入'上海黄浦区'，会自动提取为'上海'")
    
    user_input = input("\n请输入: 地址关键词,酒店关键词（默认为 上海,外滩）：").strip()
    if not user_input:
        user_input = "上海,外滩"
    
    parts = [p.strip() for p in user_input.replace('，', ',').split(',')]
    while len(parts) < 2:
        parts.append(parts[-1] if parts else "上海")
    
    print(f"\n搜索参数:")
    print(f"  地址: {parts[0]} (将自动提取城市名)")
    print(f"  酒店关键词: {parts[1]}")
    print(f"  入住: 明天")
    print(f"  住宿: 1晚")
    print("\n正在启动浏览器...")
    
    run(parts[0], parts[1], check_in_days=1, nights=1)

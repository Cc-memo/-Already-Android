# -*- coding: utf-8 -*-
"""
携程自动下单模块
用于在携程平台自动预订酒店房间

使用方式:
    from orders.ctrip_order import CtripOrderPlacer
    
    placer = CtripOrderPlacer()
    placer.setup_browser()
    success, order_id = placer.place_order(
        hotel_name="美利居酒店",
        room_type="商务大床房",
        check_in="2026-01-10",
        check_out="2026-01-11",
        guest_name="张三",
        phone="13800138000",
        dry_run=False
    )
    placer.close_browser()
"""

import os
import sys
import time
import random
import logging
import platform
from datetime import datetime
from typing import Tuple, Optional

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# 添加项目根目录到路径
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 携程目录和Cookies文件（与 ctrip_crawler.py 共用）
XIECHENG_DIR = os.path.join(PROJECT_ROOT, "xiecheng")
COOKIES_FILE = os.path.join(XIECHENG_DIR, "ctrip_cookies.pkl")

# 调试截图保存目录
DEBUG_DIR = SCRIPT_DIR


class CtripOrderPlacer:
    """
    携程自动下单器（使用Selenium + Cookies，与爬虫模块共用登录态）
    
    功能：
    1. 搜索指定酒店
    2. 选择匹配的房型
    3. 填写入住人信息
    4. 提交订单（到支付页面停止）
    """
    
    # 携程酒店URL
    CTRIP_URL = "https://www.ctrip.com"
    CTRIP_HOTEL_URL = "https://hotels.ctrip.com"
    
    def __init__(self):
        self.driver = None
        self.wait = None
    
    def setup_browser(self) -> bool:
        """
        启动浏览器（使用Selenium，与 ctrip_crawler.py 相同方式）
        
        返回:
            是否成功
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.support.ui import WebDriverWait
            
            logger.info("🚀 启动携程浏览器...")
            
            chrome_options = Options()
            
            # 设置Chrome路径（与爬虫模块相同）
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
            
            # 浏览器选项
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # 尝试使用 webdriver-manager
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            # 防止被检测为自动化程序
            try:
                self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                    'source': '''
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        })
                    '''
                })
            except:
                pass
            
            self.wait = WebDriverWait(self.driver, 15)
            
            # 加载Cookies
            if self._load_cookies():
                logger.info("✓ 携程浏览器启动成功（已加载登录态）")
            else:
                logger.warning("⚠️ 未找到登录态，请先运行: python xiecheng/ctrip_cookies.py")
            
            return True
            
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _load_cookies(self) -> bool:
        """加载Cookies（与 ctrip_cookies.py 相同方式）"""
        import pickle
        
        if not os.path.exists(COOKIES_FILE):
            logger.warning(f"  未找到Cookies文件: {COOKIES_FILE}")
            return False
        
        try:
            with open(COOKIES_FILE, 'rb') as f:
                cookies = pickle.load(f)
            
            # 先访问携程域名
            self.driver.get(self.CTRIP_URL)
            time.sleep(1)
            
            # 加载cookies
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass
            
            logger.info(f"  ✓ 已加载 {len(cookies)} 个cookie")
            return True
        except Exception as e:
            logger.error(f"  加载Cookies失败: {e}")
            return False
    
    def close_browser(self):
        """关闭浏览器"""
        try:
            if self.driver:
                self.driver.quit()
            logger.info("✓ 携程浏览器已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器失败: {e}")
    
    def _random_sleep(self, min_s: float = 0.5, max_s: float = 1.5):
        """随机等待，模拟人工操作"""
        time.sleep(random.uniform(min_s, max_s))
    
    def _simulate_typing(self, element, text, delay=0.1):
        """模拟人工输入"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(delay * 0.5, delay * 1.5))
    
    def place_order(self, hotel_name: str, room_type: str,
                    check_in: str, check_out: str,
                    guest_name: str, phone: str,
                    dry_run: bool = False) -> Tuple[bool, str]:
        """
        在携程下单
        
        参数:
            hotel_name: 酒店名称
            room_type: 房型名称
            check_in: 入住日期 (YYYY-MM-DD)
            check_out: 退房日期 (YYYY-MM-DD)
            guest_name: 入住人姓名
            phone: 联系电话
            dry_run: 是否演示模式（不实际下单）
        
        返回:
            (是否成功, 订单号或错误信息)
        """
        logger.info(f"\n{'='*50}")
        logger.info(f"📋 携程下单")
        logger.info(f"{'='*50}")
        logger.info(f"  酒店: {hotel_name}")
        logger.info(f"  房型: {room_type}")
        logger.info(f"  日期: {check_in} ~ {check_out}")
        logger.info(f"  入住人: {guest_name}")
        logger.info(f"  电话: {phone}")
        logger.info(f"  演示模式: {'是' if dry_run else '否'}")
        
        if dry_run:
            logger.info("\n[演示模式] 跳过实际下单")
            return True, f"DRY_RUN_CTRIP_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        try:
            # 步骤1: 搜索酒店
            logger.info("\n[步骤1] 搜索酒店...")
            if not self._search_hotel(hotel_name, check_in, check_out):
                return False, "搜索酒店失败"
            
            # 步骤2: 进入酒店详情页
            logger.info("\n[步骤2] 进入酒店详情页...")
            if not self._enter_hotel_detail(hotel_name):
                return False, "进入酒店详情页失败"
            
            # 步骤3: 选择房型
            logger.info("\n[步骤3] 选择房型...")
            if not self._select_room(room_type):
                return False, "选择房型失败"
            
            # 步骤4: 填写入住人信息
            logger.info("\n[步骤4] 填写入住人信息...")
            if not self._fill_guest_info(guest_name, phone):
                return False, "填写入住人信息失败"
            
            # 步骤5: 提交订单（到支付页面停止）
            logger.info("\n[步骤5] 提交订单...")
            order_id = self._submit_order()
            
            if order_id:
                logger.info(f"\n✓ 订单提交成功，订单号: {order_id}")
                return True, order_id
            else:
                return False, "提交订单失败"
            
        except Exception as e:
            logger.error(f"携程下单失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)
    
    def _select_dates(self, check_in: str, check_out: str) -> bool:
        """
        选择入住和离店日期（仿照 ctrip_crawler.py）
        
        参数:
            check_in: 入住日期，格式 "YYYY-MM-DD"
            check_out: 离店日期，格式 "YYYY-MM-DD"
        """
        from selenium.webdriver.common.by import By
        
        logger.info(f"  选择日期: {check_in} ~ {check_out}")
        
        try:
            # 点击入住日期元素打开日历
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
                    date_element = self.driver.find_element(By.XPATH, selector)
                    if date_element.is_displayed():
                        self.driver.execute_script("arguments[0].click();", date_element)
                        logger.info(f"  已点击入住日期选择器")
                        date_picker_opened = True
                        self._random_sleep(1, 1.5)
                        break
                except:
                    continue
            
            if not date_picker_opened:
                logger.warning("  未找到日期选择区域，跳过日期选择")
                return False
            
            # 解析日期
            checkin_dt = datetime.strptime(check_in, "%Y-%m-%d")
            checkout_dt = datetime.strptime(check_out, "%Y-%m-%d")
            
            # 选择入住日期
            if self._click_date_in_calendar(checkin_dt):
                logger.info(f"  ✓ 已选择入住日期: {check_in}")
                self._random_sleep(0.8, 1.2)
            else:
                logger.warning(f"  ⚠ 入住日期选择可能失败")
            
            # 选择离店日期
            if self._click_date_in_calendar(checkout_dt):
                logger.info(f"  ✓ 已选择离店日期: {check_out}")
                self._random_sleep(0.5, 1)
            else:
                logger.warning(f"  ⚠ 离店日期选择可能失败")
            
            return True
            
        except Exception as e:
            logger.warning(f"  日期选择失败: {str(e)[:50]}")
            return False
    
    def _click_date_in_calendar(self, target_date) -> bool:
        """
        在携程日历中点击指定日期（完全复制 ctrip_crawler.py 的实现）
        
        参数:
            target_date: datetime对象，目标日期
        
        返回:
            bool: 是否成功点击
        """
        from selenium.webdriver.common.by import By
        
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
                date_el = self.driver.find_element(By.XPATH, selector)
                if date_el.is_displayed():
                    # 滚动到元素可见
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_el)
                    self._random_sleep(0.2, 0.3)
                    self.driver.execute_script("arguments[0].click();", date_el)
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
            month_panels = self.driver.find_elements(By.XPATH, '//div[contains(@class, "calendar") or contains(@class, "month")]')
            
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
                            next_btn = self.driver.find_element(By.XPATH, selector)
                            if next_btn.is_displayed():
                                self.driver.execute_script("arguments[0].click();", next_btn)
                                clicked = True
                                self._random_sleep(0.3, 0.5)
                                break
                        except:
                            continue
                    
                    if not clicked:
                        break
                    
                    # 再次检查是否有目标月份
                    for selector in date_selectors:
                        try:
                            date_el = self.driver.find_element(By.XPATH, selector)
                            if date_el.is_displayed():
                                self.driver.execute_script("arguments[0].click();", date_el)
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
                    day_elements = self.driver.find_elements(By.XPATH, selector)
                    for day_el in day_elements:
                        if day_el.is_displayed():
                            class_attr = day_el.get_attribute("class") or ""
                            # 排除禁用、过去的日期
                            if "disabled" not in class_attr.lower() and "past" not in class_attr.lower() and "invalid" not in class_attr.lower():
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", day_el)
                                self._random_sleep(0.1, 0.2)
                                self.driver.execute_script("arguments[0].click();", day_el)
                                return True
                except:
                    continue
                    
        except Exception as e:
            logger.warning(f"    点击日期失败: {str(e)[:50]}")
        
        return False
    
    def _search_hotel(self, hotel_name: str, check_in: str, check_out: str) -> bool:
        """
        搜索酒店（完全参照 ctrip_crawler.py 的流程）
        
        流程：
        1. 输入目的地城市
        2. 点击城市建议
        3. 选择日期
        4. 输入酒店关键词
        5. 点击搜索
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            logger.info(f"  访问携程首页...")
            self.driver.get(self.CTRIP_URL)
            self._random_sleep(3, 5)
            
            # 提取酒店关键词和城市
            hotel_keyword = hotel_name.split("（")[0] if "（" in hotel_name else hotel_name
            
            # 从酒店名称中提取城市
            city = "上海"  # 默认城市
            if "上海" in hotel_name:
                city = "上海"
            elif "北京" in hotel_name:
                city = "北京"
            elif "广州" in hotel_name:
                city = "广州"
            elif "深圳" in hotel_name:
                city = "深圳"
            
            # [步骤1] 输入目的地城市
            logger.info(f"  输入目的地: {city}")
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
                    destination_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                    if destination_input:
                        logger.info(f"  找到目的地输入框: {selector}")
                        break
                except:
                    continue
            
            if not destination_input:
                # 尝试点击酒店入口再查找
                logger.info("  尝试点击酒店入口...")
                try:
                    hotel_entry = self.driver.find_element(By.XPATH, '//a[contains(text(), "酒店")]')
                    hotel_entry.click()
                    self._random_sleep(2, 3)
                    
                    for selector in destination_selectors:
                        try:
                            destination_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                            if destination_input:
                                break
                        except:
                            continue
                except:
                    pass
            
            if destination_input:
                destination_input.click()
                self._random_sleep(0.5, 1)
                destination_input.send_keys(Keys.CONTROL + 'a')
                self._random_sleep(0.2, 0.3)
                destination_input.send_keys(Keys.DELETE)
                self._random_sleep(0.3, 0.5)
                destination_input.clear()
                self._random_sleep(0.3, 0.5)
                self._simulate_typing(destination_input, city)
                logger.info(f"  ✓ 已输入目的地: {city}")
                self._random_sleep(1, 2)
            else:
                logger.error("  ❌ 未找到目的地输入框")
                return False
            
            # [步骤2] 点击城市建议
            logger.info("  等待并点击城市建议...")
            self._random_sleep(2, 3)
            suggestion_selector = '//*[@id="kakxi"]/li[1]/div/div[2]/div[2]/div[1]/div'
            try:
                suggestion = self.wait.until(EC.element_to_be_clickable((By.XPATH, suggestion_selector)))
                suggestion.click()
                logger.info("  ✓ 已点击城市建议选项")
            except:
                logger.warning("  未找到建议选项，尝试按回车")
                destination_input.send_keys(Keys.ENTER)
            
            self._random_sleep(1, 2)
            
            # [步骤3] 选择入住和离店日期
            logger.info(f"  选择日期: {check_in} ~ {check_out}")
            self._select_dates(check_in, check_out)
            self._random_sleep(1, 2)
            
            # [步骤4] 输入酒店关键词
            logger.info(f"  输入酒店关键词: {hotel_keyword}")
            keyword_selectors = [
                '//*[@id="keyword"]',
                '//input[contains(@placeholder, "关键词")]',
                '//input[contains(@placeholder, "酒店")]',
            ]
            
            keyword_input = None
            for selector in keyword_selectors:
                try:
                    keyword_input = self.driver.find_element(By.XPATH, selector)
                    if keyword_input.is_displayed():
                        break
                except:
                    continue
            
            if keyword_input:
                keyword_input.clear()
                self._simulate_typing(keyword_input, hotel_keyword)
                self._random_sleep(1, 2)
            
            # [步骤5] 点击搜索按钮
            logger.info("  点击搜索按钮...")
            search_selectors = [
                '//button[contains(text(), "搜索")]',
                '//div[contains(@class, "search-btn")]',
                '//a[contains(@class, "search-btn")]',
                '//button[contains(@class, "search")]',
            ]
            
            for selector in search_selectors:
                try:
                    search_btn = self.driver.find_element(By.XPATH, selector)
                    if search_btn.is_displayed():
                        search_btn.click()
                        break
                except:
                    continue
            
            self._random_sleep(3, 5)
            logger.info("  ✓ 搜索完成")
            return True
            
        except Exception as e:
            logger.error(f"  搜索酒店失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _enter_hotel_detail(self, hotel_name: str) -> bool:
        """进入酒店详情页"""
        from selenium.webdriver.common.by import By
        
        try:
            logger.info(f"  查找酒店: {hotel_name}")
            self._random_sleep(2, 3)
            
            # 使用与 ctrip_crawler.py 相同的选择器
            hotel_name_selector = '//span[@class="hotelName"]'
            hotel_names = self.driver.find_elements(By.XPATH, hotel_name_selector)
            logger.info(f"  找到 {len(hotel_names)} 个酒店")
            
            if not hotel_names:
                # 备用选择器
                backup_selectors = [
                    '//div[contains(@class, "hotel-card")]//a',
                    '//div[contains(@class, "list-card")]//a',
                    '//div[contains(@class, "hotel-item")]//a',
                ]
                for selector in backup_selectors:
                    try:
                        hotels = self.driver.find_elements(By.XPATH, selector)
                        if hotels:
                            logger.info(f"  使用备用选择器找到 {len(hotels)} 个酒店")
                            hotels[0].click()
                            self._random_sleep(2, 3)
                            break
                    except:
                        continue
                else:
                    logger.error("  ❌ 未找到酒店列表")
                    self.driver.save_screenshot(os.path.join(DEBUG_DIR, "debug_ctrip_hotel_list.png"))
                    return False
            else:
                # 点击第一个酒店
                hotel_names[0].click()
                self._random_sleep(2, 3)
            
            # 切换到新标签页
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
                logger.info("  已切换到酒店详情页")
            
            self._random_sleep(3, 5)
            logger.info("  ✓ 已进入酒店详情页")
            return True
            
        except Exception as e:
            logger.error(f"  进入酒店详情页失败: {e}")
            return False
    
    def _select_room(self, room_type: str) -> bool:
        """选择房型"""
        from selenium.webdriver.common.by import By
        
        try:
            logger.info(f"  查找房型: {room_type}")
            self._random_sleep(2, 3)
            
            # 提取房型关键词
            keywords = []
            if "大床" in room_type:
                keywords.append("大床")
            if "双床" in room_type:
                keywords.append("双床")
            if "单人" in room_type:
                keywords.append("单人")
            if "商务" in room_type:
                keywords.append("商务")
            
            # 查找房型容器（ID为纯数字且长度>5的div）
            room_containers = self.driver.find_elements(By.XPATH, '//div[@id]')
            room_ids = []
            for container in room_containers:
                try:
                    container_id = container.get_attribute("id")
                    if container_id and container_id.isdigit() and len(container_id) > 5:
                        room_ids.append(container_id)
                except:
                    pass
            
            logger.info(f"  找到 {len(room_ids)} 个房型")
            
            if not room_ids:
                logger.error("  ❌ 未找到房型列表")
                self.driver.save_screenshot(os.path.join(DEBUG_DIR, "debug_ctrip_room_list.png"))
                return False
            
            # 查找匹配的房型
            target_room_id = None
            for room_id in room_ids:
                try:
                    name_xpath = f'//*[@id="{room_id}"]/div[1]/span'
                    name_element = self.driver.find_element(By.XPATH, name_xpath)
                    room_name = name_element.text.strip()
                    
                    for keyword in keywords:
                        if keyword in room_name:
                            target_room_id = room_id
                            logger.info(f"  找到匹配房型: {room_name}")
                            break
                    if target_room_id:
                        break
                except:
                    continue
            
            if not target_room_id:
                logger.warning("  未找到精确匹配，选择第一个房型")
                target_room_id = room_ids[0]
            
            # 点击预订按钮（使用用户提供的XPath规律）
            # //*[@id="房型ID"]/div[2]/div[2]/div[?]/div[3]/div/div/div[2]/button
            book_selectors = [
                f'//*[@id="{target_room_id}"]/div[2]/div[2]/div[2]/div[3]/div/div/div[2]/button',
                f'//*[@id="{target_room_id}"]/div[2]/div[2]/div[3]/div[3]/div/div/div[2]/button',
                f'//*[@id="{target_room_id}"]/div[2]/div[2]/div[4]/div[3]/div/div/div[2]/button',
                f'//*[@id="{target_room_id}"]//button[contains(@class, "book")]',
                f'//*[@id="{target_room_id}"]//button',
            ]
            
            clicked = False
            for selector in book_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for book_btn in buttons:
                        if book_btn.is_displayed():
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", book_btn)
                            self._random_sleep(0.5, 1)
                            self.driver.execute_script("arguments[0].click();", book_btn)
                            clicked = True
                            logger.info(f"  点击了预订按钮")
                            break
                    if clicked:
                        break
                except:
                    continue
            
            if not clicked:
                logger.warning("  ⚠️ 未找到预订按钮，尝试点击房型区域")
                try:
                    room_element = self.driver.find_element(By.XPATH, f'//*[@id="{target_room_id}"]')
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", room_element)
                    room_element.click()
                except:
                    pass
            
            self._random_sleep(2, 3)
            logger.info("  ✓ 已选择房型")
            return True
            
        except Exception as e:
            logger.error(f"  选择房型失败: {e}")
            return False
    
    def _fill_guest_info(self, guest_name: str, phone: str) -> bool:
        """填写入住人信息"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            logger.info(f"  填写入住人: {guest_name}, 电话: {phone}")
            self._random_sleep(2, 3)
            
            # 切换到新窗口（如果有）
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
                logger.info(f"  已切换到新页面: {self.driver.current_url}")
                self._random_sleep(2, 3)
            
            # 等待页面加载
            try:
                self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="trip_main_content"]')))
            except:
                pass
            
            # 查找姓名输入框（使用用户提供的XPath）
            name_selectors = [
                '//*[@id="trip_main_content"]/div[2]/div[2]/div[2]/div/div/div[2]/div/div[1]/div/input',
                '//*[@id="trip_main_content"]//input[contains(@placeholder, "姓名")]',
                '//*[@id="trip_main_content"]//input[contains(@placeholder, "入住人")]',
                '//input[contains(@placeholder, "姓名")]',
                '//input[contains(@placeholder, "入住人")]',
            ]
            
            name_filled = False
            for selector in name_selectors:
                try:
                    name_input = self.driver.find_element(By.XPATH, selector)
                    if name_input.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", name_input)
                        self._random_sleep(0.3, 0.5)
                        name_input.click()
                        # 清空原内容
                        self.driver.execute_script("arguments[0].value = '';", name_input)
                        name_input.clear()
                        from selenium.webdriver.common.keys import Keys
                        name_input.send_keys(Keys.CONTROL, 'a')
                        name_input.send_keys(Keys.DELETE)
                        self._random_sleep(0.2, 0.3)
                        name_input.send_keys(guest_name)
                        logger.info(f"  ✓ 已填写姓名")
                        name_filled = True
                        break
                except:
                    continue
            
            if not name_filled:
                logger.warning("  ⚠️ 未找到姓名输入框")
            
            self._random_sleep(0.5, 1)
            
            # 查找电话输入框
            phone_selectors = [
                '//*[@id="trip_main_content"]/div[2]/div[2]/div[2]/div/div/div[2]/div/div[2]/div/input',
                '//*[@id="trip_main_content"]//input[contains(@placeholder, "手机")]',
                '//*[@id="trip_main_content"]//input[contains(@placeholder, "电话")]',
                '//*[@id="trip_main_content"]//input[@type="tel"]',
                '//input[contains(@placeholder, "手机")]',
                '//input[contains(@placeholder, "电话")]',
                '//input[@type="tel"]',
            ]
            
            phone_filled = False
            for selector in phone_selectors:
                try:
                    phone_input = self.driver.find_element(By.XPATH, selector)
                    if phone_input.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", phone_input)
                        self._random_sleep(0.3, 0.5)
                        phone_input.click()
                        # 清空原内容
                        self.driver.execute_script("arguments[0].value = '';", phone_input)
                        phone_input.clear()
                        from selenium.webdriver.common.keys import Keys
                        phone_input.send_keys(Keys.CONTROL, 'a')
                        phone_input.send_keys(Keys.DELETE)
                        self._random_sleep(0.2, 0.3)
                        phone_input.send_keys(phone)
                        logger.info(f"  ✓ 已填写电话")
                        phone_filled = True
                        break
                except:
                    continue
            
            if not phone_filled:
                logger.warning("  ⚠️ 未找到电话输入框")
            
            self._random_sleep(1, 2)
            logger.info("  ✓ 入住人信息填写完成")
            return True
            
        except Exception as e:
            logger.error(f"  填写入住人信息失败: {e}")
            return False
    
    def _submit_order(self) -> Optional[str]:
        """提交订单"""
        from selenium.webdriver.common.by import By
        
        try:
            logger.info("  查找提交按钮...")
            
            # 使用用户提供的XPath
            submit_selectors = [
                '//*[@id="trip_main_content"]/div[6]/div[3]/div/button/div',
                '//*[@id="trip_main_content"]/div[6]/div[3]/div/button',
                '//*[@id="trip_main_content"]//button[contains(text(), "提交")]',
                '//button[contains(text(), "提交订单")]',
                '//button[contains(text(), "确认预订")]',
            ]
            
            submit_btn = None
            for selector in submit_selectors:
                try:
                    submit_btn = self.driver.find_element(By.XPATH, selector)
                    if submit_btn.is_displayed():
                        logger.info(f"  找到提交按钮: {selector[:50]}...")
                        break
                except:
                    continue
            
            if not submit_btn:
                logger.warning("  ⚠️ 未找到提交按钮，可能需要手动操作")
                self.driver.save_screenshot(os.path.join(DEBUG_DIR, "debug_ctrip_submit.png"))
                logger.info("  请手动完成订单提交...")
                try:
                    input("  按回车键继续...")
                except EOFError:
                    pass
                return f"MANUAL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            logger.info("  点击提交订单...")
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            self._random_sleep(0.5, 1)
            self.driver.execute_script("arguments[0].click();", submit_btn)
            self._random_sleep(3, 5)
            
            # 提取订单号
            order_id = self._extract_order_id()
            return order_id if order_id else f"CTRIP_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
        except Exception as e:
            logger.error(f"  提交订单失败: {e}")
            return None
    
    def _extract_order_id(self) -> Optional[str]:
        """从页面提取订单号"""
        import re
        
        try:
            url = self.driver.current_url
            if "orderid=" in url.lower():
                match = re.search(r'orderid[=:](\d+)', url, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            # 尝试从页面元素获取
            from selenium.webdriver.common.by import By
            order_selectors = ['.order-id', '.order-number', '[class*="orderId"]']
            for selector in order_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        text = element.text
                        match = re.search(r'\d{10,}', text)
                        if match:
                            return match.group()
                except:
                    continue
            return None
        except Exception as e:
            logger.error(f"  提取订单号失败: {e}")
            return None


def test_ctrip_order():
    """测试携程下单"""
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
            dry_run=True  # 演示模式
        )
        
        print(f"\n结果: {'成功' if success else '失败'}")
        print(f"订单号/信息: {result}")
    finally:
        try:
            input("\n按回车键关闭浏览器...")
        except EOFError:
            pass
        placer.close_browser()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="携程自动下单测试")
    parser.add_argument("--hotel", type=str, default="美利居酒店（上海城市中心人民广场店）", help="酒店名称")
    parser.add_argument("--room", type=str, default="商务大床房", help="房型名称")
    parser.add_argument("--checkin", type=str, default="2026-01-10", help="入住日期 (YYYY-MM-DD)")
    parser.add_argument("--checkout", type=str, default="2026-01-11", help="退房日期 (YYYY-MM-DD)")
    parser.add_argument("--name", type=str, default="张三", help="入住人姓名")
    parser.add_argument("--phone", type=str, default="13800138000", help="联系电话")
    parser.add_argument("--dry-run", action="store_true", help="演示模式（不实际操作）")
    
    args = parser.parse_args()
    
    # 如果没有传任何参数，运行默认测试
    if len(sys.argv) == 1:
        test_ctrip_order()
    else:
        print("="*60)
        print("  携程自动下单测试")
        print("="*60)
        print(f"  酒店: {args.hotel}")
        print(f"  房型: {args.room}")
        print(f"  日期: {args.checkin} ~ {args.checkout}")
        print(f"  入住人: {args.name}")
        print(f"  电话: {args.phone}")
        print(f"  演示模式: {'是' if args.dry_run else '否'}")
        print("="*60)
        
        placer = CtripOrderPlacer()
        try:
            if not placer.setup_browser():
                print("启动浏览器失败")
                sys.exit(1)
            
            success, result = placer.place_order(
                hotel_name=args.hotel,
                room_type=args.room,
                check_in=args.checkin,
                check_out=args.checkout,
                guest_name=args.name,
                phone=args.phone,
                dry_run=args.dry_run
            )
            
            print(f"\n结果: {'成功' if success else '失败'}")
            print(f"订单号/信息: {result}")
        finally:
            try:
                input("\n按回车键关闭浏览器...")
            except EOFError:
                pass
            placer.close_browser()

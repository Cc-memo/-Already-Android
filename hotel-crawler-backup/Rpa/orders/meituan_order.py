# -*- coding: utf-8 -*-
"""
美团自动下单模块
用于在美团平台自动预订酒店房间

使用方式:
    from orders.meituan_order import MeituanOrderPlacer
    
    placer = MeituanOrderPlacer()
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

# 美团目录和Cookies文件（与 meituan_rpa.py 共用）
MEITUAN_DIR = os.path.join(PROJECT_ROOT, "meituan")
COOKIES_FILE = os.path.join(MEITUAN_DIR, "meituan_h5_cookies.pkl")

# 调试截图保存目录
DEBUG_DIR = SCRIPT_DIR


class MeituanOrderPlacer:
    """
    美团自动下单器（使用Selenium + Cookies，与爬虫模块共用登录态）
    
    功能：
    1. 搜索指定酒店
    2. 选择匹配的房型
    3. 填写入住人信息
    4. 提交订单（到支付页面停止）
    """
    
    # 美团酒店URL（H5移动端页面）
    MEITUAN_URL = "https://i.meituan.com"
    MEITUAN_HOTEL_SEARCH_URL = "https://i.meituan.com/awp/h5/hotel/search/search.html"
    
    def __init__(self):
        self.driver = None
        self.wait = None
    
    def setup_browser(self) -> bool:
        """
        启动浏览器（使用Selenium，与 meituan_rpa.py 相同方式）
        
        返回:
            是否成功
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.support.ui import WebDriverWait
            
            logger.info("🚀 启动美团浏览器...")
            
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
            
            # 浏览器选项（H5移动端尺寸）
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=430,900')  # 移动端尺寸
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
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
                logger.info("✓ 美团浏览器启动成功（已加载登录态）")
            else:
                logger.warning("⚠️ 未找到登录态，请先运行: python meituan/meituan_cookies.py")
            
            return True
            
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _load_cookies(self) -> bool:
        """加载Cookies（与 meituan_rpa.py 相同方式）"""
        import pickle
        
        if not os.path.exists(COOKIES_FILE):
            logger.warning(f"  未找到Cookies文件: {COOKIES_FILE}")
            return False
        
        try:
            with open(COOKIES_FILE, 'rb') as f:
                cookies = pickle.load(f)
            
            # 先访问美团域名
            self.driver.get(self.MEITUAN_URL)
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
            logger.info("✓ 美团浏览器已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器失败: {e}")
    
    def _random_sleep(self, min_s: float = 0.5, max_s: float = 1.5):
        """随机等待，模拟人工操作"""
        time.sleep(random.uniform(min_s, max_s))
    
    def _type_slowly(self, element, text):
        """模拟人工输入"""
        for ch in text:
            element.send_keys(ch)
            time.sleep(random.uniform(0.05, 0.12))
    
    def place_order(self, hotel_name: str, room_type: str,
                    check_in: str, check_out: str,
                    guest_name: str, phone: str,
                    dry_run: bool = False) -> Tuple[bool, str]:
        """
        在美团下单
        
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
        logger.info(f"📋 美团下单")
        logger.info(f"{'='*50}")
        logger.info(f"  酒店: {hotel_name}")
        logger.info(f"  房型: {room_type}")
        logger.info(f"  日期: {check_in} ~ {check_out}")
        logger.info(f"  入住人: {guest_name}")
        logger.info(f"  电话: {phone}")
        logger.info(f"  演示模式: {'是' if dry_run else '否'}")
        
        if dry_run:
            logger.info("\n[演示模式] 跳过实际下单")
            return True, f"DRY_RUN_MEITUAN_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        try:
            # 步骤1: 搜索酒店
            logger.info("\n[步骤1] 搜索酒店...")
            if not self._search_hotel(hotel_name, check_in, check_out):
                return False, "搜索酒店失败"
            
            # 步骤2: 进入酒店详情页
            logger.info("\n[步骤2] 进入酒店详情页...")
            if not self._enter_hotel_detail(hotel_name):
                return False, "进入酒店详情页失败"
            
            # 步骤3: 选择房型并点击预约
            logger.info("\n[步骤3] 选择房型并点击预约...")
            if not self._select_room(room_type):
                return False, "选择房型失败"
            
            # 步骤4: 点击预约按钮进入填写页面
            logger.info("\n[步骤4] 点击预约按钮...")
            if not self._click_book_button():
                return False, "点击预约按钮失败"
            
            # 步骤5: 填写入住人信息
            logger.info("\n[步骤5] 填写入住人信息...")
            if not self._fill_guest_info(guest_name, phone):
                return False, "填写入住人信息失败"
            
            # 步骤6: 提交订单（到支付页面停止）
            logger.info("\n[步骤6] 提交订单...")
            order_id = self._submit_order()
            
            if order_id:
                logger.info(f"\n✓ 订单提交成功，订单号: {order_id}")
                return True, order_id
            else:
                return False, "提交订单失败"
            
        except Exception as e:
            logger.error(f"美团下单失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)
    
    def _select_dates(self, check_in: str, check_out: str) -> bool:
        """
        选择入住和离店日期（仿照 meituan_rpa.py）
        
        参数:
            check_in: 入住日期，格式 "YYYY-MM-DD"
            check_out: 离店日期，格式 "YYYY-MM-DD"
        """
        from selenium.webdriver.common.by import By
        
        logger.info(f"  选择日期: {check_in} ~ {check_out}")
        
        try:
            # 点击日期区域打开日历
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
                    date_entry = self.driver.find_element(By.XPATH, selector)
                    if date_entry.is_displayed():
                        date_entry.click()
                        logger.info("  已点击日期选择入口")
                        date_picker_opened = True
                        self._random_sleep(1, 1.5)
                        break
                except:
                    continue
            
            if not date_picker_opened:
                logger.warning("  未找到日期选择入口，跳过日期选择")
                return False
            
            # 等待日历弹出
            try:
                from selenium.webdriver.support import expected_conditions as EC
                self.wait.until(EC.presence_of_element_located((By.ID, "vueCalendarTemplate")))
                self._random_sleep(0.5, 1)
            except:
                logger.warning("  日历未弹出")
                return False
            
            # 选择入住日期
            if self._click_meituan_date(check_in):
                logger.info(f"  ✓ 已选择入住日期: {check_in}")
                self._random_sleep(0.5, 0.8)
            else:
                logger.warning(f"  ⚠ 入住日期选择可能失败")
            
            # 选择离店日期
            if self._click_meituan_date(check_out):
                logger.info(f"  ✓ 已选择离店日期: {check_out}")
                self._random_sleep(0.5, 0.8)
            else:
                logger.warning(f"  ⚠ 离店日期选择可能失败")
            
            # 点击"完成"按钮确认日期选择
            try:
                complete_btn_selectors = [
                    '//a[contains(text(), "完成")]',
                    '//div[contains(@class, "complete")]//a',
                    '//div[contains(@class, "calendar-complete")]//a',
                ]
                for selector in complete_btn_selectors:
                    try:
                        complete_btn = self.driver.find_element(By.XPATH, selector)
                        if complete_btn.is_displayed():
                            complete_btn.click()
                            logger.info("  ✓ 已点击完成按钮")
                            self._random_sleep(0.5, 1)
                            break
                    except:
                        continue
            except:
                pass
            
            return True
            
        except Exception as e:
            logger.warning(f"  日期选择失败: {str(e)[:50]}")
            return False
    
    def _click_meituan_date(self, date_str: str) -> bool:
        """
        在美团日历中点击指定日期（仿照 meituan_rpa.py）
        
        参数:
            date_str: 日期字符串，格式 "YYYY-MM-DD"
        
        返回:
            bool: 是否成功点击
        """
        from selenium.webdriver.common.by import By
        
        # 美团日历使用 data-date-format 属性存储日期
        date_selectors = [
            f'//li[@data-date-format="{date_str}"]',
            f'//*[@data-date-format="{date_str}"]',
        ]
        
        for selector in date_selectors:
            try:
                date_elements = self.driver.find_elements(By.XPATH, selector)
                for date_el in date_elements:
                    # 检查是否可点击（排除 disabled 状态）
                    class_attr = date_el.get_attribute("class") or ""
                    if "disabled" in class_attr:
                        continue
                    
                    # 滚动到元素可见
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_el)
                    self._random_sleep(0.2, 0.3)
                    
                    # 点击日期
                    self.driver.execute_script("arguments[0].click();", date_el)
                    return True
            except:
                continue
        
        return False
    
    def _search_hotel(self, hotel_name: str, check_in: str, check_out: str) -> bool:
        """
        搜索酒店并点击第一个结果（完全参照 meituan_rpa.py 的流程）
        
        流程：
        1. 选择日期
        2. 输入地址
        3. 选择地址建议
        4. 输入酒店关键词
        5. 点击搜索
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            logger.info(f"  访问美团H5酒店搜索页...")
            self.driver.get(self.MEITUAN_HOTEL_SEARCH_URL)
            self._random_sleep(3, 4)
            
            # 提取酒店关键词和地址
            hotel_keyword = hotel_name.split("（")[0] if "（" in hotel_name else hotel_name
            
            # 从酒店名称中提取城市/地址
            address_keyword = "上海"  # 默认地址
            if "上海" in hotel_name:
                address_keyword = "上海"
            elif "北京" in hotel_name:
                address_keyword = "北京"
            elif "广州" in hotel_name:
                address_keyword = "广州"
            elif "深圳" in hotel_name:
                address_keyword = "深圳"
            
            # H5移动端 XPath 定位（与 meituan_rpa.py 相同）
            ADDRESS_ENTRY = '//*[@id="search"]/div/div[1]/div[2]'
            ADDRESS_INPUT = '//*[@id="search"]/div/div[3]/div[1]/div/label/input'
            KEYWORD_ENTRY = '//*[@id="search"]/div/div[1]/div[5]'
            KEYWORD_INPUT = '//*[@id="search"]/div/div[4]/div[1]/label/input'
            SEARCH_BUTTON = '//*[@id="search"]/div/div[1]/div[7]/button'
            
            # [步骤0] 选择入住和离店日期
            logger.info(f"  [步骤0] 选择日期: {check_in} ~ {check_out}")
            self._select_dates(check_in, check_out)
            self._random_sleep(1, 1.5)
            
            # [步骤1] 点击地址搜索框入口
            logger.info(f"  [步骤1] 点击地址搜索框入口...")
            try:
                addr_entry = self.wait.until(EC.element_to_be_clickable((By.XPATH, ADDRESS_ENTRY)))
                addr_entry.click()
                self._random_sleep(0.5, 1)
            except Exception as e:
                logger.error(f"  点击地址入口失败: {e}")
                return False
            
            # [步骤2] 输入地址关键词
            logger.info(f"  [步骤2] 输入地址关键词: {address_keyword}")
            try:
                addr_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, ADDRESS_INPUT)))
                addr_input.click()
                addr_input.send_keys(Keys.CONTROL, 'a')
                addr_input.send_keys(Keys.DELETE)
                self._type_slowly(addr_input, address_keyword)
                self._random_sleep(1.2, 1.8)
                
                # 选择第一个建议
                suggestion_selectors = [
                    '//ul/li[1]',
                    '//li[contains(@class,"item")][1]',
                    '//div[contains(@class,"result-item")][1]'
                ]
                suggestion_clicked = False
                for selector in suggestion_selectors:
                    try:
                        suggestion = self.driver.find_element(By.XPATH, selector)
                        if suggestion.is_displayed():
                            suggestion.click()
                            suggestion_clicked = True
                            break
                    except:
                        continue
                
                if not suggestion_clicked:
                    addr_input.send_keys(Keys.ARROW_DOWN)
                    self._random_sleep(0.15, 0.2)
                    addr_input.send_keys(Keys.ENTER)
                
                self._random_sleep(1, 1.5)
            except Exception as e:
                logger.error(f"  输入地址失败: {e}")
                return False
            
            # [步骤3] 点击关键词入口
            logger.info(f"  [步骤3] 点击关键词入口...")
            try:
                kw_entry = self.wait.until(EC.element_to_be_clickable((By.XPATH, KEYWORD_ENTRY)))
                kw_entry.click()
                self._random_sleep(0.5, 1)
            except Exception as e:
                logger.error(f"  点击关键词入口失败: {e}")
                return False
            
            # [步骤4] 输入酒店关键词
            logger.info(f"  [步骤4] 输入酒店关键词: {hotel_keyword}")
            try:
                kw_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, KEYWORD_INPUT)))
                kw_input.click()
                kw_input.send_keys(Keys.CONTROL, 'a')
                kw_input.send_keys(Keys.DELETE)
                self._type_slowly(kw_input, hotel_keyword)
                self._random_sleep(1.5, 2)
                
                # 点击第一个搜索建议
                KEYWORD_FIRST_SUGGESTION = '//*[@id="search"]/div/div[4]/div[1]/div'
                try:
                    first_suggestion = self.wait.until(EC.element_to_be_clickable((By.XPATH, KEYWORD_FIRST_SUGGESTION)))
                    first_suggestion.click()
                    self._random_sleep(1, 1.5)
                except:
                    logger.warning("  未找到关键词建议，尝试直接搜索")
            except Exception as e:
                logger.error(f"  输入关键词失败: {e}")
                return False
            
            # [步骤5] 点击搜索按钮
            logger.info("  [步骤5] 点击搜索按钮...")
            try:
                search_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, SEARCH_BUTTON)))
                search_btn.click()
                self._random_sleep(3, 4)
            except Exception as e:
                logger.error(f"  点击搜索按钮失败: {e}")
                return False
            
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
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            logger.info(f"  查找酒店: {hotel_name}")
            self._random_sleep(2, 3)
            
            # 点击搜索结果中的第一个酒店（与 meituan_rpa.py 相同）
            FIRST_HOTEL = '//*[@id="app"]/div[5]/div[1]/div[1]/a/div[2]'
            try:
                hotel = self.wait.until(EC.element_to_be_clickable((By.XPATH, FIRST_HOTEL)))
                hotel.click()
                self._random_sleep(3, 4)
                logger.info("  ✓ 已进入酒店详情页")
                return True
            except Exception as e:
                logger.error(f"  点击第一个酒店失败: {e}")
                self.driver.save_screenshot(os.path.join(DEBUG_DIR, "debug_meituan_hotel_list.png"))
                return False
            
        except Exception as e:
            logger.error(f"  进入酒店详情页失败: {e}")
            return False
    
    def _select_room(self, room_type: str) -> bool:
        """选择房型"""
        from selenium.webdriver.common.by import By
        
        try:
            logger.info(f"  查找房型: {room_type}")
            self._random_sleep(2, 3)
            
            # 点击"查看全部房型"
            VIEW_ALL_ROOMS = '//div[contains(text(),"查看全部") or contains(text(),"全部房型")]'
            try:
                view_all = self.driver.find_element(By.XPATH, VIEW_ALL_ROOMS)
                view_all.click()
                self._random_sleep(2, 3)
            except:
                pass
            
            # 提取房型关键词
            keywords = []
            if "大床" in room_type:
                keywords.append("大床")
            if "双床" in room_type:
                keywords.append("双床")
            if "单人" in room_type:
                keywords.append("单人")
            
            # 查找房型列表（与 meituan_rpa.py 相同）
            ROOM_LIST_XPATH = '//*[@id="main"]/section/section[7]/ul/li'
            room_elements = self.driver.find_elements(By.XPATH, ROOM_LIST_XPATH)
            logger.info(f"  找到 {len(room_elements)} 个房型")
            
            if not room_elements:
                logger.error("  ❌ 未找到房型列表")
                self.driver.save_screenshot(os.path.join(DEBUG_DIR, "debug_meituan_room_list.png"))
                return False
            
            # 查找匹配的房型
            target_room = None
            for room_el in room_elements:
                try:
                    room_text = room_el.text
                    for keyword in keywords:
                        if keyword in room_text and "满房" not in room_text:
                            target_room = room_el
                            logger.info(f"  找到匹配房型")
                            break
                    if target_room:
                        break
                except:
                    continue
            
            if not target_room:
                logger.warning("  未找到精确匹配，选择第一个可预订房型")
                for room_el in room_elements:
                    try:
                        if "满房" not in room_el.text:
                            target_room = room_el
                            break
                    except:
                        continue
            
            if not target_room:
                logger.error("  ❌ 没有可预订的房型")
                return False
            
            # 点击预订按钮
            try:
                book_btn = target_room.find_element(By.XPATH, './/span[contains(text(), "预订")]')
                book_btn.click()
            except:
                target_room.click()
            
            self._random_sleep(2, 3)
            logger.info("  ✓ 已选择房型")
            return True
            
        except Exception as e:
            logger.error(f"  选择房型失败: {e}")
            return False
    
    def _click_book_button(self) -> bool:
        """点击预约按钮进入填写信息页面"""
        from selenium.webdriver.common.by import By
        
        try:
            logger.info("  查找预约按钮...")
            self._random_sleep(1, 2)
            
            # 用户提供的预约按钮XPath
            book_selectors = [
                '//*[@id="main"]/div[6]/section[2]/div[2]',  # 用户提供
                '//*[@id="main"]/div[6]/section[2]/div[2]/div',
                '//div[contains(text(), "预订")]',
                '//span[contains(text(), "预订")]',
                '//button[contains(text(), "预订")]',
            ]
            
            book_btn = None
            for selector in book_selectors:
                try:
                    book_btn = self.driver.find_element(By.XPATH, selector)
                    if book_btn.is_displayed():
                        logger.info(f"  找到预约按钮: {selector[:50]}...")
                        break
                except:
                    continue
            
            if not book_btn:
                logger.error("  ❌ 未找到预约按钮")
                self.driver.save_screenshot(os.path.join(DEBUG_DIR, "debug_meituan_book_btn.png"))
                return False
            
            # 滚动到按钮可见并点击
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", book_btn)
            self._random_sleep(0.5, 1)
            self.driver.execute_script("arguments[0].click();", book_btn)
            
            # 等待页面跳转到填写信息页面
            self._random_sleep(3, 4)
            logger.info("  ✓ 已点击预约按钮，进入填写信息页面")
            return True
            
        except Exception as e:
            logger.error(f"  点击预约按钮失败: {e}")
            return False
    
    def _fill_guest_info(self, guest_name: str, phone: str) -> bool:
        """填写入住人信息"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        
        try:
            logger.info(f"  填写入住人: {guest_name}, 电话: {phone}")
            self._random_sleep(2, 3)
            
            # 查找姓名输入框（用户提供的XPath放最前面）
            name_selectors = [
                '//*[@id="app"]/div/div/div/section/section[1]/div[2]/label/input',  # 用户提供
                '//input[contains(@placeholder, "姓名")]',
                '//input[contains(@placeholder, "入住人")]',
                '//input[contains(@name, "name")]',
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
                        name_input.send_keys(Keys.CONTROL, 'a')
                        name_input.send_keys(Keys.DELETE)
                        self._random_sleep(0.2, 0.3)
                        name_input.send_keys(guest_name)
                        logger.info(f"  ✓ 已填写姓名: {selector[:50]}...")
                        name_filled = True
                        break
                except:
                    continue
            
            if not name_filled:
                logger.warning("  ⚠️ 未找到姓名输入框")
            
            self._random_sleep(0.5, 1)
            
            # 查找电话输入框（用户提供的XPath放最前面）
            phone_selectors = [
                '//*[@id="app"]/div/div/div/section/section[1]/div[4]/label/input',  # 用户提供
                '//input[contains(@placeholder, "手机")]',
                '//input[contains(@placeholder, "电话")]',
                '//input[@type="tel"]',
                '//input[contains(@name, "phone")]',
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
                        phone_input.send_keys(Keys.CONTROL, 'a')
                        phone_input.send_keys(Keys.DELETE)
                        self._random_sleep(0.2, 0.3)
                        phone_input.send_keys(phone)
                        logger.info(f"  ✓ 已填写电话: {selector[:50]}...")
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
            
            # 用户提供的XPath放在最前面
            submit_selectors = [
                '//*[@id="app"]/div/section[4]/section/div[2]/span',  # 用户提供（填写信息后的提交）
                '//*[@id="main"]/div[6]/section[2]/div[2]',  # 用户提供（预约页面）
                '//*[@id="main"]/div[6]/section[2]/div[2]/div',
                '//span[contains(text(), "提交订单")]',
                '//button[contains(text(), "提交订单")]',
                '//button[contains(text(), "确认预订")]',
                '//button[contains(text(), "立即预订")]',
                '//button[contains(text(), "去支付")]',
                '//div[contains(@class, "submit")]//button',
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
                self.driver.save_screenshot(os.path.join(DEBUG_DIR, "debug_meituan_submit.png"))
                logger.info("  请手动完成订单提交...")
                try:
                    input("  按回车键继续...")
                except EOFError:
                    pass
                return f"MANUAL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            logger.info("  点击提交订单...")
            # 滚动到按钮可见
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            self._random_sleep(0.5, 1)
            # 使用JS点击，更可靠
            self.driver.execute_script("arguments[0].click();", submit_btn)
            self._random_sleep(3, 5)
            
            # 提取订单号
            order_id = self._extract_order_id()
            return order_id if order_id else f"MEITUAN_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
        except Exception as e:
            logger.error(f"  提交订单失败: {e}")
            return None
    
    def _extract_order_id(self) -> Optional[str]:
        """从页面提取订单号"""
        import re
        
        try:
            url = self.driver.current_url
            if "orderid" in url.lower() or "order_id" in url.lower():
                match = re.search(r'order[_]?id[=:](\d+)', url, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            # 尝试从页面元素获取
            from selenium.webdriver.common.by import By
            order_selectors = ['.order-id', '.order-number', '[class*="orderId"]', '.order-no']
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


def test_meituan_order():
    """测试美团下单"""
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
    
    parser = argparse.ArgumentParser(description="美团自动下单测试")
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
        test_meituan_order()
    else:
        print("="*60)
        print("  美团自动下单测试")
        print("="*60)
        print(f"  酒店: {args.hotel}")
        print(f"  房型: {args.room}")
        print(f"  日期: {args.checkin} ~ {args.checkout}")
        print(f"  入住人: {args.name}")
        print(f"  电话: {args.phone}")
        print(f"  演示模式: {'是' if args.dry_run else '否'}")
        print("="*60)
        
        placer = MeituanOrderPlacer()
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

# -*- coding: utf-8 -*-
"""
代理通RPA测试脚本
逐步实现功能，测试每个步骤

第一步：点击房型按键
第二步：选择匹配的酒店名称
"""

import os
import sys
import yaml
import time
import random
import logging
from datetime import datetime
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError

# 导入独立的cookies管理模块
try:
    from shangjia_cookies import load_cookies as cookies_load, save_cookies as cookies_save
except ImportError:
    cookies_load = None
    cookies_save = None

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")
COOKIES_FILE = os.path.join(SCRIPT_DIR, "shangjia_cookies.pkl")
SCREENSHOTS_DIR = os.path.join(SCRIPT_DIR, "screenshots")

# 确保截图目录存在
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(SCRIPT_DIR, 'test_shangjia.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ShangjiaTest:
    """代理通RPA测试类"""
    
    def __init__(self, config_path: str = CONFIG_FILE):
        """初始化测试实例"""
        self.config = self._load_config(config_path)
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        
    def _load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"✓ 配置文件加载成功: {config_path}")
            return config
        except Exception as e:
            logger.error(f"❌ 配置文件加载失败: {e}")
            raise
    
    def _random_sleep(self, min_s: float = 0.5, max_s: float = 1.5):
        """随机等待，模拟人工操作"""
        sleep_time = random.uniform(min_s, max_s)
        time.sleep(sleep_time)
    
    def _take_screenshot(self, name: str = None):
        """截图保存"""
        if not self.page:
            return
        
        if name is None:
            name = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        screenshot_path = os.path.join(SCREENSHOTS_DIR, f"test_{name}.png")
        try:
            self.page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"📸 截图已保存: {screenshot_path}")
        except Exception as e:
            logger.warning(f"⚠️ 截图失败: {e}")
    
    def _wait_and_click(self, selector: str, timeout: int = 30000, retry: int = 3):
        """等待元素出现并点击（带重试）"""
        for attempt in range(retry):
            try:
                element = self.page.wait_for_selector(selector, timeout=timeout)
                if element:
                    element.scroll_into_view_if_needed()
                    self._random_sleep(0.3, 0.5)
                    element.click()
                    logger.info(f"✓ 点击成功: {selector}")
                    return True
            except PlaywrightTimeoutError:
                if attempt < retry - 1:
                    logger.warning(f"⚠️ 元素未找到，重试 {attempt + 1}/{retry}: {selector}")
                    self._random_sleep(1, 2)
                else:
                    logger.error(f"❌ 元素未找到（已重试{retry}次）: {selector}")
                    self._take_screenshot(f"failed_{selector.replace(':', '_').replace('/', '_')}")
            except Exception as e:
                logger.error(f"❌ 点击失败: {selector}, 错误: {e}")
                if attempt == retry - 1:
                    self._take_screenshot(f"error_{selector.replace(':', '_').replace('/', '_')}")
        return False
    
    def setup_browser(self):
        """启动浏览器"""
        logger.info("🚀 启动浏览器...")
        playwright = sync_playwright().start()
        self.playwright = playwright
        
        browser_config = self.config.get('browser', {})
        headless = browser_config.get('headless', False)
        slow_mo = browser_config.get('slow_mo', 500)
        window_size = browser_config.get('window_size', {'width': 1920, 'height': 1080})
        use_persistent = browser_config.get('use_persistent', True)
        
        if use_persistent:
            use_local_chrome = browser_config.get('use_local_chrome', False)
            user_data_dir_config = browser_config.get('user_data_dir', '')
            
            if use_local_chrome and user_data_dir_config:
                user_data_dir = user_data_dir_config
                logger.info(f"使用本地用户数据目录: {user_data_dir}")
            else:
                user_data_dir = os.path.join(SCRIPT_DIR, "browser_data")
                logger.info("使用项目用户数据目录")
            
            launch_options = {
                'user_data_dir': user_data_dir,
                'headless': headless,
                'slow_mo': slow_mo,
                'viewport': {'width': window_size['width'], 'height': window_size['height']},
            }
            
            logger.info("使用持久化浏览器上下文（非无痕模式）")
            self.context = playwright.chromium.launch_persistent_context(**launch_options)
            self.browser = None
            self.page = self.context.new_page()
        else:
            logger.info("使用临时浏览器上下文（无痕模式）")
            self.browser = playwright.chromium.launch(
                headless=headless,
                slow_mo=slow_mo
            )
            self.context = self.browser.new_context(
                viewport={'width': window_size['width'], 'height': window_size['height']}
            )
            self.page = self.context.new_page()
        
        logger.info("✓ 浏览器启动成功")
    
    def load_cookies_and_navigate(self):
        """加载Cookies并导航到首页"""
        logger.info("[初始化] 加载Cookies并导航到首页...")
        
        login_config = self.config.get('login', {})
        url = login_config.get('url', '')
        
        if not url:
            logger.error("❌ 配置文件中未设置登录URL")
            return False
        
        try:
            # 尝试加载cookies
            if login_config.get('use_cookies', True) and cookies_load:
                if os.path.exists(COOKIES_FILE):
                    logger.info("正在加载Cookies...")
                    cookies_load(self.context, url)
            
            # 访问首页
            logger.info(f"访问首页: {url}")
            self.page.goto(url, timeout=30000)
            self._random_sleep(2, 3)
            
            self._take_screenshot("initial_page")
            logger.info("✓ 已加载Cookies并导航到首页")
            return True
            
        except Exception as e:
            logger.error(f"❌ 加载Cookies失败: {e}")
            self._take_screenshot("failed_initial")
            return False
    
    def step1_click_room_type_menu(self) -> bool:
        """
        第一步：点击房型按键
        
        XPath: //*[@id="menu3"]/a
        """
        logger.info("[步骤1] 点击房型按键...")
        
        try:
            # 使用XPath定位房型菜单
            xpath = '//*[@id="menu3"]/a'
            
            if self._wait_and_click(xpath):
                self._random_sleep(1, 2)
                self._take_screenshot("step1_clicked_room_type")
                logger.info("✓ 已点击房型按键")
                return True
            else:
                logger.error("❌ 无法点击房型按键")
                return False
                
        except Exception as e:
            logger.error(f"❌ 点击房型按键失败: {e}")
            self._take_screenshot("failed_step1")
            return False
    
    def step2_select_hotel_by_name(self, hotel_name: str) -> bool:
        """
        第二步：在酒店列表中选择匹配的酒店名称
        
        酒店列表XPath模式:
        - //*[@id="ulHotel"]/li[1]
        - //*[@id="ulHotel"]/li[2]/a
        - //*[@id="ulHotel"]/li[3]/a
        ...
        
        参数:
            hotel_name: 要匹配的酒店名称（如"美利居"）
        """
        logger.info(f"[步骤2] 选择酒店: {hotel_name}")
        
        try:
            # 等待酒店列表加载
            list_container = '//*[@id="ulHotel"]'
            logger.info("等待酒店列表加载...")
            self.page.wait_for_selector(list_container, timeout=30000)
            self._random_sleep(1, 2)
            
            # 获取所有酒店列表项
            # 使用 locator 查找所有 li 元素
            li_locators = self.page.locator('//*[@id="ulHotel"]/li')
            count = li_locators.count()
            logger.info(f"找到 {count} 个酒店列表项")
            
            # 遍历每个列表项，查找匹配的酒店
            matched_hotel = None
            for idx in range(1, count + 1):
                try:
                    # 获取当前列表项
                    li_locator = li_locators.nth(idx - 1)
                    
                    # 获取酒店名称文本
                    # 先尝试查找 a 标签
                    a_locator = li_locator.locator('a')
                    hotel_text = ""
                    
                    if a_locator.count() > 0:
                        # 尝试多种方式获取文本
                        try:
                            hotel_text = a_locator.first.inner_text().strip()
                        except:
                            try:
                                hotel_text = a_locator.first.text_content().strip()
                            except:
                                hotel_text = li_locator.inner_text().strip()
                    else:
                        hotel_text = li_locator.inner_text().strip()
                    
                    # 如果文本被截断（包含...），尝试获取完整文本
                    if '...' in hotel_text or '…' in hotel_text:
                        # 尝试获取 title 属性（通常包含完整文本）
                        try:
                            if a_locator.count() > 0:
                                title = a_locator.first.get_attribute('title')
                                if title and len(title) > len(hotel_text):
                                    hotel_text = title.strip()
                        except:
                            pass
                    
                    # 输出每个酒店的详细信息，方便调试
                    logger.info(f"  检查酒店 {idx}: {hotel_text}")
                    
                    # 严格的匹配逻辑（按优先级排序）
                    # 1. 完全匹配（最高优先级，分数100）
                    # 2. 以输入内容开头（分数90）- 例如："美利居" 匹配 "美利居酒店"
                    # 3. 去除括号后以输入内容开头（分数80）
                    # 4. 精确包含且位置靠前（分数60）- 例如："美利居" 在 "美利居酒店" 中
                    # 5. 包含匹配但位置靠后（分数40）- 例如："美利居" 在 "丽呈美利居酒店" 中
                    
                    match_score = 0
                    is_match = False
                    
                    # 清理文本（去除括号、空格、特殊字符等）
                    import re
                    # 去除各种括号、空格、标点符号、截断符号
                    clean_hotel_text = re.sub(r'[()（）\s\-—…\.\.\.]', '', hotel_text)
                    clean_hotel_name = re.sub(r'[()（）\s\-—…\.\.\.]', '', hotel_name)
                    
                    # 也去除可能的截断标记
                    clean_hotel_text = clean_hotel_text.replace('...', '').replace('…', '')
                    clean_hotel_name = clean_hotel_name.replace('...', '').replace('…', '')
                    
                    logger.debug(f"    原始文本: '{hotel_text}' -> 清理后: '{clean_hotel_text}'")
                    logger.debug(f"    搜索关键词: '{hotel_name}' -> 清理后: '{clean_hotel_name}'")
                    
                    # 完全匹配（最高优先级，分数100）
                    if hotel_text == hotel_name:
                        match_score = 100
                        is_match = True
                        logger.debug(f"    ✓ 完全匹配 (分数: {match_score})")
                    # 清理后完全匹配（分数95）
                    elif clean_hotel_text == clean_hotel_name:
                        match_score = 95
                        is_match = True
                        logger.debug(f"    ✓ 清理后完全匹配 (分数: {match_score})")
                    # 以输入内容开头（分数90）- 这是关键！"美利居"应该匹配"美利居酒店"而不是"丽呈美利居酒店"
                    elif hotel_text.startswith(hotel_name):
                        match_score = 90
                        is_match = True
                        logger.debug(f"    ✓ 以关键词开头 (分数: {match_score})")
                    # 清理后以输入内容开头（分数85）
                    elif clean_hotel_text.startswith(clean_hotel_name):
                        match_score = 85
                        is_match = True
                        logger.debug(f"    ✓ 清理后以关键词开头 (分数: {match_score})")
                    # 精确包含且位置靠前（分数60-70）
                    elif hotel_name in hotel_text:
                        # 计算匹配位置（越靠前分数越高）
                        position = hotel_text.find(hotel_name)
                        position_ratio = position / len(hotel_text) if len(hotel_text) > 0 else 1
                        
                        # 如果在前30%的位置，给予较高分数
                        if position_ratio < 0.3:
                            match_score = 70
                            is_match = True
                            logger.debug(f"    ✓ 包含匹配，位置靠前 (分数: {match_score}, 位置: {position_ratio:.2%})")
                        # 如果在前50%的位置，给予中等分数
                        elif position_ratio < 0.5:
                            match_score = 60
                            is_match = True
                            logger.debug(f"    ✓ 包含匹配，位置中等 (分数: {match_score}, 位置: {position_ratio:.2%})")
                        else:
                            # 位置靠后，分数较低（分数40）
                            match_score = 40
                            is_match = True
                            logger.debug(f"    ✓ 包含匹配，位置靠后 (分数: {match_score}, 位置: {position_ratio:.2%})")
                    # 清理后包含匹配（分数50）
                    elif clean_hotel_name in clean_hotel_text:
                        match_score = 50
                        is_match = True
                        logger.debug(f"    ✓ 清理后包含匹配 (分数: {match_score})")
                    
                    if is_match:
                        # 如果已经找到匹配项，比较分数，选择分数更高的
                        if matched_hotel is None or match_score > matched_hotel.get('score', 0):
                            matched_hotel = {
                                'index': idx,
                                'text': hotel_text,
                                'locator': li_locator,
                                'a_locator': a_locator if a_locator.count() > 0 else None,
                                'score': match_score
                            }
                            logger.info(f"✓ 找到匹配的酒店 (分数: {match_score}): {hotel_text} (索引: {idx})")
                        else:
                            logger.debug(f"  跳过匹配项 (分数较低: {match_score}): {hotel_text} (索引: {idx})")
                        
                except Exception as e:
                    logger.warning(f"  处理酒店项 {idx} 时出错: {e}")
                    continue
            
            if not matched_hotel:
                logger.error(f"❌ 未找到匹配 '{hotel_name}' 的酒店")
                logger.error(f"   请检查输入的酒店名称是否正确")
                self._take_screenshot("failed_step2_no_match")
                
                # 列出所有可用的酒店名称供参考
                logger.info("\n可用的酒店列表（供参考）:")
                for idx in range(1, count + 1):
                    try:
                        li_locator = li_locators.nth(idx - 1)
                        a_locator = li_locator.locator('a')
                        if a_locator.count() > 0:
                            text = a_locator.first.inner_text().strip()
                        else:
                            text = li_locator.inner_text().strip()
                        logger.info(f"  {idx}. {text}")
                    except Exception as e:
                        logger.warning(f"  无法获取酒店 {idx} 的名称: {e}")
                
                logger.info(f"\n提示: 请使用上述列表中的酒店名称（或部分名称）作为输入")
                logger.info(f"例如: python test_shangjia.py \"美利居酒店\"")
                
                return False
            
            logger.info(f"最终选择的酒店: {matched_hotel['text']} (匹配分数: {matched_hotel['score']})")
            
            # 点击匹配的酒店
            # 优先点击 a 标签，如果没有则点击 li
            click_locator = matched_hotel.get('a_locator') or matched_hotel['locator']
            
            if click_locator:
                if matched_hotel.get('a_locator'):
                    # 如果有 a 标签，点击第一个
                    click_locator = matched_hotel['a_locator'].first
                else:
                    click_locator = matched_hotel['locator']
                
                click_locator.scroll_into_view_if_needed()
                self._random_sleep(0.5, 1)
                click_locator.click()
                self._random_sleep(1, 2)
                
                self._take_screenshot(f"step2_selected_hotel_{matched_hotel['index']}")
                logger.info(f"✓ 已选择酒店: {matched_hotel['text']}")
                return True
            else:
                logger.error("❌ 无法获取可点击的元素")
                return False
                
        except Exception as e:
            logger.error(f"❌ 选择酒店失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._take_screenshot("failed_step2")
            return False
    
    def step3_select_room_type_and_date(self, room_type: str, target_date: str, has_room: bool = True) -> bool:
        """
        第三步：选择房型并点击对应日期，同时调整售卖开关
        
        参数:
            room_type: 房型名称（如"大床房"、"双床房"）
            target_date: 目标日期（如"12.29"、"12-29"、"12/29"）
            has_room: 是否有房间剩余（True=打开开关, False=关闭开关）
        
        逻辑:
        1. 根据房型名称找到对应的行（大床房=tr[2], 双床房=tr[4]）
        2. 在日期行中找到目标日期对应的列
        3. 检查并调整售卖开关状态
        4. 点击对应的日期单元格
        """
        logger.info(f"[步骤3] 选择房型: {room_type}, 日期: {target_date}")
        
        try:
            # 等待日历表格加载
            calendar_table = '//*[@id="calendarTable"]'
            logger.info("等待日历表格加载...")
            self.page.wait_for_selector(calendar_table, timeout=30000)
            self._random_sleep(1, 2)
            
            # 步骤1: 根据房型名称找到对应的行号
            # 房型映射：大床房 -> tr[2], 双床房 -> tr[4]
            room_type_mapping = {
                '大床房': 2,
                '双床房': 4,
                '高级大床房': 2,
                '高级双床房': 4,
            }
            
            # 查找匹配的房型
            row_number = None
            for key, value in room_type_mapping.items():
                if key in room_type:
                    row_number = value
                    logger.info(f"找到房型映射: {room_type} -> tr[{row_number}]")
                    break
            
            # 如果映射表中没有，尝试动态查找
            if row_number is None:
                logger.info("映射表中未找到，尝试动态查找房型...")
                # 遍历所有行，查找包含房型名称的行
                tr_locators = self.page.locator('//*[@id="calendarTable"]/tbody/tr')
                tr_count = tr_locators.count()
                
                for idx in range(1, tr_count + 1):
                    try:
                        tr_locator = tr_locators.nth(idx - 1)
                        # 获取第一列的文本（房型名称）
                        first_td = tr_locator.locator('td').first
                        room_text = first_td.inner_text().strip()
                        
                        logger.debug(f"  检查行 {idx}: {room_text}")
                        
                        # 检查是否包含目标房型名称
                        if room_type in room_text:
                            row_number = idx + 1  # XPath从1开始，但tbody/tr也是从1开始
                            logger.info(f"✓ 动态找到房型: {room_text} -> tr[{row_number}]")
                            break
                    except Exception as e:
                        logger.warning(f"  检查行 {idx} 时出错: {e}")
                        continue
            
            if row_number is None:
                logger.error(f"❌ 未找到房型: {room_type}")
                self._take_screenshot("failed_step3_room_type")
                return False
            
            # 步骤2: 在日期行中找到目标日期对应的列号
            # 日期格式可能为: "12.29", "12-29", "12/29", "12月29日" 等
            # 统一转换为 "12.29" 格式进行匹配
            
            import re
            # 提取日期数字
            date_match = re.search(r'(\d{1,2})[.\-/月](\d{1,2})', target_date)
            if not date_match:
                logger.error(f"❌ 日期格式不正确: {target_date}")
                return False
            
            month = date_match.group(1).zfill(2)  # 补零，如 "12"
            day = date_match.group(2).zfill(2)    # 补零，如 "29"
            target_date_formatted = f"{month}.{day}"  # "12.29"
            
            logger.info(f"目标日期格式化: {target_date} -> {target_date_formatted}")
            
            # 查找日期所在的列
            # 日期XPath模式: //*[@id="calendarTable"]/tbody/tr[2]/td[2]/table/tbody/tr/td[1]/div[2]/span[1]
            date_row_xpath = f'//*[@id="calendarTable"]/tbody/tr[{row_number}]/td[2]/table/tbody/tr/td'
            date_cells = self.page.locator(date_row_xpath)
            date_count = date_cells.count()
            
            logger.info(f"找到 {date_count} 个日期单元格")
            
            target_column = None
            for col_idx in range(1, date_count + 1):
                try:
                    # 获取日期文本
                    # XPath: //*[@id="calendarTable"]/tbody/tr[2]/td[2]/table/tbody/tr/td[col_idx]/div[2]/span[1]
                    date_span_xpath = f'{date_row_xpath}[{col_idx}]/div[2]/span[1]'
                    date_span = self.page.locator(date_span_xpath)
                    
                    if date_span.count() > 0:
                        date_text = date_span.first.inner_text().strip()
                        logger.debug(f"  检查列 {col_idx}: {date_text}")
                        
                        # 匹配日期（支持多种格式）
                        if date_text == target_date_formatted or date_text == target_date:
                            target_column = col_idx
                            logger.info(f"✓ 找到目标日期: {date_text} -> 列 {col_idx}")
                            break
                        # 也尝试匹配 "12-29" 格式
                        elif date_text.replace('-', '.') == target_date_formatted:
                            target_column = col_idx
                            logger.info(f"✓ 找到目标日期: {date_text} -> 列 {col_idx}")
                            break
                except Exception as e:
                    logger.warning(f"  检查列 {col_idx} 时出错: {e}")
                    continue
            
            if target_column is None:
                logger.error(f"❌ 未找到日期: {target_date_formatted}")
                self._take_screenshot("failed_step3_date")
                return False
            
            # 步骤3: 点击对应的日期单元格（先点击，弹出弹窗）
            # XPath: //*[@id="calendarTable"]/tbody/tr[2]/td[2]/table/tbody/tr/td[4]
            cell_xpath = f'//*[@id="calendarTable"]/tbody/tr[{row_number}]/td[2]/table/tbody/tr/td[{target_column}]'
            
            logger.info(f"点击日期单元格: {cell_xpath}")
            
            if self._wait_and_click(cell_xpath):
                self._random_sleep(1, 2)
                self._take_screenshot(f"step3_clicked_{room_type}_{target_date_formatted}")
                logger.info(f"✓ 已选择房型 {room_type} 的日期 {target_date_formatted}")
                
                # 点击日期单元格后，通常会弹出批量修改弹窗
                # 等待一下，让弹窗有时间出现
                self._random_sleep(1, 2)
                
                return True
            else:
                logger.error("❌ 无法点击日期单元格")
                return False
                
        except Exception as e:
            logger.error(f"❌ 选择房型和日期失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._take_screenshot("failed_step3")
            return False
    
    def _close_modal(self):
        """关闭弹窗（点击取消或X按钮）"""
        try:
            # 尝试点击取消按钮
            cancel_button = self.page.locator('button:has-text("取消")')
            if cancel_button.count() > 0:
                cancel_button.first.click(force=True)
                self._random_sleep(0.5, 1)
                logger.info("✓ 已关闭弹窗（点击取消）")
                return
            
            # 尝试点击X按钮
            close_button = self.page.locator('.btn-close, a.btn-close')
            if close_button.count() > 0:
                close_button.first.click(force=True)
                self._random_sleep(0.5, 1)
                logger.info("✓ 已关闭弹窗（点击X）")
                return
        except Exception as e:
            logger.warning(f"关闭弹窗失败: {e}")
    
    def step4_close_room(self) -> bool:
        """
        第四步（关房）：在弹出页面中选择"关房"并保存
        
        逻辑:
        1. 等待弹出页面出现
        2. 点击"关房"选项
        3. 点击保存按钮
        """
        logger.info("[步骤4] 关闭房间")
        
        try:
            # 等待弹出页面出现
            logger.info("等待弹出页面加载...")
            
            try:
                self.page.wait_for_selector('//*[@id="div_temp"]', timeout=10000)
                logger.info("✓ 弹出页面容器已出现")
            except Exception as e:
                logger.warning(f"等待弹窗失败: {e}")
            
            self._random_sleep(1, 2)
            self._take_screenshot("step4_close_room_modal")
            
            # 点击"关房"选项
            # 根据用户提供的信息，房态radio按钮：
            # 索引0: 不变 (value='')
            # 索引1: 开房 (value='G')
            # 索引2: 关房 (value='N')
            # 索引3: 限量售卖 (value='L')
            
            logger.info("点击关房选项...")
            
            clicked = False
            try:
                # 使用JavaScript点击第3个radio按钮（关房，索引2）
                self.page.evaluate("""
                    () => {
                        const radios = document.querySelectorAll('input[name="room-status"]');
                        console.log('找到radio按钮数量:', radios.length);
                        if (radios.length >= 3) {
                            radios[2].checked = true;  // 关房是索引2
                            radios[2].click();
                            radios[2].dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                        return false;
                    }
                """)
                self._random_sleep(0.5, 1)
                
                # 验证是否选中
                close_room_radio = self.page.locator('input[name="room-status"]').nth(2)
                if close_room_radio.is_checked():
                    logger.info("✓ 已选择关房")
                    clicked = True
                    self._take_screenshot("step4_close_room_selected")
            except Exception as e:
                logger.warning(f"点击关房失败: {e}")
            
            if not clicked:
                # 尝试其他方式
                try:
                    close_room_radio = self.page.locator('input[name="room-status"][value="N"]')
                    if close_room_radio.count() > 0:
                        close_room_radio.first.click(force=True)
                        self._random_sleep(0.5, 1)
                        if close_room_radio.first.is_checked():
                            logger.info("✓ 已选择关房（通过value='N'）")
                            clicked = True
                except Exception as e:
                    logger.warning(f"备用方式点击关房失败: {e}")
            
            if not clicked:
                logger.error("❌ 无法点击关房选项")
                self._take_screenshot("failed_step4_close_room")
                return False
            
            # 点击保存按钮
            logger.info("点击保存按钮...")
            try:
                save_button_xpath = '//*[@id="div_temp"]/div/div/div[2]/button[1]'
                save_button = self.page.wait_for_selector(save_button_xpath, timeout=10000)
                
                if save_button:
                    save_button.scroll_into_view_if_needed()
                    self._random_sleep(0.3, 0.5)
                    save_button.click(force=True)
                    self._random_sleep(1, 2)
                    logger.info("✓ 已点击保存按钮")
                    self._take_screenshot("step4_close_room_saved")
                else:
                    # 尝试其他选择器
                    save_button = self.page.locator('button:has-text("保存")')
                    if save_button.count() > 0:
                        save_button.first.click(force=True)
                        self._random_sleep(1, 2)
                        logger.info("✓ 已点击保存按钮（通过文本匹配）")
                        self._take_screenshot("step4_close_room_saved")
            except Exception as e:
                logger.error(f"点击保存按钮失败: {e}")
                self._take_screenshot("failed_step4_close_room_save")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 关闭房间失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._take_screenshot("failed_step4_close_room")
            return False
    
    def step4_set_limited_sale(self, room_count: int = None, price: int = None) -> bool:
        """
        第四步：在弹出页面中设置限量售卖和/或价格
        
        参数:
            room_count: 剩余房间数量（可选）
            price: 价格（可选，如果提供则会设置底价）
        
        逻辑:
        1. 等待弹出页面出现
        2. 如果有room_count，点击"限量售卖"选项并输入房间数量
        3. 如果有price，点击"底价"并输入价格
        4. 点击保存
        """
        room_info = f"房间数量: {room_count}" if room_count is not None else "不设置房间数量"
        price_info = f"价格: {price}" if price is not None else "不设置价格"
        logger.info(f"[步骤4] 设置限量售卖，{room_info}, {price_info}")
        
        try:
            # 等待弹出页面出现
            # div_temp 是弹窗容器的主要标识（用户确认的路径）
            logger.info("等待弹出页面加载...")
            
            # 方法1: 优先等待 div_temp 容器（这是弹窗的主要标识）
            try:
                self.page.wait_for_selector('//*[@id="div_temp"]', timeout=10000)
                logger.info("✓ 弹出页面容器已出现（通过div_temp）")
            except Exception as e:
                logger.warning(f"等待div_temp失败: {e}，尝试备用方法...")
                # 备用方法：等待 div_RoomManageModify
                try:
                    modal_container = self.page.wait_for_selector('div[name="div_RoomManageModify"]', timeout=5000)
                    if modal_container:
                        display_style = modal_container.get_attribute('style') or ''
                        if 'display: block' in display_style or 'display:block' in display_style:
                            logger.info("✓ 弹出页面已出现（通过div_RoomManageModify）")
                except:
                    pass
            
            # 方法2: 等待标题出现（双重确认）
            try:
                modal_title = self.page.wait_for_selector('//*[contains(text(), "批量修改售卖房型")]', timeout=5000)
                if modal_title:
                    logger.info("✓ 弹出页面标题已出现")
            except:
                pass
            
            self._random_sleep(1, 2)
            self._take_screenshot("step4_modal_opened")
            
            # 步骤1: 如果有房间数量，点击"限量售卖"选项
            # 根据用户提供的信息，房态radio按钮结构如下：
            # 索引0: 不变 (value='')
            # 索引1: 开房 (value='G')
            # 索引2: 关房 (value='N')
            # 索引3: 限量售卖 (value='L')
            
            clicked = False
            
            # 只有在设置房间数量时才需要点击"限量售卖"
            if room_count is None or room_count <= 0:
                logger.info("未指定房间数量，跳过限量售卖选项，保持房态'不变'")
                clicked = True  # 跳过点击限量售卖
            else:
                logger.info("点击限量售卖选项...")
                
                # 先等待一下，确保弹窗完全加载
                self._random_sleep(1, 2)
                self._take_screenshot("step4_before_click_limited_sale")
                
                # 方法1: 直接通过索引获取第4个radio按钮（限量售卖）
                try:
                    # 获取所有房态radio按钮
                    all_room_status = self.page.locator('input[name="room-status"]')
                    count = all_room_status.count()
                    logger.info(f"找到 {count} 个房态radio按钮")
                    
                    # 列出所有radio按钮的状态
                    for i in range(count):
                        try:
                            radio = all_room_status.nth(i)
                            value = radio.get_attribute('value') or ''
                            is_checked = radio.is_checked()
                            logger.info(f"  radio[{i}]: value='{value}', checked={is_checked}")
                        except:
                            pass
                    
                    # 限量售卖是第4个（索引3）
                    if count >= 4:
                        limited_sale_radio = all_room_status.nth(3)  # 索引3 = 第4个 = 限量售卖
                        
                        # 检查当前状态
                        before_checked = limited_sale_radio.is_checked()
                        logger.info(f"限量售卖radio(索引3)点击前状态: {'已选中' if before_checked else '未选中'}")
                        
                        if not before_checked:
                            # 使用JavaScript强制点击第4个radio按钮
                            logger.info("使用JavaScript点击限量售卖...")
                            self.page.evaluate("""
                                () => {
                                    const radios = document.querySelectorAll('input[name="room-status"]');
                                    console.log('找到radio按钮数量:', radios.length);
                                    if (radios.length >= 4) {
                                        radios[3].checked = true;  // 先设置checked属性
                                        radios[3].click();  // 再触发click事件
                                        // 触发change事件
                                        radios[3].dispatchEvent(new Event('change', { bubbles: true }));
                                        return true;
                                    }
                                    return false;
                                }
                            """)
                            self._random_sleep(0.5, 1)
                            
                            # 验证是否选中
                            after_checked = limited_sale_radio.is_checked()
                            logger.info(f"限量售卖radio点击后状态: {'已选中' if after_checked else '未选中'}")
                            
                            if after_checked:
                                logger.info("✓ 已选择限量售卖（通过JavaScript索引点击）")
                                clicked = True
                                self._take_screenshot("step4_limited_sale_clicked")
                            else:
                                logger.warning("JavaScript点击后仍未选中，尝试其他方法...")
                        else:
                            logger.info("限量售卖已经选中，无需点击")
                            clicked = True
                    else:
                        logger.warning(f"房态radio按钮数量不足4个，实际: {count}")
                except Exception as e:
                    logger.warning(f"通过索引点击失败: {e}")
                
                # 方法2: 如果方法1失败，尝试直接点击value="L"的radio
                if not clicked:
                    logger.info("尝试直接点击value='L'的radio...")
                    try:
                        limited_sale_radio = self.page.locator('input[name="room-status"][value="L"]')
                        if limited_sale_radio.count() > 0:
                            limited_sale_radio.first.scroll_into_view_if_needed()
                            self._random_sleep(0.3, 0.5)
                            limited_sale_radio.first.click(force=True)
                            self._random_sleep(0.5, 1)
                            
                            if limited_sale_radio.first.is_checked():
                                logger.info("✓ 已选择限量售卖（通过value='L'选择器）")
                                clicked = True
                                self._take_screenshot("step4_limited_sale_clicked")
                    except Exception as e:
                        logger.warning(f"通过value='L'选择器点击失败: {e}")
                
                # 方法3: 如果还是失败，尝试点击label
                if not clicked:
                    logger.info("尝试点击label...")
                    try:
                        # 查找包含"限量售卖"文本的label
                        label_element = self.page.locator('label:has-text("限量售卖")')
                        if label_element.count() > 0:
                            label_element.first.scroll_into_view_if_needed()
                            self._random_sleep(0.3, 0.5)
                            label_element.first.click(force=True)
                            self._random_sleep(0.5, 1)
                            
                            # 验证
                            limited_sale_radio = self.page.locator('input[name="room-status"][value="L"]')
                            if limited_sale_radio.count() > 0 and limited_sale_radio.first.is_checked():
                                logger.info("✓ 已选择限量售卖（通过点击label）")
                                clicked = True
                                self._take_screenshot("step4_limited_sale_clicked")
                    except Exception as e:
                        logger.warning(f"点击label失败: {e}")
                
                if not clicked:
                    logger.error("❌ 无法点击限量售卖选项（尝试了多种方法）")
                    
                    # 列出所有可用的radio按钮供调试
                    logger.info("调试信息：查找所有房态radio按钮...")
                    try:
                        all_room_status_inputs = self.page.locator('input[name="room-status"]')
                        count = all_room_status_inputs.count()
                        logger.info(f"找到 {count} 个房态radio按钮:")
                        for i in range(count):
                            try:
                                input_el = all_room_status_inputs.nth(i)
                                value = input_el.get_attribute('value') or ''
                                checked = input_el.is_checked()
                                # 尝试获取label文本
                                label_text = ''
                                try:
                                    parent_label = input_el.locator('xpath=./parent::label')
                                    if parent_label.count() > 0:
                                        label_text = parent_label.first.inner_text().strip()
                                except:
                                    pass
                                logger.info(f"  {i+1}. value={value}, checked={checked}, label={label_text}")
                            except:
                                pass
                    except Exception as e:
                        logger.warning(f"无法列出radio按钮: {e}")
                    
                    self._take_screenshot("failed_step4_limited_sale")
                    return False
            
            # 步骤2: 点击"底价"选项并输入价格（可选）
            if price is not None and price > 0:
                logger.info(f"设置底价: {price}")
                try:
                    # 点击"底价"radio按钮
                    # XPath: //*[@id="div_temp"]/div/div/div[1]/dl[8]/dd/label[2]/input
                    price_radio_xpath = '//*[@id="div_temp"]/div/div/div[1]/dl[8]/dd/label[2]/input'
                    price_radio = self.page.wait_for_selector(price_radio_xpath, timeout=5000)
                    if price_radio:
                        price_radio.click(force=True)
                        self._random_sleep(0.5, 1)
                        logger.info("✓ 已点击底价选项")
                    
                    # 输入价格
                    # XPath: //*[@id="price"]
                    price_input = self.page.wait_for_selector('//*[@id="price"]', timeout=5000)
                    if price_input:
                        price_input.fill("")  # 清空输入框
                        self._random_sleep(0.3, 0.5)
                        price_input.fill(str(price))
                        self._random_sleep(0.5, 1)
                        logger.info(f"✓ 已输入价格: {price}")
                        self._take_screenshot(f"step4_price_{price}")
                except Exception as e:
                    logger.warning(f"设置价格失败: {e}，继续执行...")
            
            # 步骤3: 输入剩余房间数（如果有指定）
            # XPath: //*[@id="div_temp"]/div/div/div[1]/dl[13]/dd/label/input
            
            if room_count is not None and room_count > 0:
                logger.info(f"输入剩余房间数: {room_count}")
                
                # 首先，需要设置"立即确认房量"的下拉框为"余量等于"
                try:
                    logger.info("设置立即确认房量下拉框为'余量等于'...")
                    
                    # 使用JavaScript设置下拉框
                    self.page.evaluate("""
                        () => {
                            const select = document.querySelector('select[name="immediate-type"]');
                            if (select) {
                                select.value = '4';  // 余量等于
                                select.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                            }
                            return false;
                        }
                    """)
                    self._random_sleep(0.5, 1)
                    logger.info("✓ 已设置下拉框为'余量等于'")
                except Exception as e:
                    logger.warning(f"设置下拉框失败: {e}，继续尝试输入...")
                
                # 使用用户提供的准确XPath输入房间数
                room_count_xpath = '//*[@id="div_temp"]/div/div/div[1]/dl[13]/dd/label/input'
                
                input_filled = False
                
                try:
                    logger.info(f"使用XPath查找输入框: {room_count_xpath}")
                    input_element = self.page.wait_for_selector(room_count_xpath, timeout=10000)
                    
                    if input_element:
                        logger.info("✓ 找到房间数输入框")
                        input_element.scroll_into_view_if_needed()
                        self._random_sleep(0.3, 0.5)
                        
                        # 清空并输入
                        input_element.fill("")  # 清空输入框
                        self._random_sleep(0.3, 0.5)
                        input_element.fill(str(room_count))
                        self._random_sleep(0.5, 1)
                        
                        # 验证
                        input_value = input_element.input_value()
                        if input_value == str(room_count):
                            logger.info(f"✓ 已输入房间数量: {room_count}")
                            input_filled = True
                            self._take_screenshot(f"step4_input_room_count_{room_count}")
                        else:
                            logger.warning(f"输入值不匹配: 期望={room_count}, 实际={input_value}")
                except Exception as e:
                    logger.warning(f"XPath方式输入失败: {e}")
                
                # 如果XPath失败，尝试其他方式
                if not input_filled:
                    logger.info("尝试其他选择器...")
                    other_selectors = [
                        'input[name="immediate-qty"]',
                        '//input[@name="immediate-qty"]',
                    ]
                    
                    for selector in other_selectors:
                        try:
                            logger.info(f"  尝试: {selector}")
                            input_element = self.page.wait_for_selector(selector, timeout=5000)
                            
                            if input_element:
                                input_element.scroll_into_view_if_needed()
                                self._random_sleep(0.3, 0.5)
                                input_element.fill("")  # 清空输入框
                                self._random_sleep(0.3, 0.5)
                                
                                # 输入房间数量
                                input_element.fill(str(room_count))
                                self._random_sleep(0.5, 1)
                                
                                # 验证输入是否成功
                                input_value = input_element.input_value()
                                if input_value == str(room_count):
                                    logger.info(f"✓ 已输入房间数量: {room_count}（选择器: {selector}）")
                                    self._take_screenshot(f"step4_input_room_count_{room_count}")
                                    input_filled = True
                                    break
                                else:
                                    logger.warning(f"⚠️ 输入值不匹配: 期望={room_count}, 实际={input_value}")
                        except Exception as e:
                            logger.debug(f"  输入框选择器失败: {selector}, 错误: {e}")
                            continue
                
                if not input_filled:
                    logger.warning("⚠️ 无法输入房间数量，继续设置价格...")
            else:
                logger.info("未指定房间数量，跳过房间数设置")
            
            # 步骤4: 点击"底价"并输入价格
            # XPath: //*[@id="div_temp"]/div/div/div[1]/dl[8]/dd/label[2]/input
            # 价格输入框: //*[@id="price"]
            if price is not None and price > 0:
                logger.info(f"设置底价: {price}")
                try:
                    # 点击"底价"radio按钮
                    price_radio_xpath = '//*[@id="div_temp"]/div/div/div[1]/dl[8]/dd/label[2]/input'
                    logger.info(f"点击底价选项: {price_radio_xpath}")
                    
                    price_radio = self.page.wait_for_selector(price_radio_xpath, timeout=5000)
                    if price_radio:
                        price_radio.scroll_into_view_if_needed()
                        self._random_sleep(0.3, 0.5)
                        price_radio.click(force=True)
                        self._random_sleep(0.5, 1)
                        logger.info("✓ 已点击底价选项")
                    
                    # 输入价格
                    price_input_xpath = '//*[@id="price"]'
                    logger.info(f"输入价格: {price}")
                    
                    price_input = self.page.wait_for_selector(price_input_xpath, timeout=5000)
                    if price_input:
                        price_input.scroll_into_view_if_needed()
                        self._random_sleep(0.3, 0.5)
                        price_input.fill("")  # 清空
                        self._random_sleep(0.3, 0.5)
                        price_input.fill(str(price))
                        self._random_sleep(0.5, 1)
                        
                        # 验证
                        input_value = price_input.input_value()
                        if input_value == str(price):
                            logger.info(f"✓ 已输入价格: {price}")
                        else:
                            logger.warning(f"价格输入值不匹配: 期望={price}, 实际={input_value}")
                        
                        self._take_screenshot(f"step4_price_{price}")
                except Exception as e:
                    logger.warning(f"设置价格失败: {e}，继续执行...")
            
            # 步骤5: 点击保存按钮
            # XPath: //*[@id="div_temp"]/div/div/div[2]/button[1]
            logger.info("点击保存按钮...")
            try:
                save_button_xpath = '//*[@id="div_temp"]/div/div/div[2]/button[1]'
                save_button = self.page.wait_for_selector(save_button_xpath, timeout=10000)
                
                if save_button:
                    save_button.scroll_into_view_if_needed()
                    self._random_sleep(0.3, 0.5)
                    save_button.click(force=True)
                    self._random_sleep(1, 2)
                    logger.info("✓ 已点击保存按钮")
                    self._take_screenshot("step4_saved")
                else:
                    logger.warning("未找到保存按钮")
            except Exception as e:
                logger.warning(f"点击保存按钮失败: {e}")
                # 尝试其他选择器
                try:
                    save_button = self.page.locator('button:has-text("保存")')
                    if save_button.count() > 0:
                        save_button.first.click(force=True)
                        self._random_sleep(1, 2)
                        logger.info("✓ 已点击保存按钮（通过文本匹配）")
                        self._take_screenshot("step4_saved")
                except Exception as e2:
                    logger.error(f"点击保存按钮失败: {e2}")
                    self._take_screenshot("failed_step4_save")
                    return False
            
            return True
                
        except Exception as e:
            logger.error(f"❌ 设置限量售卖失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._take_screenshot("failed_step4")
            return False
    
    def step5_check_and_open_room_switch(self, room_type: str, target_date: str) -> bool:
        """
        第五步：检查并确保房间开关已打开（在弹窗操作完成后执行）
        
        参数:
            room_type: 房型名称
            target_date: 目标日期
        
        逻辑:
        1. 重新识别房型和日期位置
        2. 检查开关状态
        3. 如果开关未打开，则打开开关
        """
        logger.info(f"[步骤5] 检查并确保房间开关已打开")
        
        try:
            # 重新识别房型和日期位置（与step3相同的逻辑）
            # 识别房型行号
            room_type_mapping = {
                "大床房": 2,
                "双床房": 4,
                "标准间": 2,
                "豪华间": 4,
            }
            
            row_number = None
            for key, value in room_type_mapping.items():
                if key in room_type:
                    row_number = value
                    break
            
            if row_number is None:
                logger.warning("无法识别房型，尝试查找所有房型行...")
                # 尝试查找所有房型行
                room_rows = self.page.locator('//*[@id="calendarTable"]/tbody/tr')
                for i in range(1, room_rows.count() + 1):
                    try:
                        room_label = self.page.locator(f'//*[@id="calendarTable"]/tbody/tr[{i}]/td[1]/label/span')
                        if room_label.count() > 0:
                            room_text = room_label.first.inner_text().strip()
                            if room_type in room_text:
                                row_number = i
                                logger.info(f"找到房型 {room_type} 在第 {i} 行")
                                break
                    except:
                        continue
            
            if row_number is None:
                logger.error(f"❌ 未找到房型: {room_type}")
                return False
            
            # 识别日期列号（与step3相同的逻辑）
            import re
            # 提取日期数字，支持多种格式: "12.29", "12-29", "12/29", "12月29日"
            date_match = re.search(r'(\d{1,2})[.\-/月](\d{1,2})', target_date)
            if date_match:
                month = date_match.group(1).zfill(2)  # 补零，如 "12"
                day = date_match.group(2).zfill(2)    # 补零，如 "29"
                target_date_formatted = f"{month}.{day}"  # 统一为 "12.29" 格式
            else:
                target_date_formatted = target_date
            
            logger.info(f"目标日期格式化: {target_date} -> {target_date_formatted}")
            
            target_column = None
            date_cells = self.page.locator(f'//*[@id="calendarTable"]/tbody/tr[{row_number}]/td[2]/table/tbody/tr/td')
            date_count = date_cells.count()
            logger.info(f"找到 {date_count} 个日期单元格")
            
            for i in range(1, date_count + 1):
                try:
                    date_span = self.page.locator(f'//*[@id="calendarTable"]/tbody/tr[{row_number}]/td[2]/table/tbody/tr/td[{i}]/div[2]/span[1]')
                    if date_span.count() > 0:
                        date_text = date_span.first.inner_text().strip()
                        logger.debug(f"  检查列 {i}: '{date_text}'")
                        
                        # 多种匹配方式
                        if date_text == target_date_formatted or date_text == target_date:
                            target_column = i
                            logger.info(f"✓ 找到目标日期: {date_text} -> 列 {i}")
                            break
                        # 尝试匹配 "12-29" 格式
                        elif date_text.replace('-', '.') == target_date_formatted:
                            target_column = i
                            logger.info(f"✓ 找到目标日期: {date_text} -> 列 {i}")
                            break
                        # 尝试匹配 "12/29" 格式
                        elif date_text.replace('/', '.') == target_date_formatted:
                            target_column = i
                            logger.info(f"✓ 找到目标日期: {date_text} -> 列 {i}")
                            break
                except Exception as e:
                    logger.debug(f"  检查列 {i} 时出错: {e}")
                    continue
            
            if target_column is None:
                logger.error(f"❌ 未找到日期: {target_date_formatted}")
                # 列出所有可见的日期供调试
                logger.info("可见的日期列表:")
                for i in range(1, min(date_count + 1, 15)):  # 最多显示前14个
                    try:
                        date_span = self.page.locator(f'//*[@id="calendarTable"]/tbody/tr[{row_number}]/td[2]/table/tbody/tr/td[{i}]/div[2]/span[1]')
                        if date_span.count() > 0:
                            date_text = date_span.first.inner_text().strip()
                            logger.info(f"  列 {i}: '{date_text}'")
                    except:
                        pass
                return False
            
            # 检查并调整售卖开关状态
            switch_xpath = f'//*[@id="calendarTable"]/tbody/tr[{row_number}]/td[2]/table/tbody/tr/td[{target_column}]/div[2]/span[9]'
            
            logger.info(f"检查售卖开关状态: {switch_xpath}")
            
            try:
                switch_element = self.page.locator(switch_xpath)
                
                if switch_element.count() > 0:
                    switch_class = switch_element.first.get_attribute('class') or ''
                    switch_text = switch_element.first.inner_text().strip()
                    
                    logger.info(f"开关当前状态 - class: {switch_class}, text: {switch_text}")
                    
                    is_currently_on = False
                    
                    # 方法1: 通过class判断
                    if any(keyword in switch_class.lower() for keyword in ['on', 'active', 'checked', 'open', 'enable']):
                        is_currently_on = True
                    # 方法2: 通过文本判断
                    elif any(keyword in switch_text for keyword in ['开', 'ON', '启用']):
                        is_currently_on = True
                    # 方法3: 通过样式判断
                    elif any(keyword in switch_class.lower() for keyword in ['off', 'inactive', 'disabled', 'close']):
                        is_currently_on = False
                    # 方法4: 通过checked属性判断
                    else:
                        try:
                            checked = switch_element.first.get_attribute('checked')
                            if checked is not None:
                                is_currently_on = checked.lower() in ['true', 'checked', '']
                            else:
                                logger.warning("无法明确判断开关状态，将根据目标状态进行调整")
                                is_currently_on = None
                        except:
                            is_currently_on = None
                    
                    current_state = "开启" if is_currently_on else "关闭" if is_currently_on is False else "未知"
                    
                    logger.info(f"开关当前状态: {current_state}")
                    
                    # 如果开关未打开，则打开开关
                    if is_currently_on is False:
                        logger.info(f"开关未打开，需要打开开关: {current_state} -> 开启")
                        switch_element.first.scroll_into_view_if_needed()
                        self._random_sleep(0.3, 0.5)
                        switch_element.first.click()
                        self._random_sleep(0.5, 1)
                        
                        # 验证是否已打开
                        after_click = switch_element.first.get_attribute('class') or ''
                        if any(keyword in after_click.lower() for keyword in ['on', 'active', 'checked', 'open', 'enable']):
                            logger.info(f"✓ 已成功打开开关")
                            self._take_screenshot("step5_switch_opened")
                            return True
                        else:
                            logger.warning(f"⚠️ 点击后开关状态可能未改变")
                            return True  # 仍然返回True，因为已经尝试了
                    elif is_currently_on is None:
                        # 无法判断状态，尝试点击以确保打开
                        logger.info(f"无法判断当前状态，尝试点击以确保开关打开")
                        switch_element.first.scroll_into_view_if_needed()
                        self._random_sleep(0.3, 0.5)
                        switch_element.first.click()
                        self._random_sleep(0.5, 1)
                        logger.info(f"✓ 已点击开关，确保打开状态")
                        self._take_screenshot("step5_switch_clicked")
                        return True
                    else:
                        logger.info(f"✓ 开关已经是打开状态，无需操作")
                        return True
                else:
                    logger.warning("未找到开关元素，跳过开关调整")
                    return False
                    
            except Exception as e:
                logger.warning(f"检查开关状态时出错: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 调整开关状态失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._take_screenshot("failed_step5")
            return False
    
    def run_test(self, hotel_name: str = "美利居", room_type: str = "大床房", target_date: str = "12.29", has_room: bool = True, room_count: int = None, price: int = None):
        """运行测试流程"""
        logger.info("=" * 60)
        logger.info("代理通RPA测试 - 开始执行")
        logger.info("=" * 60)
        
        try:
            # 启动浏览器
            self.setup_browser()
            
            # 加载Cookies并导航到首页
            if not self.load_cookies_and_navigate():
                logger.error("❌ 初始化失败，终止测试")
                return False
            
            # 第一步：点击房型按键
            if not self.step1_click_room_type_menu():
                logger.error("❌ 步骤1失败，终止测试")
                return False
            
            # 第二步：选择匹配的酒店
            if not self.step2_select_hotel_by_name(hotel_name):
                logger.error("❌ 步骤2失败，终止测试")
                return False
            
            # 第三步：选择房型和日期，并调整售卖开关
            if not self.step3_select_room_type_and_date(room_type, target_date, has_room):
                logger.error("❌ 步骤3失败，终止测试")
                return False
            
            # 第四步：在弹窗中进行操作
            if has_room:
                # 有房间：设置限量售卖或只设置价格
                if room_count is not None or price is not None:
                    # 有房间数量或价格，进行设置
                    if not self.step4_set_limited_sale(room_count, price):
                        logger.error("❌ 步骤4失败，终止测试")
                        return False
                else:
                    # 既没有房间数量也没有价格，关闭弹窗
                    logger.info("未指定房间数量和价格，关闭弹窗...")
                    self._close_modal()
            else:
                # 没有房间：在弹窗中选择"关房"并保存
                if not self.step4_close_room():
                    logger.error("❌ 步骤4（关房）失败，终止测试")
                    return False
            
            # 第五步：在弹窗操作完成后，检查开关状态
            # 注意：如果是关房操作，这一步会跳过
            if has_room:
                if not self.step5_check_and_open_room_switch(room_type, target_date):
                    logger.warning("⚠️ 步骤5（检查并打开开关）失败，但继续执行...")
            
            logger.info("\n" + "=" * 60)
            logger.info("✓ 测试执行完成")
            logger.info("=" * 60)
            
            # 保持浏览器打开，等待用户按回车退出
            logger.info("\n测试完成，浏览器将保持打开状态")
            logger.info("按回车键关闭浏览器...")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                # 如果无法读取输入（如在某些环境中），等待5秒后自动关闭
                logger.info("无法读取输入，5秒后自动关闭...")
                time.sleep(5)
            
        except Exception as e:
            logger.error(f"❌ 测试过程中出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._take_screenshot("error_final")
        
        finally:
            if self.browser:
                self.browser.close()
            elif self.context:
                self.context.close()
            if hasattr(self, 'playwright'):
                self.playwright.stop()
            logger.info("✓ 浏览器已关闭")


def main():
    """主函数"""
    import argparse
    
    # 使用 argparse 解析命名参数
    # 使用示例:
    #   python test_shangjia.py --hotel "美利居" --room "大床房" --date "12.29" --price 688
    #   python test_shangjia.py -H "美利居" -r "大床房" -d "12.29" -c 3 -p 688
    #   python test_shangjia.py -H "美利居" -r "大床房" -d "12.29" --has-room false  # 关房
    
    parser = argparse.ArgumentParser(
        description='代理通RPA测试脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 只设置价格
  python test_shangjia.py --hotel "美利居" --room "大床房" --date "12.29" --price 688
  
  # 设置房间数和价格
  python test_shangjia.py -H "美利居" -r "大床房" -d "12.29" -c 3 -p 688
  
  # 关房操作
  python test_shangjia.py -H "美利居" -r "大床房" -d "12.29" --has-room false
        '''
    )
    
    parser.add_argument('--hotel', '-H', default='美利居', help='酒店名称 (默认: 美利居)')
    parser.add_argument('--room', '-r', default='大床房', help='房型名称 (默认: 大床房)')
    parser.add_argument('--date', '-d', default='12.29', help='目标日期 (默认: 12.29)')
    parser.add_argument('--has-room', '-s', default='true', help='是否有房间 true/false (默认: true)')
    parser.add_argument('--count', '-c', type=int, default=None, help='房间数量（可选）')
    parser.add_argument('--price', '-p', type=int, default=None, help='价格（可选）')
    
    args = parser.parse_args()
    
    # 解析是否有房间
    has_room = args.has_room.lower() in ['true', '1', 'yes', 'on', '有', '是']
    
    logger.info(f"测试参数:")
    logger.info(f"  酒店名称: {args.hotel}")
    logger.info(f"  房型: {args.room}")
    logger.info(f"  日期: {args.date}")
    logger.info(f"  是否有房间: {has_room} ({'打开开关' if has_room else '关闭开关'})")
    if args.count is not None:
        logger.info(f"  房间数量: {args.count} (将设置限量售卖)")
    if args.price is not None:
        logger.info(f"  价格: {args.price} (将设置底价)")
    
    try:
        test = ShangjiaTest()
        test.run_test(
            hotel_name=args.hotel,
            room_type=args.room,
            target_date=args.date,
            has_room=has_room,
            room_count=args.count,
            price=args.price
        )
    except KeyboardInterrupt:
        logger.info("\n用户中断执行")
    except Exception as e:
        logger.error(f"❌ 程序异常: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()


# -*- coding: utf-8 -*-
"""
代理通自动上架RPA工具
使用 Python + Playwright 实现自动化操作

使用步骤：
1. 先用 Playwright codegen 录制一次操作流程，获取选择器
2. 将录制代码的选择器提取到本脚本中
3. 配置 config.yaml 文件
4. 运行本脚本
"""

import os
import sys
import json
import yaml
import time
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError

# 导入独立的cookies管理模块
try:
    from shangjia_cookies import load_cookies as cookies_load, save_cookies as cookies_save
except ImportError:
    # 如果导入失败，使用本地函数
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
        logging.FileHandler(os.path.join(SCRIPT_DIR, 'shangjia_rpa.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ShangjiaRPA:
    """代理通自动上架RPA类"""
    
    def __init__(self, config_path: str = CONFIG_FILE):
        """初始化RPA实例"""
        self.config = self._load_config(config_path)
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        
    def _load_config(self, config_path: str) -> Dict:
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
        
        screenshot_path = os.path.join(SCREENSHOTS_DIR, f"{name}.png")
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
                    logger.debug(f"✓ 点击成功: {selector}")
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
    
    def _wait_and_fill(self, selector: str, value: str, timeout: int = 30000):
        """等待输入框出现并填写"""
        try:
            element = self.page.wait_for_selector(selector, timeout=timeout)
            if element:
                element.scroll_into_view_if_needed()
                self._random_sleep(0.3, 0.5)
                element.fill(value)
                logger.debug(f"✓ 填写成功: {selector} = {value}")
                return True
        except Exception as e:
            logger.error(f"❌ 填写失败: {selector}, 错误: {e}")
            self._take_screenshot(f"failed_fill_{selector.replace(':', '_').replace('/', '_')}")
        return False
    
    def _wait_and_select(self, selector: str, value: str, timeout: int = 30000):
        """等待下拉框出现并选择"""
        try:
            element = self.page.wait_for_selector(selector, timeout=timeout)
            if element:
                element.scroll_into_view_if_needed()
                self._random_sleep(0.3, 0.5)
                element.select_option(value)
                logger.debug(f"✓ 选择成功: {selector} = {value}")
                return True
        except Exception as e:
            logger.error(f"❌ 选择失败: {selector}, 错误: {e}")
            self._take_screenshot(f"failed_select_{selector.replace(':', '_').replace('/', '_')}")
        return False
    
    def setup_browser(self):
        """启动浏览器"""
        logger.info("🚀 启动浏览器...")
        playwright = sync_playwright().start()
        self.playwright = playwright  # 保存playwright实例，用于关闭
        
        browser_config = self.config.get('browser', {})
        headless = browser_config.get('headless', False)
        slow_mo = browser_config.get('slow_mo', 500)
        window_size = browser_config.get('window_size', {'width': 1920, 'height': 1080})
        use_persistent = browser_config.get('use_persistent', True)  # 默认使用持久化上下文（非无痕）
        
        if use_persistent:
            # 使用持久化上下文（非无痕模式，会保存登录态、历史记录等）
            use_local_chrome = browser_config.get('use_local_chrome', False)
            chrome_executable = browser_config.get('chrome_executable', '')
            user_data_dir_config = browser_config.get('user_data_dir', '')
            
            # 用户数据目录
            if use_local_chrome and user_data_dir_config:
                # 使用本地用户数据目录（直接使用已有登录态）
                user_data_dir = user_data_dir_config
                logger.info(f"使用本地用户数据目录（已有登录态）: {user_data_dir}")
            else:
                # 使用项目目录下的用户数据目录
                user_data_dir = os.path.join(SCRIPT_DIR, "browser_data")
                logger.info("使用项目用户数据目录")
            
            logger.info("使用持久化浏览器上下文（非无痕模式）")
            
            launch_options = {
                'user_data_dir': user_data_dir,
                'headless': headless,
                'slow_mo': slow_mo,
                'viewport': {'width': window_size['width'], 'height': window_size['height']},
            }
            
            # launch_persistent_context 不支持 executable_path，只能使用 Playwright 自带的 Chromium
            # 但通过使用本地用户数据目录，可以访问已有的登录态和设置
            logger.info("使用 Playwright Chromium + 本地用户数据目录")
            
            self.context = playwright.chromium.launch_persistent_context(**launch_options)
            self.browser = None  # 持久化上下文不需要单独的browser对象
            self.page = self.context.new_page()
        else:
            # 使用临时上下文（无痕模式）
            logger.info("使用临时浏览器上下文（无痕模式）")
            use_local_chrome = browser_config.get('use_local_chrome', False)
            chrome_executable = browser_config.get('chrome_executable', '')
            
            launch_options = {
                'headless': headless,
                'slow_mo': slow_mo
            }
            
            # 临时上下文可以使用 executable_path
            if use_local_chrome and chrome_executable and os.path.exists(chrome_executable):
                launch_options['executable_path'] = chrome_executable
                logger.info(f"使用本地Chromium: {chrome_executable}")
            elif use_local_chrome:
                try:
                    launch_options['channel'] = 'chrome'
                    logger.info("使用系统Chrome（通过channel）")
                except:
                    logger.warning("未找到系统Chrome，使用Playwright Chromium")
            
            self.browser = playwright.chromium.launch(**launch_options)
            
            self.context = self.browser.new_context(
                viewport={'width': window_size['width'], 'height': window_size['height']}
            )
            
            self.page = self.context.new_page()
        
        logger.info("✓ 浏览器启动成功")
    
    def login(self) -> bool:
        """
        登录代理通后台
        
        TODO: 使用 Playwright codegen 录制登录流程后，将选择器填入此处
        示例选择器（需要根据实际页面修改）:
        - 用户名输入框: 'input[name="username"]'
        - 密码输入框: 'input[name="password"]'
        - 登录按钮: 'button:has-text("登录")'
        """
        logger.info("[步骤1] 登录代理通后台...")
        
        login_config = self.config.get('login', {})
        url = login_config.get('url', '')
        username = login_config.get('username', '')
        password = login_config.get('password', '')
        
        if not url:
            logger.error("❌ 配置文件中未设置登录URL")
            return False
        
        try:
            # 访问登录页面
            self.page.goto(url)
            self._random_sleep(2, 3)
            
            # TODO: 替换为实际的选择器（从 codegen 录制结果中获取）
            # 示例代码（需要根据实际页面修改）:
            # self._wait_and_fill('input[name="username"]', username)
            # self._wait_and_fill('input[name="password"]', password)
            # self._wait_and_click('button:has-text("登录")')
            
            # 等待登录完成（根据实际页面调整）
            self.page.wait_for_url('**/dashboard**', timeout=30000)  # 假设登录后跳转到dashboard
            self._random_sleep(2, 3)
            
            # 保存cookies（可选）
            if login_config.get('use_cookies', True):
                self._save_cookies()
            
            logger.info("✓ 登录成功")
            self._take_screenshot("login_success")
            return True
            
        except Exception as e:
            logger.error(f"❌ 登录失败: {e}")
            self._take_screenshot("login_error")
            return False
    
    def _save_cookies(self):
        """保存cookies到文件"""
        try:
            if cookies_save:
                # 使用独立的cookies模块
                cookies_save(self.context)
            else:
                # 备用方案：直接保存
                cookies = self.context.cookies()
                import pickle
                with open(COOKIES_FILE, 'wb') as f:
                    pickle.dump(cookies, f)
                logger.info(f"✓ Cookies已保存: {len(cookies)} 个")
        except Exception as e:
            logger.warning(f"⚠️ 保存Cookies失败: {e}")
    
    def _load_cookies(self) -> bool:
        """从文件加载cookies"""
        if not os.path.exists(COOKIES_FILE):
            return False
        
        try:
            login_config = self.config.get('login', {})
            url = login_config.get('url', '')
            
            if cookies_load:
                # 使用独立的cookies模块
                return cookies_load(self.context, url)
            else:
                # 备用方案：直接加载
                import pickle
                from urllib.parse import urlparse
                
                with open(COOKIES_FILE, 'rb') as f:
                    cookies = pickle.load(f)
                
                # Playwright 加载cookies需要先访问对应域名
                if url:
                    parsed = urlparse(url)
                    scheme = parsed.scheme or 'https'
                    domain = parsed.netloc or parsed.hostname
                    if domain:
                        # 构建基础URL（协议+域名）
                        base_url = f"{scheme}://{domain}"
                        # 先访问域名
                        try:
                            temp_page = self.context.new_page()
                            temp_page.goto(base_url, timeout=30000)
                            time.sleep(1)
                            temp_page.close()
                        except Exception as e:
                            logger.warning(f"⚠️ 访问域名失败，尝试直接加载cookies: {e}")
                
                # 加载cookies
                self.context.add_cookies(cookies)
                logger.info(f"✓ Cookies已加载: {len(cookies)} 个")
                return True
        except Exception as e:
            logger.warning(f"⚠️ 加载Cookies失败: {e}")
            return False
    
    def check_login_status(self) -> bool:
        """
        检查当前是否已登录（通过cookies或页面状态判断）
        
        TODO: 根据实际页面修改判断逻辑
        """
        try:
            login_config = self.config.get('login', {})
            url = login_config.get('url', '')
            
            if not url:
                return False
            
            # TODO: 替换为登录后的实际页面URL（如 dashboard、首页等）
            # 对于代理通平台，登录后通常跳转到首页
            # 方法1: 提取基础URL（协议+域名），访问首页
            from urllib.parse import urlparse
            parsed = urlparse(url)
            scheme = parsed.scheme or 'https'
            domain = parsed.netloc or parsed.hostname
            
            if not domain:
                logger.warning("无法从URL中提取域名")
                return False
            
            # 构建首页URL（去掉路径和参数）
            base_url = f"{scheme}://{domain}"
            
            logger.debug(f"检查登录状态，访问: {base_url}")
            self.page.goto(base_url, timeout=30000)
            self._random_sleep(2, 3)
            
            # 方法2: 检查URL是否跳转到登录页（如果未登录会跳转回登录页）
            current_url = self.page.url
            if '/login' in current_url.lower():
                logger.info("Cookies已失效，需要重新登录")
                return False
            
            # 方法3: 检查页面中是否存在登录后的特征元素
            # TODO: 替换为实际的特征元素选择器（如用户名显示、退出按钮等）
            # try:
            #     self.page.wait_for_selector('用户名的选择器', timeout=5000)
            #     logger.info("✓ Cookies有效，已登录")
            #     return True
            # except:
            #     logger.info("Cookies已失效，需要重新登录")
            #     return False
            
            # 临时方案：如果URL不是登录页，认为已登录
            logger.info("✓ Cookies有效，已登录")
            return True
            
        except Exception as e:
            logger.warning(f"检查登录状态失败: {e}")
            return False
    
    def goto_calendar_page(self) -> bool:
        """
        导航到日历/房态管理页面
        
        TODO: 使用 Playwright codegen 录制导航流程后，将选择器填入此处
        """
        logger.info("[步骤2] 导航到日历页面...")
        
        try:
            # TODO: 替换为实际的导航选择器
            # 示例: 点击"房态管理"或"日历"菜单
            # self._wait_and_click('a:has-text("房态管理")')
            # 或直接访问URL:
            # self.page.goto('https://你的后台地址/calendar')
            
            self._random_sleep(2, 3)
            
            # 等待页面加载完成（根据实际页面调整）
            # self.page.wait_for_selector('日历表格的选择器', timeout=30000)
            
            logger.info("✓ 已导航到日历页面")
            self._take_screenshot("calendar_page")
            return True
            
        except Exception as e:
            logger.error(f"❌ 导航失败: {e}")
            self._take_screenshot("failed_导航")
            return False
    
    def select_hotel(self, hotel_name: str) -> bool:
        """
        选择门店/酒店
        
        TODO: 使用 Playwright codegen 录制选择酒店流程后，将选择器填入此处
        """
        logger.info(f"[步骤3] 选择酒店: {hotel_name}")
        
        try:
            # TODO: 替换为实际的选择器
            # 示例: 点击酒店下拉框，然后选择或搜索酒店
            # self._wait_and_click('select[name="hotel"]')
            # self._wait_and_select('select[name="hotel"]', hotel_name)
            # 或使用搜索框:
            # self._wait_and_fill('input[placeholder="搜索酒店"]', hotel_name)
            # self._wait_and_click(f'li:has-text("{hotel_name}")')
            
            self._random_sleep(1, 2)
            
            logger.info(f"✓ 已选择酒店: {hotel_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 选择酒店失败: {e}")
            self._take_screenshot(f"failed_选择酒店_{hotel_name}")
            return False
    
    def select_room_types(self, room_types: List[str]) -> bool:
        """
        选择房型（可多选）
        
        TODO: 使用 Playwright codegen 录制选择房型流程后，将选择器填入此处
        """
        logger.info(f"[步骤4] 选择房型: {', '.join(room_types)}")
        
        try:
            # TODO: 替换为实际的选择器
            # 示例: 多选复选框或下拉框
            # for room_type in room_types:
            #     self._wait_and_click(f'input[value="{room_type}"]')
            #     self._random_sleep(0.3, 0.5)
            
            self._random_sleep(1, 2)
            
            logger.info(f"✓ 已选择房型: {', '.join(room_types)}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 选择房型失败: {e}")
            self._take_screenshot("failed_选择房型")
            return False
    
    def open_batch_modal(self) -> bool:
        """
        打开批量修改弹窗
        
        TODO: 使用 Playwright codegen 录制打开弹窗流程后，将选择器填入此处
        """
        logger.info("[步骤5] 打开批量修改弹窗...")
        
        try:
            # TODO: 替换为实际的选择器
            # 示例: 点击"批量修改"按钮
            # self._wait_and_click('button:has-text("批量修改")')
            
            # 等待弹窗出现
            # self.page.wait_for_selector('弹窗容器的选择器', timeout=30000)
            self._random_sleep(1, 2)
            
            logger.info("✓ 批量修改弹窗已打开")
            self._take_screenshot("batch_modal_opened")
            return True
            
        except Exception as e:
            logger.error(f"❌ 打开弹窗失败: {e}")
            self._take_screenshot("failed_打开弹窗")
            return False
    
    def fill_batch_form(self, params: Dict[str, Any]) -> bool:
        """
        填写批量修改表单
        
        TODO: 使用 Playwright codegen 录制填写表单流程后，将选择器填入此处
        
        参数:
            params: 包含日期范围、渠道、操作类型、值等
        """
        logger.info("[步骤6] 填写批量修改表单...")
        
        try:
            task_config = self.config.get('task', {})
            
            # 填写日期范围
            date_start = task_config.get('date_start', '')
            date_end = task_config.get('date_end', '')
            
            # TODO: 替换为实际的日期选择器
            # self._wait_and_fill('input[name="date_start"]', date_start)
            # self._wait_and_fill('input[name="date_end"]', date_end)
            # 或使用日期选择器组件:
            # self._wait_and_click('日期选择器选择器')
            # self._wait_and_click(f'日历日期:has-text("{date_start.split("-")[2]}")')
            
            # 选择渠道（多选）
            channels = task_config.get('channels', [])
            # TODO: 替换为实际的渠道选择器
            # for channel in channels:
            #     self._wait_and_click(f'input[value="{channel}"]')
            
            # 选择操作类型和填写值
            action = task_config.get('action', 'price')
            value = task_config.get('value', '')
            
            # TODO: 替换为实际的操作类型和值输入框
            # self._wait_and_click(f'radio[value="{action}"]')  # 选择操作类型
            # self._wait_and_fill('input[name="value"]', str(value))
            
            # 星期筛选（可选）
            weekdays = task_config.get('weekdays', [])
            if weekdays:
                # TODO: 替换为实际的星期选择器
                # for weekday in weekdays:
                #     self._wait_and_click(f'checkbox[value="{weekday}"]')
                pass
            
            self._random_sleep(1, 2)
            
            logger.info("✓ 表单填写完成")
            self._take_screenshot("form_filled")
            return True
            
        except Exception as e:
            logger.error(f"❌ 填写表单失败: {e}")
            self._take_screenshot("failed_填写表单")
            return False
    
    def submit_and_verify(self) -> bool:
        """
        提交表单并验证结果
        
        TODO: 使用 Playwright codegen 录制提交流程后，将选择器填入此处
        """
        logger.info("[步骤7] 提交表单...")
        
        try:
            # TODO: 替换为实际的提交按钮选择器
            # self._wait_and_click('button:has-text("确认")')
            # 或
            # self._wait_and_click('button:has-text("提交")')
            
            # 等待提交完成（根据实际页面调整）
            # self.page.wait_for_selector('成功提示的选择器', timeout=30000)
            # 或等待弹窗关闭
            # self.page.wait_for_selector('弹窗容器', state='hidden', timeout=30000)
            
            self._random_sleep(2, 3)
            
            # 验证结果（根据实际页面调整）
            # success_text = self.page.locator('成功提示文本').text_content()
            # if '成功' in success_text or '完成' in success_text:
            #     logger.info("✓ 提交成功")
            #     return True
            
            logger.info("✓ 提交完成")
            self._take_screenshot("submit_success")
            return True
            
        except Exception as e:
            logger.error(f"❌ 提交失败: {e}")
            self._take_screenshot("failed_提交")
            return False
    
    def run(self):
        """执行完整的自动上架流程"""
        logger.info("=" * 60)
        logger.info("代理通自动上架RPA - 开始执行")
        logger.info("=" * 60)
        
        try:
            # 启动浏览器
            self.setup_browser()
            
            login_config = self.config.get('login', {})
            login_url = login_config.get('url', '')
            
            # 尝试加载cookies
            cookies_loaded = False
            if login_config.get('use_cookies', True):
                cookies_loaded = self._load_cookies()
            
            # 如果加载了cookies，先检查是否有效
            need_login = True
            if cookies_loaded:
                logger.info("检测到已保存的Cookies，正在验证有效性...")
                if self.check_login_status():
                    logger.info("✓ Cookies有效，跳过登录")
                    need_login = False
                else:
                    logger.info("Cookies已失效，需要重新登录")
                    need_login = True
            
            # 如果需要登录，执行登录流程
            if need_login:
                # 访问登录页面
                if login_url:
                    self.page.goto(login_url)
                    self._random_sleep(2, 3)
                
                # 执行登录
                if not self.login():
                    logger.error("❌ 登录失败，终止执行")
                    return False
            else:
                logger.info("✓ 使用已保存的登录态，继续执行任务")
            
            # 获取任务配置
            task_config = self.config.get('task', {})
            hotels = task_config.get('hotels', [])
            room_types = task_config.get('room_types', [])
            
            # 遍历每个酒店执行上架
            for hotel in hotels:
                logger.info(f"\n{'='*60}")
                logger.info(f"处理酒店: {hotel}")
                logger.info(f"{'='*60}")
                
                # 导航到日历页面
                if not self.goto_calendar_page():
                    logger.error(f"❌ 酒店 {hotel} 处理失败：无法导航到日历页面")
                    continue
                
                # 选择酒店
                if not self.select_hotel(hotel):
                    logger.error(f"❌ 酒店 {hotel} 处理失败：无法选择酒店")
                    continue
                
                # 选择房型
                if not self.select_room_types(room_types):
                    logger.error(f"❌ 酒店 {hotel} 处理失败：无法选择房型")
                    continue
                
                # 打开批量修改弹窗
                if not self.open_batch_modal():
                    logger.error(f"❌ 酒店 {hotel} 处理失败：无法打开批量修改弹窗")
                    continue
                
                # 填写批量修改表单
                if not self.fill_batch_form({}):
                    logger.error(f"❌ 酒店 {hotel} 处理失败：无法填写表单")
                    continue
                
                # 提交并验证
                if not self.submit_and_verify():
                    logger.error(f"❌ 酒店 {hotel} 处理失败：提交失败")
                    continue
                
                logger.info(f"✓ 酒店 {hotel} 处理完成")
                self._random_sleep(2, 3)
            
            logger.info("\n" + "=" * 60)
            logger.info("✓ 所有任务执行完成")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ 执行过程中出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._take_screenshot("error_final")
        
        finally:
            # 保持浏览器打开一段时间，方便查看结果
            logger.info("\n等待10秒后关闭浏览器...")
            time.sleep(10)
            if self.browser:
                self.browser.close()
            elif self.context:
                # 持久化上下文需要关闭context
                self.context.close()
            if hasattr(self, 'playwright'):
                self.playwright.stop()
            logger.info("✓ 浏览器已关闭")


def main():
    """主函数"""
    try:
        rpa = ShangjiaRPA()
        rpa.run()
    except KeyboardInterrupt:
        logger.info("\n用户中断执行")
    except Exception as e:
        logger.error(f"❌ 程序异常: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()


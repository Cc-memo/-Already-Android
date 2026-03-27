"""
浏览器操作核心模块 - 可复用
"""
from typing import Optional, List, Dict, Any
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
import time
import random
import os
import platform
import tempfile
import uuid

from crawler.utils.logger import logger
from crawler.utils.helpers import get_random_user_agent
from crawler.config.settings import CRAWLER_CONFIG


class BrowserManager:
    """浏览器管理器 - 可复用"""
    
    def __init__(self, headless: bool = True, window_size: tuple = (1920, 1080), use_isolated_profile: bool = True):
        """
        初始化浏览器管理器
        
        Args:
            headless: 是否无头模式
            window_size: 窗口大小
            use_isolated_profile: 是否使用独立的用户数据目录（支持并发，默认True）
        """
        self.driver: Optional[webdriver.Chrome] = None
        self.headless = headless
        self.window_size = window_size
        self.wait_timeout = CRAWLER_CONFIG['selenium']['implicit_wait']
        self.use_isolated_profile = use_isolated_profile
        self.user_data_dir: Optional[str] = None
        
    def _find_chromium_binary(self) -> Optional[str]:
        """查找Chromium浏览器可执行文件路径"""
        chrome_bin = os.getenv("CHROME_BIN")
        if chrome_bin and os.path.exists(chrome_bin):
            return chrome_bin
        
        if platform.system() == "Linux":
            for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
                if os.path.exists(candidate):
                    return candidate
        elif platform.system() == "Windows":
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
                    return candidate
        
        return None
        
    def init_driver(self, driver_path: Optional[str] = None):
        """初始化WebDriver"""
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument(f"--window-size={self.window_size[0]},{self.window_size[1]}")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument(f'user-agent={get_random_user_agent()}')
            # 额外的反检测参数
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--lang=zh-CN')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            
            # 查找Chromium浏览器
            chromium_bin = self._find_chromium_binary()
            if chromium_bin:
                chrome_options.binary_location = chromium_bin
                is_chromium = any(k in chromium_bin.lower() for k in ("chromium", "chrome-win"))
                if is_chromium:
                    logger.info(f"使用Chromium浏览器: {chromium_bin}")
                else:
                    logger.info(f"使用Chrome浏览器: {chromium_bin}")
            else:
                logger.warning("未找到Chromium/Chrome，将使用系统默认浏览器")
            
            # 为并发支持：每个浏览器实例使用独立的用户数据目录
            if self.use_isolated_profile:
                # 创建临时目录作为用户数据目录，避免并发冲突
                temp_dir = tempfile.gettempdir()
                profile_dir = os.path.join(temp_dir, f"chromium_profile_{uuid.uuid4().hex[:8]}")
                os.makedirs(profile_dir, exist_ok=True)
                self.user_data_dir = profile_dir
                chrome_options.add_argument(f'--user-data-dir={profile_dir}')
                chrome_options.add_argument('--profile-directory=Default')
                logger.info(f"使用独立用户数据目录: {profile_dir}")
            # 注意：如果不使用独立目录，多个实例会冲突，导致只打开一个窗口



            
            # 禁用图片加载以提高速度（可选）
            # prefs = {"profile.managed_default_content_settings.images": 2}
            # chrome_options.add_experimental_option("prefs", prefs)
            
            if driver_path:
                service = Service(driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            self.driver.implicitly_wait(self.wait_timeout)
            self.driver.set_page_load_timeout(CRAWLER_CONFIG['selenium']['page_load_timeout'])
            
            # 执行反检测脚本
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    // 隐藏 webdriver 特征
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    // 隐藏 Chrome 自动化特征
                    window.navigator.chrome = {
                        runtime: {}
                    };
                    // 修改 permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                    // 修改 plugins 长度
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    // 修改 languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['zh-CN', 'zh', 'en']
                    });
                '''
            })
            
            logger.info("浏览器初始化成功")
            return True
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            return False
    
    def get(self, url: str, wait_selector: Optional[str] = None, timeout: int = 30):
        """
        打开网页
        
        Args:
            url: 网页URL
            wait_selector: 等待元素选择器（可选）
            timeout: 超时时间
        """
        if not self.driver:
            raise RuntimeError("浏览器未初始化")
        
        try:
            self.driver.get(url)
            logger.info(f"打开网页: {url}")
            
            if wait_selector:
                self.wait_for_element(wait_selector, timeout)
            
            time.sleep(1)  # 等待页面加载
            return True
        except TimeoutException:
            logger.error(f"页面加载超时: {url}")
            return False
        except Exception as e:
            logger.error(f"打开网页失败: {url}, 错误: {e}")
            return False
    
    def wait_for_element(self, selector: str, timeout: int = 10, by: By = By.CSS_SELECTOR):
        """等待元素出现"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return True
        except TimeoutException:
            logger.warning(f"等待元素超时: {selector}")
            return False
    
    def find_element(self, selector: str, by: By = By.CSS_SELECTOR, timeout: int = 10):
        """查找元素"""
        try:
            if timeout > 0:
                self.wait_for_element(selector, timeout, by)
            return self.driver.find_element(by, selector)
        except (NoSuchElementException, TimeoutException):
            return None
    
    def find_elements(self, selector: str, by: By = By.CSS_SELECTOR, timeout: int = 10):
        """查找多个元素"""
        try:
            if timeout > 0:
                self.wait_for_element(selector, timeout, by)
            return self.driver.find_elements(by, selector)
        except (NoSuchElementException, TimeoutException):
            return []
    
    def click(self, selector: str, by: By = By.CSS_SELECTOR, timeout: int = 10):
        """点击元素"""
        element = self.find_element(selector, by, timeout)
        if element:
            try:
                # 尝试直接点击
                element.click()
                time.sleep(0.5)
                return True
            except:
                # 如果直接点击失败，使用JavaScript点击
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    time.sleep(0.5)
                    return True
                except Exception as e:
                    logger.error(f"点击元素失败: {selector}, 错误: {e}")
                    return False
        return False
    
    def input_text(self, selector: str, text: str, by: By = By.CSS_SELECTOR, clear_first: bool = True):
        """输入文本"""
        element = self.find_element(selector, by)
        if element:
            try:
                if clear_first:
                    element.clear()
                element.send_keys(text)
                time.sleep(0.3)
                return True
            except Exception as e:
                logger.error(f"输入文本失败: {selector}, 错误: {e}")
                return False
        return False
    
    def get_text(self, selector: str, by: By = By.CSS_SELECTOR) -> Optional[str]:
        """获取元素文本"""
        element = self.find_element(selector, by)
        if element:
            try:
                return element.text.strip()
            except:
                return None
        return None
    
    def get_attribute(self, selector: str, attribute: str, by: By = By.CSS_SELECTOR) -> Optional[str]:
        """获取元素属性"""
        element = self.find_element(selector, by)
        if element:
            try:
                return element.get_attribute(attribute)
            except:
                return None
        return None
    
    def scroll_to_element(self, selector: str, by: By = By.CSS_SELECTOR):
        """滚动到元素"""
        element = self.find_element(selector, by)
        if element:
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(0.5)
                return True
            except:
                return False
        return False
    
    def scroll_page(self, pixels: int = 500):
        """滚动页面"""
        try:
            self.driver.execute_script(f"window.scrollBy(0, {pixels});")
            time.sleep(0.5)
            return True
        except:
            return False
    
    def execute_script(self, script: str, *args):
        """执行JavaScript"""
        try:
            return self.driver.execute_script(script, *args)
        except Exception as e:
            logger.error(f"执行JavaScript失败: {e}")
            return None
    
    def get_page_source(self) -> str:
        """获取页面源码"""
        return self.driver.page_source if self.driver else ""
    
    def get_current_url(self) -> str:
        """获取当前URL"""
        return self.driver.current_url if self.driver else ""
    
    def find_element_by_xpath(self, xpath: str, timeout: int = 10):
        """通过XPath查找元素"""
        try:
            if timeout > 0:
                self.wait_for_element(xpath, timeout, By.XPATH)
            return self.driver.find_element(By.XPATH, xpath)
        except (NoSuchElementException, TimeoutException):
            return None
    
    def find_elements_by_xpath(self, xpath: str, timeout: int = 10):
        """通过XPath查找多个元素"""
        try:
            if timeout > 0:
                self.wait_for_element(xpath, timeout, By.XPATH)
            return self.driver.find_elements(By.XPATH, xpath)
        except (NoSuchElementException, TimeoutException):
            return []
    
    def click_by_xpath(self, xpath: str, timeout: int = 10, simulate_human: bool = True, 
                       user_action_config: Dict[str, Any] = None):
        """
        通过XPath点击元素，模拟人类操作
        
        Args:
            xpath: XPath表达式
            timeout: 超时时间
            simulate_human: 是否模拟人类操作（移动鼠标、延迟等）
            user_action_config: 用户操作配置字典，包含：
                - mouse_move_offset: 鼠标移动偏移范围元组，如(-5, 5)
                - click_delay_range: 点击后延迟范围元组，如(0.5, 1.0)
                - scroll_before_click: 是否在点击前滚动
        
        Returns:
            是否点击成功
        """
        element = self.find_element_by_xpath(xpath, timeout)
        if element:
            try:
                if simulate_human:
                    # 从配置读取参数
                    scroll_before = user_action_config.get('scroll_before_click', True) if user_action_config else True
                    mouse_offset = user_action_config.get('mouse_move_offset', (-5, 5)) if user_action_config else (-5, 5)
                    click_delay = user_action_config.get('click_delay_range', (0.5, 1.0)) if user_action_config else (0.5, 1.0)
                    
                    # 滚动到元素可见
                    if scroll_before:
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                        time.sleep(random.uniform(0.3, 0.6))
                    
                    # 使用ActionChains模拟鼠标移动和点击
                    actions = ActionChains(self.driver)
                    # 移动到元素附近（模拟人类不会精确点击中心）
                    offset_x = random.randint(mouse_offset[0], mouse_offset[1])
                    offset_y = random.randint(mouse_offset[0], mouse_offset[1])
                    actions.move_to_element_with_offset(element, offset_x, offset_y)
                    time.sleep(random.uniform(0.1, 0.3))
                    actions.click()
                    actions.perform()
                else:
                    element.click()
                
                delay = random.uniform(click_delay[0], click_delay[1]) if isinstance(click_delay, tuple) else click_delay
                time.sleep(delay)
                logger.info(f"成功点击元素: {xpath}")
                return True
            except Exception as e:
                # 如果ActionChains失败，尝试JavaScript点击
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    time.sleep(random.uniform(0.5, 1.0))
                    logger.info(f"使用JavaScript点击元素: {xpath}")
                    return True
                except Exception as e2:
                    logger.error(f"点击元素失败: {xpath}, 错误: {e2}")
                    return False
        return False
    
    def input_text_by_xpath(self, xpath: str, text: str, clear_first: bool = True, simulate_human: bool = True,
                           user_action_config: Dict[str, Any] = None):
        """
        通过XPath输入文本，模拟人类输入
        
        Args:
            xpath: XPath表达式
            text: 要输入的文本
            clear_first: 是否先清空
            simulate_human: 是否模拟人类输入（逐字符输入、随机延迟）
            user_action_config: 用户操作配置字典，包含：
                - typing_delay_range: 打字延迟范围元组，如(0.05, 0.15)
                - scroll_before_click: 是否在输入前滚动
        
        Returns:
            是否输入成功
        """
        element = self.find_element_by_xpath(xpath)
        if element:
            try:
                scroll_before = user_action_config.get('scroll_before_click', True) if user_action_config else True
                typing_delay = user_action_config.get('typing_delay_range', (0.05, 0.15)) if user_action_config else (0.05, 0.15)
                
                # 滚动到元素可见
                if scroll_before:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(random.uniform(0.2, 0.4))
                
                # 点击输入框
                element.click()
                time.sleep(random.uniform(0.2, 0.4))
                
                if clear_first:
                    # 模拟人类清空（全选+删除）
                    element.send_keys(Keys.CONTROL + "a")
                    time.sleep(random.uniform(0.1, 0.2))
                    element.send_keys(Keys.DELETE)
                    time.sleep(random.uniform(0.1, 0.2))
                
                if simulate_human:
                    # 逐字符输入，模拟人类打字速度
                    for char in text:
                        element.send_keys(char)
                        delay = random.uniform(typing_delay[0], typing_delay[1]) if isinstance(typing_delay, tuple) else typing_delay
                        time.sleep(delay)
                else:
                    element.send_keys(text)
                
                time.sleep(random.uniform(0.3, 0.5))
                logger.info(f"成功输入文本到: {xpath}")
                return True
            except Exception as e:
                logger.error(f"输入文本失败: {xpath}, 错误: {e}")
                return False
        return False
    
    def detect_page_type(self, login_indicators: List[str] = None, 
                        result_indicators: List[str] = None) -> str:
        """
        检测当前页面类型
        
        Args:
            login_indicators: 登录页面的标识XPath列表
            result_indicators: 结果页面的标识XPath列表
        
        Returns:
            'login' - 登录页面
            'results' - 结果页面
            'unknown' - 未知页面
        """
        if login_indicators:
            for indicator in login_indicators:
                element = self.find_element_by_xpath(indicator, timeout=2)
                if element:
                    logger.info(f"检测到登录页面，标识: {indicator}")
                    return 'login'
        
        if result_indicators:
            for indicator in result_indicators:
                element = self.find_element_by_xpath(indicator, timeout=2)
                if element:
                    logger.info(f"检测到结果页面，标识: {indicator}")
                    return 'results'
        
        # 尝试更通用的结果页检测
        if result_indicators is None or len(result_indicators) == 0:
            # 尝试一些通用的结果页标识
            generic_indicators = [
                '//div[contains(@class, "list")]',
                '//div[contains(@class, "result")]',
                '//div[contains(@class, "item")]',
                '//ul[contains(@class, "list")]',
                '//ul[contains(@class, "result")]'
            ]
            for indicator in generic_indicators:
                element = self.find_element_by_xpath(indicator, timeout=1)
                if element:
                    logger.info(f"通过通用标识检测到结果页面: {indicator}")
                    return 'results'
        
        logger.warning("无法确定页面类型")
        return 'unknown'
    
    def wait_for_page_change(self, original_url: str = None, timeout: int = 30):
        """
        等待页面跳转
        
        Args:
            original_url: 原始URL（可选）
            timeout: 超时时间
        
        Returns:
            是否发生跳转
        """
        if original_url is None:
            original_url = self.get_current_url()
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_url = self.get_current_url()
            if current_url != original_url:
                logger.info(f"页面已跳转: {original_url} -> {current_url}")
                time.sleep(2)  # 等待页面加载
                return True
            time.sleep(0.5)
        
        logger.warning("页面未发生跳转")
        return False
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("浏览器已关闭")
            except:
                pass
            self.driver = None
    
    def __enter__(self):
        """上下文管理器入口"""
        self.init_driver()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


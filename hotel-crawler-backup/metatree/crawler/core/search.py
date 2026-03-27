"""
搜索核心模块 - 可复用
"""
from typing import Optional, List, Dict, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import random

from crawler.utils.logger import logger
from crawler.core.browser import BrowserManager


class SearchManager:
    """搜索管理器 - 可复用"""
    
    def __init__(self, browser: BrowserManager):
        """
        初始化搜索管理器
        
        Args:
            browser: 浏览器管理器实例
        """
        self.browser = browser
    
    def search_hotel_by_name(self, search_config: Dict[str, Any], 
                            hotel_name: str) -> bool:
        """
        通过酒店名称搜索
        
        Args:
            search_config: 搜索配置，包含：
                - search_url: 搜索页面URL
                - search_input_selector: 搜索输入框选择器
                - search_button_selector: 搜索按钮选择器（可选，如果按回车搜索则不需要）
                - use_enter: 是否使用回车键搜索（默认False）
            hotel_name: 酒店名称
        
        Returns:
            是否搜索成功
        """
        try:
            logger.info(f"搜索酒店: {hotel_name}")
            
            # 打开搜索页面
            if not self.browser.get(search_config['search_url']):
                return False
            
            time.sleep(2)  # 等待页面加载
            
            # 输入酒店名称
            if not self.browser.input_text(
                search_config['search_input_selector'],
                hotel_name,
                by=By.CSS_SELECTOR
            ):
                logger.error("输入酒店名称失败")
                return False
            
            time.sleep(0.5)
            
            # 执行搜索
            if search_config.get('use_enter', False):
                # 使用回车键搜索
                element = self.browser.find_element(search_config['search_input_selector'])
                if element:
                    element.send_keys(Keys.RETURN)
            else:
                # 点击搜索按钮
                if not self.browser.click(search_config.get('search_button_selector', '')):
                    logger.error("点击搜索按钮失败")
                    return False
            
            time.sleep(3)  # 等待搜索结果加载
            
            logger.info("搜索完成")
            return True
            
        except Exception as e:
            logger.error(f"搜索酒店失败: {e}")
            return False
    
    def search_hotel_by_address(self, search_config: Dict[str, Any],
                               address: str) -> bool:
        """
        通过地址搜索
        
        Args:
            search_config: 搜索配置
            address: 地址
        
        Returns:
            是否搜索成功
        """
        return self.search_hotel_by_name(search_config, address)
    
    def wait_for_results(self, results_selector: str, timeout: int = 30) -> bool:
        """
        等待搜索结果出现
        
        Args:
            results_selector: 搜索结果容器选择器
            timeout: 超时时间
        
        Returns:
            是否找到结果
        """
        return self.browser.wait_for_element(results_selector, timeout)
    
    def scroll_to_load_more(self, load_more_selector: Optional[str] = None,
                          max_scrolls: int = 5) -> int:
        """
        滚动加载更多结果
        
        Args:
            load_more_selector: "加载更多"按钮选择器（可选）
            max_scrolls: 最大滚动次数
        
        Returns:
            滚动次数
        """
        scroll_count = 0
        
        if load_more_selector:
            # 如果有"加载更多"按钮，点击加载
            while scroll_count < max_scrolls:
                if self.browser.click(load_more_selector):
                    time.sleep(2)
                    scroll_count += 1
                else:
                    break
        else:
            # 否则滚动页面
            last_height = self.browser.driver.execute_script("return document.body.scrollHeight")
            while scroll_count < max_scrolls:
                # 滚动到底部
                self.browser.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                # 检查是否有新内容加载
                new_height = self.browser.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_count += 1
        
        logger.info(f"已滚动加载 {scroll_count} 次")
        return scroll_count
    
    def search_hotel_with_flow_control(self, search_config: Dict[str, Any], 
                                      hotel_name: str,
                                      login_config: Optional[Dict[str, Any]] = None,
                                      username: Optional[str] = None,
                                      password: Optional[str] = None) -> bool:
        """
        带流程控制的酒店搜索（使用XPath和页面状态检测）
        
        Args:
            search_config: 搜索配置，包含：
                - search_url: 搜索页面URL
                - search_input_xpath: 搜索输入框XPath（优先）或 search_input_selector
                - search_button_xpath: 搜索按钮XPath（优先）或 search_button_selector
                - use_enter: 是否使用回车键搜索
                - login_indicators: 登录页面标识XPath列表
                - result_indicators: 结果页面标识XPath列表
            hotel_name: 酒店名称
            login_config: 登录配置（如果需要自动登录）
            username: 用户名（如果需要自动登录）
            password: 密码（如果需要自动登录）
        
        Returns:
            是否搜索成功
        """
        try:
            logger.info(f"开始搜索酒店流程: {hotel_name}")
            
            # 1. 打开搜索页面
            if not self.browser.get(search_config['search_url']):
                logger.error("打开搜索页面失败")
                return False
            
            time.sleep(2)  # 等待页面加载
            
            # 2. 检测页面类型
            page_type = self.browser.detect_page_type(
                login_indicators=search_config.get('login_indicators', []),
                result_indicators=search_config.get('result_indicators', [])
            )
            
            logger.info(f"当前页面类型: {page_type}")
            logger.info(f"当前URL: {self.browser.get_current_url()}")
            
            # 3. 如果已经在结果页，跳过搜索操作
            if page_type == 'results':
                logger.info("已在结果页面，跳过搜索操作")
                # 等待页面完全加载
                time.sleep(2)
                return True
            
            # 4. 如果跳转到登录页，处理登录
            if page_type == 'login':
                logger.info("检测到登录页面，开始处理登录")
                
                if login_config and username and password:
                    # 自动登录
                    from crawler.core.auth import AuthManager
                    auth = AuthManager(self.browser)
                    if not auth.login('auto', username, password, login_config):
                        logger.error("自动登录失败")
                        return False
                    
                    # 等待登录完成并跳转
                    time.sleep(3)
                    
                    # 重新检测页面类型
                    page_type = self.browser.detect_page_type(
                        login_indicators=search_config.get('login_indicators', []),
                        result_indicators=search_config.get('result_indicators', [])
                    )
                    
                    # 如果登录后已经在结果页，直接返回
                    if page_type == 'results':
                        logger.info("登录后已在结果页面")
                        return True
                    
                    # 重新打开搜索页面
                    if not self.browser.get(search_config['search_url']):
                        return False
                    time.sleep(2)
                else:
                    # 等待用户手动登录
                    logger.info("等待用户手动登录...")
                    input("请在浏览器中完成登录，然后按回车继续...")
                    time.sleep(2)
                    
                    # 登录后重新检测页面类型
                    page_type = self.browser.detect_page_type(
                        login_indicators=search_config.get('login_indicators', []),
                        result_indicators=search_config.get('result_indicators', [])
                    )
                    
                    if page_type == 'results':
                        logger.info("手动登录后已在结果页面")
                        return True
            
            # 5. 执行搜索操作
            logger.info("开始输入搜索关键词")
            
            # 优先使用XPath，如果没有则使用CSS选择器
            search_input_xpath = search_config.get('search_input_xpath')
            search_input_selector = search_config.get('search_input_selector')
            
            if search_input_xpath:
                # 从配置获取用户操作参数
                user_action_config = search_config.get('user_actions', {})
                # 使用XPath输入（模拟人类输入）
                if not self.browser.input_text_by_xpath(
                    search_input_xpath,
                    hotel_name,
                    simulate_human=search_config.get('simulate_human', True),
                    user_action_config=user_action_config
                ):
                    logger.error("输入酒店名称失败")
                    return False
            elif search_input_selector:
                # 使用CSS选择器输入
                if not self.browser.input_text(
                    search_input_selector,
                    hotel_name,
                    by=By.CSS_SELECTOR
                ):
                    logger.error("输入酒店名称失败")
                    return False
            else:
                logger.error("未配置搜索输入框XPath或选择器")
                return False
            
            time.sleep(random.uniform(0.5, 1.0))
            
            # 5. 执行搜索（点击按钮或按回车）
            if search_config.get('use_enter', False):
                # 按回车键
                if search_input_xpath:
                    element = self.browser.find_element_by_xpath(search_input_xpath)
                else:
                    element = self.browser.find_element(search_input_selector)
                
                if element:
                    element.send_keys(Keys.RETURN)
                    logger.info("已按回车键执行搜索")
                else:
                    logger.error("未找到搜索输入框")
                    return False
            else:
                # 点击搜索按钮
                search_button_xpath = search_config.get('search_button_xpath')
                search_button_selector = search_config.get('search_button_selector')
                
                if search_button_xpath:
                    # 从配置获取用户操作参数
                    user_action_config = search_config.get('user_actions', {})
                    if not self.browser.click_by_xpath(
                        search_button_xpath, 
                        simulate_human=search_config.get('simulate_human', True),
                        user_action_config=user_action_config
                    ):
                        logger.error("点击搜索按钮失败")
                        return False
                    logger.info("已点击搜索按钮")
                elif search_button_selector:
                    if not self.browser.click(search_button_selector):
                        logger.error("点击搜索按钮失败")
                        return False
                    logger.info("已点击搜索按钮")
                else:
                    logger.warning("未配置搜索按钮，尝试使用回车键")
                    if search_input_xpath:
                        element = self.browser.find_element_by_xpath(search_input_xpath)
                    else:
                        element = self.browser.find_element(search_input_selector)
                    if element:
                        element.send_keys(Keys.RETURN)
            
            # 6. 等待页面跳转或结果加载
            time.sleep(3)
            
            # 7. 再次检测页面类型
            page_type = self.browser.detect_page_type(
                login_indicators=search_config.get('login_indicators', []),
                result_indicators=search_config.get('result_indicators', [])
            )
            
            if page_type == 'login':
                logger.warning("搜索后跳转到登录页，可能需要登录")
                if login_config and username and password:
                    from crawler.core.auth import AuthManager
                    auth = AuthManager(self.browser)
                    if auth.login('auto', username, password, login_config):
                        time.sleep(3)
                        # 重新搜索
                        return self.search_hotel_with_flow_control(
                            search_config, hotel_name, login_config, username, password
                        )
                else:
                    input("请在浏览器中完成登录，然后按回车继续...")
            
            # 8. 等待搜索结果出现
            result_indicators = search_config.get('result_indicators', [])
            if result_indicators:
                found = False
                for indicator in result_indicators:
                    logger.info(f"尝试查找结果标识: {indicator}")
                    if self.browser.wait_for_element(indicator, timeout=15, by=By.XPATH):
                        found = True
                        logger.info(f"找到结果标识: {indicator}")
                        break
                if not found:
                    logger.warning("未找到搜索结果标识，但继续尝试提取数据")
                    # 不直接返回False，让调用者尝试提取数据
                    # 因为可能标识不准确，但页面确实有结果
            else:
                logger.warning("未配置结果标识，直接尝试提取数据")
            
            # 再次检测页面类型确认
            final_page_type = self.browser.detect_page_type(
                login_indicators=search_config.get('login_indicators', []),
                result_indicators=search_config.get('result_indicators', [])
            )
            logger.info(f"搜索后页面类型: {final_page_type}")
            logger.info(f"当前URL: {self.browser.get_current_url()}")
            
            logger.info("搜索流程完成")
            return True
            
        except Exception as e:
            logger.error(f"搜索流程失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def click_hotel_item_by_xpath(self, hotel_item_xpath: str, index: int = 0) -> bool:
        """
        点击酒店列表项进入详情页
        
        Args:
            hotel_item_xpath: 酒店列表项的XPath（支持索引，如 //div[@class='hotel-item'][1]）
            index: 要点击的酒店索引（从0开始）
        
        Returns:
            是否点击成功
        """
        try:
            # 构建带索引的XPath
            if f'[{index + 1}]' not in hotel_item_xpath and '[' not in hotel_item_xpath:
                # 如果XPath中没有索引，添加索引
                xpath = f"({hotel_item_xpath})[{index + 1}]"
            else:
                xpath = hotel_item_xpath
            
            logger.info(f"点击酒店列表项 {index + 1}: {xpath}")
            
            # 滚动到元素可见
            element = self.browser.find_element_by_xpath(xpath)
            if element:
                self.browser.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(random.uniform(0.5, 1.0))
                
                # 模拟点击（使用默认配置）
                if self.browser.click_by_xpath(xpath, simulate_human=True):
                    # 等待页面跳转
                    time.sleep(3)
                    logger.info("成功进入酒店详情页")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"点击酒店项失败: {e}")
            return False


"""
LangGraph角色定义
"""
from typing import Dict, Any, List, Optional
from .state import CrawlState
from crawler.core.browser import BrowserManager
from crawler.core.auth import AuthManager
from crawler.core.search import SearchManager
from crawler.core.extractor import DataExtractor
from crawler.config.settings import PLATFORM_CONFIG
from loguru import logger
import time


class BaseAgent:
    """基础角色类"""
    
    def __init__(self, browser: BrowserManager = None):
        self.browser = browser
        self.name = self.__class__.__name__
    
    def execute(self, state: CrawlState) -> CrawlState:
        """执行角色逻辑"""
        state.current_node = self.name
        state.add_log(f"开始执行 {self.name}")
        
        try:
            result = self._execute(state)
            state.visited_nodes.append(self.name)
            state.add_log(f"{self.name} 执行成功")
            return result
        except Exception as e:
            state.add_error(f"{self.name} 执行失败: {str(e)}")
            logger.error(f"{self.name} 执行失败: {e}")
            raise
    
    def _execute(self, state: CrawlState) -> CrawlState:
        """子类实现具体逻辑"""
        raise NotImplementedError


class URLFetcherAgent(BaseAgent):
    """网址获取角色"""
    
    def _execute(self, state: CrawlState) -> CrawlState:
        """获取平台URL"""
        platform_config = PLATFORM_CONFIG.get(state.platform, {})
        
        # 获取基础URL
        state.urls['base_url'] = platform_config.get('base_url', '')
        state.urls['search_url'] = platform_config.get('search_url', '')
        state.urls['detail_url'] = platform_config.get('detail_url', '')
        
        # 获取登录URL（如果有）
        login_config = platform_config.get('login', {})
        if login_config:
            state.urls['login_url'] = login_config.get('login_url', '')
        
        state.add_log(f"获取URL成功: base_url={state.urls['base_url']}")
        return state


class LoginAgent(BaseAgent):
    """登入角色"""
    
    def __init__(self, browser: BrowserManager = None):
        super().__init__(browser)
        self.auth = AuthManager(browser) if browser else None
    
    def _execute(self, state: CrawlState) -> CrawlState:
        """执行登录"""
        if not state.login_credentials:
            state.add_log("未提供登录凭证，跳过登录")
            return state
        
        if not self.browser:
            raise ValueError("浏览器未初始化")
        
        platform_config = PLATFORM_CONFIG.get(state.platform, {})
        login_config = platform_config.get('login', {})
        
        if not login_config:
            state.add_log("平台未配置登录信息，跳过登录")
            return state
        
        # 构建登录配置
        login_params = {
            'login_url': login_config.get('login_url', ''),
            'username_selector': login_config.get('username_xpath', ''),
            'password_selector': login_config.get('password_xpath', ''),
            'submit_selector': login_config.get('submit_xpath', ''),
            'success_selector': login_config.get('success_xpath', ''),
        }
        
        # 执行登录
        username = state.login_credentials.get('username')
        password = state.login_credentials.get('password')
        
        success = self.auth.login(
            state.platform,
            username,
            password,
            login_params
        )
        
        if success:
            state.login_status = True
            state.add_log("登录成功")
        else:
            state.add_error("登录失败")
            raise Exception("登录失败")
        
        return state


class LocatorAgent(BaseAgent):
    """定位角色"""
    
    def _execute(self, state: CrawlState) -> CrawlState:
        """定位页面元素"""
        if not self.browser:
            raise ValueError("浏览器未初始化")
        
        platform_config = PLATFORM_CONFIG.get(state.platform, {})
        search_config = platform_config.get('search', {})
        
        # 先打开搜索页面
        search_url = state.urls.get('search_url') or state.urls.get('base_url')
        if search_url:
            logger.info(f"打开页面: {search_url}")
            if not self.browser.get(search_url):
                state.add_error(f"打开页面失败: {search_url}")
                raise Exception(f"打开页面失败: {search_url}")
            import time
            time.sleep(3)  # 等待页面加载
        
        # 定位搜索输入框
        search_input_xpath = search_config.get('input_xpath', '')
        if search_input_xpath:
            element = self.browser.find_element_by_xpath(search_input_xpath, timeout=5)
            if element:
                state.located_elements['search_input'] = search_input_xpath
                state.add_log(f"定位搜索输入框成功: {search_input_xpath}")
        
        # 定位搜索按钮
        search_button_xpath = search_config.get('button_xpath', '')
        if search_button_xpath:
            element = self.browser.find_element_by_xpath(search_button_xpath, timeout=5)
            if element:
                state.located_elements['search_button'] = search_button_xpath
                state.add_log(f"定位搜索按钮成功: {search_button_xpath}")
        
        # 定位结果列表容器
        extraction_config = platform_config.get('extraction', {})
        hotel_list_xpath = extraction_config.get('hotel_list_xpath', '')
        if hotel_list_xpath:
            elements = self.browser.find_elements_by_xpath(hotel_list_xpath, timeout=5)
            if elements:
                state.located_elements['hotel_list'] = hotel_list_xpath
                state.located_elements['hotel_count'] = len(elements)
                state.add_log(f"定位酒店列表成功: {hotel_list_xpath}, 找到{len(elements)}个")
        
        return state


class SearchAgent(BaseAgent):
    """酒店查找角色"""
    
    def __init__(self, browser: BrowserManager = None):
        super().__init__(browser)
        self.search = SearchManager(browser) if browser else None
    
    def _execute(self, state: CrawlState) -> CrawlState:
        """执行搜索"""
        if not self.browser:
            raise ValueError("浏览器未初始化")
        
        if not self.search:
            raise ValueError("搜索管理器未初始化")
        
        platform_config = PLATFORM_CONFIG.get(state.platform, {})
        search_config = platform_config.get('search', {})
        page_detection = platform_config.get('page_detection', {})
        
        # 构建搜索配置
        search_params = {
            'search_url': state.urls.get('search_url', ''),
            'search_input_xpath': search_config.get('input_xpath', ''),
            'search_button_xpath': search_config.get('button_xpath', ''),
            'use_enter': search_config.get('use_enter', True),
            'login_indicators': page_detection.get('login_indicators', []),
            'result_indicators': page_detection.get('result_indicators', []),
            'user_actions': platform_config.get('user_actions', {}),
        }
        
        # 登录配置（如果需要）
        login_config = None
        if state.login_credentials:
            login_cfg = platform_config.get('login', {})
            login_config = {
                'login_url': login_cfg.get('login_url', ''),
                'username_selector': login_cfg.get('username_xpath', ''),
                'password_selector': login_cfg.get('password_xpath', ''),
                'submit_selector': login_cfg.get('submit_xpath', ''),
                'success_selector': login_cfg.get('success_xpath', ''),
            }
        
        # 执行搜索
        username = state.login_credentials.get('username') if state.login_credentials else None
        password = state.login_credentials.get('password') if state.login_credentials else None
        
        success = self.search.search_hotel_with_flow_control(
            search_params,
            state.hotel_name,
            login_config,
            username,
            password
        )
        
        if success:
            state.add_log(f"搜索成功: {state.hotel_name}")
        else:
            state.add_error("搜索失败")
            raise Exception("搜索失败")
        
        return state


class ExtractorAgent(BaseAgent):
    """数据提取角色"""
    
    def _execute(self, state: CrawlState) -> CrawlState:
        """提取数据"""
        if not self.browser:
            raise ValueError("浏览器未初始化")
        
        platform_config = PLATFORM_CONFIG.get(state.platform, {})
        extraction_config = platform_config.get('extraction', {})
        
        # 获取页面HTML
        html = self.browser.get_page_source()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        
        # 提取酒店列表
        hotel_list_xpath = extraction_config.get('hotel_list_xpath', '')
        hotels = []
        
        if hotel_list_xpath:
            # 使用XPath从浏览器中查找
            try:
                hotel_elements = self.browser.find_elements_by_xpath(hotel_list_xpath, timeout=5)
                for elem in hotel_elements:
                    try:
                        html = elem.get_attribute('outerHTML')
                        if html:
                            item_soup = BeautifulSoup(html, 'lxml')
                            hotel_data = self._extract_hotel_data(item_soup, extraction_config, state.platform)
                            if hotel_data:
                                hotels.append(hotel_data)
                    except Exception as e:
                        logger.warning(f"提取酒店数据失败: {e}")
                        continue
            except Exception as e:
                logger.warning(f"使用XPath提取失败: {e}")
                # 使用CSS选择器作为备选
                hotel_items = soup.select('.hotel-item, .hotel-card, [data-hotel-id]')
                for item in hotel_items:
                    hotel_data = self._extract_hotel_data(item, extraction_config, state.platform)
                    if hotel_data:
                        hotels.append(hotel_data)
        
        state.hotel_data = hotels
        state.add_log(f"提取到 {len(hotels)} 个酒店数据")
        
        return state
    
    def _extract_hotel_data(self, soup, extraction_config: Dict[str, str], platform: str = '') -> Optional[Dict[str, Any]]:
        """提取单个酒店数据"""
        try:
            # 转换XPath到CSS选择器（简单处理）
            def xpath_to_css(xpath_str):
                if xpath_str.startswith('.//') or xpath_str.startswith('//'):
                    css = xpath_str.replace('.//', '').replace('//', '')
                    css = css.replace('contains(@class, "', '[class*="').replace('")', '"]')
                    css = css.replace('@', '')
                    return css
                return xpath_str
            
            name_selector = xpath_to_css(extraction_config.get('hotel_name_xpath', '.hotel-name, h3'))
            price_selector = xpath_to_css(extraction_config.get('hotel_price_xpath', '.price'))
            rating_selector = xpath_to_css(extraction_config.get('hotel_rating_xpath', '.rating'))
            address_selector = xpath_to_css(extraction_config.get('hotel_address_xpath', '.address'))
            link_selector = xpath_to_css(extraction_config.get('hotel_link_xpath', 'a'))
            
            hotel_data = {
                'platform': platform,
                'hotel_name': DataExtractor.extract_text(soup, name_selector),
                'min_price': DataExtractor.extract_price(
                    DataExtractor.extract_text(soup, price_selector)
                ),
                'rating_score': DataExtractor.extract_rating(
                    DataExtractor.extract_text(soup, rating_selector)
                ),
                'address': DataExtractor.extract_text(soup, address_selector),
                'hotel_url': DataExtractor.extract_attribute(soup, link_selector if link_selector.startswith('a') else 'a', 'href'),
            }
            
            return hotel_data if hotel_data.get('hotel_name') else None
        except Exception as e:
            logger.warning(f"提取酒店数据失败: {e}")
            return None


class ValidatorAgent(BaseAgent):
    """内容校验角色"""
    
    def _execute(self, state: CrawlState) -> CrawlState:
        """校验数据"""
        validation_results = {
            'total_count': len(state.hotel_data),
            'valid_count': 0,
            'invalid_count': 0,
            'errors': []
        }
        
        for hotel in state.hotel_data:
            is_valid = True
            errors = []
            
            # 校验必填字段
            if not hotel.get('hotel_name'):
                is_valid = False
                errors.append("酒店名称为空")
            
            if not hotel.get('platform'):
                is_valid = False
                errors.append("平台信息缺失")
            
            # 校验数据格式
            if hotel.get('min_price') and not isinstance(hotel.get('min_price'), (int, float)):
                is_valid = False
                errors.append("价格格式错误")
            
            if hotel.get('rating_score') and not isinstance(hotel.get('rating_score'), (int, float)):
                is_valid = False
                errors.append("评分格式错误")
            
            if is_valid:
                validation_results['valid_count'] += 1
            else:
                validation_results['invalid_count'] += 1
                validation_results['errors'].extend(errors)
        
        state.validation_results = validation_results
        state.add_log(f"校验完成: 有效{validation_results['valid_count']}条, 无效{validation_results['invalid_count']}条")
        
        if validation_results['invalid_count'] > validation_results['valid_count']:
            state.add_error("数据校验失败，无效数据过多")
            raise Exception("数据校验失败")
        
        return state


class ErrorHandlerAgent(BaseAgent):
    """错误处理角色"""
    
    def _execute(self, state: CrawlState) -> CrawlState:
        """处理错误"""
        state.add_log(f"错误处理: 当前错误数={state.error_count}")
        
        # 决定处理策略
        if state.error_count < state.max_retries:
            state.add_log("错误数未超过最大重试次数，可以重试")
            # 可以回退到上一个节点
            if state.visited_nodes:
                state.current_node = state.visited_nodes[-1]
        else:
            state.add_log("错误数超过最大重试次数，任务失败")
            from datetime import datetime
            state.end_time = datetime.now()
        
        return state


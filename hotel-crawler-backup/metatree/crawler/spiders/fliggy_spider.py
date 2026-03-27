"""
飞猪平台爬虫
"""
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import time

from crawler.utils.logger import logger
from crawler.core.browser import BrowserManager
from crawler.core.auth import AuthManager
from crawler.core.search import SearchManager
from crawler.core.extractor import DataExtractor
from crawler.config.settings import PLATFORM_CONFIG


class FliggySpider:
    """飞猪酒店爬虫"""
    
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.platform = 'fliggy'
        self.config = PLATFORM_CONFIG['fliggy']
        self.username = username
        self.password = password
        self.browser = BrowserManager(headless=False)
        self.auth = None
        self.search = None
    
    def __enter__(self):
        self.browser.init_driver()
        self.auth = AuthManager(self.browser)
        self.search = SearchManager(self.browser)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.browser.close()
    
    def login(self) -> bool:
        """登录飞猪"""
        if not self.username or not self.password:
            return True
        
        login_config = {
            'login_url': f"{self.config['base_url']}/login",
            'username_selector': 'input[name="username"]',
            'password_selector': 'input[type="password"]',
            'submit_selector': '.login-btn',
            'success_selector': '.user-name',
        }
        
        return self.auth.login(self.platform, self.username, self.password, login_config)
    
    def search_hotel(self, hotel_name: str) -> List[Dict[str, Any]]:
        """搜索酒店（使用XPath和流程控制，从配置文件读取）"""
        try:
            logger.info(f"飞猪搜索酒店: {hotel_name}")
            
            # 从配置文件读取XPath和页面检测标识
            search_config = {
                'search_url': self.config['search_url'],
                'search_input_xpath': self.config.get('search', {}).get('input_xpath', '//input[@name="keyword"]'),
                'search_button_xpath': self.config.get('search', {}).get('button_xpath', '//button[contains(@class, "search")]'),
                'use_enter': self.config.get('search', {}).get('use_enter', True),
                'input_delay': self.config.get('search', {}).get('input_delay', 0.5),
                'click_delay': self.config.get('search', {}).get('click_delay', 0.3),
                # 登录页面标识（从配置读取）
                'login_indicators': self.config.get('page_detection', {}).get('login_indicators', [
                    '//div[contains(@class, "login")]',
                    '//input[@type="password"]',
                ]),
                # 结果页面标识（从配置读取）
                'result_indicators': self.config.get('page_detection', {}).get('result_indicators', [
                    '//div[contains(@class, "hotel-list")]',
                    '//div[contains(@class, "hotel-item")]',
                ]),
            }
            
            # 登录配置（如果需要，从配置读取）
            login_config = None
            if self.username and self.password:
                login_cfg = self.config.get('login', {})
                login_config = {
                    'login_url': login_cfg.get('login_url', f"{self.config['base_url']}/login"),
                    'username_selector': login_cfg.get('username_xpath', '//input[@name="username"]'),
                    'password_selector': login_cfg.get('password_xpath', '//input[@type="password"]'),
                    'submit_selector': login_cfg.get('submit_xpath', '//button[contains(text(), "登录")]'),
                    'success_selector': login_cfg.get('success_xpath', '//div[contains(@class, "user")]'),
                }
            
            # 获取用户操作配置
            user_actions = self.config.get('user_actions', {})
            search_config['simulate_human'] = user_actions.get('simulate_human', True)
            search_config['mouse_move_offset'] = user_actions.get('mouse_move_offset', (-5, 5))
            search_config['typing_delay_range'] = user_actions.get('typing_delay_range', (0.05, 0.15))
            search_config['click_delay_range'] = user_actions.get('click_delay_range', (0.5, 1.0))
            search_config['scroll_before_click'] = user_actions.get('scroll_before_click', True)
            
            # 执行带流程控制的搜索
            search_success = self.search.search_hotel_with_flow_control(
                search_config, 
                hotel_name,
                login_config,
                self.username,
                self.password
            )
            
            if not search_success:
                logger.warning("搜索流程可能未完全成功，但继续尝试提取数据")
            
            # 等待页面稳定
            time.sleep(2)
            
            # 提取酒店列表
            logger.info("开始提取酒店列表数据")
            html = self.browser.get_page_source()
            soup = BeautifulSoup(html, 'lxml')
            
            hotels = self._extract_hotel_list(soup)
            
            if not hotels:
                logger.warning("未提取到酒店数据，尝试更通用的选择器")
                # 尝试更通用的提取方式
                hotels = self._extract_hotel_list_generic(soup)
            
            logger.info(f"飞猪找到 {len(hotels)} 个酒店")
            return hotels
            
        except Exception as e:
            logger.error(f"飞猪搜索酒店失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_hotel_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取酒店列表（使用配置文件中的XPath）"""
        hotels = []
        
        # 从配置文件读取提取XPath
        extraction_cfg = self.config.get('extraction', {})
        hotel_list_xpath = extraction_cfg.get('hotel_list_xpath', '//div[contains(@class, "hotel-item")]')
        
        # 优先使用XPath从浏览器中查找元素
        hotel_items = []
        if self.browser and self.browser.driver:
            try:
                hotel_elements = self.browser.find_elements_by_xpath(hotel_list_xpath, timeout=5)
                logger.info(f"通过XPath找到 {len(hotel_elements)} 个酒店项")
                
                # 将Selenium元素转换为BeautifulSoup对象
                for elem in hotel_elements:
                    try:
                        html = elem.get_attribute('outerHTML')
                        if html:
                            item_soup = BeautifulSoup(html, 'lxml')
                            hotel_items.append(item_soup)
                    except:
                        continue
            except Exception as e:
                logger.warning(f"使用XPath提取失败: {e}，改用CSS选择器")
        
        # 如果XPath没找到，使用CSS选择器作为备选
        if not hotel_items:
            # 将XPath转换为CSS选择器（简单转换）
            css_selectors = [
                '.hotel-item', '.hotel-card', '[data-hotel-id]', 
                '.item', '[class*="hotel"]', '[class*="list"]'
            ]
            hotel_items = soup.select(', '.join(css_selectors))
            logger.info(f"使用CSS选择器找到 {len(hotel_items)} 个可能的酒店项")
        
        # 从配置文件读取各个字段的XPath/CSS选择器
        name_selector = extraction_cfg.get('hotel_name_xpath', '.hotel-name, h3, h4, .name, [class*="name"]')
        price_selector = extraction_cfg.get('hotel_price_xpath', '.price, .min-price, [class*="price"]')
        rating_selector = extraction_cfg.get('hotel_rating_xpath', '.rating, .score, [class*="rating"]')
        address_selector = extraction_cfg.get('hotel_address_xpath', '.address, .location, [class*="address"]')
        link_selector = extraction_cfg.get('hotel_link_xpath', 'a')
        
        # 将XPath转换为CSS选择器（简单处理）
        def xpath_to_css(xpath_str):
            """简单将XPath转换为CSS选择器"""
            if xpath_str.startswith('.//') or xpath_str.startswith('//'):
                # 移除XPath前缀，尝试转换为CSS
                css = xpath_str.replace('.//', '').replace('//', '')
                # 简单的XPath到CSS转换
                css = css.replace('[@', '[').replace('="', '="').replace('"]', '"]')
                css = css.replace('contains(@class, "', '[class*="').replace('")', '"]')
                css = css.replace('@', '')
                return css
            return xpath_str
        
        name_css = xpath_to_css(name_selector)
        price_css = xpath_to_css(price_selector)
        rating_css = xpath_to_css(rating_selector)
        address_css = xpath_to_css(address_selector)
        link_css = xpath_to_css(link_selector)
        
        for item in hotel_items:
            try:
                hotel_data = {
                    'platform': self.platform,
                    'hotel_name': DataExtractor.extract_text(item, name_css),
                    'star_level': DataExtractor.extract_text(item, '.star-level, .star, [class*="star"]'),
                    'rating_score': DataExtractor.extract_rating(
                        DataExtractor.extract_text(item, rating_css)
                    ),
                    'review_count': DataExtractor.extract_review_count(
                        DataExtractor.extract_text(item, '.review-count, .comment-count, [class*="review"]')
                    ),
                    'min_price': DataExtractor.extract_price(
                        DataExtractor.extract_text(item, price_css)
                    ),
                    'address': DataExtractor.extract_text(item, address_css),
                    'hotel_url': DataExtractor.extract_attribute(item, link_css if link_css.startswith('a') or link_css.startswith('.') else 'a', 'href'),
                }
                
                if hotel_data['hotel_url'] and not hotel_data['hotel_url'].startswith('http'):
                    hotel_data['hotel_url'] = self.config['base_url'] + hotel_data['hotel_url']
                
                if hotel_data['hotel_name']:
                    hotels.append(hotel_data)
            
            except Exception as e:
                logger.warning(f"提取酒店信息失败: {e}")
                continue
        
        return hotels
    
    def _extract_hotel_list_generic(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """使用更通用的方式提取酒店列表"""
        hotels = []
        # 尝试查找所有包含链接的div或li元素
        items = soup.select('div a, li a, [class*="item"] a, [class*="card"] a')
        
        logger.info(f"使用通用方法找到 {len(items)} 个可能的链接")
        
        seen_names = set()
        for item in items[:20]:  # 限制数量避免太多
            try:
                parent = item.parent
                if parent:
                    hotel_name = DataExtractor.extract_text(parent, 'h3, h4, .name, [class*="name"]')
                    if not hotel_name:
                        hotel_name = item.get_text(strip=True)
                    
                    if hotel_name and hotel_name not in seen_names and len(hotel_name) > 2:
                        seen_names.add(hotel_name)
                        hotel_url = item.get('href', '')
                        
                        if hotel_url and not hotel_url.startswith('http'):
                            hotel_url = self.config['base_url'] + hotel_url
                        
                        hotel_data = {
                            'platform': self.platform,
                            'hotel_name': hotel_name,
                            'hotel_url': hotel_url,
                            'star_level': '',
                            'rating_score': None,
                            'review_count': None,
                            'min_price': None,
                            'address': '',
                        }
                        hotels.append(hotel_data)
            except Exception as e:
                logger.warning(f"通用提取失败: {e}")
                continue
        
        return hotels
    
    def get_hotel_detail(self, hotel_url: str) -> Dict[str, Any]:
        """获取酒店详情（通过URL）"""
        try:
            logger.info(f"获取飞猪酒店详情: {hotel_url}")
            
            if not self.browser.get(hotel_url):
                return {}
            
            time.sleep(2)
            html = self.browser.get_page_source()
            soup = BeautifulSoup(html, 'lxml')
            
            detail = self._extract_hotel_detail(soup)
            detail['hotel_url'] = hotel_url
            detail['platform'] = self.platform
            detail['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            return detail
            
        except Exception as e:
            logger.error(f"获取飞猪酒店详情失败: {e}")
            return {}
    
    def get_hotel_detail_by_click(self, hotel_item_xpath: str, index: int = 0) -> Dict[str, Any]:
        """
        通过点击酒店列表项进入详情页
        
        Args:
            hotel_item_xpath: 酒店列表项的XPath
            index: 要点击的酒店索引
        """
        try:
            logger.info(f"点击进入酒店详情页（索引: {index}）")
            
            # 点击酒店项
            if not self.search.click_hotel_item_by_xpath(hotel_item_xpath, index):
                logger.error("点击酒店项失败")
                return {}
            
            # 等待详情页加载
            time.sleep(3)
            
            # 提取详情
            html = self.browser.get_page_source()
            soup = BeautifulSoup(html, 'lxml')
            
            detail = self._extract_hotel_detail(soup)
            detail['hotel_url'] = self.browser.get_current_url()
            detail['platform'] = self.platform
            detail['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            return detail
            
        except Exception as e:
            logger.error(f"获取酒店详情失败: {e}")
            return {}
    
    def _extract_hotel_detail(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """提取酒店详情"""
        detail = {
            'hotel_name': DataExtractor.extract_text(soup, '.hotel-name, h1'),
            'star_level': DataExtractor.extract_text(soup, '.star-level'),
            'rating_score': DataExtractor.extract_rating(
                DataExtractor.extract_text(soup, '.rating')
            ),
            'review_count': DataExtractor.extract_review_count(
                DataExtractor.extract_text(soup, '.review-count')
            ),
            'address': DataExtractor.extract_text(soup, '.address'),
            'opening_date': DataExtractor.extract_text(soup, '.opening-date'),
            'region': self._extract_region(soup),
        }
        
        contact_selectors = {
            'phone': '.phone, .tel',
            'email': '.email',
            'address': '.address',
            'website': '.website',
        }
        contact_info = DataExtractor.extract_contact_info(soup, contact_selectors)
        detail.update(contact_info)
        
        room_config = {
            'container_selector': '.room-item',
            'name_selector': '.room-name',
            'price_selector': '.price',
            'stock_selector': '.stock',
        }
        detail['room_types'] = DataExtractor.extract_room_types(soup, room_config)
        
        return detail
    
    def _extract_region(self, soup: BeautifulSoup) -> str:
        """提取区域"""
        address = DataExtractor.extract_text(soup, '.address')
        if address:
            parts = address.split('-')
            if len(parts) >= 2:
                return parts[0] + '-' + parts[1]
        return ''
    
    def crawl_hotel(self, hotel_name: str, need_detail: bool = True, use_click: bool = False) -> List[Dict[str, Any]]:
        """
        完整爬取流程（使用XPath和流程控制）
        
        Args:
            hotel_name: 酒店名称
            need_detail: 是否需要详情
            use_click: 是否通过点击进入详情页（True）或直接访问URL（False）
        """
        results = []
        
        # 搜索酒店
        hotels = self.search_hotel(hotel_name)
        if not hotels:
            logger.warning(f"未找到酒店: {hotel_name}")
            return results
        
        # 获取详情
        if need_detail:
            if use_click:
                # 从配置文件读取酒店列表项XPath
                hotel_item_xpath = self.config.get('extraction', {}).get('hotel_list_xpath', '//div[contains(@class, "hotel-item") or @data-hotel-id]')
                
                for i, hotel in enumerate(hotels):
                    try:
                        # 通过点击进入详情页
                        detail = self.get_hotel_detail_by_click(hotel_item_xpath, i)
                        if detail:
                            hotel.update(detail)
                        results.append(hotel)
                        
                        # 返回列表页继续下一个
                        self.browser.driver.back()
                        time.sleep(2)
                        
                    except Exception as e:
                        logger.error(f"获取酒店详情失败（索引 {i}）: {e}")
                        results.append(hotel)
            else:
                # 直接访问URL获取详情
                for hotel in hotels:
                    if hotel.get('hotel_url'):
                        detail = self.get_hotel_detail(hotel['hotel_url'])
                        hotel.update(detail)
                    results.append(hotel)
        else:
            results = hotels
        
        return results


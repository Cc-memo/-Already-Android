"""
美团平台爬虫
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


class MeituanSpider:
    """美团酒店爬虫"""
    
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        """
        初始化美团爬虫
        
        Args:
            username: 登录用户名（可选）
            password: 登录密码（可选）
        """
        self.platform = 'meituan'
        self.config = PLATFORM_CONFIG['meituan']
        self.username = username
        self.password = password
        self.browser = BrowserManager(headless=False)  # 美团可能需要非无头模式
        self.auth = None
        self.search = None
        
    def __enter__(self):
        """上下文管理器入口"""
        self.browser.init_driver()
        self.auth = AuthManager(self.browser)
        self.search = SearchManager(self.browser)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.browser.close()
    
    def login(self) -> bool:
        """登录美团"""
        if not self.username or not self.password:
            logger.warning("未提供登录凭据，跳过登录")
            return True  # 某些页面可能不需要登录
        
        login_config = {
            'login_url': f"{self.config['base_url']}/account/login",
            'username_selector': 'input[name="username"], input[type="text"]',
            'password_selector': 'input[type="password"]',
            'submit_selector': 'button[type="submit"], .login-btn',
            'success_selector': '.user-info, .user-name',
        }
        
        return self.auth.login(self.platform, self.username, self.password, login_config)
    
    def search_hotel(self, hotel_name: str) -> List[Dict[str, Any]]:
        """
        搜索酒店（使用XPath和流程控制）
        
        Args:
            hotel_name: 酒店名称
        
        Returns:
            酒店列表
        """
        try:
            logger.info(f"美团搜索酒店: {hotel_name}")
            
            # 配置XPath和页面检测标识
            search_config = {
                'search_url': f"{self.config['base_url']}/s/",
                'search_input_xpath': '//input[@type="search" or contains(@class, "search-input")]',
                'search_button_xpath': '//button[contains(@class, "search-btn") or @type="submit"]',
                'use_enter': True,
                # 登录页面标识
                'login_indicators': [
                    '//div[contains(@class, "login")]',
                    '//input[@type="password"]',
                    '//button[contains(text(), "登录")]'
                ],
                # 结果页面标识
                'result_indicators': [
                    '//div[contains(@class, "hotel-list")]',
                    '//div[contains(@class, "hotel-item")]',
                    '//div[@data-hotel-id]'
                ]
            }
            
            # 登录配置（如果需要）
            login_config = None
            if self.username and self.password:
                login_config = {
                    'login_url': f"{self.config['base_url']}/account/login",
                    'username_selector': '//input[@name="username" or @type="text"]',
                    'password_selector': '//input[@type="password"]',
                    'submit_selector': '//button[@type="submit" or contains(@class, "login-btn")]',
                    'success_selector': '//div[contains(@class, "user-info") or contains(@class, "user-name")]',
                }
            
            # 执行带流程控制的搜索
            if not self.search.search_hotel_with_flow_control(
                search_config, 
                hotel_name,
                login_config,
                self.username,
                self.password
            ):
                logger.error("搜索流程失败")
                return []
            
            # 获取页面源码
            html = self.browser.get_page_source()
            soup = BeautifulSoup(html, 'lxml')
            
            # 提取酒店列表
            hotels = self._extract_hotel_list(soup)
            
            logger.info(f"美团找到 {len(hotels)} 个酒店")
            return hotels
            
        except Exception as e:
            logger.error(f"美团搜索酒店失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_hotel_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取酒店列表"""
        hotels = []
        
        # 美团酒店列表选择器（需要根据实际页面调整）
        hotel_items = soup.select('.hotel-item, .hotel-card, [data-hotel-id]')
        
        for item in hotel_items:
            try:
                hotel_data = {
                    'platform': self.platform,
                    'hotel_name': DataExtractor.extract_text(item, '.hotel-name, h3, .name'),
                    'star_level': DataExtractor.extract_text(item, '.star-level, .star'),
                    'rating_score': DataExtractor.extract_rating(
                        DataExtractor.extract_text(item, '.rating, .score')
                    ),
                    'review_count': DataExtractor.extract_review_count(
                        DataExtractor.extract_text(item, '.review-count, .comment-count')
                    ),
                    'min_price': DataExtractor.extract_price(
                        DataExtractor.extract_text(item, '.price, .min-price')
                    ),
                    'address': DataExtractor.extract_text(item, '.address, .location'),
                    'hotel_url': DataExtractor.extract_attribute(item, 'a', 'href'),
                    'hotel_id': DataExtractor.extract_attribute(item, '[data-hotel-id]', 'data-hotel-id'),
                }
                
                # 处理相对URL
                if hotel_data['hotel_url'] and not hotel_data['hotel_url'].startswith('http'):
                    hotel_data['hotel_url'] = self.config['base_url'] + hotel_data['hotel_url']
                
                if hotel_data['hotel_name']:
                    hotels.append(hotel_data)
            
            except Exception as e:
                logger.warning(f"提取酒店信息失败: {e}")
                continue
        
        return hotels
    
    def get_hotel_detail(self, hotel_url: str) -> Dict[str, Any]:
        """
        获取酒店详情（通过URL）
        
        Args:
            hotel_url: 酒店详情页URL
        
        Returns:
            酒店详情信息
        """
        try:
            logger.info(f"获取美团酒店详情: {hotel_url}")
            
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
            logger.error(f"获取美团酒店详情失败: {e}")
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
            'star_level': DataExtractor.extract_text(soup, '.star-level, .star'),
            'rating_score': DataExtractor.extract_rating(
                DataExtractor.extract_text(soup, '.rating, .score')
            ),
            'review_count': DataExtractor.extract_review_count(
                DataExtractor.extract_text(soup, '.review-count, .comment-count')
            ),
            'address': DataExtractor.extract_text(soup, '.address, .location, [class*="address"]'),
            'opening_date': DataExtractor.extract_text(soup, '.opening-date, [class*="opening"]'),
            'region': self._extract_region(soup),
        }
        
        # 提取联系方式
        contact_selectors = {
            'phone': '.phone, .tel, [class*="phone"], [class*="tel"]',
            'email': '.email, [class*="email"]',
            'address': '.address, .location',
            'website': '.website, a[href*="http"]',
        }
        contact_info = DataExtractor.extract_contact_info(soup, contact_selectors)
        detail.update(contact_info)
        
        # 提取房型信息
        room_config = {
            'container_selector': '.room-item, .room-type, [class*="room"]',
            'name_selector': '.room-name, .name',
            'price_selector': '.price, .room-price',
            'stock_selector': '.stock, .available',
        }
        detail['room_types'] = DataExtractor.extract_room_types(soup, room_config)
        
        return detail
    
    def _extract_region(self, soup: BeautifulSoup) -> str:
        """提取区域信息"""
        # 从地址中提取区域
        address = DataExtractor.extract_text(soup, '.address, .location')
        if address:
            # 提取城市和区域（如：北京-东城区）
            parts = address.split('-')
            if len(parts) >= 2:
                return parts[0] + '-' + parts[1]
            elif len(parts) == 1:
                # 尝试从地址文本中提取
                if '北京' in address:
                    return '北京'
                elif '上海' in address:
                    return '上海'
                # 可以添加更多城市判断
        return ''
    
    def crawl_hotel(self, hotel_name: str, need_detail: bool = True, use_click: bool = False) -> List[Dict[str, Any]]:
        """
        完整爬取流程（使用XPath和流程控制）
        
        Args:
            hotel_name: 酒店名称
            need_detail: 是否需要详情
            use_click: 是否通过点击进入详情页（True）或直接访问URL（False）
        
        Returns:
            酒店数据列表
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
                # 使用XPath定位酒店列表项，通过点击进入详情页
                hotel_item_xpath = '//div[contains(@class, "hotel-item") or @data-hotel-id]'
                
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


"""
高德平台爬虫
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


class GaodeSpider:
    """高德酒店爬虫"""
    
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.platform = 'gaode'
        self.config = PLATFORM_CONFIG['gaode']
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
        """登录高德"""
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
        """搜索酒店（使用XPath和流程控制）"""
        try:
            logger.info(f"高德搜索酒店: {hotel_name}")
            
            # 配置XPath和页面检测标识
            search_config = {
                'search_url': self.config['search_url'],
                'search_input_xpath': '//input[@name="query" or contains(@placeholder, "搜索")]',
                'search_button_xpath': '//button[contains(@class, "search-btn") or contains(text(), "搜索")]',
                'use_enter': True,
                # 登录页面标识
                'login_indicators': [
                    '//div[contains(@class, "login")]',
                    '//input[@type="password"]',
                    '//button[contains(text(), "登录")]'
                ],
                # 结果页面标识
                'result_indicators': [
                    '//div[contains(@class, "poi-list")]',
                    '//div[contains(@class, "hotel-list")]',
                    '//div[contains(@class, "poi-item")]'
                ]
            }
            
            # 登录配置（如果需要）
            login_config = None
            if self.username and self.password:
                login_config = {
                    'login_url': f"{self.config['base_url']}/login",
                    'username_selector': '//input[@name="username" or @type="text"]',
                    'password_selector': '//input[@type="password"]',
                    'submit_selector': '//button[contains(@class, "login-btn") or contains(text(), "登录")]',
                    'success_selector': '//div[contains(@class, "user-name")]',
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
            
            html = self.browser.get_page_source()
            soup = BeautifulSoup(html, 'lxml')
            
            hotels = self._extract_hotel_list(soup)
            logger.info(f"高德找到 {len(hotels)} 个酒店")
            return hotels
            
        except Exception as e:
            logger.error(f"高德搜索酒店失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_hotel_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取酒店列表"""
        hotels = []
        hotel_items = soup.select('.poi-item, .hotel-item, .hotel-card')
        
        for item in hotel_items:
            try:
                hotel_data = {
                    'platform': self.platform,
                    'hotel_name': DataExtractor.extract_text(item, '.poi-name, .hotel-name'),
                    'star_level': DataExtractor.extract_text(item, '.star-level'),
                    'rating_score': DataExtractor.extract_rating(
                        DataExtractor.extract_text(item, '.rating')
                    ),
                    'review_count': DataExtractor.extract_review_count(
                        DataExtractor.extract_text(item, '.review-count')
                    ),
                    'min_price': DataExtractor.extract_price(
                        DataExtractor.extract_text(item, '.price')
                    ),
                    'address': DataExtractor.extract_text(item, '.address'),
                    'hotel_url': DataExtractor.extract_attribute(item, 'a', 'href'),
                }
                
                if hotel_data['hotel_url'] and not hotel_data['hotel_url'].startswith('http'):
                    hotel_data['hotel_url'] = self.config['base_url'] + hotel_data['hotel_url']
                
                if hotel_data['hotel_name']:
                    hotels.append(hotel_data)
            
            except Exception as e:
                logger.warning(f"提取酒店信息失败: {e}")
                continue
        
        return hotels
    
    def get_hotel_detail(self, hotel_url: str) -> Dict[str, Any]:
        """获取酒店详情（通过URL）"""
        try:
            logger.info(f"获取高德酒店详情: {hotel_url}")
            
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
            logger.error(f"获取高德酒店详情失败: {e}")
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
            'hotel_name': DataExtractor.extract_text(soup, '.poi-name, .hotel-name, h1'),
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
        
        hotels = self.search_hotel(hotel_name)
        if not hotels:
            return results
        
        if need_detail:
            if use_click:
                # 使用XPath定位酒店列表项，通过点击进入详情页
                hotel_item_xpath = '//div[contains(@class, "poi-item") or contains(@class, "hotel-item")]'
                
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


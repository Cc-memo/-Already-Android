"""
爬虫基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import requests
from bs4 import BeautifulSoup

from crawler.utils.logger import logger
from crawler.utils.helpers import (
    build_headers, random_delay, retry_on_exception,
    parse_price, parse_rating, parse_review_count
)
from crawler.config.settings import CRAWLER_CONFIG, PLATFORM_CONFIG


class BaseSpider(ABC):
    """爬虫基类"""
    
    def __init__(self, platform: str, use_selenium: bool = False):
        """
        初始化爬虫
        
        Args:
            platform: 平台名称 (meituan, ctrip, fliggy, gaode)
            use_selenium: 是否使用Selenium
        """
        self.platform = platform
        self.use_selenium = use_selenium
        self.driver: Optional[webdriver.Chrome] = None
        self.session = requests.Session()
        self.config = PLATFORM_CONFIG.get(platform, {})
        self.crawler_config = CRAWLER_CONFIG
        
        # 配置请求session
        self.session.headers.update(build_headers(platform))
        
    def __enter__(self):
        """上下文管理器入口"""
        if self.use_selenium:
            self.init_selenium()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
    
    def init_selenium(self):
        """初始化Selenium WebDriver"""
        try:
            chrome_options = Options()
            if self.crawler_config['selenium']['headless']:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument(f"--window-size={self.crawler_config['selenium']['window_size'][0]},{self.crawler_config['selenium']['window_size'][1]}")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # 设置User-Agent
            from crawler.utils.helpers import get_random_user_agent
            chrome_options.add_argument(f'user-agent={get_random_user_agent()}')
            
            driver_path = self.crawler_config['selenium'].get('driver_path')
            if driver_path:
                service = Service(driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            self.driver.implicitly_wait(self.crawler_config['selenium']['implicit_wait'])
            self.driver.set_page_load_timeout(self.crawler_config['selenium']['page_load_timeout'])
            
            logger.info(f"{self.platform} Selenium WebDriver 初始化成功")
        except Exception as e:
            logger.error(f"{self.platform} Selenium WebDriver 初始化失败: {e}")
            raise
    
    def close(self):
        """关闭资源"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info(f"{self.platform} WebDriver 已关闭")
            except:
                pass
        self.session.close()
    
    @retry_on_exception(max_retries=3, delay=1.0)
    def fetch_page(self, url: str, use_selenium: Optional[bool] = None) -> Optional[str]:
        """
        获取页面内容
        
        Args:
            url: 页面URL
            use_selenium: 是否使用Selenium，None则使用初始化时的设置
        
        Returns:
            页面HTML内容
        """
        use_selenium = use_selenium if use_selenium is not None else self.use_selenium
        
        if use_selenium and self.driver:
            return self._fetch_with_selenium(url)
        else:
            return self._fetch_with_requests(url)
    
    def _fetch_with_selenium(self, url: str) -> Optional[str]:
        """使用Selenium获取页面"""
        try:
            self.driver.get(url)
            random_delay(1, 2)
            return self.driver.page_source
        except TimeoutException:
            logger.error(f"{self.platform} 页面加载超时: {url}")
            return None
        except WebDriverException as e:
            logger.error(f"{self.platform} Selenium获取页面失败: {url}, 错误: {e}")
            return None
    
    def _fetch_with_requests(self, url: str) -> Optional[str]:
        """使用requests获取页面"""
        try:
            headers = build_headers(self.platform, referer=url)
            response = self.session.get(
                url,
                headers=headers,
                timeout=self.crawler_config['request_timeout']
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            random_delay(1, 2)
            return response.text
        except requests.RequestException as e:
            logger.error(f"{self.platform} requests获取页面失败: {url}, 错误: {e}")
            return None
    
    def parse_html(self, html: str) -> BeautifulSoup:
        """解析HTML"""
        return BeautifulSoup(html, 'lxml')
    
    @abstractmethod
    def search_hotel(self, hotel_name: str) -> List[Dict[str, Any]]:
        """
        搜索酒店列表
        
        Args:
            hotel_name: 酒店名称
        
        Returns:
            酒店列表信息
        """
        pass
    
    @abstractmethod
    def get_hotel_detail(self, hotel_id: str, hotel_url: str) -> Dict[str, Any]:
        """
        获取酒店详情
        
        Args:
            hotel_id: 酒店ID
            hotel_url: 酒店详情页URL
        
        Returns:
            酒店详情信息
        """
        pass
    
    def extract_list_data(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        从列表页提取数据（子类可重写）
        
        Args:
            soup: BeautifulSoup对象
        
        Returns:
            酒店列表数据
        """
        return []
    
    def extract_detail_data(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        从详情页提取数据（子类可重写）
        
        Args:
            soup: BeautifulSoup对象
        
        Returns:
            酒店详情数据
        """
        return {}
    
    def normalize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化数据格式
        
        Args:
            data: 原始数据
        
        Returns:
            标准化后的数据
        """
        normalized = {
            'platform': self.platform,
            'hotel_name': data.get('hotel_name', ''),
            'star_level': data.get('star_level', ''),
            'rating_score': parse_rating(data.get('rating_score', '')),
            'review_count': parse_review_count(data.get('review_count', '')),
            'min_price': parse_price(data.get('min_price', '')),
            'booking_dynamic': data.get('booking_dynamic', ''),
            'address': data.get('address', ''),
            'region': data.get('region', ''),
            'opening_date': data.get('opening_date', ''),
            'room_types': data.get('room_types', []),
            'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        return normalized


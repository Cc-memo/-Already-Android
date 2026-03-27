"""
美团爬虫测试
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import unittest
from unittest.mock import Mock, patch
from crawler.spiders.meituan_spider import MeituanSpider


class TestMeituanSpider(unittest.TestCase):
    """美团爬虫测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.spider = MeituanSpider()
    
    def tearDown(self):
        """测试后清理"""
        if hasattr(self.spider, 'browser'):
            self.spider.browser.close()
    
    @patch('crawler.spiders.meituan_spider.BrowserManager')
    def test_init(self, mock_browser):
        """测试初始化"""
        spider = MeituanSpider(username='test', password='test')
        self.assertEqual(spider.platform, 'meituan')
        self.assertEqual(spider.username, 'test')
        self.assertEqual(spider.password, 'test')
    
    @patch('crawler.spiders.meituan_spider.BrowserManager')
    @patch('crawler.spiders.meituan_spider.AuthManager')
    def test_login(self, mock_auth, mock_browser):
        """测试登录"""
        spider = MeituanSpider(username='test', password='test')
        spider.browser = Mock()
        spider.auth = Mock()
        spider.auth.login.return_value = True
        
        result = spider.login()
        self.assertTrue(result)
    
    @patch('crawler.spiders.meituan_spider.BrowserManager')
    @patch('crawler.spiders.meituan_spider.SearchManager')
    def test_search_hotel(self, mock_search, mock_browser):
        """测试搜索酒店"""
        spider = MeituanSpider()
        spider.browser = Mock()
        spider.search = Mock()
        spider.search.search_hotel_by_name.return_value = True
        spider.search.wait_for_results.return_value = True
        spider.browser.get_page_source.return_value = '<html><body><div class="hotel-item"><h3>测试酒店</h3></div></body></html>'
        
        results = spider.search_hotel('测试酒店')
        self.assertIsInstance(results, list)
    
    def test_extract_hotel_list(self):
        """测试提取酒店列表"""
        from bs4 import BeautifulSoup
        
        html = '''
        <div class="hotel-item">
            <h3 class="hotel-name">测试酒店</h3>
            <div class="star-level">五星级</div>
            <div class="rating">4.8分</div>
            <div class="price">¥588/晚</div>
            <div class="address">北京市东城区</div>
            <a href="/hotel/123">详情</a>
        </div>
        '''
        soup = BeautifulSoup(html, 'lxml')
        
        spider = MeituanSpider()
        hotels = spider._extract_hotel_list(soup)
        
        self.assertGreater(len(hotels), 0)
        self.assertEqual(hotels[0]['hotel_name'], '测试酒店')
    
    def test_extract_region(self):
        """测试提取区域"""
        from bs4 import BeautifulSoup
        
        html = '<div class="address">北京市-东城区-东长安街33号</div>'
        soup = BeautifulSoup(html, 'lxml')
        
        spider = MeituanSpider()
        region = spider._extract_region(soup)
        
        self.assertEqual(region, '北京市-东城区')


if __name__ == '__main__':
    unittest.main()


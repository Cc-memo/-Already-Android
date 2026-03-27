"""
高德爬虫测试
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import unittest
from unittest.mock import Mock
from crawler.spiders.gaode_spider import GaodeSpider


class TestGaodeSpider(unittest.TestCase):
    """高德爬虫测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.spider = GaodeSpider()
    
    def tearDown(self):
        """测试后清理"""
        if hasattr(self.spider, 'browser'):
            self.spider.browser.close()
    
    def test_init(self):
        """测试初始化"""
        spider = GaodeSpider()
        self.assertEqual(spider.platform, 'gaode')
    
    def test_extract_hotel_list(self):
        """测试提取酒店列表"""
        from bs4 import BeautifulSoup
        
        html = '''
        <div class="poi-item">
            <div class="poi-name">测试酒店</div>
            <div class="address">北京市朝阳区</div>
        </div>
        '''
        soup = BeautifulSoup(html, 'lxml')
        
        spider = GaodeSpider()
        hotels = spider._extract_hotel_list(soup)
        
        self.assertIsInstance(hotels, list)


if __name__ == '__main__':
    unittest.main()


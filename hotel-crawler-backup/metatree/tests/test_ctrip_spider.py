"""
携程爬虫测试
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
from crawler.spiders.ctrip_spider import CtripSpider


class TestCtripSpider(unittest.TestCase):
    """携程爬虫测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.spider = CtripSpider()
    
    def tearDown(self):
        """测试后清理"""
        if hasattr(self.spider, 'browser'):
            self.spider.browser.close()
    
    @patch('crawler.spiders.ctrip_spider.BrowserManager')
    def test_init(self, mock_browser):
        """测试初始化"""
        spider = CtripSpider(username='test', password='test')
        self.assertEqual(spider.platform, 'ctrip')
    
    def test_extract_hotel_list(self):
        """测试提取酒店列表"""
        from bs4 import BeautifulSoup
        
        html = '''
        <div class="hotel-item">
            <h3 class="hotel-name">测试酒店</h3>
            <div class="star-level">五星级</div>
            <div class="rating">4.8</div>
            <div class="price">¥588</div>
            <div class="address">上海市黄浦区</div>
        </div>
        '''
        soup = BeautifulSoup(html, 'lxml')
        
        spider = CtripSpider()
        hotels = spider._extract_hotel_list(soup)
        
        self.assertIsInstance(hotels, list)

    def test_crawl_hotel_interactive(self):
        """交互式测试：实际爬取携程平台酒店数据"""
        hotel_name = input("\n请输入要测试的酒店名称（携程）: ").strip()
        
        if not hotel_name:
            print("未输入酒店名称，跳过测试")
            return
        
        print(f"\n{'='*60}")
        print(f"开始爬取携程平台酒店: {hotel_name}")
        print(f"{'='*60}")
        
        try:
            with CtripSpider() as spider:
                results = spider.crawl_hotel(hotel_name, need_detail=True)
                
                print(f"\n爬取完成！找到 {len(results)} 个酒店")
                print(f"{'='*60}")
                
                if results:
                    import json
                    print("\n爬取结果（JSON格式）:")
                    print(json.dumps(results, ensure_ascii=False, indent=2))
                    
                    print(f"\n{'='*60}")
                    print("结果摘要:")
                    for i, hotel in enumerate(results, 1):
                        print(f"\n{i}. {hotel.get('hotel_name', '未知')}")
                        print(f"   平台: {hotel.get('platform', '未知')}")
                        print(f"   评分: {hotel.get('rating_score', '未知')}")
                        print(f"   价格: {hotel.get('min_price', '未知')}")
                        print(f"   地址: {hotel.get('address', '未知')}")
                        if hotel.get('hotel_url'):
                            print(f"   链接: {hotel.get('hotel_url')}")
                else:
                    print("未找到任何酒店")
                    
        except Exception as e:
            print(f"\n爬取失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    import sys
    # 检查是否有 --interactive 参数
    if '--interactive' in sys.argv:
        sys.argv.remove('--interactive')
        test = TestCtripSpider()
        test.test_crawl_hotel_interactive()
    else:
        unittest.main()


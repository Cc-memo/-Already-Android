"""
飞猪爬虫测试
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
from crawler.spiders.fliggy_spider import FliggySpider
import json


class TestFliggySpider(unittest.TestCase):
    """飞猪爬虫测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.spider = FliggySpider()
    
    def tearDown(self):
        """测试后清理"""
        if hasattr(self.spider, 'browser'):
            self.spider.browser.close()
    
    def test_init(self):
        """测试初始化"""
        spider = FliggySpider()
        self.assertEqual(spider.platform, 'fliggy')
    
    def test_extract_hotel_list(self):
        """测试提取酒店列表"""
        from bs4 import BeautifulSoup
        
        html = '''
        <div class="hotel-item">
            <div class="hotel-name">测试酒店</div>
            <div class="price">¥588</div>
        </div>
        '''
        soup = BeautifulSoup(html, 'lxml')
        
        spider = FliggySpider()
        hotels = spider._extract_hotel_list(soup)
        
        self.assertIsInstance(hotels, list)

    def test_crawl_hotel_interactive(self):
        """交互式测试：实际爬取飞猪平台酒店数据"""
        hotel_name = input("\n请输入要测试的酒店名称（飞猪）: ").strip()
        
        if not hotel_name:
            print("未输入酒店名称，跳过测试")
            return
        
        print(f"\n{'='*60}")
        print(f"开始爬取飞猪平台酒店: {hotel_name}")
        print(f"{'='*60}")
        
        try:
            with FliggySpider() as spider:
                results = spider.crawl_hotel(hotel_name, need_detail=True)
                
                print(f"\n爬取完成！找到 {len(results)} 个酒店")
                print(f"{'='*60}")
                
                if results:
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
        test = TestFliggySpider()
        test.test_crawl_hotel_interactive()
    else:
        unittest.main()


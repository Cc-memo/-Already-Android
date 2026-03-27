#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
爬虫使用示例
"""
from crawler.spiders.meituan_spider import MeituanSpider
from crawler.spiders.ctrip_spider import CtripSpider
from crawler.spiders.fliggy_spider import FliggySpider
from crawler.spiders.gaode_spider import GaodeSpider
from crawler.utils.logger import logger


def example_single_platform():
    """示例：单个平台爬虫"""
    print("=" * 50)
    print("示例1: 使用美团爬虫")
    print("=" * 50)
    
    # 使用上下文管理器（推荐）
    with MeituanSpider() as spider:
        # 搜索酒店（不需要登录也可以搜索）
        hotels = spider.search_hotel("北京饭店")
        
        print(f"\n找到 {len(hotels)} 个酒店:")
        for i, hotel in enumerate(hotels[:3], 1):  # 只显示前3个
            print(f"\n{i}. {hotel.get('hotel_name', 'N/A')}")
            print(f"   星级: {hotel.get('star_level', 'N/A')}")
            print(f"   评分: {hotel.get('rating_score', 'N/A')}")
            print(f"   价格: {hotel.get('min_price', 'N/A')}")
            print(f"   地址: {hotel.get('address', 'N/A')}")


def example_with_login():
    """示例：需要登录的爬虫"""
    print("\n" + "=" * 50)
    print("示例2: 带登录的爬虫（需要提供真实凭据）")
    print("=" * 50)
    
    # 注意：这里需要真实的登录凭据
    username = "your_username"  # 替换为真实用户名
    password = "your_password"  # 替换为真实密码
    
    with MeituanSpider(username=username, password=password) as spider:
        # 登录
        if spider.login():
            print("登录成功")
            # 执行爬取
            hotels = spider.crawl_hotel("北京饭店", need_detail=True)
            print(f"爬取完成，获得 {len(hotels)} 条数据")
        else:
            print("登录失败")


def example_multi_platform():
    """示例：多平台爬取"""
    print("\n" + "=" * 50)
    print("示例3: 多平台爬取")
    print("=" * 50)
    
    hotel_name = "北京饭店"
    platforms = [
        ('美团', MeituanSpider),
        ('携程', CtripSpider),
        # ('飞猪', FliggySpider),
        # ('高德', GaodeSpider),
    ]
    
    all_results = {}
    
    for platform_name, SpiderClass in platforms:
        print(f"\n正在爬取 {platform_name}...")
        try:
            with SpiderClass() as spider:
                hotels = spider.search_hotel(hotel_name)
                all_results[platform_name] = hotels
                print(f"{platform_name}: 找到 {len(hotels)} 个酒店")
        except Exception as e:
            logger.error(f"{platform_name} 爬取失败: {e}")
            all_results[platform_name] = []
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("爬取结果汇总:")
    print("=" * 50)
    for platform, hotels in all_results.items():
        print(f"{platform}: {len(hotels)} 条数据")


def example_get_detail():
    """示例：获取酒店详情（包含联系方式）"""
    print("\n" + "=" * 50)
    print("示例4: 获取酒店详情")
    print("=" * 50)
    
    with MeituanSpider() as spider:
        # 先搜索
        hotels = spider.search_hotel("北京饭店")
        
        if hotels and hotels[0].get('hotel_url'):
            # 获取第一个酒店的详情
            hotel_url = hotels[0]['hotel_url']
            print(f"获取详情: {hotel_url}")
            
            detail = spider.get_hotel_detail(hotel_url)
            
            print("\n酒店详情:")
            print(f"名称: {detail.get('hotel_name', 'N/A')}")
            print(f"星级: {detail.get('star_level', 'N/A')}")
            print(f"评分: {detail.get('rating_score', 'N/A')}")
            print(f"地址: {detail.get('address', 'N/A')}")
            print(f"区域: {detail.get('region', 'N/A')}")
            print(f"开业时间: {detail.get('opening_date', 'N/A')}")
            
            # 联系方式
            print("\n联系方式:")
            print(f"电话: {detail.get('phone', 'N/A')}")
            print(f"邮箱: {detail.get('email', 'N/A')}")
            print(f"网站: {detail.get('website', 'N/A')}")
            
            # 房型信息
            room_types = detail.get('room_types', [])
            if room_types:
                print(f"\n房型信息 ({len(room_types)} 种):")
                for room in room_types[:3]:  # 只显示前3种
                    print(f"  - {room.get('room_name', 'N/A')}: ¥{room.get('min_price', 'N/A')}/晚")


if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("酒店信息爬虫 - 使用示例")
    print("=" * 50)
    
    # 运行示例（根据需要取消注释）
    example_single_platform()
    # example_with_login()  # 需要真实凭据
    # example_multi_platform()
    # example_get_detail()
    
    print("\n" + "=" * 50)
    print("示例运行完成！")
    print("=" * 50)
    print("\n提示:")
    print("1. 修改代码中的示例函数调用以运行不同示例")
    print("2. 某些功能可能需要登录，请提供真实凭据")
    print("3. 实际爬取时请遵守各平台的robots.txt和使用条款")


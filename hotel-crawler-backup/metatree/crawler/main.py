"""
爬虫主程序入口
支持传统爬虫和LangGraph流程两种模式
"""
import argparse
import sys
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from crawler.utils.logger import logger
from crawler.core.browser import BrowserManager
from crawler.config.settings import CRAWLER_CONFIG
from crawler.graph import CrawlState, get_graph_for_platform

# 保留传统爬虫接口（向后兼容）
from crawler.spiders.meituan_spider import MeituanSpider
from crawler.spiders.ctrip_spider import CtripSpider
from crawler.spiders.fliggy_spider import FliggySpider
from crawler.spiders.gaode_spider import GaodeSpider


def crawl_hotel_with_graph(hotel_name: str, platform: str,
                           username: str = None, password: str = None,
                           task_id: str = None) -> Dict[str, Any]:
    """
    使用LangGraph流程爬取酒店信息
    
    Args:
        hotel_name: 酒店名称
        platform: 平台名称
        username: 登录用户名（可选）
        password: 登录密码（可选）
        task_id: 任务ID（可选，不提供则自动生成）
    
    Returns:
        爬取结果字典，包含状态、数据、日志等
    """
    if not task_id:
        task_id = str(uuid.uuid4())
    
    # 初始化浏览器
    selenium_config = CRAWLER_CONFIG.get('selenium', {})
    browser = BrowserManager(
        headless=selenium_config.get('headless', True),
        window_size=selenium_config.get('window_size', (1920, 1080))
    )
    # 初始化浏览器驱动，显式传入 driver_path，避免 Selenium Manager 兜底
    if not browser.init_driver(driver_path=selenium_config.get('driver_path')):
        raise RuntimeError("浏览器初始化失败，请检查 Chrome/ChromeDriver 是否安装并匹配")
    
    try:
        # 创建初始状态
        initial_state = CrawlState(
            task_id=task_id,
            hotel_name=hotel_name,
            platform=platform,
            login_credentials={
                'username': username,
                'password': password
            } if username and password else None
        )
        
        # 获取平台对应的流程图
        graph = get_graph_for_platform(platform, browser)
        
        # 执行流程
        logger.info(f"开始执行 {platform} 平台爬取流程: {hotel_name}")
        final_state = graph.invoke(initial_state)
        
        # LangGraph 返回的是字典类型，需要用字典方式访问
        # 如果是 CrawlState 对象则用属性访问，否则用字典访问
        if hasattr(final_state, 'task_id'):
            # CrawlState 对象
            result = {
                'task_id': final_state.task_id,
                'platform': final_state.platform,
                'hotel_name': final_state.hotel_name,
                'status': 'success' if final_state.error_count == 0 else 'failed',
                'current_node': final_state.current_node,
                'visited_nodes': final_state.visited_nodes,
                'error_count': final_state.error_count,
                'hotel_data': final_state.hotel_data,
                'validation_results': final_state.validation_results,
                'logs': final_state.logs,
                'error_messages': final_state.error_messages,
                'start_time': final_state.start_time.isoformat() if hasattr(final_state.start_time, 'isoformat') else str(final_state.start_time),
                'end_time': final_state.end_time.isoformat() if final_state.end_time and hasattr(final_state.end_time, 'isoformat') else None,
            }
            hotel_data = final_state.hotel_data
        else:
            # 字典类型 (AddableValuesDict)
            result = {
                'task_id': final_state.get('task_id', task_id),
                'platform': final_state.get('platform', platform),
                'hotel_name': final_state.get('hotel_name', hotel_name),
                'status': 'success' if final_state.get('error_count', 0) == 0 else 'failed',
                'current_node': final_state.get('current_node', ''),
                'visited_nodes': final_state.get('visited_nodes', []),
                'error_count': final_state.get('error_count', 0),
                'hotel_data': final_state.get('hotel_data', []),
                'validation_results': final_state.get('validation_results', {}),
                'logs': final_state.get('logs', []),
                'error_messages': final_state.get('error_messages', []),
                'start_time': str(final_state.get('start_time', '')),
                'end_time': str(final_state.get('end_time', '')) if final_state.get('end_time') else None,
            }
            hotel_data = final_state.get('hotel_data', [])
        
        logger.info(f"{platform} 平台爬取完成，获得 {len(hotel_data)} 条数据")
        return result
        
    except Exception as e:
        logger.error(f"{platform} 平台爬取失败: {e}")
        return {
            'task_id': task_id,
            'platform': platform,
            'hotel_name': hotel_name,
            'status': 'failed',
            'error': str(e),
            'hotel_data': [],
        }
    finally:
        browser.close()


def crawl_hotel(hotel_name: str, platforms: List[str], 
                username: str = None, password: str = None,
                need_detail: bool = True,
                use_graph: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """
    爬取酒店信息（支持LangGraph和传统模式）
    
    Args:
        hotel_name: 酒店名称
        platforms: 平台列表 ['meituan', 'ctrip', 'fliggy', 'gaode']
        username: 登录用户名（可选）
        password: 登录密码（可选）
        need_detail: 是否需要详情（传统模式使用）
        use_graph: 是否使用LangGraph流程（默认True）
    
    Returns:
        各平台的酒店数据字典
    """
    results = {}
    
    if use_graph:
        # 使用LangGraph流程
        for platform in platforms:
            try:
                logger.info(f"开始爬取 {platform} 平台: {hotel_name} (LangGraph模式)")
                result = crawl_hotel_with_graph(
                    hotel_name=hotel_name,
                    platform=platform,
                    username=username,
                    password=password
                )
                results[platform] = result.get('hotel_data', [])
            except Exception as e:
                logger.error(f"{platform} 平台爬取失败: {e}")
                results[platform] = []
    else:
        # 使用传统爬虫（向后兼容）
        spider_classes = {
            'meituan': MeituanSpider,
            'ctrip': CtripSpider,
            'fliggy': FliggySpider,
            'gaode': GaodeSpider,
        }
        
        for platform in platforms:
            if platform not in spider_classes:
                logger.warning(f"不支持的平台: {platform}")
                continue
            
            try:
                logger.info(f"开始爬取 {platform} 平台: {hotel_name} (传统模式)")
                
                SpiderClass = spider_classes[platform]
                with SpiderClass(username=username, password=password) as spider:
                    hotels = spider.crawl_hotel(hotel_name, need_detail=need_detail)
                    results[platform] = hotels
                    logger.info(f"{platform} 平台爬取完成，获得 {len(hotels)} 条数据")
            
            except Exception as e:
                logger.error(f"{platform} 平台爬取失败: {e}")
                results[platform] = []
    
    return results


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='酒店信息爬虫')
    parser.add_argument('--hotel', '-n', type=str, required=True, help='酒店名称')
    parser.add_argument('--platforms', '-p', type=str, nargs='+', 
                       default=['meituan', 'ctrip', 'fliggy', 'gaode'],
                       choices=['meituan', 'ctrip', 'fliggy', 'gaode'],
                       help='目标平台')
    parser.add_argument('--username', '-u', type=str, help='登录用户名')
    parser.add_argument('--password', '-w', type=str, help='登录密码')
    parser.add_argument('--no-detail', action='store_true', help='不获取详情（仅传统模式）')
    parser.add_argument('--output', '-o', type=str, help='输出文件路径（JSON格式）')
    parser.add_argument('--use-graph', action='store_true', default=True, 
                       help='使用LangGraph流程（默认启用）')
    parser.add_argument('--no-graph', dest='use_graph', action='store_false',
                       help='不使用LangGraph流程，使用传统爬虫')
    
    args = parser.parse_args()
    
    # 执行爬取
    results = crawl_hotel(
        hotel_name=args.hotel,
        platforms=args.platforms,
        username=args.username,
        password=args.password,
        need_detail=not args.no_detail,
        use_graph=args.use_graph
    )
    
    # 输出结果
    import json
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已保存到: {args.output}")
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    
    # 统计信息
    total = sum(len(hotels) for hotels in results.values())
    logger.info(f"爬取完成，共获得 {total} 条数据")


if __name__ == '__main__':
    main()


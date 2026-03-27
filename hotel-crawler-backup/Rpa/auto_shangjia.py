# -*- coding: utf-8 -*-
"""
自动比价上架脚本
1. 调用 price_comparison 模块进行比价
2. 筛选出有利润的房型
3. 调用 test_shangjia RPA 自动上架

使用方式:
    python auto_shangjia.py --hotel "美利居" --date "12.29"
    python auto_shangjia.py --hotel "美利居" --date "12.29" --count 3
    python auto_shangjia.py --hotel "美利居" --date "12.29" --dry-run  # 只显示不执行
"""

import os
import sys
import argparse
import logging
from typing import List, Dict, Optional
from datetime import datetime

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 添加路径以便导入模块
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'shangjia'))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(SCRIPT_DIR, 'auto_shangjia.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PriceRecommendation:
    """价格推荐数据类"""
    def __init__(self, room_type: str, room_level: str, price: int, 
                 profit_percent: float, original_room_name: str,
                 cheaper_platform: str, room_count: int = None):
        self.room_type = room_type          # 房间类型: "双人间", "单人间", "三人间"
        self.room_level = room_level        # 房间等级: "商务", "舒适", "豪华" 等
        self.price = price                  # 推荐价格（更便宜的那个）
        self.profit_percent = profit_percent  # 利润百分比
        self.original_room_name = original_room_name  # 原始房型名称
        self.cheaper_platform = cheaper_platform  # 更便宜的平台
        self.room_count = room_count        # 剩余房间数量
        self.shangjia_room_type = ""        # 映射后的代理通房型名称
    
    def __repr__(self):
        count_str = f", {self.room_count}间" if self.room_count else ""
        return f"PriceRecommendation({self.room_level}{self.room_type}, {self.price}元{count_str}, 利润{self.profit_percent:.1f}%)"


class RoomTypeMapper:
    """房型名称映射器 - 将比价结果映射到代理通房型"""
    
    # 代理通房型映射规则
    # 比价结果的 (room_type, room_level) -> 代理通房型名称
    # 映射规则：比价结果 (room_type, room_level) -> 代理通房型名称
    # 注意：这里的映射需要根据实际代理通中的房型名称来配置
    # 只有明确匹配的房型才会被处理，未匹配的返回 None 跳过
    MAPPING_RULES = {
        # 大床房类型 -> 代理通的 "高级大床房"
        ("双人间", "商务"): "高级大床房",
        ("双人间", "舒适"): "高级大床房",
        ("双人间", "豪华"): "高级大床房",
        ("双人间", "基础"): "高级大床房",
        ("双人间", "其他"): "高级大床房",
        
        # 双床房类型 -> 代理通的 "高级双床房"
        ("双床", "商务"): "高级双床房",
        ("双床", "舒适"): "高级双床房",
        ("双床", "豪华"): "高级双床房",
        ("双床", "基础"): "高级双床房",
        ("双床", "其他"): "高级双床房",
        
        # 三人间、单人间等没有对应的代理通房型，不在映射表中
        # 这些房型会返回 None，不会被处理
    }
    
    @classmethod
    def map_to_shangjia(cls, room_type: str, room_level: str) -> Optional[str]:
        """
        将比价结果的房型映射到代理通房型名称
        
        参数:
            room_type: 房间类型 ("双人间", "单人间", "三人间")
            room_level: 房间等级 ("商务", "舒适", "豪华", "基础", "其他")
        
        返回:
            代理通房型名称，如果没有匹配则返回 None
        """
        # 先尝试精确匹配
        key = (room_type, room_level)
        if key in cls.MAPPING_RULES:
            return cls.MAPPING_RULES[key]
        
        # 如果没有精确匹配，尝试模糊匹配（只匹配双人间和双床）
        # 根据房间类型生成默认房型名称
        if "双人" in room_type or "大床" in room_type:
            return "高级大床房"
        elif "双床" in room_type:
            return "高级双床房"
        
        # 其他房型（单人间、三人间等）没有对应的代理通房型，返回 None 跳过
        logger.info(f"  跳过未匹配房型: {room_type} + {room_level}")
        return None


class PriceComparisonLoader:
    """比价数据加载器"""
    
    def __init__(self, profit_threshold: float = 10.0):
        """
        初始化
        
        参数:
            profit_threshold: 利润阈值百分比，默认10%
        """
        self.profit_threshold = profit_threshold
        self.xiecheng_file = os.path.join(SCRIPT_DIR, "xiecheng", "hotel_data.json")
        self.meituan_file = os.path.join(SCRIPT_DIR, "meituan", "meituan_hotel.json")
    
    @staticmethod
    def _parse_room_count(remaining_str: str) -> Optional[int]:
        """
        从剩余房间字符串中提取数量
        
        例如:
            "仅剩1间" -> 1
            "仅剩2间" -> 2
            "剩余3间" -> 3
            "满房" -> None
            "" -> None
        """
        import re
        if not remaining_str:
            return None
        if "满房" in remaining_str or "全部订完" in remaining_str:
            return None
        
        # 提取数字
        match = re.search(r'(\d+)', remaining_str)
        if match:
            return int(match.group(1))
        return None
    
    def _build_room_count_map(self, data: Dict) -> Dict[str, int]:
        """
        构建房型名称到剩余房间数量的映射
        
        返回:
            {房型名称: 剩余数量}
        """
        room_count_map = {}
        room_list = data.get("房型列表", [])
        
        for room in room_list:
            room_name = room.get("房型名称", "")
            remaining = room.get("剩余房间", "")
            count = self._parse_room_count(remaining)
            
            if room_name and count is not None:
                # 如果同一房型有多个价格，取第一个（通常是最便宜的）
                if room_name not in room_count_map:
                    room_count_map[room_name] = count
        
        return room_count_map
    
    def load_recommendations(self) -> List[PriceRecommendation]:
        """
        加载比价数据并返回有利润的推荐列表
        
        返回:
            PriceRecommendation 列表
        """
        # 导入比价模块
        try:
            from price_comparison import DataLoader, PriceComparator
        except ImportError as e:
            logger.error(f"无法导入比价模块: {e}")
            raise
        
        # 检查文件是否存在
        if not os.path.exists(self.xiecheng_file):
            raise FileNotFoundError(f"携程数据文件不存在: {self.xiecheng_file}")
        if not os.path.exists(self.meituan_file):
            raise FileNotFoundError(f"美团数据文件不存在: {self.meituan_file}")
        
        # 加载数据
        logger.info("加载比价数据...")
        xiecheng_data = DataLoader.load_json(self.xiecheng_file)
        meituan_data = DataLoader.load_json(self.meituan_file)
        
        logger.info(f"携程数据: {xiecheng_data.get('酒店名称', '未知')}")
        logger.info(f"美团数据: {meituan_data.get('酒店关键词', '未知')}")
        
        # 构建房间数量映射（用于后续提取剩余房间数）
        xiecheng_room_count_map = self._build_room_count_map(xiecheng_data)
        meituan_room_count_map = self._build_room_count_map(meituan_data)
        
        logger.info(f"携程房间数量映射: {len(xiecheng_room_count_map)} 个房型")
        logger.info(f"美团房间数量映射: {len(meituan_room_count_map)} 个房型")
        
        # 解析房间数据
        xiecheng_rooms = DataLoader.parse_room_data(xiecheng_data, "携程")
        meituan_rooms = DataLoader.parse_room_data(meituan_data, "美团")
        
        logger.info(f"携程房间数: {len(xiecheng_rooms)}")
        logger.info(f"美团房间数: {len(meituan_rooms)}")
        
        # 比较价格
        comparator = PriceComparator(
            threshold=50.0, 
            threshold_percent=self.profit_threshold, 
            profit_threshold_percent=self.profit_threshold
        )
        comparisons = comparator.compare_all_rooms(xiecheng_rooms, meituan_rooms)
        
        logger.info(f"比较结果数: {len(comparisons)}")
        
        # 筛选有利润的
        recommendations = []
        seen_rooms = set()  # 用于去重
        
        for comp in comparisons:
            if not comp.has_profit:
                continue
            
            # 取更便宜的价格和对应的房间数量
            if comp.price_a < comp.price_b:
                price = int(comp.price_a)
                original_name = comp.room_name_a
                cheaper_platform = comp.platform_a
                # 从对应平台的映射中获取房间数量
                if cheaper_platform == "携程":
                    room_count = xiecheng_room_count_map.get(original_name)
                else:
                    room_count = meituan_room_count_map.get(original_name)
            else:
                price = int(comp.price_b)
                original_name = comp.room_name_b
                cheaper_platform = comp.platform_b
                if cheaper_platform == "携程":
                    room_count = xiecheng_room_count_map.get(original_name)
                else:
                    room_count = meituan_room_count_map.get(original_name)
            
            room_type = comp.room_type.value
            # room_level 暂时使用默认值（PriceComparison 中未实现此属性）
            room_level = "其他"
            
            # 映射到代理通房型
            shangjia_room_type = RoomTypeMapper.map_to_shangjia(room_type, room_level)
            
            # 如果没有匹配的代理通房型，跳过
            if shangjia_room_type is None:
                continue
            
            # 去重：同一个代理通房型只保留价格最低的（利润最高的）
            # 使用映射后的代理通房型名称作为去重key
            if shangjia_room_type in seen_rooms:
                logger.debug(f"  跳过重复房型: {room_type}+{room_level} -> {shangjia_room_type}")
                continue
            seen_rooms.add(shangjia_room_type)
            
            rec = PriceRecommendation(
                room_type=room_type,
                room_level=room_level,  # 使用默认值 "其他"
                price=price,
                room_count=room_count,
                profit_percent=comp.price_diff_percent,
                original_room_name=original_name,
                cheaper_platform=cheaper_platform
            )
            
            rec.shangjia_room_type = shangjia_room_type
            
            recommendations.append(rec)
        
        # 按利润百分比排序（高的在前）
        recommendations.sort(key=lambda x: x.profit_percent, reverse=True)
        
        return recommendations


class AutoShangjia:
    """自动上架主类"""
    
    def __init__(self, hotel_name: str, target_date: str, 
                 room_count: int = None, dry_run: bool = False):
        """
        初始化
        
        参数:
            hotel_name: 代理通中的酒店名称
            target_date: 目标日期（如 "12.29"）
            room_count: 房间数量（可选）
            dry_run: 是否只显示不执行
        """
        self.hotel_name = hotel_name
        self.target_date = target_date
        self.room_count = room_count
        self.dry_run = dry_run
        
        self.loader = PriceComparisonLoader()
        self.rpa = None  # RPA 实例，延迟初始化
    
    def run(self):
        """运行自动上架流程"""
        logger.info("=" * 60)
        logger.info("🚀 自动比价上架程序")
        logger.info("=" * 60)
        logger.info(f"酒店名称: {self.hotel_name}")
        logger.info(f"目标日期: {self.target_date}")
        logger.info(f"房间数量覆盖: {self.room_count if self.room_count else '使用比价数据中的剩余房间数'}")
        logger.info(f"模式: {'演示模式（不实际执行）' if self.dry_run else '正式执行'}")
        logger.info("=" * 60)
        
        # 步骤1: 获取比价推荐
        logger.info("\n[步骤1] 获取比价推荐...")
        try:
            recommendations = self.loader.load_recommendations()
        except Exception as e:
            logger.error(f"获取比价数据失败: {e}")
            return False
        
        if not recommendations:
            logger.warning("❌ 没有找到有利润的房型推荐")
            return False
        
        logger.info(f"✓ 找到 {len(recommendations)} 个有利润的房型:")
        for i, rec in enumerate(recommendations, 1):
            logger.info(f"  {i}. {rec.room_level}{rec.room_type}")
            logger.info(f"     → 代理通房型: {rec.shangjia_room_type}")
            logger.info(f"     → 推荐价格: {rec.price}元 (来自{rec.cheaper_platform})")
            room_count_str = f"{rec.room_count}间" if rec.room_count else "未知"
            logger.info(f"     → 剩余房间: {room_count_str}")
            logger.info(f"     → 利润空间: {rec.profit_percent:.1f}%")
        
        if self.dry_run:
            logger.info("\n[演示模式] 以下是将要执行的操作:")
            for rec in recommendations:
                # 优先使用命令行参数的房间数量，否则使用比价数据中的
                actual_count = self.room_count if self.room_count else rec.room_count
                count_str = f", 房间数: {actual_count}" if actual_count else ""
                logger.info(f"  - 设置 {rec.shangjia_room_type} 的价格为 {rec.price}元{count_str}")
            logger.info("\n[演示模式] 如需实际执行，请去掉 --dry-run 参数")
            return True
        
        # 步骤2: 初始化 RPA
        logger.info("\n[步骤2] 初始化代理通RPA...")
        try:
            from test_shangjia import ShangjiaTest
            self.rpa = ShangjiaTest()
        except ImportError as e:
            logger.error(f"无法导入RPA模块: {e}")
            return False
        
        # 步骤3: 启动浏览器
        logger.info("\n[步骤3] 启动浏览器...")
        try:
            self.rpa.setup_browser()
            
            if not self.rpa.load_cookies_and_navigate():
                logger.error("❌ 初始化失败")
                return False
            
            # 点击房型菜单
            if not self.rpa.step1_click_room_type_menu():
                logger.error("❌ 点击房型菜单失败")
                return False
            
            # 选择酒店
            if not self.rpa.step2_select_hotel_by_name(self.hotel_name):
                logger.error("❌ 选择酒店失败")
                return False
            
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            return False
        
        # 步骤4: 逐个设置房型价格
        logger.info("\n[步骤4] 设置房型价格...")
        success_count = 0
        fail_count = 0
        
        for i, rec in enumerate(recommendations, 1):
            # 优先使用命令行参数的房间数量，否则使用比价数据中的
            actual_count = self.room_count if self.room_count else rec.room_count
            count_str = f", 房间数: {actual_count}" if actual_count else ""
            
            logger.info(f"\n  [{i}/{len(recommendations)}] 设置: {rec.shangjia_room_type}")
            logger.info(f"       价格: {rec.price}元{count_str}, 利润: {rec.profit_percent:.1f}%")
            
            try:
                # 选择房型和日期
                if self.rpa.step3_select_room_type_and_date(
                    rec.shangjia_room_type, 
                    self.target_date, 
                    has_room=True
                ):
                    # 设置价格（和房间数量）
                    if self.rpa.step4_set_limited_sale(
                        room_count=actual_count, 
                        price=rec.price
                    ):
                        logger.info(f"  ✓ {rec.shangjia_room_type} 设置成功")
                        success_count += 1
                    else:
                        logger.warning(f"  ⚠️ {rec.shangjia_room_type} 设置失败（弹窗操作）")
                        fail_count += 1
                else:
                    logger.warning(f"  ⚠️ {rec.shangjia_room_type} 未找到或点击失败")
                    fail_count += 1
                    
            except Exception as e:
                logger.error(f"  ❌ {rec.shangjia_room_type} 出错: {e}")
                fail_count += 1
        
        # 步骤5: 完成
        logger.info("\n" + "=" * 60)
        logger.info("🎯 自动上架完成!")
        logger.info("=" * 60)
        logger.info(f"  成功: {success_count} 个")
        logger.info(f"  失败: {fail_count} 个")
        logger.info("=" * 60)
        
        # 保持浏览器打开
        logger.info("\n浏览器将保持打开状态，按回车键关闭...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        
        # 关闭浏览器
        if self.rpa:
            if self.rpa.browser:
                self.rpa.browser.close()
            elif self.rpa.context:
                self.rpa.context.close()
            if hasattr(self.rpa, 'playwright'):
                self.rpa.playwright.stop()
        
        return success_count > 0


def main():
    """主函数"""
    # 自动获取当天日期作为默认值
    today = datetime.now()
    today_str = today.strftime("%m.%d")  # 格式: "12.29"
    
    parser = argparse.ArgumentParser(
        description='自动比价上架程序',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'''
使用示例:
  # 自动比价并上架（使用当天日期 {today_str}）
  python auto_shangjia.py --hotel "美利居"
  
  # 自动比价并上架（指定日期）
  python auto_shangjia.py --hotel "美利居" --date "12.30"
  
  # 自动比价并上架（设置价格和房间数量）
  python auto_shangjia.py --hotel "美利居" --date "12.29" --count 3
  
  # 演示模式（只显示推荐，不实际执行）
  python auto_shangjia.py --hotel "美利居" --dry-run
        '''
    )
    
    parser.add_argument('--hotel', '-H', default='美利居', help='代理通中的酒店名称 (默认: 美利居)')
    parser.add_argument('--date', '-d', default=today_str, help=f'目标日期 (默认: 当天日期 {today_str})')
    parser.add_argument('--count', '-c', type=int, default=None, help='房间数量（可选，默认使用比价数据中的剩余房间数）')
    parser.add_argument('--dry-run', action='store_true', help='演示模式：只显示推荐，不实际执行')
    
    args = parser.parse_args()
    
    try:
        auto = AutoShangjia(
            hotel_name=args.hotel,
            target_date=args.date,
            room_count=args.count,
            dry_run=args.dry_run
        )
        success = auto.run()
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("\n用户中断执行")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()


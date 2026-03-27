# -*- coding: utf-8 -*-
"""
酒店价格比较程序
支持多平台酒店价格比较和阈值预警
"""

import json
import os
import re
import sys
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7 不支持reconfigure
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')


class RoomType(Enum):
    """房间类型枚举 - 按床型分类"""
    SINGLE = "单人房"    # 单人房/单人间
    DOUBLE_BED = "大床房"  # 大床房（一张大床）
    TWIN_BED = "双床房"   # 双床房（两张单人床）
    TRIPLE = "三人间"    # 三人间
    OTHER = "其他"       # 其他类型


class WindowType(Enum):
    """窗户类型枚举"""
    HAS_WINDOW = "有窗"   # 有窗
    NO_WINDOW = "无窗"    # 无窗
    UNKNOWN = "未知"      # 未知


class BreakfastType(Enum):
    """早餐类型枚举"""
    NO_BREAKFAST = "无早餐"     # 无早餐/不含早
    BREAKFAST_1 = "含1份早餐"   # 1份早餐
    BREAKFAST_2 = "含2份早餐"   # 2份早餐
    BREAKFAST_3 = "含3份早餐"   # 3份或更多早餐
    UNKNOWN = "未知"            # 未知


@dataclass
class RoomInfo:
    """房间信息数据类"""
    platform: str              # 平台名称
    room_name: str             # 房型名称
    price: float               # 价格（数值）
    price_str: str             # 价格（字符串）
    remaining: str             # 剩余房间
    remark: str                # 备注
    room_type: RoomType        # 房间类型（单人房/大床房/双床房/三人间）
    window_type: WindowType    # 窗户类型（有窗/无窗）
    breakfast_type: BreakfastType  # 早餐类型
    normalized_name: str       # 标准化后的房型名称（类型+窗户+早餐）


@dataclass
class PriceComparison:
    """价格比较结果"""
    platform_a: str            # 平台A名称
    platform_b: str            # 平台B名称
    room_type: RoomType        # 房间类型
    window_type: WindowType    # 窗户类型
    breakfast_type: BreakfastType  # 早餐类型
    price_a: float             # 平台A价格
    price_b: float             # 平台B价格
    price_diff: float          # 价格差
    price_diff_percent: float  # 价格差百分比
    cheaper_platform: str      # 更便宜的平台
    room_name_a: str           # 平台A房型名称
    room_name_b: str           # 平台B房型名称
    warning: bool = False      # 是否触发预警
    warning_reason: str = ""   # 预警原因
    has_profit: bool = False   # 是否有利润（价差>10%才有利润）
    profit_platform: str = ""  # 有利润的平台（如果价差>10%，则更便宜的平台有利润）


class RoomTypeMapper:
    """房间类型映射器 - 支持三维匹配（房间类型+窗户+早餐）"""
    
    # 房间类型映射规则 - 按床型分类
    TYPE_MAPPING = {
        # 单人房相关
        "单人": RoomType.SINGLE,
        "单人间": RoomType.SINGLE,
        "单人房": RoomType.SINGLE,
        "单床": RoomType.SINGLE,
        
        # 大床房相关（一张大床）
        "大床": RoomType.DOUBLE_BED,
        "大床房": RoomType.DOUBLE_BED,
        
        # 双床房相关（两张单人床）
        "双床": RoomType.TWIN_BED,
        "双床房": RoomType.TWIN_BED,
        
        # 三人间相关
        "三人": RoomType.TRIPLE,
        "三人间": RoomType.TRIPLE,
        "三人房": RoomType.TRIPLE,
    }
    
    # 窗户类型映射规则
    WINDOW_MAPPING = {
        "有窗": WindowType.HAS_WINDOW,
        "无窗": WindowType.NO_WINDOW,
        "内窗": WindowType.NO_WINDOW,  # 内窗视为无窗
    }
    
    # 早餐类型映射规则
    BREAKFAST_MAPPING = {
        "无早餐": BreakfastType.NO_BREAKFAST,
        "不含早": BreakfastType.NO_BREAKFAST,
        "无早": BreakfastType.NO_BREAKFAST,
        "1份早餐": BreakfastType.BREAKFAST_1,
        "含1份早餐": BreakfastType.BREAKFAST_1,
        "单早": BreakfastType.BREAKFAST_1,
        "2份早餐": BreakfastType.BREAKFAST_2,
        "含2份早餐": BreakfastType.BREAKFAST_2,
        "双早": BreakfastType.BREAKFAST_2,
        "3份早餐": BreakfastType.BREAKFAST_3,
        "含3份早餐": BreakfastType.BREAKFAST_3,
    }
    
    @classmethod
    def extract_room_type(cls, room_name: str) -> RoomType:
        """从房型名称中提取房间类型（按床型分类）"""
        # 优先检查更具体的关键词
        # 注意：需要先检查"双床"再检查"大床"，避免误判
        if "双床" in room_name:
            return RoomType.TWIN_BED
        if "大床" in room_name:
            return RoomType.DOUBLE_BED
        if "三人" in room_name:
            return RoomType.TRIPLE
        if "单人" in room_name or "单床" in room_name:
            return RoomType.SINGLE
        return RoomType.OTHER
    
    @classmethod
    def extract_window_type(cls, room_name: str, window_info: str, remark: str) -> WindowType:
        """
        从房间信息中提取窗户类型
        
        参数:
            room_name: 房型名称
            window_info: 窗户信息字段（携程专用）
            remark: 备注字段
        """
        # 优先使用窗户信息字段（携程）
        if window_info:
            for keyword, window_type in cls.WINDOW_MAPPING.items():
                if keyword in window_info:
                    return window_type
        
        # 从备注中提取（美团）
        if remark:
            for keyword, window_type in cls.WINDOW_MAPPING.items():
                if keyword in remark:
                    return window_type
        
        # 从房型名称中提取
        for keyword, window_type in cls.WINDOW_MAPPING.items():
            if keyword in room_name:
                return window_type
        
        # 特殊处理：房型名称中包含"阳光"通常表示有窗
        if "阳光" in room_name:
            return WindowType.HAS_WINDOW
        
        # 特殊处理：房型名称中包含"静谧"通常表示无窗
        if "静谧" in room_name:
            return WindowType.NO_WINDOW
        
        return WindowType.UNKNOWN
    
    @classmethod
    def extract_breakfast_type(cls, remark: str) -> BreakfastType:
        """
        从备注中提取早餐类型
        
        参数:
            remark: 备注字段
        """
        if not remark:
            return BreakfastType.UNKNOWN
        
        # 检查是否含早餐（按数量从多到少检查）
        if "3份早餐" in remark:
            return BreakfastType.BREAKFAST_3
        if "2份早餐" in remark:
            return BreakfastType.BREAKFAST_2
        if "1份早餐" in remark:
            return BreakfastType.BREAKFAST_1
        if "双早" in remark:
            return BreakfastType.BREAKFAST_2
        if "单早" in remark:
            return BreakfastType.BREAKFAST_1
        
        # 检查无早餐
        if "无早餐" in remark or "不含早" in remark or "无早" in remark:
            return BreakfastType.NO_BREAKFAST
        
        return BreakfastType.UNKNOWN
    
    @classmethod
    def normalize_room_name(cls, room_type: RoomType, window_type: WindowType, breakfast_type: BreakfastType) -> str:
        """
        标准化房型名称
        
        格式：房间类型 + 窗户情况 + 早餐情况
        例如：大床房-有窗-无早餐
        """
        type_name = room_type.value if room_type != RoomType.OTHER else "其他"
        window_name = window_type.value if window_type != WindowType.UNKNOWN else "未知窗"
        breakfast_name = breakfast_type.value if breakfast_type != BreakfastType.UNKNOWN else "未知早餐"
        return f"{type_name}-{window_name}-{breakfast_name}"


class PriceParser:
    """价格解析器"""
    
    @staticmethod
    def parse_price(price_str: str) -> float:
        """解析价格字符串，返回数值"""
        # 移除所有非数字字符（除了小数点）
        price_clean = re.sub(r'[^\d.]', '', price_str)
        try:
            return float(price_clean)
        except ValueError:
            return 0.0


class DataLoader:
    """数据加载器"""
    
    @staticmethod
    def load_json(file_path: str) -> Dict:
        """加载JSON文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"文件不存在: {file_path}")
        except json.JSONDecodeError:
            raise ValueError(f"JSON格式错误: {file_path}")
    
    @staticmethod
    def parse_room_data(data: Dict, platform_name: str) -> List[RoomInfo]:
        """解析房间数据"""
        rooms = []
        room_list = data.get("房型列表", [])
        
        for room in room_list:
            room_name = room.get("房型名称", "")
            price_str = room.get("价格", "¥0")
            remaining = room.get("剩余房间", "")
            remark = room.get("备注", "")
            window_info = room.get("窗户信息", "")  # 携程专用字段
            
            # 如果房间满房，跳过（不参与价格比较）
            if remaining and ("满房" in remaining or "全部订完" in remaining):
                continue
            
            # 解析价格
            price = PriceParser.parse_price(price_str)
            
            # 如果价格为0或无效，也跳过
            if price <= 0:
                continue
            
            # 提取房间类型（按床型分类）
            room_type = RoomTypeMapper.extract_room_type(room_name)
            
            # 提取窗户类型
            window_type = RoomTypeMapper.extract_window_type(room_name, window_info, remark)
            
            # 提取早餐类型
            breakfast_type = RoomTypeMapper.extract_breakfast_type(remark)
            
            # 标准化房型名称（类型+窗户+早餐）
            normalized_name = RoomTypeMapper.normalize_room_name(room_type, window_type, breakfast_type)
            
            room_info = RoomInfo(
                platform=platform_name,
                room_name=room_name,
                price=price,
                price_str=price_str,
                remaining=remaining,
                remark=remark,
                room_type=room_type,
                window_type=window_type,
                breakfast_type=breakfast_type,
                normalized_name=normalized_name
            )
            rooms.append(room_info)
        
        return rooms


class PriceComparator:
    """价格比较器"""
    
    def __init__(self, threshold: float = 0.0, threshold_percent: float = 0.0, profit_threshold_percent: float = 20.0):
        """
        初始化价格比较器
        
        参数:
            threshold: 绝对价格差阈值（元），超过此值触发预警
            threshold_percent: 相对价格差阈值（百分比），超过此值触发预警
            profit_threshold_percent: 利润阈值（百分比），价差必须超过此值才有利润，默认20%
        """
        self.threshold = threshold
        self.threshold_percent = threshold_percent
        self.profit_threshold_percent = profit_threshold_percent
    
    def compare_rooms(self, room_a: RoomInfo, room_b: RoomInfo) -> Optional[PriceComparison]:
        """
        比较两个房间的价格
        
        三维匹配规则：
        1. 房间类型必须相同（单人房/大床房/双床房/三人间）
        2. 窗户情况必须相同（有窗/无窗）
        3. 早餐服务必须相同（无早餐/含1份/含2份/含3份）
        
        参数:
            room_a: 平台A的房间信息
            room_b: 平台B的房间信息
        
        返回:
            价格比较结果，如果不满足三维匹配则返回None
        """
        # 1. 检查房间类型是否匹配（单人房和单人房比，大床房和大床房比，双床房和双床房比）
        if room_a.room_type != room_b.room_type:
            return None
        
        # 跳过其他类型（无法准确分类的房间不参与比较）
        if room_a.room_type == RoomType.OTHER:
            return None
        
        # 2. 检查窗户情况是否匹配
        if not self._is_window_match(room_a.window_type, room_b.window_type):
            return None
        
        # 3. 检查早餐服务是否匹配
        if not self._is_breakfast_match(room_a.breakfast_type, room_b.breakfast_type):
            return None
        
        # 计算价格差
        price_diff = abs(room_a.price - room_b.price)
        price_diff_percent = 0.0
        if min(room_a.price, room_b.price) > 0:
            price_diff_percent = (price_diff / min(room_a.price, room_b.price)) * 100
        
        # 确定更便宜的平台
        if room_a.price < room_b.price:
            cheaper_platform = room_a.platform
        elif room_b.price < room_a.price:
            cheaper_platform = room_b.platform
        else:
            cheaper_platform = "相同"
        
        # 检查是否有利润（价差必须超过利润阈值才有利润）
        has_profit = price_diff_percent > self.profit_threshold_percent
        profit_platform = cheaper_platform if has_profit else ""
        
        # 检查是否触发预警
        warning = False
        warning_reason = ""
        if price_diff >= self.threshold or price_diff_percent >= self.threshold_percent:
            warning = True
            reasons = []
            if price_diff >= self.threshold:
                reasons.append(f"价格差超过阈值 {self.threshold}元")
            if price_diff_percent >= self.threshold_percent:
                reasons.append(f"价格差超过阈值 {self.threshold_percent}%")
            warning_reason = "；".join(reasons)
        
        return PriceComparison(
            platform_a=room_a.platform,
            platform_b=room_b.platform,
            room_type=room_a.room_type,
            window_type=room_a.window_type,
            breakfast_type=room_a.breakfast_type,
            price_a=room_a.price,
            price_b=room_b.price,
            price_diff=price_diff,
            price_diff_percent=price_diff_percent,
            cheaper_platform=cheaper_platform,
            room_name_a=room_a.room_name,
            room_name_b=room_b.room_name,
            warning=warning,
            warning_reason=warning_reason,
            has_profit=has_profit,
            profit_platform=profit_platform
        )
    
    def _is_window_match(self, window_a: WindowType, window_b: WindowType) -> bool:
        """
        检查两个房间的窗户情况是否匹配
        
        匹配规则：
        - 有窗和有窗匹配
        - 无窗和无窗匹配
        - 如果任一方为未知，也允许匹配（容错处理）
        """
        # 如果窗户类型相同，直接匹配
        if window_a == window_b:
            return True
        
        # 如果任一方为未知，允许匹配（容错）
        if window_a == WindowType.UNKNOWN or window_b == WindowType.UNKNOWN:
            return True
        
        return False
    
    def _is_breakfast_match(self, breakfast_a: BreakfastType, breakfast_b: BreakfastType) -> bool:
        """
        检查两个房间的早餐服务是否匹配
        
        匹配规则：
        - 无早餐和无早餐匹配
        - 含1份早餐和含1份早餐匹配
        - 含2份早餐和含2份早餐匹配
        - 如果任一方为未知，也允许匹配（容错处理）
        """
        # 如果早餐类型相同，直接匹配
        if breakfast_a == breakfast_b:
            return True
        
        # 如果任一方为未知，允许匹配（容错）
        if breakfast_a == BreakfastType.UNKNOWN or breakfast_b == BreakfastType.UNKNOWN:
            return True
        
        return False
    
    def compare_all_rooms(self, rooms_a: List[RoomInfo], rooms_b: List[RoomInfo]) -> List[PriceComparison]:
        """
        比较两个平台的所有房间
        
        参数:
            rooms_a: 平台A的房间列表
            rooms_b: 平台B的房间列表
        
        返回:
            价格比较结果列表
        """
        comparisons = []
        
        for room_a in rooms_a:
            for room_b in rooms_b:
                comparison = self.compare_rooms(room_a, room_b)
                if comparison:
                    comparisons.append(comparison)
        
        return comparisons


class ReportExporter:
    """报告导出器 - 将比较结果导出到文档"""
    
    @staticmethod
    def export_to_markdown(comparisons: List[PriceComparison], 
                          xiecheng_data: Dict, 
                          meituan_data: Dict,
                          threshold: float,
                          threshold_percent: float,
                          profit_threshold_percent: float = 20.0,
                          output_file: str = "price_comparison_report.md"):
        """
        导出比较结果到Markdown文档
        
        参数:
            comparisons: 价格比较结果列表
            xiecheng_data: 携程数据
            meituan_data: 美团数据
            threshold: 绝对价格差阈值
            threshold_percent: 相对价格差阈值
            output_file: 输出文件路径
        """
        from datetime import datetime
        
        content = []
        
        # 文档标题和元信息
        content.append("# 酒店价格比较报告\n")
        content.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        content.append(f"**酒店名称**: {xiecheng_data.get('酒店名称', '未知酒店')}\n")
        content.append(f"**携程搜索时间**: {xiecheng_data.get('搜索时间', '未知')}\n")
        content.append(f"**美团搜索时间**: {meituan_data.get('搜索时间', '未知')}\n")
        content.append("\n---\n")
        
        # 优先展示：推荐选择（每个房间类型的最优选择，仅显示有利润的）
        content.append("## 💰 推荐选择（有利润的选择）\n")
        content.append(f"> ⚠️ **重要提示**：价差必须超过{profit_threshold_percent}%才有利润空间。即使一个平台价格更低，如果价差≤{profit_threshold_percent}%，仍然没有利润。\n\n")
        
        if comparisons:
            # 按房间类型+窗户+早餐分组，找出每个组合的最优选择（优先选择有利润的）
            best_choices = {}
            for comp in comparisons:
                key = (comp.room_type.value, comp.window_type.value, comp.breakfast_type.value)
                if key not in best_choices:
                    best_choices[key] = comp
                else:
                    current_best = best_choices[key]
                    # 优先选择有利润的
                    if comp.has_profit and not current_best.has_profit:
                        best_choices[key] = comp
                    elif not comp.has_profit and current_best.has_profit:
                        pass  # 保持当前有利润的选择
                    else:
                        # 都有利润或都没利润，选择价格更低的
                        if min(comp.price_a, comp.price_b) < min(current_best.price_a, current_best.price_b):
                            best_choices[key] = comp
            
            # 按房间类型排序展示
            profitable_count = 0
            for (type_name, window_name, breakfast_name), comp in sorted(best_choices.items()):
                # 只显示有利润的选择
                if not comp.has_profit:
                    continue
                
                profitable_count += 1
                content.append(f"### {type_name} | {window_name} | {breakfast_name}\n\n")
                
                # 确定推荐平台和价格（有利润的平台）
                if comp.profit_platform == comp.platform_a:
                    recommend_platform = comp.platform_a
                    recommend_price = comp.price_a
                    recommend_room = comp.room_name_a
                    other_platform = comp.platform_b
                    other_price = comp.price_b
                    other_room = comp.room_name_b
                    save_amount = comp.price_b - comp.price_a
                elif comp.profit_platform == comp.platform_b:
                    recommend_platform = comp.platform_b
                    recommend_price = comp.price_b
                    recommend_room = comp.room_name_b
                    other_platform = comp.platform_a
                    other_price = comp.price_a
                    other_room = comp.room_name_a
                    save_amount = comp.price_a - comp.price_b
                else:
                    continue  # 不应该发生
                
                content.append(f"**✅ 推荐选择**: {recommend_platform} - **{recommend_price:.0f}元**\n\n")
                content.append(f"- 房型: {recommend_room}\n")
                content.append(f"- 比{other_platform}便宜: **{save_amount:.0f}元** ({comp.price_diff_percent:.1f}%)\n")
                content.append(f"- {other_platform}价格: {other_price:.0f}元 ({other_room})\n")
                content.append(f"- 💰 **利润空间**: {comp.price_diff_percent:.1f}%（价差>{profit_threshold_percent}%，有利润）\n")
                content.append("\n")
            
            if profitable_count == 0:
                content.append(f"**⚠️ 未找到有利润的选择**（所有比较的价差都≤{profit_threshold_percent}%，无利润空间）\n\n")
        
        content.append("---\n")
        
        # 详细价格对比表（按平台分组展示）
        content.append("## 📊 详细价格对比\n")
        content.append("> 所有可比较的房间价格对比（按房间类型+窗户+早餐分组，先列出各平台房型，最后给出推荐）\n\n")
        
        if comparisons:
            # 按房间类型+窗户+早餐分组
            grouped = {}
            for comp in comparisons:
                key = (comp.room_type.value, comp.window_type.value, comp.breakfast_type.value)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(comp)
            
            for (type_name, window_name, breakfast_name), comps in sorted(grouped.items()):
                content.append(f"### {type_name} | {window_name} | {breakfast_name}\n\n")
                
                # 收集各平台的所有房型（不去重，用列表存储）
                platform_a_rooms = []  # [(房型名称, 价格), ...]
                platform_b_rooms = []
                platform_a_name = comps[0].platform_a
                platform_b_name = comps[0].platform_b
                
                # 用集合去重（房型名称+价格的组合）
                seen_a = set()
                seen_b = set()
                
                for comp in comps:
                    # 平台A的房型
                    key_a = (comp.room_name_a, comp.price_a)
                    if key_a not in seen_a:
                        seen_a.add(key_a)
                        platform_a_rooms.append((comp.room_name_a, comp.price_a))
                    # 平台B的房型
                    key_b = (comp.room_name_b, comp.price_b)
                    if key_b not in seen_b:
                        seen_b.add(key_b)
                        platform_b_rooms.append((comp.room_name_b, comp.price_b))
                
                # 按价格排序
                platform_a_rooms.sort(key=lambda x: x[1])
                platform_b_rooms.sort(key=lambda x: x[1])
                
                # 展示平台A的所有房型
                content.append(f"**📱 {platform_a_name}房型**\n")
                content.append("| 房型 | 价格 |\n")
                content.append("|------|------|\n")
                for room_name, price in platform_a_rooms:
                    content.append(f"| {room_name} | {price:.0f}元 |\n")
                content.append("\n")
                
                # 展示平台B的所有房型
                content.append(f"**📱 {platform_b_name}房型**\n")
                content.append("| 房型 | 价格 |\n")
                content.append("|------|------|\n")
                for room_name, price in platform_b_rooms:
                    content.append(f"| {room_name} | {price:.0f}元 |\n")
                content.append("\n")
                
                # 找出最优选择（价格最低且有利润的）
                best_comp = None
                for comp in comps:
                    if best_comp is None:
                        best_comp = comp
                    else:
                        # 优先选择有利润的
                        if comp.has_profit and not best_comp.has_profit:
                            best_comp = comp
                        elif not comp.has_profit and best_comp.has_profit:
                            pass
                        else:
                            # 都有利润或都没利润，选择价格更低的
                            if min(comp.price_a, comp.price_b) < min(best_comp.price_a, best_comp.price_b):
                                best_comp = comp
                
                # 展示推荐选择
                content.append("**🎯 推荐选择**\n")
                content.append("| 推荐平台 | 推荐房型 | 推荐价格 | 对比最低价 | 节省金额 | 节省比例 | 是否有利润 |\n")
                content.append("|---------|---------|---------|-----------|---------|---------|----------|\n")
                
                if best_comp:
                    profit_mark = "✅ 有利润" if best_comp.has_profit else f"❌ 无利润（价差≤{profit_threshold_percent}%）"
                    
                    if best_comp.price_a < best_comp.price_b:
                        # 平台A更便宜，对比平台B的最低价
                        other_min_price = min(p for _, p in platform_b_rooms)
                        save_amount = other_min_price - best_comp.price_a
                        save_percent = (save_amount / best_comp.price_a) * 100 if best_comp.price_a > 0 else 0
                        content.append(f"| ✅ **{best_comp.platform_a}** | {best_comp.room_name_a} | **{best_comp.price_a:.0f}元** | {best_comp.platform_b} {other_min_price:.0f}元 | {save_amount:.0f}元 | {save_percent:.1f}% | {profit_mark} |\n")
                    elif best_comp.price_b < best_comp.price_a:
                        # 平台B更便宜，对比平台A的最低价
                        other_min_price = min(p for _, p in platform_a_rooms)
                        save_amount = other_min_price - best_comp.price_b
                        save_percent = (save_amount / best_comp.price_b) * 100 if best_comp.price_b > 0 else 0
                        content.append(f"| ✅ **{best_comp.platform_b}** | {best_comp.room_name_b} | **{best_comp.price_b:.0f}元** | {best_comp.platform_a} {other_min_price:.0f}元 | {save_amount:.0f}元 | {save_percent:.1f}% | {profit_mark} |\n")
                    else:
                        content.append(f"| 价格相同 | {best_comp.room_name_a} | {best_comp.price_a:.0f}元 | - | 0元 | 0% | ❌ 无利润 |\n")
                
                content.append("\n")
        
        content.append("---\n")
        
        # 比价逻辑说明（放到后面）
        content.append("## 📖 比价逻辑说明\n")
        content.append("### 1. 三维匹配规则\n")
        content.append("房间必须同时满足以下三个条件才能进行价格比较：\n\n")
        content.append("#### 1.1 房间类型（按床型分类）\n")
        content.append("- **单人房**：单人间、单人房、单床房\n")
        content.append("- **大床房**：大床房（一张大床）\n")
        content.append("- **双床房**：双床房（两张单人床）\n")
        content.append("- **三人间**：三人间、三人房\n")
        content.append("- ⚠️ **注意**：大床房和双床房是不同类型，不会互相比较\n")
        content.append("\n#### 1.2 窗户情况\n")
        content.append("- **有窗**：房间有窗户\n")
        content.append("- **无窗**：房间无窗户或内窗\n")
        content.append("- ⚠️ **匹配原则**：有窗和有窗比，无窗和无窗比\n")
        content.append("\n#### 1.3 早餐服务\n")
        content.append("- **无早餐**：不含早餐\n")
        content.append("- **含1份早餐**：单早\n")
        content.append("- **含2份早餐**：双早\n")
        content.append("- **含3份早餐**：三人早餐\n")
        content.append("- ⚠️ **匹配原则**：相同早餐数量才能比较\n")
        content.append("\n### 2. 价格比较方法\n")
        content.append("- **价格差计算**：|平台A价格 - 平台B价格|\n")
        content.append("- **价格差百分比**：(价格差 / 较低价格) × 100%\n")
        content.append("- **更便宜平台**：价格较低的平台\n")
        content.append("\n### 3. 利润判断规则（重要）\n")
        content.append(f"⚠️ **价格变动不是等价关系**：即使一个平台价格更低，如果价差≤{profit_threshold_percent}%，仍然没有利润。\n")
        content.append(f"- **利润阈值**：价差必须**大于{profit_threshold_percent}%**才有利润空间\n")
        content.append(f"- **有利润条件**：价差百分比 > {profit_threshold_percent}%\n")
        content.append(f"- **无利润情况**：价差百分比 ≤ {profit_threshold_percent}%（即使价格更低，也无利润）\n")
        content.append(f"- **示例**：携程500元，美团550元，价差50元（{profit_threshold_percent}%），仍然没有利润\n")
        content.append("\n### 4. 预警机制\n")
        content.append(f"- **绝对价格差阈值**：{threshold}元（价格差超过此值触发预警）\n")
        content.append(f"- **相对价格差阈值**：{threshold_percent}%（价格差百分比超过此值触发预警）\n")
        content.append("- **预警条件**：满足任一阈值条件即触发预警\n")
        content.append("\n### 5. 比较流程\n")
        content.append("```\n")
        content.append("1. 加载两个平台的酒店数据\n")
        content.append("2. 解析每个房型：提取房间类型、窗户情况、早餐服务\n")
        content.append("3. 标准化房型名称：类型-窗户-早餐\n")
        content.append("4. 三维匹配：只有类型+窗户+早餐都相同的房间才比较\n")
        content.append("5. 计算价格差和价格差百分比\n")
        content.append("6. 判断是否触发预警\n")
        content.append("7. 生成比较报告\n")
        content.append("```\n")
        content.append("\n---\n")
        
        # 统计摘要（简化）
        content.append("## 📈 统计摘要\n")
        if not comparisons:
            content.append("**未找到可比较的房间**\n")
        else:
            total_comparisons = len(comparisons)
            warnings = sum(1 for c in comparisons if c.warning)
            profitable_count = sum(1 for c in comparisons if c.has_profit)
            
            content.append(f"- **总比较数**: {total_comparisons}\n")
            content.append(f"- **有利润数量**: {profitable_count}（价差>{profit_threshold_percent}%）\n")
            content.append(f"- **有利润比例**: {profitable_count/total_comparisons*100:.2f}%\n")
            content.append(f"- **预警数量**: {warnings}\n")
            content.append(f"- **预警比例**: {warnings/total_comparisons*100:.2f}%\n")
            
            # 按房间类型统计
            by_type = {}
            for comp in comparisons:
                type_name = comp.room_type.value
                if type_name not in by_type:
                    by_type[type_name] = []
                by_type[type_name].append(comp)
            
            content.append("\n### 按房间类型统计\n")
            content.append("| 房间类型 | 窗户 | 早餐 | 总比较数 | 有利润数 | 携程更便宜 | 美团更便宜 | 价格相同 |\n")
            content.append("|---------|------|------|---------|---------|-----------|-----------|--------|\n")
            
            # 按三维分组统计
            by_key = {}
            for comp in comparisons:
                key = (comp.room_type.value, comp.window_type.value, comp.breakfast_type.value)
                if key not in by_key:
                    by_key[key] = []
                by_key[key].append(comp)
            
            for (type_name, window_name, breakfast_name), comps in sorted(by_key.items()):
                cheaper_a = sum(1 for c in comps if c.cheaper_platform == comps[0].platform_a)
                cheaper_b = sum(1 for c in comps if c.cheaper_platform == comps[0].platform_b)
                same = sum(1 for c in comps if c.cheaper_platform == "相同")
                profitable = sum(1 for c in comps if c.has_profit)
                content.append(f"| {type_name} | {window_name} | {breakfast_name} | {len(comps)} | {profitable} | {cheaper_a} | {cheaper_b} | {same} |\n")
        
        content.append("\n---\n")
        
        # 大额价格差异提醒（只显示差异超过20%的）
        warnings = [c for c in comparisons if c.warning and c.price_diff_percent > 20]
        if warnings:
            content.append("## ⚠️ 大额价格差异提醒\n")
            content.append(f"> 以下为价格差异超过20%的情况（共{len(warnings)}项），建议重点关注\n\n")
            
            # 按价格差百分比排序，最大的在前
            warnings_sorted = sorted(warnings, key=lambda x: x.price_diff_percent, reverse=True)
            
            content.append("| 房间类型 | 推荐平台 | 推荐价格 | 对比平台 | 对比价格 | 节省金额 | 节省比例 |\n")
            content.append("|---------|---------|---------|---------|---------|---------|---------|\n")
            
            for comp in warnings_sorted[:15]:  # 只显示前15个最大的差异
                room_desc = f"{comp.room_type.value}|{comp.window_type.value}|{comp.breakfast_type.value}"
                if comp.price_a < comp.price_b:
                    content.append(f"| {room_desc} | **{comp.platform_a}** | "
                                 f"**{comp.price_a:.0f}元** | {comp.platform_b} | {comp.price_b:.0f}元 | "
                                 f"**{comp.price_diff:.0f}元** | **{comp.price_diff_percent:.1f}%** |\n")
                else:
                    content.append(f"| {room_desc} | **{comp.platform_b}** | "
                                 f"**{comp.price_b:.0f}元** | {comp.platform_a} | {comp.price_a:.0f}元 | "
                                 f"**{comp.price_diff:.0f}元** | **{comp.price_diff_percent:.1f}%** |\n")
        
        # 写入文件
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, output_file)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(''.join(content))
        
        return output_path


class ComparisonReporter:
    """比较结果报告器"""
    
    @staticmethod
    def print_summary(comparisons: List[PriceComparison]):
        """打印比较结果摘要"""
        if not comparisons:
            print("\n[错误] 未找到可比较的房间")
            return
        
        print("\n" + "=" * 80)
        print("[统计] 价格比较结果摘要")
        print("=" * 80)
        
        # 统计信息
        total_comparisons = len(comparisons)
        warnings = sum(1 for c in comparisons if c.warning)
        
        print(f"\n总比较数: {total_comparisons}")
        print(f"预警数量: {warnings}")
        
        # 按房间类型分组统计
        by_type = {}
        for comp in comparisons:
            type_name = comp.room_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(comp)
        
        print("\n按房间类型统计:")
        # 按三维分组
        by_key = {}
        for comp in comparisons:
            key = (comp.room_type.value, comp.window_type.value, comp.breakfast_type.value)
            if key not in by_key:
                by_key[key] = []
            by_key[key].append(comp)
        
        for (type_name, window_name, breakfast_name), comps in sorted(by_key.items()):
            cheaper_a = sum(1 for c in comps if c.cheaper_platform == comps[0].platform_a)
            cheaper_b = sum(1 for c in comps if c.cheaper_platform == comps[0].platform_b)
            same = sum(1 for c in comps if c.cheaper_platform == "相同")
            print(f"  {type_name}|{window_name}|{breakfast_name}: 总计{len(comps)}个比较，"
                  f"{comps[0].platform_a}更便宜{cheaper_a}个，{comps[0].platform_b}更便宜{cheaper_b}个，相同{same}个")
    
    @staticmethod
    def print_detailed_results(comparisons: List[PriceComparison], show_all: bool = False):
        """打印详细比较结果"""
        if not comparisons:
            return
        
        print("\n" + "=" * 80)
        print("[详情] 详细比较结果")
        print("=" * 80)
        
        # 按房间类型+窗户+早餐分组
        grouped = {}
        for comp in comparisons:
            key = (comp.room_type.value, comp.window_type.value, comp.breakfast_type.value)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(comp)
        
        # 打印分组结果
        for (type_name, window_name, breakfast_name), comps in sorted(grouped.items()):
            print(f"\n【{type_name} | {window_name} | {breakfast_name}】")
            print("-" * 80)
            
            for comp in comps:
                # 只显示有差异的或触发预警的，除非show_all=True
                if not show_all and comp.price_diff == 0 and not comp.warning:
                    continue
                
                print(f"\n  平台A ({comp.platform_a}):")
                print(f"    房型: {comp.room_name_a}")
                print(f"    价格: {comp.price_a:.2f}元")
                
                print(f"\n  平台B ({comp.platform_b}):")
                print(f"    房型: {comp.room_name_b}")
                print(f"    价格: {comp.price_b:.2f}元")
                
                print(f"\n  比较结果:")
                print(f"    价格差: {comp.price_diff:.2f}元 ({comp.price_diff_percent:.2f}%)")
                print(f"    更便宜: {comp.cheaper_platform}")
                if comp.has_profit:
                    print(f"    [利润] ✅ 有利润（价差>{comp.price_diff_percent:.1f}%）")
                else:
                    print(f"    [利润] ❌ 无利润（价差≤{comp.price_diff_percent:.1f}%）")
                
                if comp.warning:
                    print(f"    [预警] {comp.warning_reason}")
                
                print()
    
    @staticmethod
    def print_warnings(comparisons: List[PriceComparison]):
        """打印预警信息"""
        warnings = [c for c in comparisons if c.warning]
        
        if not warnings:
            print("\n[提示] 未触发任何预警")
            return
        
        print("\n" + "=" * 80)
        print("[预警] 价格预警")
        print("=" * 80)
        
        for comp in warnings:
            print(f"\n【{comp.room_type.value} | {comp.window_type.value} | {comp.breakfast_type.value}】")
            print(f"  {comp.platform_a}: {comp.room_name_a} - {comp.price_a:.2f}元")
            print(f"  {comp.platform_b}: {comp.room_name_b} - {comp.price_b:.2f}元")
            print(f"  价格差: {comp.price_diff:.2f}元 ({comp.price_diff_percent:.2f}%)")
            print(f"  预警原因: {comp.warning_reason}")
            print()


def main():
    """主函数"""
    print("=" * 80)
    print("=" * 80)
    print("酒店价格比较工具")
    print("=" * 80)
    
    # 配置文件路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    xiecheng_file = os.path.join(script_dir, "xiecheng", "hotel_data.json")
    meituan_file = os.path.join(script_dir, "meituan", "meituan_hotel.json")
    
    # 检查文件是否存在
    if not os.path.exists(xiecheng_file):
        print(f"\n[错误] 携程数据文件不存在: {xiecheng_file}")
        return
    
    if not os.path.exists(meituan_file):
        print(f"\n[错误] 美团数据文件不存在: {meituan_file}")
        return
    
    # 加载数据
    print("\n[加载] 正在加载数据...")
    try:
        xiecheng_data = DataLoader.load_json(xiecheng_file)
        meituan_data = DataLoader.load_json(meituan_file)
        print(f"[成功] 已加载携程数据: {xiecheng_data.get('酒店名称', '未知酒店')}")
        print(f"[成功] 已加载美团数据")
    except Exception as e:
        print(f"\n[错误] 加载数据失败: {str(e)}")
        return
    
    # 解析房间数据
    print("\n[解析] 正在解析房间数据...")
    xiecheng_rooms = DataLoader.parse_room_data(xiecheng_data, "携程")
    meituan_rooms = DataLoader.parse_room_data(meituan_data, "美团")
    print(f"[成功] 携程房间数: {len(xiecheng_rooms)}")
    print(f"[成功] 美团房间数: {len(meituan_rooms)}")
    
    # 获取阈值设置（可以从配置文件或命令行参数获取，这里使用默认值）
    print("\n[设置] 阈值设置:")
    threshold = 50.0  # 默认价格差阈值50元
    threshold_percent = 10.0  # 默认价格差百分比阈值10%
    profit_threshold_percent = 20.0  # 利润阈值20%（价差必须超过此值才有利润）
    print(f"  绝对价格差阈值: {threshold}元")
    print(f"  相对价格差阈值: {threshold_percent}%")
    print(f"  利润阈值: {profit_threshold_percent}%（价差必须超过此值才有利润）")
    
    # 创建价格比较器
    comparator = PriceComparator(threshold=threshold, threshold_percent=threshold_percent, profit_threshold_percent=profit_threshold_percent)
    
    # 执行比较
    print("\n[比较] 正在比较价格...")
    comparisons = comparator.compare_all_rooms(xiecheng_rooms, meituan_rooms)
    print(f"[成功] 完成比较，共找到 {len(comparisons)} 个可比较的房间")
    
    # 生成报告
    reporter = ComparisonReporter()
    reporter.print_summary(comparisons)
    reporter.print_detailed_results(comparisons, show_all=False)
    reporter.print_warnings(comparisons)
    
    # 导出到文档
    print("\n[导出] 正在生成文档...")
    try:
        output_file = ReportExporter.export_to_markdown(
            comparisons=comparisons,
            xiecheng_data=xiecheng_data,
            meituan_data=meituan_data,
            threshold=threshold,
            threshold_percent=threshold_percent,
            profit_threshold_percent=profit_threshold_percent,
            output_file="price_comparison_report.md"
        )
        print(f"[成功] 报告已保存到: {output_file}")
    except Exception as e:
        print(f"[错误] 导出文档失败: {str(e)}")
    
    print("\n" + "=" * 80)
    print("[完成] 比较完成")
    print("=" * 80)


if __name__ == "__main__":
    main()

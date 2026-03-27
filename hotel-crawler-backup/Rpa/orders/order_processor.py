# -*- coding: utf-8 -*-
"""
订单处理模块 (Order Processor)
用于获取美团代理上的客户下单信息，并在价格低的平台自动下单

业务流程：
1. 监控美团代理平台的新订单
2. 获取客户下单信息（入住人、联系方式、入住日期、房型等）
3. 调用 search.py 搜索酒店价格
4. 比价确定最便宜的平台（使用三维匹配：房间类型+窗户+早餐）
5. 在价格最低的平台（如携程）自动下单
6. 记录订单状态和利润

使用方式:
    # 🔥 从代理通获取订单并处理（推荐）
    python orders/order_processor.py --fetch
    
    # 演示模式（不实际下单）
    python orders/order_processor.py --fetch --dry-run
    
    # 启动订单监控
    python orders/order_processor.py --monitor
    
    # 查看所有订单
    python orders/order_processor.py --list
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# 获取脚本所在目录和项目根目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# 添加项目根目录到路径
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 数据文件路径
ORDERS_FILE = os.path.join(SCRIPT_DIR, "orders.json")
ORDERS_HISTORY_FILE = os.path.join(SCRIPT_DIR, "orders_history.json")

# shangjia 目录路径（用于代理通登录态）
SHANGJIA_DIR = os.path.join(PROJECT_ROOT, 'shangjia')
SHANGJIA_CONFIG_FILE = os.path.join(SHANGJIA_DIR, "config.yaml")
SHANGJIA_COOKIES_FILE = os.path.join(SHANGJIA_DIR, "shangjia_cookies.pkl")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(SCRIPT_DIR, 'order_processor.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==================== 数据结构定义 ====================

class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "待处理"           # 新订单，等待处理
    PROCESSING = "处理中"        # 正在处理
    BOOKED = "已预订"            # 已在低价平台下单
    CONFIRMED = "已确认"         # 低价平台确认成功
    FAILED = "下单失败"          # 下单失败
    CANCELLED = "已取消"         # 订单取消
    COMPLETED = "已完成"         # 订单完成


class Platform(Enum):
    """平台枚举"""
    MEITUAN = "美团"
    XIECHENG = "携程"
    FEIZHU = "飞猪"


@dataclass
class GuestInfo:
    """客人信息"""
    name: str                    # 入住人姓名
    phone: str                   # 联系电话
    id_card: str = ""            # 身份证号（可选）
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GuestInfo':
        return cls(**data)


@dataclass
class RoomInfo:
    """房间信息"""
    room_type: str               # 房型名称（如"商务大床房"）
    room_count: int              # 房间数量
    check_in_date: str           # 入住日期（格式: YYYY-MM-DD）
    check_out_date: str          # 退房日期（格式: YYYY-MM-DD）
    nights: int                  # 入住天数
    breakfast: str = ""          # 早餐信息
    window: str = ""             # 窗户信息
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'RoomInfo':
        return cls(**data)


@dataclass
class OrderInfo:
    """订单信息"""
    order_id: str                # 订单ID（美团订单号）
    hotel_name: str              # 酒店名称
    guest: GuestInfo             # 客人信息
    room: RoomInfo               # 房间信息
    source_platform: Platform    # 来源平台（美团代理）
    source_price: float          # 来源平台价格（客户支付价格）
    target_platform: Platform = None    # 目标平台（下单平台）
    target_price: float = 0.0    # 目标平台价格（成本价格）
    target_order_id: str = ""    # 目标平台订单号
    profit: float = 0.0          # 利润
    status: OrderStatus = OrderStatus.PENDING
    created_at: str = ""         # 创建时间
    updated_at: str = ""         # 更新时间
    remark: str = ""             # 备注
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def calculate_profit(self):
        """计算利润"""
        if self.source_price > 0 and self.target_price > 0:
            self.profit = self.source_price - self.target_price
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "order_id": self.order_id,
            "hotel_name": self.hotel_name,
            "guest": self.guest.to_dict(),
            "room": self.room.to_dict(),
            "source_platform": self.source_platform.value if self.source_platform else "",
            "source_price": self.source_price,
            "target_platform": self.target_platform.value if self.target_platform else "",
            "target_price": self.target_price,
            "target_order_id": self.target_order_id,
            "profit": self.profit,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "remark": self.remark
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'OrderInfo':
        """从字典创建"""
        guest = GuestInfo.from_dict(data.get("guest", {}))
        room = RoomInfo.from_dict(data.get("room", {}))
        
        # 解析枚举
        source_platform = None
        for p in Platform:
            if p.value == data.get("source_platform"):
                source_platform = p
                break
        
        target_platform = None
        for p in Platform:
            if p.value == data.get("target_platform"):
                target_platform = p
                break
        
        status = OrderStatus.PENDING
        for s in OrderStatus:
            if s.value == data.get("status"):
                status = s
                break
        
        return cls(
            order_id=data.get("order_id", ""),
            hotel_name=data.get("hotel_name", ""),
            guest=guest,
            room=room,
            source_platform=source_platform,
            source_price=data.get("source_price", 0.0),
            target_platform=target_platform,
            target_price=data.get("target_price", 0.0),
            target_order_id=data.get("target_order_id", ""),
            profit=data.get("profit", 0.0),
            status=status,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            remark=data.get("remark", "")
        )


# ==================== 订单存储管理 ====================

class OrderStorage:
    """订单存储管理"""
    
    def __init__(self, orders_file: str = ORDERS_FILE):
        self.orders_file = orders_file
        self.orders: Dict[str, OrderInfo] = {}
        self._load_orders()
    
    def _load_orders(self):
        """加载订单数据"""
        if os.path.exists(self.orders_file):
            try:
                with open(self.orders_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for order_data in data.get("orders", []):
                        order = OrderInfo.from_dict(order_data)
                        self.orders[order.order_id] = order
                logger.info(f"已加载 {len(self.orders)} 个订单")
            except Exception as e:
                logger.error(f"加载订单失败: {e}")
    
    def _save_orders(self):
        """保存订单数据"""
        try:
            data = {
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_orders": len(self.orders),
                "orders": [order.to_dict() for order in self.orders.values()]
            }
            with open(self.orders_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(self.orders)} 个订单")
        except Exception as e:
            logger.error(f"保存订单失败: {e}")
    
    def add_order(self, order: OrderInfo) -> bool:
        """添加订单"""
        if order.order_id in self.orders:
            logger.warning(f"订单已存在: {order.order_id}")
            return False
        
        self.orders[order.order_id] = order
        self._save_orders()
        logger.info(f"已添加订单: {order.order_id}")
        return True
    
    def update_order(self, order: OrderInfo) -> bool:
        """更新订单"""
        if order.order_id not in self.orders:
            logger.warning(f"订单不存在: {order.order_id}")
            return False
        
        order.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.orders[order.order_id] = order
        self._save_orders()
        logger.info(f"已更新订单: {order.order_id}")
        return True
    
    def get_order(self, order_id: str) -> Optional[OrderInfo]:
        """获取订单"""
        return self.orders.get(order_id)
    
    def get_pending_orders(self) -> List[OrderInfo]:
        """获取待处理订单"""
        return [order for order in self.orders.values() 
                if order.status == OrderStatus.PENDING]
    
    def get_all_orders(self) -> List[OrderInfo]:
        """获取所有订单"""
        return list(self.orders.values())


# ==================== 代理通订单获取 ====================

class DailitongOrderFetcher:
    """
    代理通平台订单获取器
    
    登录代理通平台 (https://www.vipdlt.com) 获取订单信息
    使用 shangjia 模块的登录态
    """
    
    # 代理通平台URL
    BASE_URL = "https://www.vipdlt.com"
    ORDER_LIST_URL = "https://www.vipdlt.com/order/orderList"
    
    # XPath选择器
    XPATH_ORDER_MANAGE = '//*[@id="orderManage"]'
    XPATH_ORDER_TABLE = '//*[@id="tabOrderList"]'
    XPATH_ORDER_DETAIL_BTN = '//a[contains(text(), "详情")]'
    
    # 订单详情页面 XPath
    XPATH_HOTEL_NAME = '//*[@id="h_hotelName"]'
    XPATH_CLIENT_NAME = '//*[@id="dfl-clientName"]'
    XPATH_CHECK_DATE = '//*[@id="dfl-checkDate"]'
    XPATH_ROOM_NAME = '//*[@id="dfl-roomName"]'
    
    def __init__(self):
        self.page = None
        self.browser = None
        self.context = None
        self.playwright = None
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """加载配置文件"""
        import yaml
        try:
            with open(SHANGJIA_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"✓ 配置文件加载成功")
            return config
        except Exception as e:
            logger.error(f"❌ 配置文件加载失败: {e}")
            return {}
    
    def setup_browser(self) -> bool:
        """启动浏览器"""
        try:
            from playwright.sync_api import sync_playwright
            
            logger.info("🚀 启动浏览器...")
            self.playwright = sync_playwright().start()
            
            browser_config = self.config.get('browser', {})
            headless = browser_config.get('headless', False)
            slow_mo = browser_config.get('slow_mo', 500)
            window_size = browser_config.get('window_size', {'width': 1920, 'height': 1080})
            
            # 使用 shangjia 目录下的 browser_data
            user_data_dir = os.path.join(SHANGJIA_DIR, "browser_data")
            logger.info(f"使用项目用户数据目录: {user_data_dir}")
            
            launch_options = {
                'user_data_dir': user_data_dir,
                'headless': headless,
                'slow_mo': slow_mo,
                'viewport': {'width': window_size['width'], 'height': window_size['height']},
            }
            
            self.context = self.playwright.chromium.launch_persistent_context(**launch_options)
            self.browser = None
            self.page = self.context.new_page()
            
            logger.info("✓ 浏览器启动成功")
            return True
            
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def load_cookies_and_navigate(self) -> bool:
        """加载Cookies并导航到首页"""
        import pickle
        
        logger.info("[初始化] 加载Cookies并导航...")
        
        login_config = self.config.get('login', {})
        url = login_config.get('url', self.BASE_URL)
        
        try:
            # 尝试加载cookies
            if login_config.get('use_cookies', True) and os.path.exists(SHANGJIA_COOKIES_FILE):
                logger.info("正在加载Cookies...")
                try:
                    with open(SHANGJIA_COOKIES_FILE, 'rb') as f:
                        cookies = pickle.load(f)
                    self.context.add_cookies(cookies)
                    logger.info(f"✓ 已加载 {len(cookies)} 个cookie")
                except Exception as e:
                    logger.warning(f"⚠️ 加载Cookies失败: {e}")
            
            # 访问首页
            logger.info(f"访问首页: {url}")
            self.page.goto(url, timeout=30000)
            self._random_sleep(2, 3)
            
            logger.info("✓ 已加载Cookies并导航到首页")
            return True
            
        except Exception as e:
            logger.error(f"❌ 加载Cookies失败: {e}")
            return False
    
    def close_browser(self):
        """关闭浏览器"""
        try:
            if self.browser:
                self.browser.close()
            elif self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("✓ 浏览器已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器失败: {e}")
    
    def _random_sleep(self, min_s: float = 0.5, max_s: float = 1.5):
        """随机等待"""
        import random
        time.sleep(random.uniform(min_s, max_s))
    
    def navigate_to_order_list(self) -> bool:
        """导航到订单列表页面"""
        try:
            logger.info(f"导航到订单列表: {self.ORDER_LIST_URL}")
            self.page.goto(self.ORDER_LIST_URL, timeout=30000)
            self._random_sleep(2, 3)
            logger.info("✓ 已导航到订单列表页面")
            return True
        except Exception as e:
            logger.error(f"导航失败: {e}")
            return False
    
    def click_order_detail(self, order_index: int = 0) -> bool:
        """点击订单详情按钮"""
        try:
            logger.info(f"点击订单详情按钮 (索引: {order_index})...")
            self._random_sleep(1, 2)
            
            detail_links = self.page.locator('a:text-is("详情")')
            link_count = detail_links.count()
            logger.info(f"  找到 {link_count} 个'详情'链接")
            
            if link_count == 0:
                detail_links = self.page.locator('text=详情')
                link_count = detail_links.count()
            
            if link_count == 0:
                logger.error("❌ 未找到详情链接")
                return False
            
            if order_index < link_count:
                detail_btn = detail_links.nth(order_index)
                detail_btn.scroll_into_view_if_needed()
                self._random_sleep(0.3, 0.5)
                
                with self.context.expect_page() as new_page_info:
                    detail_btn.click()
                
                new_page = new_page_info.value
                new_page.wait_for_load_state('networkidle', timeout=15000)
                self.page = new_page
                logger.info(f"✓ 已切换到新页面: {self.page.url}")
                return True
            else:
                logger.error(f"❌ 订单索引 {order_index} 超出范围")
                return False
                
        except Exception as e:
            logger.error(f"点击订单详情按钮失败: {e}")
            return False
    
    def parse_order_detail(self) -> Optional[OrderInfo]:
        """解析订单详情页面"""
        try:
            logger.info("解析订单详情页面...")
            self.page.wait_for_load_state('networkidle', timeout=15000)
            self._random_sleep(1, 2)
            
            order_data = {}
            
            # 获取酒店名称
            try:
                hotel_element = self.page.locator(self.XPATH_HOTEL_NAME)
                if hotel_element.count() > 0:
                    order_data["酒店名称"] = hotel_element.first.inner_text().strip()
                    logger.info(f"  酒店名称: {order_data['酒店名称']}")
            except Exception as e:
                logger.warning(f"获取酒店名称失败: {e}")
            
            # 获取姓名
            try:
                name_element = self.page.locator(self.XPATH_CLIENT_NAME)
                if name_element.count() > 0:
                    order_data["姓名"] = name_element.first.inner_text().strip()
                    logger.info(f"  姓名: {order_data['姓名']}")
            except Exception as e:
                logger.warning(f"获取姓名失败: {e}")
            
            # 获取住离日期
            try:
                date_element = self.page.locator(self.XPATH_CHECK_DATE)
                if date_element.count() > 0:
                    order_data["入离日期"] = date_element.first.inner_text().strip()
                    logger.info(f"  入离日期: {order_data['入离日期']}")
            except Exception as e:
                logger.warning(f"获取入离日期失败: {e}")
            
            # 获取房型
            try:
                room_element = self.page.locator(self.XPATH_ROOM_NAME)
                if room_element.count() > 0:
                    order_data["房型"] = room_element.first.inner_text().strip()
                    logger.info(f"  房型: {order_data['房型']}")
            except Exception as e:
                logger.warning(f"获取房型失败: {e}")
            
            # 电话写死
            order_data["电话"] = "12345678910"
            
            return self._build_order_info(order_data)
            
        except Exception as e:
            logger.error(f"解析订单详情失败: {e}")
            return None
    
    def _build_order_info(self, order_data: Dict) -> Optional[OrderInfo]:
        """从解析的数据构建 OrderInfo 对象"""
        try:
            import re
            
            hotel_name = order_data.get("酒店名称", "")
            guest_name = order_data.get("姓名", "")
            phone = order_data.get("电话", "12345678910")
            room_type = order_data.get("房型", "")
            date_str = order_data.get("入离日期", "")
            
            check_in_date = ""
            check_out_date = ""
            nights = 1
            
            if date_str:
                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s*(?:至|-|~)\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})', date_str)
                if date_match:
                    check_in_date = date_match.group(1).replace('/', '-')
                    check_out_date = date_match.group(2).replace('/', '-')
                    try:
                        from datetime import datetime as dt
                        d1 = dt.strptime(check_in_date, "%Y-%m-%d")
                        d2 = dt.strptime(check_out_date, "%Y-%m-%d")
                        nights = (d2 - d1).days
                    except:
                        nights = 1
            
            order_id = f"DLT{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            guest = GuestInfo(name=guest_name, phone=phone, id_card="")
            room = RoomInfo(
                room_type=room_type,
                room_count=1,
                check_in_date=check_in_date,
                check_out_date=check_out_date,
                nights=nights,
                breakfast="",
                window=""
            )
            
            order = OrderInfo(
                order_id=order_id,
                hotel_name=hotel_name,
                guest=guest,
                room=room,
                source_platform=Platform.MEITUAN,
                source_price=0.0
            )
            
            logger.info(f"✓ 订单解析成功: {order.order_id}")
            return order
            
        except Exception as e:
            logger.error(f"构建订单信息失败: {e}")
            return None


# ==================== 订单处理器主类 ====================

class OrderProcessor:
    """订单处理器主类"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.storage = OrderStorage()
        self.dailitong_fetcher = DailitongOrderFetcher()
        
        # 导入下单模块
        self.ctrip_placer = None
        self.meituan_placer = None
    
    def _get_ctrip_placer(self):
        """懒加载携程下单器"""
        if self.ctrip_placer is None:
            try:
                from orders.ctrip_order import CtripOrderPlacer
                self.ctrip_placer = CtripOrderPlacer()
            except ImportError as e:
                logger.error(f"导入携程下单模块失败: {e}")
        return self.ctrip_placer
    
    def _get_meituan_placer(self):
        """懒加载美团下单器"""
        if self.meituan_placer is None:
            try:
                from orders.meituan_order import MeituanOrderPlacer
                self.meituan_placer = MeituanOrderPlacer()
            except ImportError as e:
                logger.error(f"导入美团下单模块失败: {e}")
        return self.meituan_placer
    
    def _search_hotel_prices(self, hotel_name: str) -> bool:
        """调用 search.py 搜索酒店价格"""
        import subprocess
        
        logger.info(f"  🔍 调用 search.py 搜索酒店: {hotel_name}")
        
        # 从酒店名称中提取城市
        city = "上海"
        if "上海" in hotel_name:
            city = "上海"
        elif "北京" in hotel_name:
            city = "北京"
        elif "广州" in hotel_name:
            city = "广州"
        elif "深圳" in hotel_name:
            city = "深圳"
        
        import re
        hotel_keyword = re.sub(r'[（(].*?[）)]', '', hotel_name)
        hotel_keyword = hotel_keyword.replace(city, '').strip()
        if not hotel_keyword:
            hotel_keyword = hotel_name
        
        search_input = f"{city},{hotel_keyword}"
        logger.info(f"  搜索参数: {search_input}")
        
        try:
            search_script = os.path.join(PROJECT_ROOT, "search.py")
            subprocess_env = os.environ.copy()
            subprocess_env['PYTHONIOENCODING'] = 'utf-8'
            
            process = subprocess.Popen(
                [sys.executable, search_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=PROJECT_ROOT,
                env=subprocess_env
            )
            
            stdout, _ = process.communicate(input=f"{search_input}\n\n", timeout=300)
            
            if "成功" in stdout or "完成" in stdout:
                logger.info("  ✓ 搜索完成")
                return True
            else:
                logger.warning("  ⚠️ 搜索可能未完全成功")
                return True
                
        except subprocess.TimeoutExpired:
            logger.error("  ❌ 搜索超时")
            return False
        except Exception as e:
            logger.error(f"  ❌ 搜索失败: {e}")
            return False
    
    def _extract_room_type_category(self, room_type_str: str) -> str:
        """从房型名称中提取房间类型分类"""
        if "双床" in room_type_str:
            return "双床房"
        if "大床" in room_type_str:
            return "大床房"
        if "三人" in room_type_str:
            return "三人间"
        if "单人" in room_type_str or "单床" in room_type_str:
            return "单人房"
        return "其他"
    
    def _extract_window_type(self, room_type_str: str) -> str:
        """从房型名称中提取窗户类型"""
        if "有窗" in room_type_str or "阳光" in room_type_str:
            return "有窗"
        if "无窗" in room_type_str or "内窗" in room_type_str or "静谧" in room_type_str:
            return "无窗"
        return "未知"
    
    def _extract_breakfast_type(self, room_type_str: str) -> str:
        """从房型名称中提取早餐类型"""
        if "3份早餐" in room_type_str:
            return "含3份早餐"
        if "2份早餐" in room_type_str or "双早" in room_type_str:
            return "含2份早餐"
        if "1份早餐" in room_type_str or "单早" in room_type_str:
            return "含1份早餐"
        if "无早餐" in room_type_str or "不含早" in room_type_str or "无早" in room_type_str or "<无早>" in room_type_str:
            return "无早餐"
        return "未知"
    
    def _find_cheapest_platform_with_comparison(self, order: OrderInfo) -> Tuple[Optional[Platform], float, bool, float]:
        """
        使用三维匹配逻辑比价
        
        🔥 修复：放宽窗户匹配条件，如果精确匹配找不到，则忽略窗户条件
        """
        try:
            from price_comparison import (
                DataLoader, PriceComparator, RoomTypeMapper, 
                RoomType, WindowType, BreakfastType
            )
            
            order_room_type = order.room.room_type
            logger.info(f"  订单房型: {order_room_type}")
            
            room_category = self._extract_room_type_category(order_room_type)
            window_category = self._extract_window_type(order_room_type)
            breakfast_category = self._extract_breakfast_type(order_room_type)
            
            logger.info(f"  解析结果:")
            logger.info(f"    房间类型: {room_category}")
            logger.info(f"    窗户类型: {window_category}")
            logger.info(f"    早餐类型: {breakfast_category}")
            
            xiecheng_file = os.path.join(PROJECT_ROOT, "xiecheng", "hotel_data.json")
            meituan_file = os.path.join(PROJECT_ROOT, "meituan", "meituan_hotel.json")
            
            if not os.path.exists(xiecheng_file) or not os.path.exists(meituan_file):
                logger.warning("  ⚠️ 比价数据文件不存在")
                return None, 0.0, False, 0.0
            
            xiecheng_data = DataLoader.load_json(xiecheng_file)
            meituan_data = DataLoader.load_json(meituan_file)
            
            xiecheng_rooms = DataLoader.parse_room_data(xiecheng_data, "携程")
            meituan_rooms = DataLoader.parse_room_data(meituan_data, "美团")
            
            logger.info(f"  携程房间数: {len(xiecheng_rooms)}")
            logger.info(f"  美团房间数: {len(meituan_rooms)}")
            
            comparator = PriceComparator(
                threshold=50.0, 
                threshold_percent=10.0, 
                profit_threshold_percent=20.0
            )
            
            comparisons = comparator.compare_all_rooms(xiecheng_rooms, meituan_rooms)
            logger.info(f"  比价结果数: {len(comparisons)}")
            
            # 转换枚举
            order_room_enum = None
            for rt in RoomType:
                if rt.value == room_category:
                    order_room_enum = rt
                    break
            
            order_window_enum = None
            for wt in WindowType:
                if wt.value == window_category:
                    order_window_enum = wt
                    break
            
            order_breakfast_enum = None
            for bt in BreakfastType:
                if bt.value == breakfast_category:
                    order_breakfast_enum = bt
                    break
            
            if order_room_enum is None:
                logger.warning(f"  ⚠️ 无法识别房间类型: {room_category}")
                return None, 0.0, False, 0.0
            
            # 🔥 第一次尝试：精确匹配（房间类型+窗户+早餐）
            matching_comparisons = []
            for comp in comparisons:
                if comp.room_type != order_room_enum:
                    continue
                
                # 窗户匹配
                if order_window_enum and order_window_enum != WindowType.UNKNOWN:
                    if comp.window_type != order_window_enum and comp.window_type != WindowType.UNKNOWN:
                        continue
                
                # 早餐匹配
                if order_breakfast_enum and order_breakfast_enum != BreakfastType.UNKNOWN:
                    if comp.breakfast_type != order_breakfast_enum and comp.breakfast_type != BreakfastType.UNKNOWN:
                        continue
                
                matching_comparisons.append(comp)
            
            logger.info(f"  精确匹配结果: {len(matching_comparisons)}")
            
            # 🔥 第二次尝试：放宽窗户条件（只匹配房间类型+早餐）
            if not matching_comparisons:
                logger.info("  尝试放宽窗户条件...")
                for comp in comparisons:
                    if comp.room_type != order_room_enum:
                        continue
                    
                    # 只匹配早餐
                    if order_breakfast_enum and order_breakfast_enum != BreakfastType.UNKNOWN:
                        if comp.breakfast_type != order_breakfast_enum and comp.breakfast_type != BreakfastType.UNKNOWN:
                            continue
                    
                    matching_comparisons.append(comp)
                
                logger.info(f"  放宽窗户后匹配结果: {len(matching_comparisons)}")
            
            # 🔥 第三次尝试：只匹配房间类型
            if not matching_comparisons:
                logger.info("  尝试只匹配房间类型...")
                for comp in comparisons:
                    if comp.room_type == order_room_enum:
                        matching_comparisons.append(comp)
                
                logger.info(f"  只匹配房间类型结果: {len(matching_comparisons)}")
            
            if not matching_comparisons:
                logger.warning(f"  ⚠️ 未找到匹配的房型比价结果")
                return None, 0.0, False, 0.0
            
            # 找出最优选择
            best_comp = None
            for comp in matching_comparisons:
                if best_comp is None:
                    best_comp = comp
                else:
                    if comp.has_profit and not best_comp.has_profit:
                        best_comp = comp
                    elif not comp.has_profit and best_comp.has_profit:
                        pass
                    else:
                        if min(comp.price_a, comp.price_b) < min(best_comp.price_a, best_comp.price_b):
                            best_comp = comp
            
            if best_comp:
                logger.info(f"\n  📊 最优比价结果:")
                logger.info(f"    房间类型: {best_comp.room_type.value} | {best_comp.window_type.value} | {best_comp.breakfast_type.value}")
                logger.info(f"    携程: {best_comp.room_name_a} - {best_comp.price_a}元")
                logger.info(f"    美团: {best_comp.room_name_b} - {best_comp.price_b}元")
                logger.info(f"    价格差: {best_comp.price_diff}元 ({best_comp.price_diff_percent:.1f}%)")
                logger.info(f"    有利润: {'✅ 是' if best_comp.has_profit else '❌ 否'}")
                
                if best_comp.price_a < best_comp.price_b:
                    recommend_platform = Platform.XIECHENG
                    recommend_price = best_comp.price_a
                else:
                    recommend_platform = Platform.MEITUAN
                    recommend_price = best_comp.price_b
                
                return recommend_platform, recommend_price, best_comp.has_profit, best_comp.price_diff_percent
            
            return None, 0.0, False, 0.0
            
        except Exception as e:
            logger.error(f"比价失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, 0.0, False, 0.0
    
    def _place_order_on_platform(self, order: OrderInfo, platform: Platform) -> Tuple[bool, str]:
        """在指定平台下单"""
        if platform == Platform.XIECHENG:
            placer = self._get_ctrip_placer()
            if placer is None:
                return False, "携程下单模块不可用"
            
            try:
                if not placer.setup_browser():
                    return False, "启动浏览器失败"
                
                success, result = placer.place_order(
                    hotel_name=order.hotel_name,
                    room_type=order.room.room_type,
                    check_in=order.room.check_in_date,
                    check_out=order.room.check_out_date,
                    guest_name=order.guest.name,
                    phone=order.guest.phone,
                    dry_run=self.dry_run
                )
                return success, result
            finally:
                placer.close_browser()
                
        elif platform == Platform.MEITUAN:
            placer = self._get_meituan_placer()
            if placer is None:
                return False, "美团下单模块不可用"
            
            try:
                if not placer.setup_browser():
                    return False, "启动浏览器失败"
                
                success, result = placer.place_order(
                    hotel_name=order.hotel_name,
                    room_type=order.room.room_type,
                    check_in=order.room.check_in_date,
                    check_out=order.room.check_out_date,
                    guest_name=order.guest.name,
                    phone=order.guest.phone,
                    dry_run=self.dry_run
                )
                return success, result
            finally:
                placer.close_browser()
        
        return False, f"不支持的平台: {platform.value}"
    
    def fetch_and_process_from_dailitong(self, order_index: int = 0) -> bool:
        """从代理通获取订单并处理（完整流程）"""
        logger.info("\n" + "=" * 60)
        logger.info("  🚀 从代理通获取订单并处理")
        logger.info("=" * 60)
        
        try:
            # 步骤1: 启动浏览器
            logger.info("\n[步骤1] 启动浏览器...")
            if not self.dailitong_fetcher.setup_browser():
                logger.error("❌ 启动浏览器失败")
                return False
            
            # 步骤2: 加载Cookies并导航
            logger.info("\n[步骤2] 加载Cookies...")
            if not self.dailitong_fetcher.load_cookies_and_navigate():
                logger.error("❌ 加载Cookies失败")
                return False
            
            # 步骤3: 导航到订单列表
            logger.info("\n[步骤3] 导航到代理通订单列表...")
            if not self.dailitong_fetcher.navigate_to_order_list():
                logger.error("❌ 导航失败")
                return False
            
            # 步骤4: 点击订单详情
            logger.info("\n[步骤4] 点击订单详情...")
            if not self.dailitong_fetcher.click_order_detail(order_index):
                logger.error("❌ 点击订单详情失败")
                return False
            
            # 步骤5: 解析订单信息
            logger.info("\n[步骤5] 解析订单信息...")
            order = self.dailitong_fetcher.parse_order_detail()
            
            if order is None:
                logger.error("❌ 解析订单信息失败")
                return False
            
            self.storage.add_order(order)
            
            # 步骤6: 搜索酒店价格
            logger.info("\n[步骤6] 搜索酒店价格...")
            self._search_hotel_prices(order.hotel_name)
            
            # 步骤7: 三维匹配比价
            logger.info("\n[步骤7] 三维匹配比价...")
            target_platform, target_price, has_profit, profit_percent = self._find_cheapest_platform_with_comparison(order)
            
            if target_platform and target_price > 0:
                logger.info(f"\n  📊 比价结果:")
                logger.info(f"    推荐平台: {target_platform.value}")
                logger.info(f"    推荐价格: {target_price}元")
                logger.info(f"    有利润: {'✅ 是' if has_profit else '❌ 否'}")
            else:
                logger.warning("  ⚠️ 未找到匹配的比价数据")
            
            # 步骤8: 下单
            logger.info("\n[步骤8] 下单...")
            
            if has_profit and target_platform:
                logger.info(f"  ✅ 有利润空间（价差{profit_percent:.1f}%>20%）")
                logger.info(f"  → 在{target_platform.value}下单")
                order.target_platform = target_platform
                order.target_price = target_price
                order.calculate_profit()
                
                # 🔥 调用新的下单模块
                success, result = self._place_order_on_platform(order, target_platform)
            else:
                if target_platform:
                    logger.info(f"  ❌ 无利润空间（价差{profit_percent:.1f}%≤20%），暂不处理")
                    order.remark = f"无利润空间（价差{profit_percent:.1f}%≤20%）"
                else:
                    logger.info(f"  ❌ 未找到匹配的房型，暂不处理")
                    order.remark = "未找到匹配的房型"
                
                order.status = OrderStatus.PENDING
                self.storage.update_order(order)
                logger.info("\n⚠️ 该订单暂不处理")
                return True
            
            # 更新订单状态
            if success:
                order.target_order_id = result
                order.status = OrderStatus.BOOKED
                order.remark = f"已在{target_platform.value}下单"
                logger.info(f"\n✓ 订单处理成功")
            else:
                order.status = OrderStatus.FAILED
                order.remark = f"处理失败: {result}"
                logger.error(f"\n✗ 订单处理失败: {result}")
            
            self.storage.update_order(order)
            
            # 显示处理结果
            logger.info("\n" + "=" * 60)
            logger.info("  📋 处理结果")
            logger.info("=" * 60)
            logger.info(f"  订单号: {order.order_id}")
            logger.info(f"  酒店: {order.hotel_name}")
            logger.info(f"  状态: {order.status.value}")
            logger.info("=" * 60)
            
            return success
            
        except Exception as e:
            logger.error(f"处理订单失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
        
        finally:
            logger.info("\n处理完成，按回车键关闭浏览器...")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass
            self.dailitong_fetcher.close_browser()
    
    def create_test_order(self) -> OrderInfo:
        """创建测试订单"""
        guest = GuestInfo(name="张三", phone="13800138000", id_card="")
        room = RoomInfo(
            room_type="商务大床房",
            room_count=1,
            check_in_date="2026-01-10",
            check_out_date="2026-01-11",
            nights=1,
            breakfast="不含早",
            window="无窗"
        )
        
        return OrderInfo(
            order_id=f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
            hotel_name="美利居酒店（上海城市中心人民广场店）",
            guest=guest,
            room=room,
            source_platform=Platform.MEITUAN,
            source_price=500.0
        )


# ==================== 主函数 ====================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='订单处理模块 - 获取代理通订单并在低价平台下单',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 🔥 从代理通获取订单并处理（推荐）
  python orders/order_processor.py --fetch
  
  # 演示模式（不实际下单）
  python orders/order_processor.py --fetch --dry-run
  
  # 查看所有订单
  python orders/order_processor.py --list
  
  # 测试携程下单
  python orders/order_processor.py --test-ctrip
  
  # 测试美团下单
  python orders/order_processor.py --test-meituan
        '''
    )
    
    parser.add_argument('--fetch', '-f', action='store_true', help='从代理通获取订单并处理')
    parser.add_argument('--index', type=int, default=0, help='订单索引（从0开始）')
    parser.add_argument('--dry-run', action='store_true', help='演示模式（不实际下单）')
    parser.add_argument('--list', '-l', action='store_true', help='查看所有订单')
    parser.add_argument('--test-ctrip', action='store_true', help='测试携程下单')
    parser.add_argument('--test-meituan', action='store_true', help='测试美团下单')
    
    args = parser.parse_args()
    
    processor = OrderProcessor(dry_run=args.dry_run)
    
    if args.fetch:
        print("\n" + "=" * 60)
        print("  🚀 从代理通获取订单并处理")
        print("=" * 60)
        print(f"  订单索引: {args.index}")
        print(f"  演示模式: {'是' if args.dry_run else '否'}")
        print("=" * 60)
        
        success = processor.fetch_and_process_from_dailitong(order_index=args.index)
        sys.exit(0 if success else 1)
    
    elif args.list:
        orders = processor.storage.get_all_orders()
        if not orders:
            print("暂无订单")
        else:
            print(f"\n共 {len(orders)} 个订单:\n")
            print("-" * 80)
            for order in orders:
                print(f"订单号: {order.order_id}")
                print(f"  酒店: {order.hotel_name}")
                print(f"  入住人: {order.guest.name}")
                print(f"  房型: {order.room.room_type}")
                print(f"  状态: {order.status.value}")
                print(f"  备注: {order.remark}")
                print("-" * 80)
    
    elif args.test_ctrip:
        print("\n测试携程下单...")
        test_order = processor.create_test_order()
        success, result = processor._place_order_on_platform(test_order, Platform.XIECHENG)
        print(f"结果: {'成功' if success else '失败'} - {result}")
    
    elif args.test_meituan:
        print("\n测试美团下单...")
        test_order = processor.create_test_order()
        success, result = processor._place_order_on_platform(test_order, Platform.MEITUAN)
        print(f"结果: {'成功' if success else '失败'} - {result}")
    
    else:
        parser.print_help()
        print("\n" + "=" * 60)
        print("  💡 快速开始:")
        print("  python orders/order_processor.py --fetch --dry-run")
        print("=" * 60)


if __name__ == "__main__":
    main()


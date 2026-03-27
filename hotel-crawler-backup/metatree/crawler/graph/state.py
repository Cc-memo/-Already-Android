"""
爬取状态定义
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class CrawlState:
    """爬取状态"""
    # 任务信息
    task_id: str
    hotel_name: str
    platform: str
    
    # 流程状态
    current_node: str = "START"
    visited_nodes: List[str] = field(default_factory=list)
    error_count: int = 0
    max_retries: int = 3
    
    # 数据
    urls: Dict[str, str] = field(default_factory=dict)  # base_url, search_url, detail_url等
    login_status: bool = False
    login_credentials: Optional[Dict[str, str]] = None  # username, password
    located_elements: Dict[str, Any] = field(default_factory=dict)  # 定位的元素
    search_results: List[Dict] = field(default_factory=list)  # 搜索结果
    hotel_data: List[Dict] = field(default_factory=list)  # 酒店数据
    validation_results: Dict[str, Any] = field(default_factory=dict)  # 校验结果
    
    # 元数据
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    logs: List[str] = field(default_factory=list)  # 日志记录
    error_messages: List[str] = field(default_factory=list)  # 错误消息
    
    def add_log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{timestamp}] [{self.current_node}] {message}")
    
    def add_error(self, error: str):
        """添加错误"""
        self.error_count += 1
        self.error_messages.append(error)
        self.add_log(f"错误: {error}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'hotel_name': self.hotel_name,
            'platform': self.platform,
            'current_node': self.current_node,
            'visited_nodes': self.visited_nodes,
            'error_count': self.error_count,
            'login_status': self.login_status,
            'hotel_data_count': len(self.hotel_data),
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'logs_count': len(self.logs),
        }


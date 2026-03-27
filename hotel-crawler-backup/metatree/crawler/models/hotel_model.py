"""
酒店数据模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class HotelData(Base):
    """酒店数据表模型"""
    __tablename__ = 'hotel_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    hotel_name = Column(String(200), nullable=False, index=True, comment='酒店名称')
    platform = Column(String(50), nullable=False, index=True, comment='平台名称')
    hotel_id = Column(String(100), comment='平台酒店ID')
    hotel_url = Column(String(500), comment='酒店URL')
    
    # 基本信息
    star_level = Column(String(50), comment='星级')
    rating_score = Column(Float, comment='评分')
    review_count = Column(Integer, comment='点评数量')
    min_price = Column(Float, comment='最低价格')
    booking_dynamic = Column(String(200), comment='预订动态')
    
    # 位置信息
    address = Column(String(500), comment='地址')
    region = Column(String(100), index=True, comment='区域（城市-区县）')
    
    # 详细信息
    opening_date = Column(String(100), comment='开业时间')
    room_types = Column(JSON, comment='房型信息（JSON格式）')
    
    # 联系方式（新增字段）
    phone = Column(String(50), comment='联系电话')
    email = Column(String(100), comment='邮箱')
    website = Column(String(500), comment='官网')
    
    # 元数据
    crawl_time = Column(DateTime, default=datetime.now, comment='爬取时间')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'hotel_name': self.hotel_name,
            'platform': self.platform,
            'hotel_id': self.hotel_id,
            'hotel_url': self.hotel_url,
            'star_level': self.star_level,
            'rating_score': self.rating_score,
            'review_count': self.review_count,
            'min_price': self.min_price,
            'booking_dynamic': self.booking_dynamic,
            'address': self.address,
            'region': self.region,
            'opening_date': self.opening_date,
            'room_types': self.room_types,
            'phone': self.phone,
            'email': self.email,
            'website': self.website,
            'crawl_time': self.crawl_time.isoformat() if self.crawl_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class CrawlTask(Base):
    """爬取任务表模型"""
    __tablename__ = 'crawl_tasks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    hotel_name = Column(String(200), nullable=False, comment='酒店名称')
    platforms = Column(String(200), nullable=False, comment='目标平台（逗号分隔）')
    task_type = Column(String(50), default='immediate', comment='任务类型：immediate/scheduled')
    status = Column(String(50), default='pending', comment='任务状态：pending/running/completed/failed')
    progress = Column(Integer, default=0, comment='进度（0-100）')
    error_message = Column(Text, comment='错误信息')
    
    created_by = Column(String(100), comment='创建人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    started_at = Column(DateTime, comment='开始时间')
    completed_at = Column(DateTime, comment='完成时间')
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'hotel_name': self.hotel_name,
            'platforms': self.platforms,
            'task_type': self.task_type,
            'status': self.status,
            'progress': self.progress,
            'error_message': self.error_message,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


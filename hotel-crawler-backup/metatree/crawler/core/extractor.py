"""
数据提取核心模块 - 可复用
"""
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
import re

from crawler.utils.logger import logger
from crawler.utils.helpers import (
    clean_text, parse_price, parse_rating, 
    parse_review_count, format_datetime
)


class DataExtractor:
    """数据提取器 - 可复用"""
    
    @staticmethod
    def extract_text(soup: BeautifulSoup, selector: str, 
                    default: str = '') -> str:
        """
        提取文本内容
        
        Args:
            soup: BeautifulSoup对象
            selector: CSS选择器
            default: 默认值
        
        Returns:
            提取的文本
        """
        try:
            element = soup.select_one(selector)
            if element:
                return clean_text(element.get_text())
            return default
        except:
            return default
    
    @staticmethod
    def extract_attribute(soup: BeautifulSoup, selector: str, 
                         attribute: str, default: str = '') -> str:
        """
        提取元素属性
        
        Args:
            soup: BeautifulSoup对象
            selector: CSS选择器
            attribute: 属性名
            default: 默认值
        
        Returns:
            属性值
        """
        try:
            element = soup.select_one(selector)
            if element:
                return element.get(attribute, default)
            return default
        except:
            return default
    
    @staticmethod
    def extract_list(soup: BeautifulSoup, selector: str) -> List[str]:
        """
        提取列表数据
        
        Args:
            soup: BeautifulSoup对象
            selector: CSS选择器
        
        Returns:
            文本列表
        """
        try:
            elements = soup.select(selector)
            return [clean_text(elem.get_text()) for elem in elements]
        except:
            return []
    
    @staticmethod
    def extract_price(text: str) -> Optional[float]:
        """提取价格"""
        return parse_price(text)
    
    @staticmethod
    def extract_rating(text: str) -> Optional[float]:
        """提取评分"""
        return parse_rating(text)
    
    @staticmethod
    def extract_review_count(text: str) -> Optional[int]:
        """提取点评数量"""
        return parse_review_count(text)
    
    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        """
        提取电话号码
        
        Args:
            text: 文本内容
        
        Returns:
            电话号码
        """
        if not text:
            return None
        
        # 匹配各种电话号码格式
        patterns = [
            r'1[3-9]\d{9}',  # 手机号
            r'0\d{2,3}-?\d{7,8}',  # 固定电话
            r'400-?\d{3}-?\d{4}',  # 400电话
            r'\(\d{3,4}\)\s?\d{7,8}',  # 带区号的固定电话
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group(0)
                # 清理格式
                phone = re.sub(r'[-\s()]', '', phone)
                return phone
        
        return None
    
    @staticmethod
    def extract_email(text: str) -> Optional[str]:
        """
        提取邮箱地址
        
        Args:
            text: 文本内容
        
        Returns:
            邮箱地址
        """
        if not text:
            return None
        
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None
    
    @staticmethod
    def extract_contact_info(soup: BeautifulSoup, 
                           contact_selectors: Dict[str, str]) -> Dict[str, Optional[str]]:
        """
        提取联系方式信息
        
        Args:
            soup: BeautifulSoup对象
            contact_selectors: 联系方式选择器字典，格式：
                {
                    'phone': '电话选择器',
                    'email': '邮箱选择器',
                    'address': '地址选择器',
                    'website': '网站选择器'
                }
        
        Returns:
            联系方式字典
        """
        contact_info = {
            'phone': None,
            'email': None,
            'address': None,
            'website': None
        }
        
        # 提取电话
        if 'phone' in contact_selectors:
            phone_text = DataExtractor.extract_text(soup, contact_selectors['phone'])
            contact_info['phone'] = DataExtractor.extract_phone(phone_text)
        
        # 提取邮箱
        if 'email' in contact_selectors:
            email_text = DataExtractor.extract_text(soup, contact_selectors['email'])
            contact_info['email'] = DataExtractor.extract_email(email_text)
        
        # 提取地址
        if 'address' in contact_selectors:
            contact_info['address'] = DataExtractor.extract_text(
                soup, contact_selectors['address']
            )
        
        # 提取网站
        if 'website' in contact_selectors:
            website = DataExtractor.extract_attribute(
                soup, contact_selectors['website'], 'href'
            )
            if website:
                contact_info['website'] = website
        
        return contact_info
    
    @staticmethod
    def extract_room_types(soup: BeautifulSoup, 
                          room_config: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        提取房型信息
        
        Args:
            soup: BeautifulSoup对象
            room_config: 房型配置，格式：
                {
                    'container_selector': '房型容器选择器',
                    'name_selector': '房型名称选择器',
                    'price_selector': '价格选择器',
                    'stock_selector': '库存选择器（可选）'
                }
        
        Returns:
            房型列表
        """
        room_types = []
        
        try:
            containers = soup.select(room_config['container_selector'])
            
            for container in containers:
                room_info = {
                    'room_name': DataExtractor.extract_text(
                        container, room_config['name_selector']
                    ),
                    'min_price': None,
                    'stock': None
                }
                
                # 提取价格
                price_text = DataExtractor.extract_text(
                    container, room_config['price_selector']
                )
                room_info['min_price'] = DataExtractor.extract_price(price_text)
                
                # 提取库存（如果有）
                if 'stock_selector' in room_config:
                    stock_text = DataExtractor.extract_text(
                        container, room_config['stock_selector']
                    )
                    room_info['stock'] = stock_text
                
                if room_info['room_name']:
                    room_types.append(room_info)
        
        except Exception as e:
            logger.error(f"提取房型信息失败: {e}")
        
        return room_types


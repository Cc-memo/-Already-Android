"""
工具函数模块
"""
import time
import random
import re
from typing import Optional, Dict, Any
from fake_useragent import UserAgent
from crawler.utils.logger import logger

ua = UserAgent()


def get_random_user_agent() -> str:
    """获取随机User-Agent"""
    try:
        return ua.random
    except:
        return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


def random_delay(min_delay: float = 1.0, max_delay: float = 3.0):
    """随机延迟"""
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)


def clean_text(text: str) -> str:
    """清理文本"""
    if not text:
        return ''
    # 移除多余空白字符
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_number(text: str) -> Optional[float]:
    """从文本中提取数字"""
    if not text:
        return None
    # 提取数字（包括小数）
    numbers = re.findall(r'\d+\.?\d*', text.replace(',', ''))
    if numbers:
        try:
            return float(numbers[0])
        except ValueError:
            return None
    return None


def parse_price(price_text: str) -> Optional[float]:
    """解析价格文本"""
    if not price_text:
        return None
    # 移除货币符号和空格
    price_text = re.sub(r'[¥$€£,\s]', '', price_text)
    number = extract_number(price_text)
    return number


def parse_rating(rating_text: str) -> Optional[float]:
    """解析评分文本"""
    if not rating_text:
        return None
    # 提取评分数字
    rating = extract_number(rating_text)
    if rating and rating > 10:
        rating = rating / 10  # 如果是100分制，转换为10分制
    return rating


def parse_review_count(count_text: str) -> Optional[int]:
    """解析点评数量文本"""
    if not count_text:
        return None
    # 处理"1.2万"这样的格式
    if '万' in count_text:
        number = extract_number(count_text)
        if number:
            return int(number * 10000)
    # 处理普通数字
    number = extract_number(count_text)
    if number:
        return int(number)
    return None


def format_datetime(dt_str: str) -> Optional[str]:
    """格式化日期时间字符串"""
    if not dt_str:
        return None
    # 尝试解析常见格式
    patterns = [
        r'(\d{4})年(\d{1,2})月',
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
        r'(\d{4})/(\d{1,2})/(\d{1,2})',
    ]
    for pattern in patterns:
        match = re.search(pattern, dt_str)
        if match:
            return dt_str
    return dt_str


def retry_on_exception(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"函数 {func.__name__} 重试 {max_retries} 次后仍失败: {e}")
                        raise
                    logger.warning(f"函数 {func.__name__} 第 {attempt + 1} 次尝试失败: {e}, {delay}秒后重试")
                    time.sleep(delay * (attempt + 1))
            return None
        return wrapper
    return decorator


def build_headers(platform: str, referer: Optional[str] = None) -> Dict[str, str]:
    """构建请求头"""
    from crawler.config.settings import CRAWLER_CONFIG, PLATFORM_CONFIG
    
    headers = CRAWLER_CONFIG['headers'].copy()
    headers['User-Agent'] = get_random_user_agent()
    
    if platform in PLATFORM_CONFIG:
        headers.update(PLATFORM_CONFIG[platform].get('headers', {}))
    
    if referer:
        headers['Referer'] = referer
    
    return headers


__all__ = [
    'get_random_user_agent',
    'random_delay',
    'clean_text',
    'extract_number',
    'parse_price',
    'parse_rating',
    'parse_review_count',
    'format_datetime',
    'retry_on_exception',
    'build_headers'
]


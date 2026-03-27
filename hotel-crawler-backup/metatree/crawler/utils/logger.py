"""
日志工具模块
"""
from loguru import logger
import sys
from pathlib import Path
from crawler.config.settings import LOG_CONFIG

# 创建日志目录
log_dir = LOG_CONFIG['log_dir']
log_dir.mkdir(parents=True, exist_ok=True)

# 配置日志
logger.remove()  # 移除默认处理器

# 控制台输出
logger.add(
    sys.stderr,
    format=LOG_CONFIG['format'],
    level=LOG_CONFIG['level'],
    colorize=True
)

# 文件输出
logger.add(
    str(log_dir / LOG_CONFIG['log_file']),
    format=LOG_CONFIG['format'],
    level=LOG_CONFIG['level'],
    rotation=LOG_CONFIG['rotation'],
    retention=LOG_CONFIG['retention'],
    encoding='utf-8'
)

__all__ = ['logger']


"""
爬虫配置文件
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 数据库配置
DATABASE_CONFIG = {
    'mysql': {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', 'root'),
        'password': os.getenv('MYSQL_PASSWORD', 'password'),
        'database': os.getenv('MYSQL_DATABASE', 'hotel_crawler'),
        'charset': 'utf8mb4'
    },
    'mongodb': {
        'host': os.getenv('MONGODB_HOST', 'localhost'),
        'port': int(os.getenv('MONGODB_PORT', 27017)),
        'database': os.getenv('MONGODB_DATABASE', 'hotel_crawler'),
        'username': os.getenv('MONGODB_USER', ''),
        'password': os.getenv('MONGODB_PASSWORD', '')
    }
}

# Redis配置
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'db': int(os.getenv('REDIS_DB', 0)),
    'password': os.getenv('REDIS_PASSWORD', '')
}

# 爬虫配置
CRAWLER_CONFIG = {
    # 请求配置
    'request_timeout': 30,  # 请求超时时间（秒）
    'request_delay': 1,  # 请求间隔（秒）
    'retry_times': 3,  # 重试次数
    'concurrent_requests': 5,  # 并发请求数
    
    # 反爬配置
    'use_proxy': False,  # 是否使用代理
    'proxy_pool': [],  # 代理池
    'user_agent_rotation': True,  # 是否轮换User-Agent
    'headers': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    },
    
    # Selenium配置
    'selenium': {
        'headless': False,  # 无头模式
        'window_size': (1920, 1080),
        'implicit_wait': 10,
        'page_load_timeout': 30,
        # Chrome驱动路径，None则自动查找；可在此写死或用环境变量 CHROME_DRIVER_PATH 覆盖
        'driver_path': os.getenv('CHROME_DRIVER_PATH', r'D:\yingyong\tool\chrome-win\chromedriver.exe'),
    },
    
    # 数据存储配置
    'save_interval': 100,  # 每爬取多少条数据保存一次
    'enable_cache': True,  # 是否启用缓存
    'cache_expire': 3600,  # 缓存过期时间（秒）
}

# 平台配置
PLATFORM_CONFIG = {
    'meituan': {
        'base_url': os.getenv('MEITUAN_BASE_URL', 'https://hotel.meituan.com'),
        'search_url': os.getenv('MEITUAN_SEARCH_URL', 'https://hotel.meituan.com/beijing/'),
        'detail_url': os.getenv('MEITUAN_DETAIL_URL', 'https://hotel.meituan.com/'),
        'headers': {
            'Referer': os.getenv('MEITUAN_BASE_URL', 'https://www.meituan.com/'),
        },
        # XPath配置 - 搜索相关
        'search': {
            'input_xpath': os.getenv('MEITUAN_SEARCH_INPUT_XPATH', '//input[@type="search" or contains(@class, "search-input") or contains(@placeholder, "搜索")]'),
            'button_xpath': os.getenv('MEITUAN_SEARCH_BUTTON_XPATH', '//button[contains(@class, "search-btn") or @type="submit" or contains(text(), "搜索")]'),
            'use_enter': True,  # 是否使用回车键搜索
            'input_delay': 0.5,  # 输入后等待时间（秒）
            'click_delay': 0.3,  # 点击后等待时间（秒）
        },
        # XPath配置 - 登录相关
        'login': {
            'login_url': os.getenv('MEITUAN_LOGIN_URL', 'https://www.meituan.com/account/login'),
            'username_xpath': os.getenv('MEITUAN_USERNAME_XPATH', '//input[@name="username" or @type="text" or contains(@placeholder, "用户名")]'),
            'password_xpath': os.getenv('MEITUAN_PASSWORD_XPATH', '//input[@type="password"]'),
            'submit_xpath': os.getenv('MEITUAN_SUBMIT_XPATH', '//button[@type="submit" or contains(@class, "login-btn") or contains(text(), "登录")]'),
            'success_xpath': os.getenv('MEITUAN_SUCCESS_XPATH', '//div[contains(@class, "user-info") or contains(@class, "user-name")]'),
        },
        # XPath配置 - 页面识别
        'page_detection': {
            'login_indicators': [
                os.getenv('MEITUAN_LOGIN_INDICATOR_1', '//div[contains(@class, "login")]'),
                os.getenv('MEITUAN_LOGIN_INDICATOR_2', '//input[@type="password"]'),
                os.getenv('MEITUAN_LOGIN_INDICATOR_3', '//button[contains(text(), "登录")]'),
            ],
            'result_indicators': [
                os.getenv('MEITUAN_RESULT_INDICATOR_1', '//div[contains(@class, "hotel-list")]'),
                os.getenv('MEITUAN_RESULT_INDICATOR_2', '//div[contains(@class, "hotel-item")]'),
                os.getenv('MEITUAN_RESULT_INDICATOR_3', '//div[@data-hotel-id]'),
            ],
        },
        # XPath配置 - 数据提取
        'extraction': {
            'hotel_list_xpath': os.getenv('MEITUAN_HOTEL_LIST_XPATH', '//div[contains(@class, "hotel-item") or @data-hotel-id]'),
            'hotel_name_xpath': os.getenv('MEITUAN_HOTEL_NAME_XPATH', './/h3 | .//div[contains(@class, "hotel-name")] | .//span[contains(@class, "name")]'),
            'hotel_price_xpath': os.getenv('MEITUAN_HOTEL_PRICE_XPATH', './/div[contains(@class, "price")] | .//span[contains(@class, "price")]'),
            'hotel_rating_xpath': os.getenv('MEITUAN_HOTEL_RATING_XPATH', './/div[contains(@class, "rating")] | .//span[contains(@class, "score")]'),
            'hotel_address_xpath': os.getenv('MEITUAN_HOTEL_ADDRESS_XPATH', './/div[contains(@class, "address")] | .//span[contains(@class, "location")]'),
            'hotel_link_xpath': os.getenv('MEITUAN_HOTEL_LINK_XPATH', './/a[@href]'),
        },
        # 用户操作配置
        'user_actions': {
            'simulate_human': True,  # 是否模拟人类操作
            'mouse_move_offset': (-5, 5),  # 鼠标移动偏移范围
            'typing_delay_range': (0.05, 0.15),  # 打字延迟范围（秒）
            'click_delay_range': (0.5, 1.0),  # 点击后延迟范围（秒）
            'scroll_before_click': True,  # 点击前是否滚动到元素
        },
    },
    'ctrip': {
        'base_url': os.getenv('CTRIP_BASE_URL', 'https://www.ctrip.com'),
        'search_url': os.getenv('CTRIP_SEARCH_URL', 'https://hotels.ctrip.com/hotels/list'),
        'detail_url': os.getenv('CTRIP_DETAIL_URL', 'https://hotels.ctrip.com/hotels/detail'),
        'headers': {
            'Referer': os.getenv('CTRIP_BASE_URL', 'https://www.ctrip.com/'),
        },
        # XPath配置 - 搜索相关
        'search': {
            'input_xpath': os.getenv('CTRIP_SEARCH_INPUT_XPATH', '//input[@name="keyword" or contains(@class, "search-input") or contains(@placeholder, "酒店")]'),
            'button_xpath': os.getenv('CTRIP_SEARCH_BUTTON_XPATH', '//button[contains(@class, "search-btn") or contains(@class, "search") or contains(text(), "搜索")]'),
            'use_enter': True,
            'input_delay': 0.5,
            'click_delay': 0.3,
        },
        # XPath配置 - 登录相关
        'login': {
            'login_url': os.getenv('CTRIP_LOGIN_URL', 'https://www.ctrip.com/login'),
            'username_xpath': os.getenv('CTRIP_USERNAME_XPATH', '//input[@name="userName" or @type="text"]'),
            'password_xpath': os.getenv('CTRIP_PASSWORD_XPATH', '//input[@type="password"]'),
            'submit_xpath': os.getenv('CTRIP_SUBMIT_XPATH', '//button[contains(@class, "login-btn") or @type="submit" or contains(text(), "登录")]'),
            'success_xpath': os.getenv('CTRIP_SUCCESS_XPATH', '//div[contains(@class, "user-name") or contains(@class, "user-info")]'),
        },
        # XPath配置 - 页面识别
        'page_detection': {
            'login_indicators': [
                os.getenv('CTRIP_LOGIN_INDICATOR_1', '//div[contains(@class, "login")]'),
                os.getenv('CTRIP_LOGIN_INDICATOR_2', '//input[@type="password"]'),
                os.getenv('CTRIP_LOGIN_INDICATOR_3', '//button[contains(text(), "登录")]'),
            ],
            'result_indicators': [
                os.getenv('CTRIP_RESULT_INDICATOR_1', '//div[contains(@class, "hotel-list")]'),
                os.getenv('CTRIP_RESULT_INDICATOR_2', '//div[contains(@class, "hotel-item")]'),
                os.getenv('CTRIP_RESULT_INDICATOR_3', '//div[@data-hotel-id]'),
            ],
        },
        # XPath配置 - 数据提取
        'extraction': {
            'hotel_list_xpath': os.getenv('CTRIP_HOTEL_LIST_XPATH', '//div[contains(@class, "hotel-item") or @data-hotel-id]'),
            'hotel_name_xpath': os.getenv('CTRIP_HOTEL_NAME_XPATH', './/h3 | .//div[contains(@class, "hotel-name")]'),
            'hotel_price_xpath': os.getenv('CTRIP_HOTEL_PRICE_XPATH', './/div[contains(@class, "price")] | .//span[contains(@class, "min-price")]'),
            'hotel_rating_xpath': os.getenv('CTRIP_HOTEL_RATING_XPATH', './/div[contains(@class, "rating")] | .//span[contains(@class, "score")]'),
            'hotel_address_xpath': os.getenv('CTRIP_HOTEL_ADDRESS_XPATH', './/div[contains(@class, "address")]'),
            'hotel_link_xpath': os.getenv('CTRIP_HOTEL_LINK_XPATH', './/a[@href]'),
        },
        # 用户操作配置
        'user_actions': {
            'simulate_human': True,
            'mouse_move_offset': (-5, 5),
            'typing_delay_range': (0.05, 0.15),
            'click_delay_range': (0.5, 1.0),
            'scroll_before_click': True,
        },
    },
    'fliggy': {
        'base_url': os.getenv('FLIGGY_BASE_URL', 'https://www.fliggy.com'),
        'search_url': os.getenv('FLIGGY_SEARCH_URL', 'https://www.fliggy.com/s/hotel'),
        'detail_url': os.getenv('FLIGGY_DETAIL_URL', 'https://www.fliggy.com/hotel/detail'),
        'headers': {
            'Referer': os.getenv('FLIGGY_BASE_URL', 'https://www.fliggy.com/'),
        },
        # XPath配置 - 搜索相关
        'search': {
            'input_xpath': os.getenv('FLIGGY_SEARCH_INPUT_XPATH', '//input[@name="keyword" or contains(@placeholder, "酒店") or contains(@placeholder, "搜索")]'),
            'button_xpath': os.getenv('FLIGGY_SEARCH_BUTTON_XPATH', '//button[contains(@class, "search") or contains(text(), "搜索")]'),
            'use_enter': True,
            'input_delay': 0.5,
            'click_delay': 0.3,
        },
        # XPath配置 - 登录相关
        'login': {
            'login_url': os.getenv('FLIGGY_LOGIN_URL', 'https://www.fliggy.com/login'),
            'username_xpath': os.getenv('FLIGGY_USERNAME_XPATH', '//input[@name="username" or @type="text"]'),
            'password_xpath': os.getenv('FLIGGY_PASSWORD_XPATH', '//input[@type="password"]'),
            'submit_xpath': os.getenv('FLIGGY_SUBMIT_XPATH', '//button[contains(@class, "login-btn") or contains(text(), "登录")]'),
            'success_xpath': os.getenv('FLIGGY_SUCCESS_XPATH', '//div[contains(@class, "user")]'),
        },
        # XPath配置 - 页面识别
        'page_detection': {
            'login_indicators': [
                os.getenv('FLIGGY_LOGIN_INDICATOR_1', '//div[contains(@class, "login")]'),
                os.getenv('FLIGGY_LOGIN_INDICATOR_2', '//input[@type="password"]'),
                os.getenv('FLIGGY_LOGIN_INDICATOR_3', '//button[contains(text(), "登录")]'),
            ],
            'result_indicators': [
                os.getenv('FLIGGY_RESULT_INDICATOR_1', '//div[contains(@class, "hotel-list")]'),
                os.getenv('FLIGGY_RESULT_INDICATOR_2', '//div[contains(@class, "hotel-item")]'),
                os.getenv('FLIGGY_RESULT_INDICATOR_3', '//div[@data-hotel-id]'),
                os.getenv('FLIGGY_RESULT_INDICATOR_4', '//div[contains(@class, "list")]'),
                os.getenv('FLIGGY_RESULT_INDICATOR_5', '//ul[contains(@class, "list")]'),
            ],
        },
        # XPath配置 - 数据提取
        'extraction': {
            'hotel_list_xpath': os.getenv('FLIGGY_HOTEL_LIST_XPATH', '//div[contains(@class, "hotel-item") or @data-hotel-id]'),
            'hotel_name_xpath': os.getenv('FLIGGY_HOTEL_NAME_XPATH', './/div[contains(@class, "hotel-name")] | .//h3 | .//span[contains(@class, "name")]'),
            'hotel_price_xpath': os.getenv('FLIGGY_HOTEL_PRICE_XPATH', './/div[contains(@class, "price")] | .//span[contains(@class, "price")]'),
            'hotel_rating_xpath': os.getenv('FLIGGY_HOTEL_RATING_XPATH', './/div[contains(@class, "rating")] | .//span[contains(@class, "score")]'),
            'hotel_address_xpath': os.getenv('FLIGGY_HOTEL_ADDRESS_XPATH', './/div[contains(@class, "address")] | .//span[contains(@class, "location")]'),
            'hotel_link_xpath': os.getenv('FLIGGY_HOTEL_LINK_XPATH', './/a[@href]'),
        },
        # 用户操作配置
        'user_actions': {
            'simulate_human': True,
            'mouse_move_offset': (-5, 5),
            'typing_delay_range': (0.05, 0.15),
            'click_delay_range': (0.5, 1.0),
            'scroll_before_click': True,
        },
    },
    'gaode': {
        'base_url': os.getenv('GAODE_BASE_URL', 'https://www.amap.com'),
        'search_url': os.getenv('GAODE_SEARCH_URL', 'https://www.amap.com/search'),
        'detail_url': os.getenv('GAODE_DETAIL_URL', 'https://www.amap.com/place'),
        'headers': {
            'Referer': os.getenv('GAODE_BASE_URL', 'https://www.amap.com/'),
        },
        # XPath配置 - 搜索相关
        'search': {
            'input_xpath': os.getenv('GAODE_SEARCH_INPUT_XPATH', '//input[@name="query" or contains(@placeholder, "搜索")]'),
            'button_xpath': os.getenv('GAODE_SEARCH_BUTTON_XPATH', '//button[contains(@class, "search-btn") or contains(text(), "搜索")]'),
            'use_enter': True,
            'input_delay': 0.5,
            'click_delay': 0.3,
        },
        # XPath配置 - 登录相关
        'login': {
            'login_url': os.getenv('GAODE_LOGIN_URL', 'https://www.amap.com/login'),
            'username_xpath': os.getenv('GAODE_USERNAME_XPATH', '//input[@name="username" or @type="text"]'),
            'password_xpath': os.getenv('GAODE_PASSWORD_XPATH', '//input[@type="password"]'),
            'submit_xpath': os.getenv('GAODE_SUBMIT_XPATH', '//button[contains(@class, "login-btn") or contains(text(), "登录")]'),
            'success_xpath': os.getenv('GAODE_SUCCESS_XPATH', '//div[contains(@class, "user-name")]'),
        },
        # XPath配置 - 页面识别
        'page_detection': {
            'login_indicators': [
                os.getenv('GAODE_LOGIN_INDICATOR_1', '//div[contains(@class, "login")]'),
                os.getenv('GAODE_LOGIN_INDICATOR_2', '//input[@type="password"]'),
                os.getenv('GAODE_LOGIN_INDICATOR_3', '//button[contains(text(), "登录")]'),
            ],
            'result_indicators': [
                os.getenv('GAODE_RESULT_INDICATOR_1', '//div[contains(@class, "poi-list")]'),
                os.getenv('GAODE_RESULT_INDICATOR_2', '//div[contains(@class, "hotel-list")]'),
                os.getenv('GAODE_RESULT_INDICATOR_3', '//div[contains(@class, "poi-item")]'),
            ],
        },
        # XPath配置 - 数据提取
        'extraction': {
            'hotel_list_xpath': os.getenv('GAODE_HOTEL_LIST_XPATH', '//div[contains(@class, "poi-item") or contains(@class, "hotel-item")]'),
            'hotel_name_xpath': os.getenv('GAODE_HOTEL_NAME_XPATH', './/div[contains(@class, "poi-name")] | .//div[contains(@class, "hotel-name")] | .//h3'),
            'hotel_price_xpath': os.getenv('GAODE_HOTEL_PRICE_XPATH', './/div[contains(@class, "price")] | .//span[contains(@class, "price")]'),
            'hotel_rating_xpath': os.getenv('GAODE_HOTEL_RATING_XPATH', './/div[contains(@class, "rating")] | .//span[contains(@class, "score")]'),
            'hotel_address_xpath': os.getenv('GAODE_HOTEL_ADDRESS_XPATH', './/div[contains(@class, "address")]'),
            'hotel_link_xpath': os.getenv('GAODE_HOTEL_LINK_XPATH', './/a[@href]'),
        },
        # 用户操作配置
        'user_actions': {
            'simulate_human': True,
            'mouse_move_offset': (-5, 5),
            'typing_delay_range': (0.05, 0.15),
            'click_delay_range': (0.5, 1.0),
            'scroll_before_click': True,
        },
    }
}

# 日志配置
LOG_CONFIG = {
    'level': 'INFO',
    'format': '{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}',
    'rotation': '100 MB',
    'retention': '30 days',
    'log_dir': BASE_DIR / 'logs',
    'log_file': 'crawler.log'
}

# Celery配置
CELERY_CONFIG = {
    'broker_url': f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}/{REDIS_CONFIG['db']}",
    'result_backend': f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}/{REDIS_CONFIG['db']}",
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'Asia/Shanghai',
    'enable_utc': True,
}


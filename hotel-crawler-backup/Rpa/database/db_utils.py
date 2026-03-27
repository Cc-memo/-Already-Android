# -*- coding: utf-8 -*-
"""
数据库工具模块
支持SQLite（本地）和MySQL（云数据库）
通过配置文件或环境变量切换
"""

import os
import json
from datetime import datetime
from typing import Dict, Optional

# 配置文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "db_config.json")
DB_FILE = os.path.join(SCRIPT_DIR, "hotel_data.db")


def load_config() -> dict:
    """加载数据库配置"""
    # 优先使用环境变量
    db_type = os.getenv('DB_TYPE', 'sqlite')
    
    # 如果存在配置文件，读取配置
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                db_type = config.get('db_type', db_type)
        except:
            pass
    
    config = {
        'db_type': db_type,
        'sqlite': {
            'db_file': DB_FILE
        },
        'mysql': {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', 'hotel_data'),
            'charset': 'utf8mb4',
            'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', 10)),
            'read_timeout': int(os.getenv('DB_READ_TIMEOUT', 30)),
            'write_timeout': int(os.getenv('DB_WRITE_TIMEOUT', 30)),
            'ssl': {
                'enabled': os.getenv('DB_SSL_ENABLED', 'false').lower() == 'true',
                'ca': os.getenv('DB_SSL_CA'),
                'cert': os.getenv('DB_SSL_CERT'),
                'key': os.getenv('DB_SSL_KEY'),
            },
            'ssl_disabled': os.getenv('DB_SSL_DISABLED', 'false').lower() == 'true',
        }
    }
    
    # 如果配置文件存在，合并MySQL配置
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                if 'mysql' in file_config:
                    config['mysql'].update(file_config['mysql'])
        except:
            pass
    
    return config


def init_database():
    """初始化数据库表"""
    config = load_config()
    db_type = config['db_type']
    
    if db_type == 'sqlite':
        import sqlite3
        conn = sqlite3.connect(config['sqlite']['db_file'])
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_time TEXT NOT NULL,
                platform TEXT NOT NULL,
                address TEXT,
                hotel_keyword TEXT,
                hotel_name TEXT,
                room_count INTEGER DEFAULT 0,
                user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 为旧数据库添加user_id字段（如果不存在）
        try:
            cursor.execute("ALTER TABLE search_records ADD COLUMN user_id INTEGER")
        except Exception:
            pass  # 字段已存在，忽略错误
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS room_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id INTEGER NOT NULL,
                room_name TEXT NOT NULL,
                price TEXT,
                remaining_rooms TEXT,
                remarks TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (search_id) REFERENCES search_records(id) ON DELETE CASCADE
            )
        ''')
        
        # 创建 hotel_data 表（用于数据查询页面）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hotel_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hotel_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                hotel_id TEXT,
                hotel_url TEXT,
                star_level TEXT,
                rating_score REAL,
                review_count INTEGER,
                min_price REAL,
                booking_dynamic TEXT,
                address TEXT,
                region TEXT,
                opening_date TEXT,
                room_types TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                crawl_time TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 创建唯一索引（防止同一酒店在同一平台重复）
        try:
            cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_hotel_platform ON hotel_data(hotel_name, platform)')
        except Exception:
            pass  # 唯一索引可能已存在
        # 创建普通索引
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_hotel_name ON hotel_data(hotel_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_platform ON hotel_data(platform)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_region ON hotel_data(region)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawl_time ON hotel_data(crawl_time)')
        except Exception:
            pass  # 索引可能已存在
        
        conn.commit()
        conn.close()
        print(f"[OK] SQLite数据库已初始化: {config['sqlite']['db_file']}")
    
    elif db_type == 'mysql':
        try:
            import pymysql
        except ImportError:
            raise ImportError("MySQL需要安装pymysql: pip install pymysql")
        
        mysql_config = config['mysql']
        # 云数据库连接参数
        connect_kwargs = {
            'host': mysql_config['host'],
            'port': mysql_config['port'],
            'user': mysql_config['user'],
            'password': mysql_config['password'],
            'database': mysql_config['database'],
            'charset': mysql_config['charset'],
            'connect_timeout': mysql_config.get('connect_timeout', 10),  # 连接超时10秒
            'read_timeout': mysql_config.get('read_timeout', 30),  # 读取超时30秒
            'write_timeout': mysql_config.get('write_timeout', 30),  # 写入超时30秒
        }
        
        # SSL配置（云数据库通常需要）
        if mysql_config.get('ssl', {}).get('enabled', False):
            ssl_config = mysql_config['ssl']
            connect_kwargs['ssl'] = {
                'ca': ssl_config.get('ca'),
                'cert': ssl_config.get('cert'),
                'key': ssl_config.get('key'),
            }
            # 移除None值
            connect_kwargs['ssl'] = {k: v for k, v in connect_kwargs['ssl'].items() if v}
        elif mysql_config.get('ssl_disabled', False):
            # 明确禁用SSL（某些云数据库允许）
            connect_kwargs['ssl'] = {'check_hostname': False}
        
        conn = pymysql.connect(**connect_kwargs)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                search_time VARCHAR(50) NOT NULL,
                platform VARCHAR(20) NOT NULL,
                address VARCHAR(255),
                hotel_keyword VARCHAR(255),
                hotel_name VARCHAR(255),
                room_count INT DEFAULT 0,
                user_id INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_search_time (search_time),
                INDEX idx_platform (platform),
                INDEX idx_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        # 为旧数据库添加user_id字段（如果不存在）
        try:
            cursor.execute("ALTER TABLE search_records ADD COLUMN user_id INT")
            cursor.execute("ALTER TABLE search_records ADD INDEX idx_user_id (user_id)")
        except Exception:
            pass  # 字段已存在，忽略错误
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS room_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                search_id INT NOT NULL,
                room_name VARCHAR(255) NOT NULL,
                price VARCHAR(50),
                remaining_rooms VARCHAR(50),
                remarks TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (search_id) REFERENCES search_records(id) ON DELETE CASCADE,
                INDEX idx_search_id (search_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        
        # 创建 hotel_data 表（用于数据查询页面）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hotel_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                hotel_name VARCHAR(200) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                hotel_id VARCHAR(100),
                hotel_url VARCHAR(500),
                star_level VARCHAR(50),
                rating_score FLOAT,
                review_count INT,
                min_price FLOAT,
                booking_dynamic VARCHAR(200),
                address VARCHAR(500),
                region VARCHAR(100),
                opening_date VARCHAR(100),
                room_types JSON,
                phone VARCHAR(50),
                email VARCHAR(100),
                website VARCHAR(500),
                crawl_time DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_hotel_platform (hotel_name, platform),
                INDEX idx_hotel_name (hotel_name),
                INDEX idx_platform (platform),
                INDEX idx_region (region),
                INDEX idx_crawl_time (crawl_time)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        
        conn.commit()
        conn.close()
        print(f"[OK] MySQL数据库已连接: {mysql_config['host']}:{mysql_config['port']}/{mysql_config['database']}")


def _save_to_hotel_data_table(search_data: Dict, platform: str, hotel_name: str, address: str, city: str, room_list: list, search_time: str, user_id: Optional[int] = None):
    """内部函数：保存数据到 hotel_data 表"""
    try:
        import re
        # 如果 hotel_name 为空，尝试从 search_data 中提取
        if not hotel_name or not hotel_name.strip():
            hotel_name = (search_data.get('酒店名称') or 
                         search_data.get('hotel_name') or 
                         search_data.get('酒店名') or
                         search_data.get('name') or
                         search_data.get('酒店关键词') or  # 美团爬虫使用"酒店关键词"
                         search_data.get('hotel_keyword') or
                         '')
            if not hotel_name or not hotel_name.strip():
                print(f"⚠️  跳过保存到 hotel_data 表：hotel_name 为空 (platform={platform}, search_data keys: {list(search_data.keys())})")
                return
        
        # 从 search_data 中提取 hotel_data 需要的字段
        hotel_data_item = {
            'hotel_name': hotel_name.strip(),
            'platform': platform,
            'hotel_id': search_data.get('酒店ID') or search_data.get('hotel_id'),
            'hotel_url': search_data.get('酒店URL') or search_data.get('hotel_url'),
            'star_level': search_data.get('星级') or search_data.get('star_level'),
            'rating_score': search_data.get('评分') or search_data.get('rating_score') or search_data.get('点评分数'),
            'review_count': search_data.get('点评数量') or search_data.get('review_count') or search_data.get('点评条数'),
            'min_price': search_data.get('最低价格') or search_data.get('min_price') or search_data.get('起价'),
            'booking_dynamic': search_data.get('预订动态') or search_data.get('booking_dynamic'),
            'address': address,
            'region': city or search_data.get('区域') or search_data.get('region'),
            'opening_date': search_data.get('开业时间') or search_data.get('opening_date'),
            'room_types': room_list,  # 房型列表
            'phone': search_data.get('电话') or search_data.get('phone'),
            'email': search_data.get('邮箱') or search_data.get('email'),
            'website': search_data.get('官网') or search_data.get('website'),
            'crawl_time': search_time,
        }
        
        # 如果没有最低价格，尝试从房型列表中提取
        if not hotel_data_item['min_price'] and room_list:
            prices = []
            for room in room_list:
                price_str = room.get("价格", "") or ""
                if price_str:
                    try:
                        price_match = re.search(r"[\d.]+", str(price_str).replace(",", ""))
                        if price_match:
                            prices.append(float(price_match.group()))
                    except:
                        pass
            if prices:
                hotel_data_item['min_price'] = min(prices)
        
        # 转换平台名称（英文转中文）
        platform_map = {
            'meituan': '美团',
            'ctrip': '携程',
            'fliggy': '飞猪',
            'gaode': '高德',
        }
        if hotel_data_item['platform'] in platform_map:
            hotel_data_item['platform'] = platform_map[hotel_data_item['platform']]
        
        # 类型转换
        if hotel_data_item.get('rating_score'):
            try:
                hotel_data_item['rating_score'] = float(hotel_data_item['rating_score'])
            except:
                hotel_data_item['rating_score'] = None
        
        if hotel_data_item.get('review_count'):
            try:
                hotel_data_item['review_count'] = int(hotel_data_item['review_count'])
            except:
                hotel_data_item['review_count'] = None
        
        if hotel_data_item.get('min_price'):
            try:
                hotel_data_item['min_price'] = float(hotel_data_item['min_price'])
            except:
                hotel_data_item['min_price'] = None
        
        # 保存到 hotel_data 表
        print(f"💾 准备保存到 hotel_data 表: hotel_name={hotel_data_item['hotel_name']}, platform={hotel_data_item['platform']}")
        save_hotel_data_to_database([hotel_data_item], user_id=user_id)
    except Exception as e:
        print(f"⚠️  保存到 hotel_data 表失败: {e}")
        import traceback
        traceback.print_exc()
        # 不抛出异常，因为主要数据已保存成功


def save_to_database(platform: str, search_data: Dict, user_id: Optional[int] = None) -> bool:
    """保存搜索数据到数据库"""
    try:
        init_database()
        config = load_config()
        db_type = config['db_type']
        
        search_time = search_data.get("搜索时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        address = search_data.get("地址", "")
        hotel_keyword = search_data.get("酒店关键词", "")
        hotel_name = search_data.get("酒店名称", "")
        room_list = search_data.get("房型列表", [])
        room_count = len(room_list)
        
        # 提取日期信息（如果有）
        check_in_date = (
            search_data.get("入住日期")
            or search_data.get("check_in_date")
            or search_data.get("checkin_date")
        )
        check_out_date = (
            search_data.get("离店日期")
            or search_data.get("退房日期")
            or search_data.get("check_out_date")
            or search_data.get("checkout_date")
        )
        city = search_data.get("城市") or search_data.get("city", "")
        
        if db_type == 'sqlite':
            import sqlite3
            conn = sqlite3.connect(config['sqlite']['db_file'])
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO search_records 
                (search_time, platform, address, hotel_keyword, hotel_name, room_count, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (search_time, platform, address, hotel_keyword, hotel_name, room_count, user_id))
            
            search_id = cursor.lastrowid
            
            for room in room_list:
                cursor.execute('''
                    INSERT INTO room_data 
                    (search_id, room_name, price, remaining_rooms, remarks)
                    VALUES (?, ?, ?, ?, ?)
                ''', (search_id, room.get("房型名称", ""), 
                      room.get("价格", ""), 
                      room.get("剩余房间", ""), 
                      room.get("备注", "")))
            
            conn.commit()
            conn.close()
        
        
        elif db_type == 'mysql':
            import pymysql
            import re
            import uuid
            mysql_config = config['mysql']
            # 云数据库连接参数（与init_database保持一致）
            connect_kwargs = {
                'host': mysql_config['host'],
                'port': mysql_config['port'],
                'user': mysql_config['user'],
                'password': mysql_config['password'],
                'database': mysql_config['database'],
                'charset': mysql_config['charset'],
                'connect_timeout': mysql_config.get('connect_timeout', 10),
                'read_timeout': mysql_config.get('read_timeout', 30),
                'write_timeout': mysql_config.get('write_timeout', 30),
            }
            
            # SSL配置
            if mysql_config.get('ssl', {}).get('enabled', False):
                ssl_config = mysql_config['ssl']
                connect_kwargs['ssl'] = {
                    'ca': ssl_config.get('ca'),
                    'cert': ssl_config.get('cert'),
                    'key': ssl_config.get('key'),
                }
                connect_kwargs['ssl'] = {k: v for k, v in connect_kwargs['ssl'].items() if v}
            elif mysql_config.get('ssl_disabled', False):
                connect_kwargs['ssl'] = {'check_hostname': False}
            
            conn = pymysql.connect(**connect_kwargs)
            cursor = conn.cursor()

            def _mysql_columns(table_name: str) -> set:
                cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
                rows = cursor.fetchall()
                # pymysql默认返回 tuple: (Field, Type, Null, Key, Default, Extra)
                return {r[0] for r in rows}

            def _resolve_platform_id(platform_code: str) -> Optional[int]:
                # 优先从 platforms 表解析
                try:
                    pcols = _mysql_columns("platforms")
                except Exception:
                    pcols = set()

                cn_map = {
                    "meituan": "美团",
                    "ctrip": "携程",
                    "fliggy": "飞猪",
                    "gaode": "高德",
                }
                want_cn = cn_map.get(platform_code)

                if pcols:
                    code_col = next((c for c in ("code", "key", "slug", "en_name", "platform_code") if c in pcols), None)
                    name_col = next((c for c in ("name", "platform", "platform_name", "title", "cn_name") if c in pcols), None)

                    select_cols = ["id"]
                    if code_col:
                        select_cols.append(code_col)
                    if name_col and name_col not in select_cols:
                        select_cols.append(name_col)

                    col_sql = ", ".join([f"`{c}`" for c in select_cols])
                    cursor.execute(f"SELECT {col_sql} FROM `platforms`")
                    rows = cursor.fetchall()

                    for row in rows:
                        # row: (id, code?, name?)
                        pid = row[0]
                        code_val = row[1] if len(select_cols) >= 2 else None
                        name_val = row[2] if len(select_cols) >= 3 else (row[1] if len(select_cols) == 2 and name_col and not code_col else None)

                        if code_val and str(code_val).strip().lower() == platform_code.lower():
                            return int(pid)
                        if name_val:
                            nv = str(name_val).strip()
                            if nv.lower() == platform_code.lower():
                                return int(pid)
                            if want_cn and nv == want_cn:
                                return int(pid)

                # 兜底：按常见顺序尝试（并验证id存在）
                fallback = {"meituan": 1, "ctrip": 2, "fliggy": 3, "gaode": 4}.get(platform_code)
                if fallback:
                    try:
                        cursor.execute("SELECT `id` FROM `platforms` WHERE `id` = %s LIMIT 1", (fallback,))
                        if cursor.fetchone():
                            return int(fallback)
                    except Exception:
                        pass

                return None

            # --- 根据实际表结构选择写入方案（云库/旧版） ---
            search_cols = _mysql_columns("search_records")
            room_cols = _mysql_columns("room_data")
            cloud_schema = (
                ("platform_id" in search_cols)
                or ("total_room_count" in search_cols)
                or ("search_record_id" in room_cols)
                or ("price_str" in room_cols)
            )

            if cloud_schema:
                platform_id = _resolve_platform_id(platform)
                if ("platform_id" in search_cols or "platform_id" in room_cols) and not platform_id:
                    raise RuntimeError(f"无法解析 platform_id（platform={platform}），请检查云库 platforms 表数据")

                # 尽量贴合云库 search_records 结构：只插入存在的列
                req_id = (
                    search_data.get("request_id")
                    or search_data.get("任务ID")
                    or search_data.get("task_id")
                    or uuid.uuid4().hex
                )
                sr = {
                    "request_id": req_id,
                    "search_time": search_time,
                    "hotel_id": None,
                    "hotel_name": hotel_name,
                    "hotel_keyword": hotel_keyword,
                    "city": city,
                    "address": address,
                    "platform_id": platform_id,
                    "platform": platform,
                    "check_in_date": check_in_date,
                    "check_out_date": check_out_date,
                    "total_room_count": room_count,
                    "user_id": user_id,
                    "is_latest": 1,
                    "status": "success",
                    "duration_ms": None,
                    "raw_data": json.dumps(search_data, ensure_ascii=False),
                }
                sr = {k: v for k, v in sr.items() if k in search_cols}

                if "platform_id" in search_cols and sr.get("platform_id") is None:
                    raise RuntimeError("search_records.platform_id 为必填，但当前无法提供")
                if "search_time" in search_cols and not sr.get("search_time"):
                    raise RuntimeError("search_records.search_time 为必填，但当前为空")

                sr_cols = list(sr.keys())
                sr_sql = (
                    f"INSERT INTO `search_records` ({', '.join([f'`{c}`' for c in sr_cols])}) "
                    f"VALUES ({', '.join(['%s'] * len(sr_cols))})"
                )
                cursor.execute(sr_sql, tuple(sr[c] for c in sr_cols))
                search_id = cursor.lastrowid

                # room_data：至少写入 search_record_id / platform_id / room_name
                fk_col = "search_record_id" if "search_record_id" in room_cols else "search_id"
                for room in room_list:
                    room_name = room.get("房型名称", "") or ""
                    price_str = room.get("价格", "") or ""
                    remaining_rooms = room.get("剩余房间", "") or ""
                    remarks = room.get("备注", "") or ""

                    # 尝试提取价格数值
                    price_numeric = None
                    if price_str:
                        try:
                            price_match = re.search(r"[\d.]+", str(price_str).replace(",", ""))
                            if price_match:
                                price_numeric = float(price_match.group())
                        except Exception:
                            price_numeric = None

                    # 尝试提取剩余数量
                    remaining_count = None
                    try:
                        m = re.search(r"\d+", str(remaining_rooms))
                        if m:
                            remaining_count = int(m.group())
                    except Exception:
                        remaining_count = None

                    s = str(remaining_rooms)
                    is_sold_out = 1 if any(x in s for x in ("售罄", "无房", "满房")) else 0
                    if remaining_count == 0:
                        is_sold_out = 1

                    rd = {
                        fk_col: search_id,
                        "platform_id": platform_id,
                        "hotel_id": None,
                        "room_name": room_name,
                        "price_str": price_str,
                        "price_numeric": price_numeric,
                        "remaining_rooms": remaining_rooms,
                        "remaining_count": remaining_count,
                        "is_sold_out": is_sold_out,
                        "check_in_date": check_in_date,
                        "check_out_date": check_out_date,
                        "remarks": remarks,
                    }
                    rd = {k: v for k, v in rd.items() if k in room_cols}

                    if fk_col in room_cols and rd.get(fk_col) is None:
                        continue
                    if "platform_id" in room_cols and rd.get("platform_id") is None:
                        raise RuntimeError("room_data.platform_id 为必填，但当前无法提供")
                    if "room_name" in room_cols and not rd.get("room_name"):
                        continue

                    rd_cols = list(rd.keys())
                    rd_sql = (
                        f"INSERT INTO `room_data` ({', '.join([f'`{c}`' for c in rd_cols])}) "
                        f"VALUES ({', '.join(['%s'] * len(rd_cols))})"
                    )
                    cursor.execute(rd_sql, tuple(rd[c] for c in rd_cols))
            else:
                # 旧结构（兼容本项目原始表）
                # 检查是否有user_id字段
                try:
                    cursor.execute("SHOW COLUMNS FROM search_records LIKE 'user_id'")
                    has_user_id = cursor.fetchone() is not None
                except Exception:
                    has_user_id = False
                
                if has_user_id:
                    cursor.execute('''
                        INSERT INTO search_records 
                        (search_time, platform, address, hotel_keyword, hotel_name, room_count, user_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (search_time, platform, address, hotel_keyword, hotel_name, room_count, user_id))
                else:
                    cursor.execute('''
                    INSERT INTO search_records 
                    (search_time, platform, address, hotel_keyword, hotel_name, room_count)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (search_time, platform, address, hotel_keyword, hotel_name, room_count))
                search_id = cursor.lastrowid

                for room in room_list:
                    cursor.execute('''
                        INSERT INTO room_data 
                        (search_id, room_name, price, remaining_rooms, remarks)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (search_id, room.get("房型名称", ""), 
                          room.get("价格", ""), 
                          room.get("剩余房间", ""), 
                          room.get("备注", "")))

            conn.commit()
            conn.close()
        
        # 同时保存到 hotel_data 表（用于数据查询页面）
        _save_to_hotel_data_table(search_data, platform, hotel_name, address, city, room_list, search_time, user_id)
        
        print(f"✓ 数据已保存到数据库（搜索ID: {search_id}，共 {room_count} 个房型）")
        return True
    except Exception as e:
        print(f"⚠️  数据库保存失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def save_hotel_data_to_database(hotel_data_list: list, user_id: Optional[int] = None) -> bool:
    """
    保存酒店数据到 hotel_data 表
    
    Args:
        hotel_data_list: 酒店数据列表，每个元素是一个字典，包含以下字段：
            - hotel_name: 酒店名称（必填）
            - platform: 平台名称（必填）
            - hotel_id: 平台酒店ID（可选）
            - hotel_url: 酒店URL（可选）
            - star_level: 星级（可选）
            - rating_score: 评分（可选）
            - review_count: 点评数量（可选）
            - min_price: 最低价格（可选）
            - booking_dynamic: 预订动态（可选）
            - address: 地址（可选）
            - region: 区域（可选）
            - opening_date: 开业时间（可选）
            - room_types: 房型信息，JSON格式或列表（可选）
            - phone: 联系电话（可选）
            - email: 邮箱（可选）
            - website: 官网（可选）
            - crawl_time: 爬取时间（可选，默认当前时间）
        user_id: 用户ID（可选）
    
    Returns:
        bool: 保存是否成功
    """
    if not hotel_data_list:
        return True
    
    try:
        init_database()
        config = load_config()
        db_type = config['db_type']
        
        if db_type == 'sqlite':
            import sqlite3
            conn = sqlite3.connect(config['sqlite']['db_file'])
            cursor = conn.cursor()
            
            for hotel in hotel_data_list:
                # 处理 room_types（如果是列表，转为JSON字符串）
                room_types = hotel.get('room_types')
                if isinstance(room_types, (list, dict)):
                    room_types = json.dumps(room_types, ensure_ascii=False)
                elif room_types is None:
                    room_types = None
                
                # 处理 crawl_time
                crawl_time = hotel.get('crawl_time')
                if not crawl_time:
                    crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(crawl_time, datetime):
                    crawl_time = crawl_time.strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    INSERT OR REPLACE INTO hotel_data 
                    (hotel_name, platform, hotel_id, hotel_url, star_level, rating_score, 
                     review_count, min_price, booking_dynamic, address, region, opening_date, 
                     room_types, phone, email, website, crawl_time, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    hotel.get('hotel_name', ''),
                    hotel.get('platform', ''),
                    hotel.get('hotel_id'),
                    hotel.get('hotel_url'),
                    hotel.get('star_level'),
                    hotel.get('rating_score'),
                    hotel.get('review_count'),
                    hotel.get('min_price'),
                    hotel.get('booking_dynamic'),
                    hotel.get('address'),
                    hotel.get('region'),
                    hotel.get('opening_date'),
                    room_types,
                    hotel.get('phone'),
                    hotel.get('email'),
                    hotel.get('website'),
                    crawl_time
                ))
            
            conn.commit()
            conn.close()
        
        elif db_type == 'mysql':
            import pymysql
            mysql_config = config['mysql']
            connect_kwargs = {
                'host': mysql_config['host'],
                'port': mysql_config['port'],
                'user': mysql_config['user'],
                'password': mysql_config['password'],
                'database': mysql_config['database'],
                'charset': mysql_config['charset'],
                'connect_timeout': mysql_config.get('connect_timeout', 10),
                'read_timeout': mysql_config.get('read_timeout', 30),
                'write_timeout': mysql_config.get('write_timeout', 30),
            }
            
            if mysql_config.get('ssl', {}).get('enabled', False):
                ssl_config = mysql_config['ssl']
                connect_kwargs['ssl'] = {
                    'ca': ssl_config.get('ca'),
                    'cert': ssl_config.get('cert'),
                    'key': ssl_config.get('key'),
                }
                connect_kwargs['ssl'] = {k: v for k, v in connect_kwargs['ssl'].items() if v}
            elif mysql_config.get('ssl_disabled', False):
                connect_kwargs['ssl'] = {'check_hostname': False}
            
            conn = pymysql.connect(**connect_kwargs)
            cursor = conn.cursor()
            
            for hotel in hotel_data_list:
                # 处理 room_types（如果是列表或字典，转为JSON字符串）
                room_types = hotel.get('room_types')
                if isinstance(room_types, (list, dict)):
                    room_types = json.dumps(room_types, ensure_ascii=False)
                elif room_types is None:
                    room_types = None
                
                # 处理 crawl_time
                crawl_time = hotel.get('crawl_time')
                if not crawl_time:
                    crawl_time = datetime.now()
                elif isinstance(crawl_time, str):
                    try:
                        crawl_time = datetime.strptime(crawl_time, "%Y-%m-%d %H:%M:%S")
                    except:
                        crawl_time = datetime.now()
                
                cursor.execute('''
                    INSERT INTO hotel_data 
                    (hotel_name, platform, hotel_id, hotel_url, star_level, rating_score, 
                     review_count, min_price, booking_dynamic, address, region, opening_date, 
                     room_types, phone, email, website, crawl_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    hotel_url = VALUES(hotel_url),
                    star_level = VALUES(star_level),
                    rating_score = VALUES(rating_score),
                    review_count = VALUES(review_count),
                    min_price = VALUES(min_price),
                    booking_dynamic = VALUES(booking_dynamic),
                    address = VALUES(address),
                    region = VALUES(region),
                    opening_date = VALUES(opening_date),
                    room_types = VALUES(room_types),
                    phone = VALUES(phone),
                    email = VALUES(email),
                    website = VALUES(website),
                    crawl_time = VALUES(crawl_time),
                    updated_at = CURRENT_TIMESTAMP
                ''', (
                    hotel.get('hotel_name', ''),
                    hotel.get('platform', ''),
                    hotel.get('hotel_id'),
                    hotel.get('hotel_url'),
                    hotel.get('star_level'),
                    hotel.get('rating_score'),
                    hotel.get('review_count'),
                    hotel.get('min_price'),
                    hotel.get('booking_dynamic'),
                    hotel.get('address'),
                    hotel.get('region'),
                    hotel.get('opening_date'),
                    room_types,
                    hotel.get('phone'),
                    hotel.get('email'),
                    hotel.get('website'),
                    crawl_time
                ))
            
            conn.commit()
            conn.close()
        
        print(f"✓ 已保存 {len(hotel_data_list)} 条酒店数据到 hotel_data 表")
        return True
    except Exception as e:
        print(f"⚠️  保存酒店数据失败: {e}")
        import traceback
        traceback.print_exc()
        return False


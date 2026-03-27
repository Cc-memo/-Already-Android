import os
import json
import sqlite3
from typing import Tuple, Any, List, Optional
from flask import g

# 配置文件路径复用 database/db_utils.py 的逻辑
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_ROOT, "database", "db_config.json")
SQLITE_DB_DIR = os.path.join(PROJECT_ROOT, "database")

# 确保 SQLite 目录存在
os.makedirs(SQLITE_DB_DIR, exist_ok=True)

class DBManager:
    def __init__(self):
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """加载配置，优先读取 db_config.json，其次环境变量，默认 sqlite"""
        db_type = os.getenv('DB_TYPE', 'sqlite')
        config = {
            'db_type': db_type,
            'mysql': {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': int(os.getenv('DB_PORT', 3306)),
                'user': os.getenv('DB_USER', 'root'),
                'password': os.getenv('DB_PASSWORD', ''),
                'database': os.getenv('DB_NAME', 'hotel_admin'), # 默认库名不同以免冲突
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
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    config['db_type'] = file_config.get('db_type', config['db_type'])
                    if 'mysql' in file_config:
                        config['mysql'].update(file_config['mysql'])
            except Exception as e:
                print(f"配置文件读取失败: {e}")
        return config

    def get_connection(self, sqlite_name: str = "default.sqlite3"):
        """
        获取数据库连接
        :param sqlite_name: 如果是 SQLite 模式，指定文件名（如 auth.sqlite3）
        """
        if self.config['db_type'] == 'mysql':
            import pymysql
            from pymysql.cursors import DictCursor
            cfg = self.config['mysql']
            # 云数据库连接参数
            connect_kwargs = {
                'host': cfg['host'],
                'port': cfg['port'],
                'user': cfg['user'],
                'password': cfg['password'],
                'database': cfg['database'],
                'charset': cfg['charset'],
                'cursorclass': DictCursor,
                'autocommit': True,
                'connect_timeout': cfg.get('connect_timeout', 10),
                'read_timeout': cfg.get('read_timeout', 30),
                'write_timeout': cfg.get('write_timeout', 30),
            }
            
            # SSL配置
            if cfg.get('ssl', {}).get('enabled', False):
                ssl_config = cfg['ssl']
                connect_kwargs['ssl'] = {
                    'ca': ssl_config.get('ca'),
                    'cert': ssl_config.get('cert'),
                    'key': ssl_config.get('key'),
                }
                connect_kwargs['ssl'] = {k: v for k, v in connect_kwargs['ssl'].items() if v}
            elif cfg.get('ssl_disabled', False):
                connect_kwargs['ssl'] = {'check_hostname': False}
            
            conn = pymysql.connect(**connect_kwargs)
            return conn
        else:
            # SQLite 模式
            db_path = os.path.join(SQLITE_DB_DIR, sqlite_name)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row  # 类似 DictCursor
            return conn

    def execute(self, sql: str, args: tuple = (), sqlite_name: str = "default.sqlite3") -> Any:
        """
        执行 SQL，自动处理占位符差异
        SQLite 使用 ?占位符
        MySQL 使用 %s 占位符
        """
        conn = self.get_connection(sqlite_name)
        
        # 转换占位符
        if self.config['db_type'] == 'mysql':
            sql = sql.replace('?', '%s')
            
        try:
            cursor = conn.cursor()
            cursor.execute(sql, args)
            if sql.strip().upper().startswith("SELECT"):
                return cursor.fetchall()
            else:
                if self.config['db_type'] == 'sqlite':
                    conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    def query_one(self, sql: str, args: tuple = (), sqlite_name: str = "default.sqlite3") -> Optional[dict]:
        conn = self.get_connection(sqlite_name)
        if self.config['db_type'] == 'mysql':
            sql = sql.replace('?', '%s')
        try:
            cursor = conn.cursor()
            cursor.execute(sql, args)
            row = cursor.fetchone()
            if not row:
                return None
            # 确保返回字典类型
            if isinstance(row, dict):
                return row
            elif hasattr(row, 'keys'):
                return dict(row)
            else:
                # 如果是元组或其他类型，尝试转换为字典
                if hasattr(cursor, 'description') and cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, row))
                return None
        finally:
            conn.close()

    def query_all(self, sql: str, args: tuple = (), sqlite_name: str = "default.sqlite3") -> List[dict]:
        """
        查询多条记录，返回字典列表
        """
        conn = self.get_connection(sqlite_name)
        if self.config['db_type'] == 'mysql':
            sql = sql.replace('?', '%s')
        try:
            cursor = conn.cursor()
            cursor.execute(sql, args)
            rows = cursor.fetchall()
            if not rows:
                return []
            
            result = []
            for row in rows:
                # 确保返回字典类型
                if isinstance(row, dict):
                    result.append(row)
                elif hasattr(row, 'keys'):
                    result.append(dict(row))
                else:
                    # 如果是元组或其他类型，尝试转换为字典
                    if hasattr(cursor, 'description') and cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        result.append(dict(zip(columns, row)))
            return result
        finally:
            conn.close()

db = DBManager()

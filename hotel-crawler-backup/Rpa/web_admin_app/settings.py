"""
系统设置管理模块
提供系统设置的获取和更新接口（仅管理员）
"""
import os
from typing import Dict, Optional

from flask import Blueprint, jsonify, request

from .auth import ROLE_ADMIN, ROLE_SUPER_ADMIN, current_user
from .constants import DATABASE_DIR
from .db import db

bp = Blueprint("settings", __name__, url_prefix="/api/settings")

SETTINGS_DB = os.path.join(DATABASE_DIR, "settings.sqlite3")

# 默认设置值
DEFAULT_SETTINGS = {
    "crawl_interval": 5,  # 爬取间隔（秒）
    "request_timeout": 30,  # 请求超时时间（秒）
    "max_retries": 3,  # 最大重试次数
    "concurrent_crawl": 3,  # 并发爬取数量
    "enable_proxy": False,  # 是否启用代理
    "data_retention_days": 365,  # 数据保留时间（天）
    "log_retention_days": 90,  # 日志保留周期（天）
}


def init_settings_db():
    """初始化系统设置数据库表"""
    os.makedirs(DATABASE_DIR, exist_ok=True)
    
    # SQLite 建表
    sql_sqlite = """
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT NOT NULL UNIQUE,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by INTEGER
        )
    """
    
    # MySQL 建表
    sql_mysql = """
        CREATE TABLE IF NOT EXISTS system_settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            setting_key VARCHAR(100) NOT NULL UNIQUE,
            setting_value TEXT NOT NULL,
            updated_at VARCHAR(30) NOT NULL,
            updated_by INT,
            INDEX idx_setting_key (setting_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    
    conn = db.get_connection("settings.sqlite3")
    try:
        cursor = conn.cursor()
        if db.config['db_type'] == 'mysql':
            cursor.execute(sql_mysql)
        else:
            cursor.execute(sql_sqlite)
        
        if db.config['db_type'] == 'sqlite':
            conn.commit()
        
        # 初始化默认设置（如果不存在）
        _init_default_settings(cursor, conn)
        
        if db.config['db_type'] == 'sqlite':
            conn.commit()
    finally:
        conn.close()


def _init_default_settings(cursor, conn):
    """初始化默认设置值"""
    from datetime import datetime
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_type = db.config['db_type']
    
    for key, value in DEFAULT_SETTINGS.items():
        # 检查设置是否已存在
        if db_type == 'mysql':
            cursor.execute("SELECT id FROM system_settings WHERE setting_key = %s", (key,))
        else:
            cursor.execute("SELECT id FROM system_settings WHERE setting_key = ?", (key,))
        
        if cursor.fetchone() is None:
            # 插入默认值
            value_str = str(value)
            if db_type == 'mysql':
                cursor.execute(
                    "INSERT INTO system_settings (setting_key, setting_value, updated_at) VALUES (%s, %s, %s)",
                    (key, value_str, now)
                )
            else:
                cursor.execute(
                    "INSERT INTO system_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                    (key, value_str, now)
                )
            
            if db_type == 'sqlite':
                conn.commit()


def _now_str() -> str:
    """获取当前时间字符串"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_all_settings() -> Dict:
    """获取所有系统设置"""
    rows = db.query_all("SELECT setting_key, setting_value FROM system_settings", sqlite_name="settings.sqlite3")
    
    settings = {}
    for row in rows:
        key = row['setting_key']
        value_str = row['setting_value']
        
        # 尝试转换数据类型
        if value_str.lower() in ('true', 'false'):
            settings[key] = value_str.lower() == 'true'
        elif value_str.isdigit():
            settings[key] = int(value_str)
        else:
            try:
                settings[key] = float(value_str)
            except ValueError:
                settings[key] = value_str
    
    # 确保所有默认设置都存在
    for key, default_value in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = default_value
    
    return settings


def get_setting(key: str, default=None):
    """
    获取单个系统设置值（供其他模块调用）
    
    Args:
        key: 设置项的键名
        default: 如果设置不存在，返回的默认值
    
    Returns:
        设置值，如果不存在则返回默认值
    """
    all_settings = get_all_settings()
    return all_settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))


def update_settings(settings: Dict, user_id: Optional[int] = None):
    """更新系统设置"""
    db_type = db.config['db_type']
    now = _now_str()
    
    conn = db.get_connection("settings.sqlite3")
    try:
        cursor = conn.cursor()
        
        for key, value in settings.items():
            # 只更新允许的设置项
            if key not in DEFAULT_SETTINGS:
                continue
            
            value_str = str(value)
            
            if db_type == 'mysql':
                # 使用 INSERT ... ON DUPLICATE KEY UPDATE
                cursor.execute(
                    """INSERT INTO system_settings (setting_key, setting_value, updated_at, updated_by)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                       setting_value = VALUES(setting_value),
                       updated_at = VALUES(updated_at),
                       updated_by = VALUES(updated_by)""",
                    (key, value_str, now, user_id)
                )
            else:
                # SQLite 使用 INSERT OR REPLACE
                cursor.execute(
                    """INSERT OR REPLACE INTO system_settings (setting_key, setting_value, updated_at, updated_by)
                       VALUES (?, ?, ?, ?)""",
                    (key, value_str, now, user_id)
                )
        
        if db_type == 'sqlite':
            conn.commit()
    finally:
        conn.close()


@bp.get("")
def get_settings():
    """获取系统设置（仅管理员）"""
    try:
        # 检查管理员权限
        user = current_user()
        if not user:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        user_role = user.get("role")
        if user_role not in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            return jsonify({"success": False, "error": "需要管理员权限"}), 403
        
        settings = get_all_settings()
        return jsonify({"success": True, "data": settings})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.put("")
def update_settings_api():
    """更新系统设置（仅管理员）"""
    try:
        # 检查管理员权限
        user = current_user()
        if not user:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        user_role = user.get("role")
        if user_role not in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            return jsonify({"success": False, "error": "需要管理员权限"}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据为空"}), 400
        
        # 验证设置值
        validated_settings = {}
        for key, value in data.items():
            if key not in DEFAULT_SETTINGS:
                continue  # 忽略未知的设置项
            
            # 类型验证和转换
            default_value = DEFAULT_SETTINGS[key]
            if isinstance(default_value, bool):
                validated_settings[key] = bool(value)
            elif isinstance(default_value, int):
                try:
                    validated_settings[key] = int(value)
                except (ValueError, TypeError):
                    return jsonify({"success": False, "error": f"设置项 {key} 的值必须是整数"}), 400
            else:
                validated_settings[key] = value
        
        # 更新设置
        user_id = user.get("id")
        update_settings(validated_settings, user_id)
        
        return jsonify({"success": True, "message": "设置已保存"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/cleanup")
def cleanup_data():
    """清理过期数据和日志（仅管理员）"""
    try:
        # 检查管理员权限
        user = current_user()
        if not user:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        user_role = user.get("role")
        if user_role not in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            return jsonify({"success": False, "error": "需要管理员权限"}), 403
        
        from datetime import datetime, timedelta
        
        # 获取保留时间设置
        data_retention_days = get_setting("data_retention_days", 365)
        log_retention_days = get_setting("log_retention_days", 90)
        
        # 计算过期时间
        data_expire_date = (datetime.now() - timedelta(days=data_retention_days)).strftime("%Y-%m-%d %H:%M:%S")
        log_expire_date = (datetime.now() - timedelta(days=log_retention_days)).strftime("%Y-%m-%d %H:%M:%S")
        
        deleted_counts = {
            "search_records": 0,
            "room_data": 0,
            "crawl_tasks": 0,
            "hotel_data": 0
        }
        
        db_type = db.config['db_type']
        
        # 清理 search_records 和关联的 room_data
        try:
            if db_type == 'mysql':
                # MySQL: 先删除关联的 room_data
                conn = db.get_connection("default.sqlite3")
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE rd FROM room_data rd
                    INNER JOIN search_records sr ON rd.search_id = sr.id
                    WHERE sr.search_time < %s
                """, (data_expire_date,))
                deleted_counts["room_data"] = cursor.rowcount
                
                # 删除过期的 search_records
                cursor.execute("""
                    DELETE FROM search_records WHERE search_time < %s
                """, (data_expire_date,))
                deleted_counts["search_records"] = cursor.rowcount
                conn.close()
            else:
                # SQLite: 先获取要删除的 search_records ID
                conn = db.get_connection("default.sqlite3")
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM search_records WHERE search_time < ?", (data_expire_date,))
                ids_to_delete = [row[0] for row in cursor.fetchall()]
                
                if ids_to_delete:
                    placeholders = ','.join(['?'] * len(ids_to_delete))
                    # 删除关联的 room_data
                    cursor.execute(f"DELETE FROM room_data WHERE search_id IN ({placeholders})", ids_to_delete)
                    deleted_counts["room_data"] = cursor.rowcount
                    
                    # 删除 search_records
                    cursor.execute(f"DELETE FROM search_records WHERE id IN ({placeholders})", ids_to_delete)
                    deleted_counts["search_records"] = cursor.rowcount
                
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"清理 search_records 和 room_data 时出错: {e}")
        
        # 清理过期的爬取任务
        try:
            if db_type == 'mysql':
                conn = db.get_connection("crawl_tasks.sqlite3")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM crawl_tasks WHERE created_at < %s", (data_expire_date,))
                deleted_counts["crawl_tasks"] = cursor.rowcount
                conn.close()
            else:
                conn = db.get_connection("crawl_tasks.sqlite3")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM crawl_tasks WHERE created_at < ?", (data_expire_date,))
                deleted_counts["crawl_tasks"] = cursor.rowcount
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"清理 crawl_tasks 时出错: {e}")
        
        # 清理过期的酒店数据（hotel_data 表，基于 crawl_time）
        try:
            if db_type == 'mysql':
                conn = db.get_connection("default.sqlite3")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM hotel_data WHERE crawl_time < %s", (data_expire_date,))
                deleted_counts["hotel_data"] = cursor.rowcount
                conn.close()
            else:
                conn = db.get_connection("default.sqlite3")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM hotel_data WHERE crawl_time < ?", (data_expire_date,))
                deleted_counts["hotel_data"] = cursor.rowcount
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"清理 hotel_data 时出错: {e}")
        
        total_deleted = sum(deleted_counts.values())
        
        return jsonify({
            "success": True,
            "message": f"清理完成，共删除 {total_deleted} 条记录",
            "data": {
                "deleted_counts": deleted_counts,
                "data_retention_days": data_retention_days,
                "log_retention_days": log_retention_days
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

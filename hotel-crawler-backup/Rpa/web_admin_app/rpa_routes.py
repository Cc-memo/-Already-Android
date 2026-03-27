import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, jsonify, request, send_file

from .constants import MEITUAN_DATA_FILE, ORDERS_FILE, PRICE_COMPARISON_REPORT, XIECHENG_DATA_FILE
from database.db_utils import load_config
from orders.order_processor import OrderStatus, OrderStorage

try:
    import pymysql

    PYMYSQL_AVAILABLE = True
except ImportError:
    pymysql = None  # type: ignore
    PYMYSQL_AVAILABLE = False


bp = Blueprint("rpa", __name__)


def get_db_connection():
    config = load_config()
    db_type = config["db_type"]

    if db_type == "sqlite":
        db_file = config["sqlite"]["db_file"]
        return sqlite3.connect(db_file)
    if db_type == "mysql":
        if not PYMYSQL_AVAILABLE:
            return None
        mysql_config = config["mysql"]
        # 注意：pymysql 默认 autocommit=False，但某些情况下可能需要显式设置
        conn = pymysql.connect(
            host=mysql_config["host"],
            port=mysql_config["port"],
            user=mysql_config["user"],
            password=mysql_config["password"],
            database=mysql_config["database"],
            charset=mysql_config["charset"],
            autocommit=False,  # 关闭自动提交，需要手动 commit
        )
        return conn
    return None


def query_search_records(limit=100, platform=None, start_date=None, end_date=None, user_id=None):
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        conditions = []
        params = []

        is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
        # 添加用户ID过滤（账户隔离）
        if user_id is not None:
            # 检查user_id字段是否存在
            try:
                if is_mysql:
                    cursor.execute("SHOW COLUMNS FROM search_records LIKE 'user_id'")
                    has_user_id = cursor.fetchone() is not None
                else:
                    cursor.execute("PRAGMA table_info(search_records)")
                    cols = cursor.fetchall()
                    has_user_id = any(col[1] == 'user_id' for col in cols)
            except Exception:
                has_user_id = False
            
            if has_user_id:
                conditions.append("user_id = %s" if is_mysql else "user_id = ?")
                params.append(user_id)
        if platform:
            conditions.append("platform = %s" if is_mysql else "platform = ?")
            params.append(platform)
        if start_date:
            conditions.append("search_time >= %s" if is_mysql else "search_time >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("search_time <= %s" if is_mysql else "search_time <= ?")
            params.append(end_date)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        # 兼容云库/旧库字段差异：room_count vs total_room_count
        room_count_col = None
        try:
            if is_mysql:
                cursor.execute("SHOW COLUMNS FROM search_records")
                sr_cols = {r[0] for r in cursor.fetchall()}
            else:
                cursor.execute("PRAGMA table_info(search_records)")
                sr_cols = {r[1] for r in cursor.fetchall()}
            if "total_room_count" in sr_cols:
                room_count_col = "total_room_count"
            elif "room_count" in sr_cols:
                room_count_col = "room_count"
        except Exception:
            sr_cols = set()

        room_count_select = f"{room_count_col} AS room_count" if room_count_col else "0 AS room_count"

        query = f"""
            SELECT id, search_time, platform, address, hotel_keyword, hotel_name, {room_count_select}, created_at
            FROM search_records
            {where_clause}
            ORDER BY created_at DESC
            LIMIT {limit}
        """
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def query_room_data(search_id):
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
        # 兼容云库/旧库字段差异：
        # - 外键：search_id vs search_record_id
        # - 价格：price vs price_str
        try:
            if is_mysql:
                cursor.execute("SHOW COLUMNS FROM room_data")
                rd_cols = {r[0] for r in cursor.fetchall()}
            else:
                cursor.execute("PRAGMA table_info(room_data)")
                rd_cols = {r[1] for r in cursor.fetchall()}
        except Exception:
            rd_cols = set()

        fk_col = "search_record_id" if "search_record_id" in rd_cols else "search_id"
        price_col = "price_str" if "price_str" in rd_cols else "price"

        query = (
            f"""
            SELECT id, room_name, {price_col} AS price, remaining_rooms, remarks, created_at
            FROM room_data
            WHERE {fk_col} = %s
            ORDER BY id
        """
            if is_mysql
            else f"""
            SELECT id, room_name, {price_col} AS price, remaining_rooms, remarks, created_at
            FROM room_data
            WHERE {fk_col} = ?
            ORDER BY id
        """
        )
        cursor.execute(query, (search_id,))
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def query_hotel_data(
    hotel_name=None,
    platform=None,
    region=None,
    star_level=None,
    min_rating=None,
    max_rating=None,
    min_price=None,
    max_price=None,
    start_date=None,
    end_date=None,
    page=1,
    per_page=10,
    order_by="crawl_time",
    order_desc=True
):
    """
    查询 hotel_data 表数据
    
    Args:
        hotel_name: 酒店名称（模糊搜索）
        platform: 平台名称
        region: 区域
        star_level: 星级
        min_rating: 最低评分
        max_rating: 最高评分
        min_price: 最低价格
        max_price: 最高价格
        start_date: 开始时间
        end_date: 结束时间
        page: 页码（从1开始）
        per_page: 每页数量
        order_by: 排序字段
        order_desc: 是否降序
    
    Returns:
        tuple: (数据列表, 总记录数)
    """
    conn = get_db_connection()
    if not conn:
        return [], 0

    try:
        cursor = conn.cursor()
        is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
        
        conditions = []
        params = []
        
        # 构建查询条件
        if hotel_name:
            conditions.append("hotel_name LIKE %s" if is_mysql else "hotel_name LIKE ?")
            params.append(f"%{hotel_name}%")
        
        if platform:
            conditions.append("platform = %s" if is_mysql else "platform = ?")
            params.append(platform)
        
        if region:
            conditions.append("region = %s" if is_mysql else "region = ?")
            params.append(region)
        
        if star_level:
            conditions.append("star_level = %s" if is_mysql else "star_level = ?")
            params.append(star_level)
        
        if min_rating is not None:
            conditions.append("rating_score >= %s" if is_mysql else "rating_score >= ?")
            params.append(min_rating)
        
        if max_rating is not None:
            conditions.append("rating_score <= %s" if is_mysql else "rating_score <= ?")
            params.append(max_rating)
        
        if min_price is not None:
            conditions.append("min_price >= %s" if is_mysql else "min_price >= ?")
            params.append(min_price)
        
        if max_price is not None:
            conditions.append("min_price <= %s" if is_mysql else "min_price <= ?")
            params.append(max_price)
        
        if start_date:
            conditions.append("crawl_time >= %s" if is_mysql else "crawl_time >= ?")
            params.append(start_date)
        
        if end_date:
            conditions.append("crawl_time <= %s" if is_mysql else "crawl_time <= ?")
            params.append(end_date)
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # 验证排序字段
        valid_order_fields = ["id", "hotel_name", "platform", "rating_score", "review_count", 
                             "min_price", "crawl_time", "created_at"]
        if order_by not in valid_order_fields:
            order_by = "crawl_time"
        
        order_direction = "DESC" if order_desc else "ASC"
        
        # 先查询总数
        count_query = f"SELECT COUNT(*) FROM hotel_data {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        # 查询数据（分页）
        offset = (page - 1) * per_page
        # MySQL 使用 LIMIT offset, count 格式，SQLite 使用 LIMIT count OFFSET offset
        if is_mysql:
            limit_clause = f"LIMIT {offset}, {per_page}"
        else:
            limit_clause = f"LIMIT {per_page} OFFSET {offset}"
        
        data_query = f"""
            SELECT id, hotel_name, platform, hotel_id, hotel_url, star_level, rating_score, 
                   review_count, min_price, booking_dynamic, address, region, opening_date, 
                   room_types, phone, email, website, crawl_time, created_at, updated_at
            FROM hotel_data
            {where_clause}
            ORDER BY {order_by} {order_direction}
            {limit_clause}
        """
        
        cursor.execute(data_query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        # 处理 room_types（如果是 JSON 字符串，解析为对象）
        result = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            # 处理 room_types
            if row_dict.get('room_types'):
                try:
                    if isinstance(row_dict['room_types'], str):
                        row_dict['room_types'] = json.loads(row_dict['room_types'])
                except:
                    pass
            result.append(row_dict)
        
        return result, total
    except Exception as e:
        import traceback
        traceback.print_exc()
        return [], 0
    finally:
        conn.close()


@bp.get("/api/orders")
def get_orders():
    try:
        storage = OrderStorage(ORDERS_FILE)
        orders = storage.get_all_orders()
        status_filter = request.args.get("status")
        if status_filter:
            orders = [o for o in orders if o.status.value == status_filter]
        orders_data = [order.to_dict() for order in orders]
        return jsonify({"success": True, "data": orders_data, "total": len(orders_data)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/orders/<order_id>")
def get_order(order_id):
    try:
        storage = OrderStorage(ORDERS_FILE)
        order = storage.get_order(order_id)
        if not order:
            return jsonify({"success": False, "error": "订单不存在"}), 404
        return jsonify({"success": True, "data": order.to_dict()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.put("/api/orders/<order_id>")
def update_order(order_id):
    try:
        storage = OrderStorage(ORDERS_FILE)
        order = storage.get_order(order_id)
        if not order:
            return jsonify({"success": False, "error": "订单不存在"}), 404

        data = request.get_json(force=True) or {}
        if "status" in data:
            for status in OrderStatus:
                if status.value == data["status"]:
                    order.status = status
                    break
        if "remark" in data:
            order.remark = data["remark"]
        if "target_order_id" in data:
            order.target_order_id = data["target_order_id"]

        storage.update_order(order)
        return jsonify({"success": True, "data": order.to_dict()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/search-records")
def get_search_records():
    try:
        from .auth import current_user
        
        # 获取当前登录用户ID
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])
        
        limit = int(request.args.get("limit", 100))
        platform = request.args.get("platform")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        records = query_search_records(limit=limit, platform=platform, start_date=start_date, end_date=end_date, user_id=user_id)
        return jsonify({"success": True, "data": records, "total": len(records)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/search-records/<int:search_id>/rooms")
def get_room_data(search_id: int):
    try:
        rooms = query_room_data(search_id)
        return jsonify({"success": True, "data": rooms, "total": len(rooms)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/statistics")
def get_statistics():
    try:
        storage = OrderStorage(ORDERS_FILE)
        orders = storage.get_all_orders()

        total_orders = len(orders)
        status_count = {}
        for order in orders:
            status = order.status.value
            status_count[status] = status_count.get(status, 0) + 1

        total_profit = sum([o.profit for o in orders if o.profit > 0])
        total_source_price = sum([o.source_price for o in orders if o.source_price > 0])
        total_target_price = sum([o.target_price for o in orders if o.target_price > 0])

        platform_count = {}
        for order in orders:
            if order.target_platform:
                platform = order.target_platform.value
                platform_count[platform] = platform_count.get(platform, 0) + 1

        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        recent_orders = [o for o in orders if o.created_at >= seven_days_ago]

        return jsonify(
            {
                "success": True,
                "data": {
                    "total_orders": total_orders,
                    "status_count": status_count,
                    "total_profit": total_profit,
                    "total_source_price": total_source_price,
                    "total_target_price": total_target_price,
                    "platform_count": platform_count,
                    "recent_orders_count": len(recent_orders),
                },
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/price-comparison")
def get_price_comparison():
    try:
        if os.path.exists(PRICE_COMPARISON_REPORT):
            with open(PRICE_COMPARISON_REPORT, "r", encoding="utf-8") as f:
                content = f.read()
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "content": content,
                        "updated_at": datetime.fromtimestamp(os.path.getmtime(PRICE_COMPARISON_REPORT)).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    },
                }
            )
        return jsonify({"success": True, "data": {"content": "暂无比价报告", "updated_at": None}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/hotel-data")
def get_hotel_data():
    """获取酒店数据（从JSON文件，保留向后兼容）"""
    try:
        platform = request.args.get("platform", "all")
        data = {}

        if platform in ["all", "meituan"] and os.path.exists(MEITUAN_DATA_FILE):
            with open(MEITUAN_DATA_FILE, "r", encoding="utf-8") as f:
                data["meituan"] = json.load(f)

        if platform in ["all", "xiecheng"] and os.path.exists(XIECHENG_DATA_FILE):
            with open(XIECHENG_DATA_FILE, "r", encoding="utf-8") as f:
                data["xiecheng"] = json.load(f)

        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/hotels")
def get_hotels():
    """查询酒店数据（从 hotel_data 表，支持多条件筛选和分页）"""
    try:
        print(f"🔍 [API] GET /api/hotels - 查询参数: {dict(request.args)}")
        
        # 获取查询参数
        hotel_name = request.args.get("hotel_name")
        platform = request.args.get("platform")
        region = request.args.get("region")
        star_level = request.args.get("star_level")
        
        # 评分范围
        min_rating = request.args.get("min_rating")
        max_rating = request.args.get("max_rating")
        min_rating = float(min_rating) if min_rating else None
        max_rating = float(max_rating) if max_rating else None
        
        # 价格范围
        min_price = request.args.get("min_price")
        max_price = request.args.get("max_price")
        min_price = float(min_price) if min_price else None
        max_price = float(max_price) if max_price else None
        
        # 时间范围
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        
        # 分页参数
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        
        # 排序参数
        order_by = request.args.get("order_by", "crawl_time")
        order_desc = request.args.get("order_desc", "true").lower() == "true"
        
        # 查询数据
        data, total = query_hotel_data(
            hotel_name=hotel_name,
            platform=platform,
            region=region,
            star_level=star_level,
            min_rating=min_rating,
            max_rating=max_rating,
            min_price=min_price,
            max_price=max_price,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=per_page,
            order_by=order_by,
            order_desc=order_desc
        )
        
        print(f"✅ [API] GET /api/hotels - 返回 {len(data)} 条数据，总计 {total} 条")
        
        # 计算总页数
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        
        return jsonify({
            "success": True,
            "data": data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/hotels/<int:hotel_id>")
def get_hotel_detail(hotel_id: int):
    """获取酒店详情"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "数据库连接失败"}), 500
    
    try:
        cursor = conn.cursor()
        is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
        
        query = (
            "SELECT * FROM hotel_data WHERE id = %s"
            if is_mysql
            else "SELECT * FROM hotel_data WHERE id = ?"
        )
        cursor.execute(query, (hotel_id,))
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        
        if not row:
            return jsonify({"success": False, "error": "酒店不存在"}), 404
        
        hotel = dict(zip(columns, row))
        
        # 处理 room_types
        if hotel.get('room_types'):
            try:
                if isinstance(hotel['room_types'], str):
                    hotel['room_types'] = json.loads(hotel['room_types'])
            except:
                pass
        
        return jsonify({"success": True, "data": hotel})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@bp.get("/api/hotels/debug")
def debug_hotels():
    """调试接口：查看数据库中的实际数据"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "数据库连接失败"}), 500
    
    try:
        cursor = conn.cursor()
        is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
        
        # 查询所有平台的数据统计
        stats_query = "SELECT platform, COUNT(*) as count FROM hotel_data GROUP BY platform"
        cursor.execute(stats_query)
        stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 查询最近10条数据（包含region字段）
        recent_query = "SELECT id, hotel_name, platform, region, crawl_time FROM hotel_data ORDER BY crawl_time DESC LIMIT 10"
        cursor.execute(recent_query)
        columns = [desc[0] for desc in cursor.description]
        recent = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # 查询所有不同的region值
        region_query = "SELECT DISTINCT region, COUNT(*) as count FROM hotel_data WHERE region IS NOT NULL AND region != '' GROUP BY region ORDER BY count DESC"
        cursor.execute(region_query)
        region_stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 查询region为NULL或空的数量
        null_region_query = "SELECT COUNT(*) FROM hotel_data WHERE region IS NULL OR region = ''"
        cursor.execute(null_region_query)
        null_region_count = cursor.fetchone()[0]
        
        return jsonify({
            "success": True,
            "data": {
                "platform_stats": stats,
                "recent_data": recent,
                "region_stats": region_stats,  # 所有不同的region值
                "null_region_count": null_region_count,  # region为空的数量
                "total": sum(stats.values())
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@bp.get("/api/hotels/analysis")
def get_hotels_analysis():
    """获取酒店数据分析（统计数据和分析图表数据）
    平均价格计算：从 room_types JSON字段中提取所有符合筛选条件的房间价格，计算平均值
    """
    import re
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "数据库连接失败"}), 500
    
    try:
        cursor = conn.cursor()
        is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
        
        # 获取筛选条件
        region = request.args.get("region")
        star_level = request.args.get("star_level")
        room_type = request.args.get("room_type")  # 房间类型筛选
        platform = request.args.get("platform")
        
        # 区域名称映射（英文转中文）
        region_map = {
            'beijing': '北京',
            'shanghai': '上海',
            'guangzhou': '广州',
            'shenzhen': '深圳',
            'hangzhou': '杭州',
            'chengdu': '成都',
            'nanjing': '南京',
            'wuhan': '武汉',
            'xian': '西安',
            'suzhou': '苏州',
        }
        
        # 构建基础查询条件
        conditions = []
        params = []
        
        if region:
            # 转换区域名称（英文转中文）
            region_cn = region_map.get(region, region)
            # 使用LIKE查询，支持"城市-区县"格式（如"北京-朝阳区"）
            # 同时匹配region字段和hotel_name/address字段（当region为null时）
            region_condition = "(region LIKE %s OR (region IS NULL AND (hotel_name LIKE %s OR address LIKE %s)))" if is_mysql else "(region LIKE ? OR (region IS NULL AND (hotel_name LIKE ? OR address LIKE ?)))"
            conditions.append(region_condition)
            region_pattern = f"{region_cn}%"
            name_pattern = f"%{region_cn}%"
            params.append(region_pattern)  # region LIKE
            params.append(name_pattern)    # hotel_name LIKE
            params.append(name_pattern)    # address LIKE
        
        if star_level:
            conditions.append("star_level LIKE %s" if is_mysql else "star_level LIKE ?")
            params.append(f"%{star_level}%")
        
        if platform:
            # 转换平台名称（英文转中文）
            platform_map = {
                'meituan': '美团',
                'ctrip': '携程',
                'fliggy': '飞猪',
                'gaode': '高德',
            }
            platform_cn = platform_map.get(platform, platform)
            conditions.append("platform = %s" if is_mysql else "platform = ?")
            params.append(platform_cn)
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # 添加调试信息
        print(f"🔍 [分析API] 筛选条件: region={region}, star_level={star_level}, platform={platform}, room_type={room_type}")
        print(f"🔍 [分析API] WHERE子句: {where_clause}")
        print(f"🔍 [分析API] 查询参数: {params}")
        
        # 查询符合条件的酒店记录（包含 room_types 和 address 字段）
        hotels_query = f"""
            SELECT 
                id,
                hotel_name,
                platform,
                region,
                address,
                star_level,
                rating_score,
                review_count,
                room_types,
                crawl_time
            FROM hotel_data
            {where_clause}
        """
        cursor.execute(hotels_query, params)
        columns = [desc[0] for desc in cursor.description]
        hotels = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # 调试：查看匹配到的酒店和region值
        print(f"🔍 [分析API] 匹配到 {len(hotels)} 个酒店")
        if hotels:
            unique_regions = set(h.get('region') for h in hotels if h.get('region'))
            print(f"🔍 [分析API] 匹配到的region值: {unique_regions}")
            # 显示前3个酒店的详细信息
            for i, h in enumerate(hotels[:3]):
                print(f"🔍 [分析API] 酒店{i+1}: name={h.get('hotel_name')}, region={h.get('region')}, platform={h.get('platform')}")
        
        # 从 room_types JSON字段中提取所有房间价格
        all_room_prices = []  # 存储所有房间的价格信息
        hotel_count = len(hotels)
        total_reviews = 0
        total_rating = 0
        rating_count = 0
        
        for hotel in hotels:
            # 累计点评数
            if hotel.get('review_count'):
                total_reviews += int(hotel['review_count'])
            
            # 累计评分（用于计算平均值）
            if hotel.get('rating_score'):
                total_rating += float(hotel['rating_score'])
                rating_count += 1
            
            # 解析 room_types JSON字段
            room_types = hotel.get('room_types')
            if room_types:
                try:
                    # 如果是字符串，先解析为JSON
                    if isinstance(room_types, str):
                        room_types = json.loads(room_types)
                    
                    # 如果是列表，遍历每个房间
                    if isinstance(room_types, list):
                        for room in room_types:
                            # 房间类型筛选
                            if room_type:
                                room_name = room.get("房型名称", "") or room.get("room_name", "") or ""
                                # 简单的关键词匹配
                                if room_type.lower() not in room_name.lower():
                                    continue
                            
                            # 提取价格
                            price_str = room.get("价格", "") or room.get("price", "") or ""
                            if price_str:
                                try:
                                    # 从价格字符串中提取数字（如 "¥388" -> 388）
                                    price_match = re.search(r"[\d.]+", str(price_str).replace(",", ""))
                                    if price_match:
                                        price = float(price_match.group())
                                        all_room_prices.append({
                                            'price': price,
                                            'platform': hotel.get('platform'),
                                            'region': hotel.get('region'),
                                            'star_level': hotel.get('star_level'),
                                            'crawl_time': hotel.get('crawl_time')
                                        })
                                except:
                                    pass
                except Exception as e:
                    print(f"⚠️  解析 room_types 失败 (hotel_id={hotel.get('id')}): {e}")
        
        # 调试：显示提取到的房间价格数量
        print(f"🔍 [分析API] 提取到 {len(all_room_prices)} 个房间价格")
        if all_room_prices:
            price_range = (min(r['price'] for r in all_room_prices), max(r['price'] for r in all_room_prices))
            print(f"🔍 [分析API] 价格范围: {price_range[0]} - {price_range[1]}")
        
        # 计算平均价格（所有符合筛选条件的房间价格的平均值）
        avg_price = 0
        if all_room_prices:
            avg_price = sum(r['price'] for r in all_room_prices) / len(all_room_prices)
        
        # 计算平均评分
        avg_rating = total_rating / rating_count if rating_count > 0 else 0
        
        stats = {
            "hotel_count": hotel_count,
            "avg_price": round(avg_price, 2),
            "avg_rating": round(avg_rating, 2),
            "total_reviews": total_reviews
        }
        
        # 2. 平台价格对比（从房间价格计算）
        platform_prices = {}
        if all_room_prices:
            platform_price_dict = {}
            platform_count_dict = {}
            for room in all_room_prices:
                p = room['platform']
                if p not in platform_price_dict:
                    platform_price_dict[p] = 0
                    platform_count_dict[p] = 0
                platform_price_dict[p] += room['price']
                platform_count_dict[p] += 1
            platform_prices = {
                p: round(platform_price_dict[p] / platform_count_dict[p], 2)
                for p in platform_price_dict
            }
        
        # 3. 平台评分对比
        platform_rating_query = f"""
            SELECT platform, AVG(rating_score) as avg_rating
            FROM hotel_data
            {where_clause}
            GROUP BY platform
        """
        cursor.execute(platform_rating_query, params)
        platform_ratings = {row[0]: round(float(row[1] or 0), 2) for row in cursor.fetchall()}
        
        # 4. 区域价格对比（从房间价格计算）
        region_prices = {}
        if all_room_prices:
            region_price_dict = {}
            region_count_dict = {}
            for room in all_room_prices:
                r = room.get('region')
                if r:
                    if r not in region_price_dict:
                        region_price_dict[r] = 0
                        region_count_dict[r] = 0
                    region_price_dict[r] += room['price']
                    region_count_dict[r] += 1
            region_prices = {
                r: round(region_price_dict[r] / region_count_dict[r], 2)
                for r in region_price_dict
            }
            # 按价格降序排序，取前10
            region_prices = dict(sorted(region_prices.items(), key=lambda x: x[1], reverse=True)[:10])
        
        # 5. 区域酒店数量
        region_condition = "region IS NOT NULL AND region != ''"
        region_where = f"{where_clause} AND {region_condition}" if where_clause else f"WHERE {region_condition}"
        region_count_query = f"""
            SELECT region, COUNT(*) as count
            FROM hotel_data
            {region_where}
            GROUP BY region
            ORDER BY count DESC
            LIMIT 10
        """
        cursor.execute(region_count_query, params)
        region_counts = {row[0]: int(row[1]) for row in cursor.fetchall()}
        
        # 6. 星级价格对比（从房间价格计算）
        star_prices = {}
        if all_room_prices:
            star_price_dict = {}
            star_count_dict = {}
            for room in all_room_prices:
                s = room.get('star_level')
                if s:
                    if s not in star_price_dict:
                        star_price_dict[s] = 0
                        star_count_dict[s] = 0
                    star_price_dict[s] += room['price']
                    star_count_dict[s] += 1
            star_prices = {
                s: round(star_price_dict[s] / star_count_dict[s], 2)
                for s in star_price_dict
            }
            # 按价格降序排序
            star_prices = dict(sorted(star_prices.items(), key=lambda x: x[1], reverse=True))
        
        # 7. 星级酒店数量
        star_condition = "star_level IS NOT NULL AND star_level != ''"
        star_where = f"{where_clause} AND {star_condition}" if where_clause else f"WHERE {star_condition}"
        star_count_query = f"""
            SELECT star_level, COUNT(*) as count
            FROM hotel_data
            {star_where}
            GROUP BY star_level
        """
        cursor.execute(star_count_query, params)
        star_counts = {row[0]: int(row[1]) for row in cursor.fetchall()}
        
        # 8. 价格趋势（按爬取时间分组，最近7天）
        price_trend = []
        if all_room_prices:
            # 按日期分组
            daily_prices = {}
            for room in all_room_prices:
                crawl_time = room.get('crawl_time')
                if crawl_time:
                    try:
                        if isinstance(crawl_time, str):
                            date_str = crawl_time.split()[0]  # "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DD"
                        else:
                            date_str = str(crawl_time).split()[0]
                        
                        if date_str not in daily_prices:
                            daily_prices[date_str] = []
                        daily_prices[date_str].append(room['price'])
                    except:
                        pass
            
            # 计算每天的平均价格
            for date_str in sorted(daily_prices.keys()):
                prices = daily_prices[date_str]
                if prices:
                    avg_price = sum(prices) / len(prices)
                    price_trend.append({"date": date_str, "price": round(avg_price, 2)})
        
        return jsonify({
            "success": True,
            "data": {
                "stats": stats,
                "platform_prices": platform_prices,
                "platform_ratings": platform_ratings,
                "region_prices": region_prices,
                "region_counts": region_counts,
                "star_prices": star_prices,
                "star_counts": star_counts,
                "price_trend": price_trend
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@bp.get("/api/config")
def get_config():
    try:
        config = load_config()
        safe_config = {
            "db_type": config.get("db_type", "sqlite"),
            "sqlite": {"db_file": config.get("sqlite", {}).get("db_file", "")},
            "mysql": {
                "host": config.get("mysql", {}).get("host", ""),
                "port": config.get("mysql", {}).get("port", 3306),
                "database": config.get("mysql", {}).get("database", ""),
            },
        }
        return jsonify({"success": True, "data": safe_config})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 数据导出相关接口 ====================
import csv
from .constants import PROJECT_ROOT

# 注意：现在不再保存文件到磁盘，只保存记录到数据库
# 新导出的记录 file_path 都是 NULL，无法重复下载
# downloads 目录已删除，不再支持文件存储


def _get_user_id():
    """获取当前用户ID"""
    from .auth import current_user
    user = current_user()
    if not user or not isinstance(user, dict) or "id" not in user:
        return None
    return int(user["id"])


@bp.post("/api/exports")
def create_export():
    """创建导出任务"""
    try:
        user_id = _get_user_id()
        if not user_id:
            return jsonify({"success": False, "error": "未登录"}), 401

        data = request.get_json(force=True) or {}
        
        print(f"📤 [导出] 收到导出请求: user_id={user_id}, data={data}")
        
        # 获取导出参数
        data_range = data.get("data_range", "all")  # all/query/date
        platforms = data.get("platforms", [])  # 平台列表
        format_type = data.get("format", "excel")  # excel/csv
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        
        # 如果是"当前查询结果"，需要传递查询条件
        query_params = data.get("query_params", {}) if data_range == "query" else {}
        
        # 平台名称映射（前端传英文，数据库存中文）
        platform_map = {
            'meituan': '美团',
            'ctrip': '携程',
            'fliggy': '飞猪',
            'gaode': '高德',
        }
        platform_list = None
        if platforms:
            platform_list = [platform_map.get(p, p) for p in platforms]
            print(f"🔍 [导出] 平台筛选: {platforms} -> {platform_list}")
        
        # 构建筛选条件
        filters = {
            "platforms": platform_list,  # 改为列表形式
            "start_date": start_date if data_range == "date" else None,
            "end_date": end_date if data_range == "date" else None,
            **query_params  # 如果是"当前查询结果"，合并查询条件
        }
        
        print(f"🔍 [导出] 筛选条件: {filters}")
        
        # 直接查询数据库（支持多平台）
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "error": "数据库连接失败"}), 500
        
        try:
            cursor = conn.cursor()
            is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
            
            conditions = []
            params = []
            
            # 构建查询条件
            if filters.get("hotel_name"):
                conditions.append("hotel_name LIKE %s" if is_mysql else "hotel_name LIKE ?")
                params.append(f"%{filters['hotel_name']}%")
            
            # 多平台筛选（使用 IN 查询）
            if platform_list and len(platform_list) > 0:
                placeholders = ",".join(["%s"] * len(platform_list) if is_mysql else ["?"] * len(platform_list))
                conditions.append(f"platform IN ({placeholders})")
                params.extend(platform_list)
            
            if filters.get("region"):
                conditions.append("region = %s" if is_mysql else "region = ?")
                params.append(filters["region"])
            
            if filters.get("star_level"):
                conditions.append("star_level = %s" if is_mysql else "star_level = ?")
                params.append(filters["star_level"])
            
            if filters.get("min_rating") is not None:
                conditions.append("rating_score >= %s" if is_mysql else "rating_score >= ?")
                params.append(filters["min_rating"])
            
            if filters.get("max_rating") is not None:
                conditions.append("rating_score <= %s" if is_mysql else "rating_score <= ?")
                params.append(filters["max_rating"])
            
            if filters.get("min_price") is not None:
                conditions.append("min_price >= %s" if is_mysql else "min_price >= ?")
                params.append(filters["min_price"])
            
            if filters.get("max_price") is not None:
                conditions.append("min_price <= %s" if is_mysql else "min_price <= ?")
                params.append(filters["max_price"])
            
            if filters.get("start_date"):
                conditions.append("crawl_time >= %s" if is_mysql else "crawl_time >= ?")
                params.append(filters["start_date"])
            
            if filters.get("end_date"):
                conditions.append("crawl_time <= %s" if is_mysql else "crawl_time <= ?")
                params.append(filters["end_date"])
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 查询总数
            count_query = f"SELECT COUNT(*) FROM hotel_data {where_clause}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # 查询所有数据（不分页）
            data_query = f"""
                SELECT id, hotel_name, platform, hotel_id, hotel_url, star_level, rating_score, 
                       review_count, min_price, booking_dynamic, address, region, opening_date, 
                       room_types, phone, email, website, crawl_time, created_at, updated_at
                FROM hotel_data
                {where_clause}
                ORDER BY crawl_time DESC
            """
            cursor.execute(data_query, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            # 处理 room_types（如果是 JSON 字符串，解析为对象）
            hotel_data = []
            for row in rows:
                row_dict = dict(zip(columns, row))
                # 处理 room_types
                if row_dict.get('room_types'):
                    try:
                        if isinstance(row_dict['room_types'], str):
                            row_dict['room_types'] = json.loads(row_dict['room_types'])
                    except:
                        pass
                hotel_data.append(row_dict)
            
            print(f"📊 [导出] 查询结果: total={total}, data_count={len(hotel_data)}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ [导出] 查询数据失败: {str(e)}")
            return jsonify({"success": False, "error": f"查询数据失败: {str(e)}"}), 500
        finally:
            conn.close()
        
        if total == 0 or not hotel_data or len(hotel_data) == 0:
            print(f"❌ [导出] 没有可导出的数据: total={total}, data_count={len(hotel_data) if hotel_data else 0}")
            return jsonify({"success": False, "error": "没有可导出的数据"}), 400
        
        # 生成文件名（仅用于记录和下载时的文件名）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "xlsx" if format_type == "excel" else "csv"
        file_name = f"酒店数据_{timestamp}.{ext}"
        
        print(f"📁 [导出] 准备生成文件（内存模式，不保存到磁盘）: {file_name}")
        
        # 生成文件到内存（不保存到磁盘）
        from io import BytesIO
        file_obj = None
        try:
            if format_type == "excel":
                file_obj = _export_to_excel_memory(hotel_data)
            else:
                file_obj = _export_to_csv_memory(hotel_data)
            
            file_size = len(file_obj.getvalue())
            print(f"✅ [导出] 文件生成成功（内存）: {file_name}, 大小: {file_size} 字节")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ [导出] 文件生成失败: {str(e)}")
            return jsonify({"success": False, "error": f"文件生成失败: {str(e)}"}), 500
        
        # 保存导出记录到数据库（不保存文件到磁盘）
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "error": "数据库连接失败"}), 500
        
        export_id = None
        try:
            cursor = conn.cursor()
            is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
            
            # 构建 filters_json
            filters_json = json.dumps({
                "data_range": data_range,
                "platforms": platforms,
                "format": format_type,
                "start_date": start_date,
                "end_date": end_date,
                "query_params": query_params
            }, ensure_ascii=False)
            
            # 不保存文件路径（因为文件不保存到磁盘，只保存记录）
            relative_path = None  # NULL 表示文件未保存到磁盘
            
            print(f"💾 [导出] 准备保存记录（不保存文件到磁盘）: user_id={user_id}, file_name={file_name}, row_count={total}")
            
            if is_mysql:
                # MySQL: 检查表是否存在，如果不存在则创建
                try:
                    cursor.execute("SHOW TABLES LIKE 'export_history'")
                    if not cursor.fetchone():
                        print("⚠️ [导出] export_history 表不存在，尝试创建...")
                        create_table_sql = """
                            CREATE TABLE IF NOT EXISTS export_history (
                                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '导出记录ID',
                                user_id INT DEFAULT NULL COMMENT '用户ID',
                                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '导出发起时间',
                                started_at TIMESTAMP NULL DEFAULT NULL COMMENT '开始处理时间',
                                finished_at TIMESTAMP NULL DEFAULT NULL COMMENT '完成时间',
                                status ENUM('queued', 'running', 'success', 'failed') NOT NULL DEFAULT 'queued' COMMENT '状态',
                                format ENUM('excel', 'csv') NOT NULL DEFAULT 'excel' COMMENT '导出格式',
                                file_name VARCHAR(255) NOT NULL COMMENT '文件名',
                                file_path VARCHAR(500) DEFAULT NULL COMMENT '文件存储路径',
                                row_count INT DEFAULT 0 COMMENT '导出数据量',
                                filters_json JSON DEFAULT NULL COMMENT '导出筛选条件',
                                error TEXT DEFAULT NULL COMMENT '错误信息',
                                download_count INT DEFAULT 0 COMMENT '下载次数',
                                expires_at TIMESTAMP NULL DEFAULT NULL COMMENT '文件过期时间',
                                INDEX idx_user_id (user_id),
                                INDEX idx_status (status),
                                INDEX idx_created_at (created_at),
                                INDEX idx_user_created (user_id, created_at)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
                        """
                        cursor.execute(create_table_sql)
                        conn.commit()
                        print("✅ [导出] export_history 表已创建并提交")
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"⚠️ [导出] 检查/创建表时出错: {str(e)}")
                    # 如果表创建失败，尝试继续（可能表已存在）
                
                sql = """
                    INSERT INTO export_history 
                    (user_id, status, format, file_name, file_path, row_count, filters_json, started_at, finished_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """
                print(f"💾 [导出] 执行 INSERT SQL: user_id={user_id}, file_name={file_name}, row_count={total}")
                cursor.execute(sql, (
                    user_id, "success", format_type, file_name, relative_path, total, filters_json
                ))
                export_id = cursor.lastrowid
                print(f"💾 [导出] lastrowid={export_id}")
                
                # MySQL 需要手动 commit
                conn.commit()
                print(f"✅ [导出] MySQL commit 成功: export_id={export_id}")
            else:
                # SQLite: 检查表是否存在
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='export_history'")
                    if not cursor.fetchone():
                        print("⚠️ [导出] export_history 表不存在，尝试创建...")
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS export_history (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id INTEGER,
                                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                                started_at TEXT,
                                finished_at TEXT,
                                status TEXT NOT NULL DEFAULT 'queued',
                                format TEXT NOT NULL DEFAULT 'excel',
                                file_name TEXT NOT NULL,
                                file_path TEXT,
                                row_count INTEGER DEFAULT 0,
                                filters_json TEXT,
                                error TEXT,
                                download_count INTEGER DEFAULT 0,
                                expires_at TEXT
                            )
                        """)
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON export_history(user_id)")
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON export_history(created_at)")
                        print("✅ [导出] export_history 表已创建")
                except Exception as e:
                    print(f"⚠️ [导出] 检查/创建表时出错: {str(e)}")
                
                sql = """
                    INSERT INTO export_history 
                    (user_id, status, format, file_name, file_path, row_count, filters_json, started_at, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """
                cursor.execute(sql, (
                    user_id, "success", format_type, file_name, relative_path, total, filters_json
                ))
                export_id = cursor.lastrowid
                conn.commit()
            
            if not export_id:
                raise Exception("无法获取导出记录ID，lastrowid 为空")
            
            print(f"✅ [导出] 导出记录已保存: export_id={export_id}, file_name={file_name}, row_count={total}")
            
            # 验证记录是否真的保存成功
            # 注意：在同一个连接中验证，因为数据已经 commit 了
            if is_mysql:
                verify_sql = "SELECT id, user_id, file_name FROM export_history WHERE id = %s"
                cursor.execute(verify_sql, (export_id,))
                verify_row = cursor.fetchone()
                if verify_row:
                    print(f"✅ [导出] 记录验证成功: export_id={export_id}, 记录={verify_row}")
                else:
                    # 如果当前连接查不到，可能是事务问题，尝试重新查询
                    print(f"⚠️ [导出] 当前连接未找到记录，尝试重新查询...")
                    verify_conn = get_db_connection()
                    if verify_conn:
                        try:
                            verify_cursor = verify_conn.cursor()
                            verify_cursor.execute(verify_sql, (export_id,))
                            verify_row2 = verify_cursor.fetchone()
                            if verify_row2:
                                print(f"✅ [导出] 重新查询找到记录: export_id={export_id}")
                            else:
                                print(f"❌ [导出] 重新查询也未找到记录: export_id={export_id}")
                                # 查询所有记录用于调试
                                verify_cursor.execute("SELECT id, user_id, file_name FROM export_history ORDER BY id DESC LIMIT 5")
                                all_records = verify_cursor.fetchall()
                                print(f"🔍 [导出] 数据库中的所有记录: {all_records}")
                        finally:
                            verify_conn.close()
            else:
                verify_sql = "SELECT id FROM export_history WHERE id = ?"
                cursor.execute(verify_sql, (export_id,))
                verify_row = cursor.fetchone()
                if not verify_row:
                    raise Exception(f"验证失败：导出记录 {export_id} 未找到")
                print(f"✅ [导出] 记录验证成功: export_id={export_id}")
            
            # 返回文件给浏览器下载（不保存到磁盘）
            # 注意：Flask 只能返回一个响应，所以这里返回文件，而不是 JSON
            # 前端需要特殊处理：收到文件下载后，通过响应头获取 export_id
            from flask import Response
            
            file_obj.seek(0)  # 重置文件指针到开头
            
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if format_type == 'excel' else 'text/csv; charset=utf-8-sig'
            
            response = Response(
                file_obj.getvalue(),
                mimetype=mimetype,
                headers={
                    'Content-Disposition': f'attachment; filename="{file_name}"',
                    'X-Export-Id': str(export_id),  # 通过响应头传递 export_id
                    'X-Export-File-Name': file_name,
                    'X-Export-Row-Count': str(total)
                }
            )
            
            print(f"✅ [导出] 返回文件响应（不保存到磁盘）: export_id={export_id}, file_name={file_name}")
            return response
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ [导出] 保存导出记录失败: {str(e)}")
            return jsonify({"success": False, "error": f"保存导出记录失败: {str(e)}"}), 500
        finally:
            conn.close()
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/exports")
def get_export_history():
    """获取导出历史列表"""
    try:
        user_id = _get_user_id()
        if not user_id:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        offset = (page - 1) * per_page
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "error": "数据库连接失败"}), 500
        
        try:
            cursor = conn.cursor()
            is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
            
            # 先检查表是否存在
            try:
                if is_mysql:
                    cursor.execute("SHOW TABLES LIKE 'export_history'")
                    table_exists = cursor.fetchone() is not None
                else:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='export_history'")
                    table_exists = cursor.fetchone() is not None
                
                if not table_exists:
                    print(f"⚠️ [历史] export_history 表不存在")
                    return jsonify({
                        "success": True,
                        "data": [],
                        "pagination": {"page": page, "per_page": per_page, "total": 0, "total_pages": 0}
                    })
            except Exception as e:
                print(f"⚠️ [历史] 检查表时出错: {str(e)}")
            
            # 查询总数
            if is_mysql:
                count_sql = "SELECT COUNT(*) FROM export_history WHERE user_id = %s"
                cursor.execute(count_sql, (user_id,))
            else:
                count_sql = "SELECT COUNT(*) FROM export_history WHERE user_id = ?"
                cursor.execute(count_sql, (user_id,))
            
            total = cursor.fetchone()[0]
            print(f"📊 [历史] 查询到 {total} 条记录 (user_id={user_id})")
            
            # 查询列表（包含 file_path，用于判断是否可以下载）
            if is_mysql:
                sql = """
                    SELECT id, created_at, format, file_name, file_path, row_count, status, download_count
                    FROM export_history
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (user_id, per_page, offset))
            else:
                sql = """
                    SELECT id, created_at, format, file_name, file_path, row_count, status, download_count
                    FROM export_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """
                cursor.execute(sql, (user_id, per_page, offset))
            
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            exports = [dict(zip(columns, row)) for row in rows]
            
            # 格式化时间
            for exp in exports:
                if exp.get("created_at"):
                    if isinstance(exp["created_at"], str):
                        try:
                            dt = datetime.strptime(exp["created_at"], "%Y-%m-%d %H:%M:%S")
                            exp["created_at"] = dt.strftime("%Y-%m-%d %H:%M")
                        except:
                            pass
            
            total_pages = (total + per_page - 1) // per_page if total > 0 else 0
            
            return jsonify({
                "success": True,
                "data": exports,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": total_pages
                }
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"success": False, "error": str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/api/exports/<int:export_id>/download")
def download_export(export_id: int):
    """下载导出文件"""
    try:
        user_id = _get_user_id()
        if not user_id:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        print(f"🔍 [下载] 开始下载: export_id={export_id}, user_id={user_id}")
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "error": "数据库连接失败"}), 500
        
        try:
            cursor = conn.cursor()
            is_mysql = PYMYSQL_AVAILABLE and pymysql and isinstance(conn, pymysql.Connection)
            
            # 先检查表是否存在
            try:
                if is_mysql:
                    cursor.execute("SHOW TABLES LIKE 'export_history'")
                    table_exists = cursor.fetchone() is not None
                else:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='export_history'")
                    table_exists = cursor.fetchone() is not None
                
                if not table_exists:
                    print(f"❌ [下载] export_history 表不存在")
                    return jsonify({"success": False, "error": "导出历史表不存在，请先创建导出记录"}), 404
            except Exception as e:
                print(f"⚠️ [下载] 检查表时出错: {str(e)}")
            
            # 查询记录（先不限制用户，用于调试）
            if is_mysql:
                check_sql = "SELECT id, user_id, file_name, file_path FROM export_history WHERE id = %s"
                cursor.execute(check_sql, (export_id,))
            else:
                check_sql = "SELECT id, user_id, file_name, file_path FROM export_history WHERE id = ?"
                cursor.execute(check_sql, (export_id,))
            
            columns = [desc[0] for desc in cursor.description]
            check_row = cursor.fetchone()
            
            if not check_row:
                # 查询所有记录用于调试
                if is_mysql:
                    debug_sql = "SELECT id, user_id, file_name FROM export_history ORDER BY id DESC LIMIT 5"
                    cursor.execute(debug_sql)
                else:
                    debug_sql = "SELECT id, user_id, file_name FROM export_history ORDER BY id DESC LIMIT 5"
                    cursor.execute(debug_sql)
                
                debug_rows = cursor.fetchall()
                print(f"❌ [下载] 导出记录不存在: export_id={export_id}")
                print(f"🔍 [下载] 数据库中的记录: {debug_rows}")
                return jsonify({"success": False, "error": f"导出记录不存在 (ID: {export_id})"}), 404
            
            # 检查用户权限
            check_record = dict(zip(columns, check_row))
            record_user_id = check_record.get("user_id")
            
            print(f"📋 [下载] 找到记录: {check_record}")
            
            if record_user_id and int(record_user_id) != int(user_id):
                print(f"❌ [下载] 用户权限不匹配: export_id={export_id}, record_user_id={record_user_id}, current_user_id={user_id}")
                return jsonify({"success": False, "error": "无权限访问此导出记录"}), 403
            
            # 查询完整导出记录
            if is_mysql:
                sql = "SELECT * FROM export_history WHERE id = %s"
                cursor.execute(sql, (export_id,))
            else:
                sql = "SELECT * FROM export_history WHERE id = ?"
                cursor.execute(sql, (export_id,))
            
            columns = [desc[0] for desc in cursor.description]
            row = cursor.fetchone()
            
            if not row:
                return jsonify({"success": False, "error": "导出记录不存在"}), 404
            
            export_record = dict(zip(columns, row))
            file_path = export_record.get("file_path")
            file_name = export_record.get("file_name")
            
            print(f"📁 [下载] file_path={file_path}, file_name={file_name}")
            
            # 检查文件是否保存到磁盘
            # file_path 为 NULL 或空字符串表示文件未保存到磁盘（只保存记录模式）
            # 注意：现在所有新导出的记录 file_path 都是 NULL，无法重复下载
            # downloads 目录已删除，不再支持从磁盘读取文件
            if not file_path or (isinstance(file_path, str) and file_path.strip() == ""):
                print(f"⚠️ [下载] 文件未保存到磁盘（file_path 为 NULL/空），无法重复下载")
                return jsonify({
                    "success": False, 
                    "error": "文件未保存到服务器，无法重复下载。请重新导出数据获取文件。"
                }), 404
            
            # 如果有旧记录（file_path 不为空），但文件存储已禁用
            # downloads 目录已删除，不再支持从磁盘读取文件
            print(f"⚠️ [下载] 检测到旧记录（file_path={file_path}），但文件存储已禁用，无法下载")
            return jsonify({
                "success": False, 
                "error": "文件存储功能已禁用，无法下载旧记录。请重新导出数据获取文件。"
            }), 404
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"success": False, "error": str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


def _export_to_excel(data, file_path):
    """导出为 Excel 文件（保存到磁盘）"""
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("需要安装 pandas 和 openpyxl: pip install pandas openpyxl")
    
    # 准备数据（展平 room_types JSON）
    rows = []
    for item in data:
        row = {
            "酒店名称": item.get("hotel_name", ""),
            "平台": item.get("platform", ""),
            "星级": item.get("star_level", ""),
            "评分": item.get("rating_score", ""),
            "点评数": item.get("review_count", ""),
            "最低价格": item.get("min_price", ""),
            "地址": item.get("address", ""),
            "区域": item.get("region", ""),
            "电话": item.get("phone", ""),
            "爬取时间": item.get("crawl_time", ""),
        }
        
        # 处理 room_types（如果有）
        room_types = item.get("room_types")
        if room_types:
            if isinstance(room_types, str):
                try:
                    room_types = json.loads(room_types)
                except:
                    room_types = []
            
            if isinstance(room_types, list) and room_types:
                room_names = []
                room_prices = []
                for room in room_types:
                    room_names.append(room.get("房型名称", ""))
                    room_prices.append(room.get("价格", ""))
                row["房型列表"] = " | ".join(room_names)
                row["价格列表"] = " | ".join(room_prices)
            else:
                row["房型列表"] = ""
                row["价格列表"] = ""
        else:
            row["房型列表"] = ""
            row["价格列表"] = ""
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    df.to_excel(file_path, index=False, engine="openpyxl")


def _export_to_excel_memory(data):
    """导出为 Excel 文件（内存模式，不保存到磁盘）"""
    try:
        import pandas as pd
        from io import BytesIO
    except ImportError:
        raise ImportError("需要安装 pandas 和 openpyxl: pip install pandas openpyxl")
    
    # 准备数据（展平 room_types JSON）
    rows = []
    for item in data:
        row = {
            "酒店名称": item.get("hotel_name", ""),
            "平台": item.get("platform", ""),
            "星级": item.get("star_level", ""),
            "评分": item.get("rating_score", ""),
            "点评数": item.get("review_count", ""),
            "最低价格": item.get("min_price", ""),
            "地址": item.get("address", ""),
            "区域": item.get("region", ""),
            "电话": item.get("phone", ""),
            "爬取时间": item.get("crawl_time", ""),
        }
        
        # 处理 room_types（如果有）
        room_types = item.get("room_types")
        if room_types:
            if isinstance(room_types, str):
                try:
                    room_types = json.loads(room_types)
                except:
                    room_types = []
            
            if isinstance(room_types, list) and room_types:
                room_names = []
                room_prices = []
                for room in room_types:
                    room_names.append(room.get("房型名称", ""))
                    room_prices.append(room.get("价格", ""))
                row["房型列表"] = " | ".join(room_names)
                row["价格列表"] = " | ".join(room_prices)
            else:
                row["房型列表"] = ""
                row["价格列表"] = ""
        else:
            row["房型列表"] = ""
            row["价格列表"] = ""
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    output = BytesIO()
    df.to_excel(output, index=False, engine="openpyxl")
    output.seek(0)
    return output


def _export_to_csv(data, file_path):
    """导出为 CSV 文件（保存到磁盘）"""
    if not data:
        return
    
    # 准备表头
    fieldnames = [
        "酒店名称", "平台", "星级", "评分", "点评数", "最低价格",
        "地址", "区域", "电话", "爬取时间", "房型列表", "价格列表"
    ]
    
    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in data:
            row = {
                "酒店名称": item.get("hotel_name", ""),
                "平台": item.get("platform", ""),
                "星级": item.get("star_level", ""),
                "评分": item.get("rating_score", ""),
                "点评数": item.get("review_count", ""),
                "最低价格": item.get("min_price", ""),
                "地址": item.get("address", ""),
                "区域": item.get("region", ""),
                "电话": item.get("phone", ""),
                "爬取时间": item.get("crawl_time", ""),
            }
            
            # 处理 room_types
            room_types = item.get("room_types")
            if room_types:
                if isinstance(room_types, str):
                    try:
                        room_types = json.loads(room_types)
                    except:
                        room_types = []
                
                if isinstance(room_types, list) and room_types:
                    room_names = []
                    room_prices = []
                    for room in room_types:
                        room_names.append(room.get("房型名称", ""))
                        room_prices.append(room.get("价格", ""))
                    row["房型列表"] = " | ".join(room_names)
                    row["价格列表"] = " | ".join(room_prices)
                else:
                    row["房型列表"] = ""
                    row["价格列表"] = ""
            else:
                row["房型列表"] = ""
                row["价格列表"] = ""
            
            writer.writerow(row)


def _export_to_csv_memory(data):
    """导出为 CSV 文件（内存模式，不保存到磁盘）"""
    if not data:
        from io import BytesIO
        return BytesIO()
    
    from io import BytesIO, StringIO
    
    # 准备表头
    fieldnames = [
        "酒店名称", "平台", "星级", "评分", "点评数", "最低价格",
        "地址", "区域", "电话", "爬取时间", "房型列表", "价格列表"
    ]
    
    # 使用 StringIO 构建 CSV 内容
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for item in data:
        row = {
            "酒店名称": item.get("hotel_name", ""),
            "平台": item.get("platform", ""),
            "星级": item.get("star_level", ""),
            "评分": item.get("rating_score", ""),
            "点评数": item.get("review_count", ""),
            "最低价格": item.get("min_price", ""),
            "地址": item.get("address", ""),
            "区域": item.get("region", ""),
            "电话": item.get("phone", ""),
            "爬取时间": item.get("crawl_time", ""),
        }
        
        # 处理 room_types
        room_types = item.get("room_types")
        if room_types:
            if isinstance(room_types, str):
                try:
                    room_types = json.loads(room_types)
                except:
                    room_types = []
            
            if isinstance(room_types, list) and room_types:
                room_names = []
                room_prices = []
                for room in room_types:
                    room_names.append(room.get("房型名称", ""))
                    room_prices.append(room.get("价格", ""))
                row["房型列表"] = " | ".join(room_names)
                row["价格列表"] = " | ".join(room_prices)
            else:
                row["房型列表"] = ""
                row["价格列表"] = ""
        else:
            row["房型列表"] = ""
            row["价格列表"] = ""
        
        writer.writerow(row)
    
    # 转换为 BytesIO（UTF-8 with BOM for Excel compatibility）
    csv_content = output.getvalue()
    output.close()
    
    # 添加 BOM（Excel 能正确识别 UTF-8）
    bom = '\ufeff'
    csv_bytes = (bom + csv_content).encode('utf-8-sig')
    
    result = BytesIO(csv_bytes)
    result.seek(0)
    return result


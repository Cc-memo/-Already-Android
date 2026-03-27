import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from .constants import CRAWL_TASK_DB
from .db import db
from .settings import get_setting

# 导入数据库保存函数
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from database.db_utils import save_to_database
    from database.db_utils import load_config
except ImportError:
    save_to_database = None
    load_config = None  # type: ignore

bp = Blueprint("crawl_tasks", __name__, url_prefix="/api/crawl-tasks")

# ---- 取消控制：删除/取消任务时用于中断后台线程 ----
_CANCEL_EVENTS: Dict[str, threading.Event] = {}
_DELETE_AFTER_CANCEL: set[str] = set()
_CANCEL_LOCK = threading.Lock()

# ---- 仪表盘简单内存缓存（按 user_id） ----
_RECENT_TASKS_CACHE: Dict[int, Dict[str, Any]] = {}
_TREND_CACHE: Dict[int, Dict[str, Any]] = {}
_RECENT_TASKS_MERGED_CACHE: Dict[int, Dict[str, Any]] = {}
_TREND_MERGED_CACHE: Dict[int, Dict[str, Any]] = {}
_DASHBOARD_CACHE_TTL = 30  # 秒

# 手机端任务表所在 DB（与 app_crawl_tasks 模块一致，避免循环导入用字符串）
_APP_TASKS_DB = "app_crawl_tasks.sqlite3"


def _ensure_cancel_event(task_id: str) -> threading.Event:
    with _CANCEL_LOCK:
        ev = _CANCEL_EVENTS.get(task_id)
        if ev is None:
            ev = threading.Event()
            _CANCEL_EVENTS[task_id] = ev
        return ev


def _request_cancel(task_id: str, delete_after_cancel: bool = False) -> None:
    """请求取消任务（尽力而为）。"""
    ev = _ensure_cancel_event(task_id)
    ev.set()
    if delete_after_cancel:
        with _CANCEL_LOCK:
            _DELETE_AFTER_CANCEL.add(task_id)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_crawl_task_db():
    """初始化 crawl_tasks 表"""
    # SQLite 建表
    sql_sqlite = """
        CREATE TABLE IF NOT EXISTS crawl_tasks (
            task_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            status TEXT NOT NULL,
            hotel_name TEXT NOT NULL,
            location TEXT,
            check_in TEXT,
            check_out TEXT,
            platforms_json TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            current_platform TEXT,
            error TEXT,
            results_json TEXT,
            user_id INTEGER
        )
    """
    # MySQL 建表 (TEXT -> VARCHAR/TEXT, PRIMARY KEY 处理)
    sql_mysql = """
        CREATE TABLE IF NOT EXISTS crawl_tasks (
            task_id VARCHAR(50) PRIMARY KEY,
            created_at VARCHAR(30) NOT NULL,
            updated_at VARCHAR(30) NOT NULL,
            started_at VARCHAR(30),
            finished_at VARCHAR(30),
            status VARCHAR(20) NOT NULL,
            hotel_name VARCHAR(255) NOT NULL,
            location VARCHAR(255),
            check_in VARCHAR(20),
            check_out VARCHAR(20),
            platforms_json TEXT NOT NULL,
            progress INT NOT NULL DEFAULT 0,
            current_platform VARCHAR(50),
            error TEXT,
            results_json LONGTEXT,
            user_id INT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    
    conn = db.get_connection("crawl_tasks.sqlite3")
    try:
        cursor = conn.cursor()
        if db.config['db_type'] == 'mysql':
            cursor.execute(sql_mysql)
            # 为旧 MySQL 数据库添加缺失的列
            try:
                cursor.execute("ALTER TABLE crawl_tasks ADD COLUMN check_in VARCHAR(20)")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE crawl_tasks ADD COLUMN check_out VARCHAR(20)")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE crawl_tasks ADD COLUMN user_id INT")
            except Exception:
                pass
        else:
            cursor.execute(sql_sqlite)
            # 补丁：为旧 SQLite 数据库添加缺失的列
            try:
                cursor.execute("ALTER TABLE crawl_tasks ADD COLUMN check_in TEXT")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE crawl_tasks ADD COLUMN check_out TEXT")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE crawl_tasks ADD COLUMN user_id INTEGER")
            except Exception:
                pass
        
        # 无论 SQLite 还是 MySQL 都需要 commit
        conn.commit()
    finally:
        conn.close()


def _task_row_to_dict(row: Any, include_results: bool) -> Dict:
    # 兼容 SQLite Row 和 MySQL DictCursor
    if hasattr(row, 'keys'): # SQLite Row
        task = dict(row)
    else: # Dict
        task = dict(row)

    task["platforms"] = json.loads(task.pop("platforms_json") or "[]")
    task["check_in"] = task.get("check_in")
    task["check_out"] = task.get("check_out")
    
    if include_results and task.get("results_json"):
        try:
            task["results"] = json.loads(task["results_json"])
        except Exception:
            task["results"] = None
    else:
        task["results"] = None
    task.pop("results_json", None)
    return task


def create_task(hotel_name: str, location: Optional[str], platforms: List[str], check_in: str = None, check_out: str = None, user_id: Optional[int] = None) -> Dict:
    task_id = str(uuid.uuid4())
    now = _now_str()
    
    # 检查是否有user_id字段
    conn = db.get_connection("crawl_tasks.sqlite3")
    try:
        cursor = conn.cursor()
        if db.config['db_type'] == 'mysql':
            cursor.execute("SHOW COLUMNS FROM crawl_tasks LIKE 'user_id'")
            has_user_id = cursor.fetchone() is not None
        else:
            cursor.execute("PRAGMA table_info(crawl_tasks)")
            cols = cursor.fetchall()
            has_user_id = any(col[1] == 'user_id' for col in cols)
    except Exception:
        has_user_id = False
    finally:
        conn.close()
    
    if has_user_id:
        sql = """
            INSERT INTO crawl_tasks
                (task_id, created_at, updated_at, started_at, finished_at, status, hotel_name, location, check_in, check_out, platforms_json, progress, current_platform, error, results_json, user_id)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        db.execute(sql, (
            task_id, now, now, None, None, "queued", hotel_name, location, check_in, check_out,
            json.dumps(platforms, ensure_ascii=False), 0, None, None, None, user_id
        ), sqlite_name="crawl_tasks.sqlite3")
    else:
        sql = """
            INSERT INTO crawl_tasks
                (task_id, created_at, updated_at, started_at, finished_at, status, hotel_name, location, check_in, check_out, platforms_json, progress, current_platform, error, results_json)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        db.execute(sql, (
            task_id, now, now, None, None, "queued", hotel_name, location, check_in, check_out,
            json.dumps(platforms, ensure_ascii=False), 0, None, None, None
        ), sqlite_name="crawl_tasks.sqlite3")
    
    # 使用传入的 user_id 来获取任务，确保能正确返回
    task = get_task(task_id, user_id=user_id)
    if task:
        return task
    
    # 如果 get_task 返回 None（可能是数据库字段问题），直接构建任务对象返回
    return {
        "task_id": task_id,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "status": "queued",
        "hotel_name": hotel_name,
        "location": location,
        "check_in": check_in,
        "check_out": check_out,
        "platforms": platforms,
        "progress": 0,
        "current_platform": None,
        "error": None,
        "results": None,
        "user_id": user_id
    }


def update_task(task_id: str, **fields) -> None:
    allowed = {
        "updated_at", "started_at", "finished_at", "status",
        "progress", "current_platform", "error", "results_json",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now_str()
    
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    params = list(updates.values()) + [task_id]
    
    db.execute(
        f"UPDATE crawl_tasks SET {set_clause} WHERE task_id = ?",
        tuple(params),
        sqlite_name="crawl_tasks.sqlite3"
    )


def get_task(task_id: str, user_id: Optional[int] = None) -> Optional[Dict]:
    # 检查是否有user_id字段
    conn = db.get_connection("crawl_tasks.sqlite3")
    try:
        cursor = conn.cursor()
        if db.config['db_type'] == 'mysql':
            cursor.execute("SHOW COLUMNS FROM crawl_tasks LIKE 'user_id'")
            has_user_id = cursor.fetchone() is not None
        else:
            cursor.execute("PRAGMA table_info(crawl_tasks)")
            cols = cursor.fetchall()
            has_user_id = any(col[1] == 'user_id' for col in cols)
    except Exception:
        has_user_id = False
    finally:
        conn.close()
    
    # 根据是否有user_id字段构建查询（严格隔离）
    if has_user_id:
        if user_id is not None:
            # 严格隔离，排除 user_id 为 NULL 的旧数据
            row = db.query_one(
                "SELECT * FROM crawl_tasks WHERE task_id = ? AND user_id = ? AND user_id IS NOT NULL",
                (task_id, user_id),
                sqlite_name="crawl_tasks.sqlite3"
            )
        else:
            # 用户未登录，不允许查看任务
            return None
    else:
        # 字段不存在，不允许查看（安全隔离）
        return None
    if not row:
        return None
    return _task_row_to_dict(row, include_results=True)


def list_tasks(limit: int = 50, user_id: Optional[int] = None) -> List[Dict]:
    # 检查是否有user_id字段
    conn = db.get_connection("crawl_tasks.sqlite3")
    try:
        cursor = conn.cursor()
        if db.config['db_type'] == 'mysql':
            cursor.execute("SHOW COLUMNS FROM crawl_tasks LIKE 'user_id'")
            has_user_id = cursor.fetchone() is not None
        else:
            cursor.execute("PRAGMA table_info(crawl_tasks)")
            cols = cursor.fetchall()
            has_user_id = any(col[1] == 'user_id' for col in cols)
    except Exception:
        has_user_id = False
    finally:
        conn.close()
    
    # 严格隔离：必须同时满足字段存在且用户已登录
    if has_user_id:
        if user_id is not None:
            # 只查询当前用户的任务（严格隔离，排除 user_id 为 NULL 的旧数据）
            # 使用 IS NOT NULL 确保不返回旧数据
            # db.execute 会自动处理占位符转换（? -> %s for MySQL）
            rows = db.execute(
                "SELECT * FROM crawl_tasks WHERE user_id = ? AND user_id IS NOT NULL ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
                sqlite_name="crawl_tasks.sqlite3"
            )
        else:
            # 用户未登录，返回空列表（安全隔离）
            return []
    else:
        # 字段不存在，返回空列表（安全隔离）
        # 这样可以强制用户重启应用以完成数据库迁移
        return []
    
    # execute对于SELECT返回列表
    return [_task_row_to_dict(r, include_results=False) for r in rows]


# ---- 执行器：调用 Rpa 下的脚本（非交互模式） ----

_LOCKS = {
    "meituan": threading.Lock(),
    "ctrip": threading.Lock(),
}


def _run_meituan(location: str, hotel_name: str, check_in: str = None, check_out: str = None, cancel_event: Optional[threading.Event] = None) -> Dict[str, Any]:
    # 兼容导入
    from meituan import meituan_rpa

    old = os.getenv("NON_INTERACTIVE", "")
    os.environ["NON_INTERACTIVE"] = "1"
    try:
        room_data = meituan_rpa.run(location, hotel_name, check_in, check_out, cancel_event=cancel_event)  # type: ignore[attr-defined]
        return {"ok": True, "data": room_data}
    finally:
        if old:
            os.environ["NON_INTERACTIVE"] = old
        else:
            os.environ.pop("NON_INTERACTIVE", None)


def _run_ctrip(location: str, hotel_name: str, check_in: str = None, check_out: str = None, cancel_event: Optional[threading.Event] = None) -> Dict[str, Any]:
    from xiecheng import ctrip_crawler

    old = os.getenv("NON_INTERACTIVE", "")
    os.environ["NON_INTERACTIVE"] = "1"
    try:
        # 需要在 ctrip_crawler.py 增加 run_non_interactive()
        return ctrip_crawler.run_non_interactive(location, hotel_name, check_in, check_out, cancel_event=cancel_event)  # type: ignore[attr-defined]
    finally:
        if old:
            os.environ["NON_INTERACTIVE"] = old
        else:
            os.environ.pop("NON_INTERACTIVE", None)


def _execute_task(task_id: str, hotel_name: str, location: str, platforms: List[str], check_in: str = None, check_out: str = None, user_id: Optional[int] = None):
    cancel_event = _ensure_cancel_event(task_id)
    if cancel_event.is_set():
        # 已取消：不执行
        return

    # 如果未传递user_id，尝试从任务记录中获取
    if user_id is None:
        task = get_task(task_id)
        if task and task.get("user_id"):
            user_id = task.get("user_id")

    # 读取系统设置
    crawl_interval = get_setting("crawl_interval", 5)  # 爬取间隔（秒）
    concurrent_crawl = get_setting("concurrent_crawl", 3)  # 并发爬取数量
    enable_proxy = get_setting("enable_proxy", False)  # 是否启用代理
    
    # 设置环境变量，供爬虫脚本使用
    if enable_proxy:
        os.environ["USE_PROXY"] = "1"
    else:
        os.environ.pop("USE_PROXY", None)
    
    os.environ["CRAWL_INTERVAL"] = str(crawl_interval)
    os.environ["REQUEST_TIMEOUT"] = str(get_setting("request_timeout", 30))
    os.environ["MAX_RETRIES"] = str(get_setting("max_retries", 3))

    update_task(task_id, status="running", started_at=_now_str(), error=None, progress=0, current_platform=None)
    results: Dict[str, Any] = {}
    
    # 线程安全的锁（虽然现在是并发，但写 results 字典本身是线程安全的，不过为了严谨还是加个锁）
    results_lock = threading.Lock()
    
    # 存储线程列表
    threads = []
    
    # 使用信号量控制并发数量
    semaphore = threading.Semaphore(concurrent_crawl)
    
    def run_platform(platform):
        res = {"ok": False, "error": "未知错误"}
        try:
            if cancel_event.is_set():
                return
            
            # 应用爬取间隔（除了第一个请求）
            if crawl_interval > 0:
                time.sleep(crawl_interval)
            
            # 更新任务状态：当前正在启动哪个平台（只是个提示，因为是并发的）
            # update_task(task_id, current_platform=platform) 
            
            if platform == "meituan":
                # 注意：_LOCKS 仍然生效，确保同平台全局串行（避免封号），但不同平台可以并行
                with _LOCKS["meituan"]:
                    with semaphore:  # 控制并发数量
                        if cancel_event.is_set():
                            return
                        res = _run_meituan(location, hotel_name, check_in, check_out, cancel_event=cancel_event)
            elif platform == "ctrip":
                with _LOCKS["ctrip"]:
                    with semaphore:  # 控制并发数量
                        if cancel_event.is_set():
                            return
                        res = _run_ctrip(location, hotel_name, check_in, check_out, cancel_event=cancel_event)
            else:
                res = {"ok": False, "error": f"平台未接入RPA脚本: {platform}"}
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        
        with results_lock:
            results[platform] = res
            # 更新进度（简单计算：完成个数 / 总数）
            current_count = len(results)
            total = max(len(platforms), 1)
            prog = int(current_count * 100 / total)
            # 可以在这里更新数据库的进度，但不要太频繁
            # update_task(task_id, progress=prog)

    try:
        # 启动所有线程（受并发数量限制）
        for p in platforms:
            if cancel_event.is_set():
                break
            t = threading.Thread(target=run_platform, args=(p,))
            t.start()
            threads.append(t)
        
        # 等待所有线程结束
        for t in threads:
            t.join()

        if cancel_event.is_set():
            # 取消：不再写结果/入库（并尽量从列表移除）
            with _CANCEL_LOCK:
                delete_after = task_id in _DELETE_AFTER_CANCEL
            if not delete_after:
                update_task(task_id, status="cancelled", finished_at=_now_str(), progress=100, current_platform=None, error="任务已取消")
            return

        # 成功/失败判定：只要有一个 ok=True 就算 success，否则 failed
        ok_any = any((v or {}).get("ok") for v in results.values())
        status = "success" if ok_any else "failed"
        update_task(
            task_id,
            status=status,
            finished_at=_now_str(),
            progress=100,
            current_platform=None,
            results_json=json.dumps(results, ensure_ascii=False),
        )
        
        # 将数据保存到 room_data 表
        with _CANCEL_LOCK:
            delete_after = task_id in _DELETE_AFTER_CANCEL
        if ok_any and save_to_database and (not cancel_event.is_set()) and (not delete_after):
            try:
                # 遍历每个平台的结果，保存到数据库
                for platform, result in results.items():
                    if result and result.get("ok") and result.get("data"):
                        data = result["data"]
                        # 确保数据格式正确
                        if isinstance(data, dict) and "房型列表" in data:
                            # 数据格式已经符合 save_to_database 的要求
                            # 补充缺失的字段
                            if "搜索时间" not in data:
                                data["搜索时间"] = _now_str()
                            # 用 task_id 作为 request_id，便于后续按任务级联删除云库数据
                            if "request_id" not in data:
                                data["request_id"] = task_id
                            # 统一补齐城市/地址/日期，方便云库入库
                            if "城市" not in data and "city" not in data and location:
                                data["城市"] = location
                            if "地址" not in data and location:
                                data["地址"] = location
                            if "酒店名称" not in data and hotel_name:
                                data["酒店名称"] = hotel_name
                            if "酒店关键词" not in data and hotel_name:
                                data["酒店关键词"] = hotel_name
                            # 携程数据里可能没有日期；补齐入住/离店日期
                            if check_in and ("入住日期" not in data and "check_in_date" not in data and "checkin_date" not in data):
                                data["入住日期"] = check_in
                            if check_out and ("离店日期" not in data and "退房日期" not in data and "check_out_date" not in data and "checkout_date" not in data):
                                data["离店日期"] = check_out
                            
                            save_to_database(platform, data, user_id=user_id)
                            print(f"✓ 平台 {platform} 的数据已保存到 room_data 表")
                        elif isinstance(data, dict):
                            # 如果没有"房型列表"，尝试从其他字段提取
                            # 这里可以根据实际数据结构调整
                            print(f"⚠️  平台 {platform} 的数据格式不符合要求，跳过保存")
            except Exception as e:
                # 保存失败不影响任务状态，只记录错误
                print(f"⚠️  保存到 room_data 表失败: {e}")
                import traceback
                traceback.print_exc()
    except Exception as e:
        update_task(task_id, status="failed", finished_at=_now_str(), error=str(e), progress=100, current_platform=None)
    finally:
        with _CANCEL_LOCK:
            _CANCEL_EVENTS.pop(task_id, None)
            _DELETE_AFTER_CANCEL.discard(task_id)


@bp.delete("/<task_id>")
def api_delete(task_id: str):
    try:
        from .auth import current_user
        
        # 获取当前登录用户ID
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])
        
        task = get_task(task_id, user_id=user_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        # 任务未完成时：请求取消（尽力而为），并从列表移除
        if task.get("status") in ("queued", "running"):
            _request_cancel(task_id, delete_after_cancel=True)

        # 先尝试删除业务数据（search_records/room_data）——按 request_id=task_id 级联删除
        try:
            if load_config:
                cfg = load_config()
                if cfg.get("db_type") == "mysql":
                    try:
                        import pymysql  # type: ignore

                        mysql_cfg = cfg["mysql"]
                        conn = pymysql.connect(
                            host=mysql_cfg["host"],
                            port=mysql_cfg["port"],
                            user=mysql_cfg["user"],
                            password=mysql_cfg["password"],
                            database=mysql_cfg["database"],
                            charset=mysql_cfg.get("charset", "utf8mb4"),
                            autocommit=True,
                        )
                        try:
                            cur = conn.cursor()
                            # 识别字段名（云库/旧库）
                            cur.execute("SHOW COLUMNS FROM search_records")
                            sr_cols = {r[0] for r in cur.fetchall()}
                            cur.execute("SHOW COLUMNS FROM room_data")
                            rd_cols = {r[0] for r in cur.fetchall()}

                            if "request_id" in sr_cols:
                                # 找到 search_records.id 列表
                                cur.execute("SELECT id FROM search_records WHERE request_id = %s", (task_id,))
                                ids = [r[0] for r in cur.fetchall()]
                                if ids:
                                    fk_col = "search_record_id" if "search_record_id" in rd_cols else "search_id"
                                    placeholders = ",".join(["%s"] * len(ids))
                                    cur.execute(f"DELETE FROM room_data WHERE {fk_col} IN ({placeholders})", tuple(ids))
                                    cur.execute(f"DELETE FROM search_records WHERE id IN ({placeholders})", tuple(ids))
                        finally:
                            conn.close()
                    except Exception as e:
                        # 不阻塞任务删除：业务数据删除失败只记录
                        print(f"⚠️  删除云库 search_records/room_data 失败: {e}")
        except Exception as e:
            print(f"⚠️  删除业务数据异常: {e}")

        db.execute(
            "DELETE FROM crawl_tasks WHERE task_id = ?",
            (task_id,),
            sqlite_name="crawl_tasks.sqlite3"
        )
        return jsonify({"success": True, "data": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("")
def api_list():
    try:
        from flask import make_response
        from .auth import current_user
        
        # 获取当前登录用户ID
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        user_id = int(user["id"])
        
        limit = int(request.args.get("limit", 50))
        tasks = list_tasks(limit=limit, user_id=user_id)
        
        # 添加无缓存头，防止浏览器缓存 API 响应
        response = make_response(jsonify({"success": True, "data": tasks, "total": len(tasks)}))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/<task_id>")
def api_get(task_id: str):
    try:
        from .auth import current_user
        
        # 获取当前登录用户ID
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])
        
        task = get_task(task_id, user_id=user_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        return jsonify({"success": True, "data": task})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/batch")
def api_batch_create():
    try:
        from .auth import current_user
        
        # 获取当前登录用户ID
        user = current_user()
        if not user:
            return jsonify({"success": False, "error": "未登录"}), 401
        if not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "用户信息无效"}), 401
        user_id = int(user["id"])
        
        data: Dict[str, Any] = request.get_json(force=True) or {}
        location = (data.get("location") or "").strip() or "上海"
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        platforms = data.get("platforms") or []
        hotels = data.get("hotels") or []

        if not isinstance(hotels, list) or not hotels:
            return jsonify({"success": False, "error": "hotels 必须是非空数组"}), 400
        if not isinstance(platforms, list) or not platforms:
            return jsonify({"success": False, "error": "platforms 必须是非空数组"}), 400

        allowed = {"meituan", "ctrip", "fliggy", "gaode"}
        platforms = [p for p in platforms if p in allowed]
        if not platforms:
            return jsonify({"success": False, "error": "platforms 无有效平台"}), 400

        created: List[Dict] = []
        for h in hotels:
            hotel_name = (str(h) or "").strip()
            if not hotel_name:
                continue
            t = create_task(hotel_name=hotel_name, location=location, platforms=platforms, check_in=check_in, check_out=check_out, user_id=user_id)
            if not t:
                continue  # 如果创建任务失败，跳过
            created.append(t)
            th = threading.Thread(
                target=_execute_task,
                args=(t["task_id"], hotel_name, location, platforms, check_in, check_out, user_id),
                daemon=True,
            )
            th.start()

        return jsonify({"success": True, "data": created, "total": len(created)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/dashboard/recent-tasks")
def api_dashboard_recent_tasks():
    """获取最近任务列表（用于首页展示，限制5条，带简单缓存）"""
    try:
        from flask import make_response
        from .auth import current_user
        
        # 获取当前登录用户ID
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        user_id = int(user["id"])
        
        now = time.time()

        # 1. 尝试读取缓存
        cache = _RECENT_TASKS_CACHE.get(user_id)
        if cache and now - cache.get("ts", 0) <= _DASHBOARD_CACHE_TTL:
            formatted_tasks = cache.get("data", [])
        else:
            # 2. 重新查询并格式化
            tasks = list_tasks(limit=5, user_id=user_id)

            formatted_tasks: List[Dict[str, Any]] = []
            platform_map = {"meituan": "美团", "ctrip": "携程", "fliggy": "飞猪", "gaode": "高德"}
            status_map = {
                "success": "已完成",
                "running": "爬取中",
                "queued": "等待中",
                "failed": "失败",
                "cancelled": "已取消",
            }

            for task in tasks:
                platforms = task.get("platforms", [])
                platform_labels = [platform_map.get(p, p) for p in platforms]
                if len(platform_labels) == 4:
                    platform_str = "全部平台"
                else:
                    platform_str = "、".join(platform_labels)

                created_at = task.get("created_at", "")
                time_str = _format_relative_time(created_at)

                status_code = task.get("status", "")
                status = status_map.get(status_code, status_code)

                formatted_tasks.append(
                    {
                        "task_id": task.get("task_id"),
                        "hotel_name": task.get("hotel_name", ""),
                        "platforms": platform_str,
                        "time": time_str,
                        "status": status,
                        "status_code": status_code,
                    }
                )

            _RECENT_TASKS_CACHE[user_id] = {"ts": now, "data": formatted_tasks}

        response = make_response(jsonify({"success": True, "data": formatted_tasks}))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _format_relative_time(time_str: str) -> str:
    """格式化时间为相对时间（如：2分钟前）"""
    if not time_str:
        return ""
    try:
        from datetime import datetime
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days}天前"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"{hours}小时前"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"{minutes}分钟前"
        else:
            return "刚刚"
    except Exception:
        return time_str


@bp.get("/dashboard/trend")
def api_dashboard_trend():
    """获取最近7天的数据趋势（用于首页图表，带简单缓存）"""
    try:
        from flask import make_response
        from .auth import current_user
        from datetime import datetime, timedelta
        
        # 获取当前登录用户ID
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        user_id = int(user["id"])
        now = time.time()

        # 1. 尝试读取缓存
        cache = _TREND_CACHE.get(user_id)
        if cache and now - cache.get("ts", 0) <= _DASHBOARD_CACHE_TTL:
            data = cache.get("data", {})
        else:
            # 2. 重新计算
            today = datetime.now()
            dates: List[str] = []
            data_counts: List[int] = []
            
            for i in range(6, -1, -1):  # 从6天前到今天
                date = today - timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                dates.append(date_str)
                
                # 查询该日期完成的任务数量
                # 注意：created_at 格式是 "YYYY-MM-DD HH:MM:SS"
                start_time = f"{date_str} 00:00:00"
                end_time = f"{date_str} 23:59:59"
                
                # 检查是否有user_id字段
                conn = db.get_connection("crawl_tasks.sqlite3")
                try:
                    cursor = conn.cursor()
                    if db.config['db_type'] == 'mysql':
                        cursor.execute("SHOW COLUMNS FROM crawl_tasks LIKE 'user_id'")
                        has_user_id = cursor.fetchone() is not None
                    else:
                        cursor.execute("PRAGMA table_info(crawl_tasks)")
                        cols = cursor.fetchall()
                        has_user_id = any(col[1] == 'user_id' for col in cols)
                except Exception:
                    has_user_id = False
                finally:
                    conn.close()
                
                if has_user_id:
                    # 查询该日期完成的任务数（status='success'）
                    if db.config['db_type'] == 'mysql':
                        sql = """
                            SELECT COUNT(*) as cnt FROM crawl_tasks 
                            WHERE user_id = %s AND user_id IS NOT NULL 
                            AND DATE(created_at) = %s 
                            AND status = 'success'
                        """
                        row = db.query_one(sql, (user_id, date_str), sqlite_name="crawl_tasks.sqlite3")
                    else:
                        # SQLite 使用字符串比较（created_at 格式：YYYY-MM-DD HH:MM:SS）
                        sql = """
                            SELECT COUNT(*) as cnt FROM crawl_tasks 
                            WHERE user_id = ? AND user_id IS NOT NULL 
                            AND created_at >= ? AND created_at < ?
                            AND status = 'success'
                        """
                        row = db.query_one(sql, (user_id, start_time, end_time), sqlite_name="crawl_tasks.sqlite3")
                    
                    count = row.get("cnt", 0) if row else 0
                else:
                    count = 0
                
                data_counts.append(count)
            
            # 格式化日期标签（如：1/9）
            labels = [f"{int(d.split('-')[1])}/{int(d.split('-')[2])}" for d in dates]
            data = {"labels": labels, "values": data_counts}
            _TREND_CACHE[user_id] = {"ts": now, "data": data}
        
        response = make_response(jsonify({
            "success": True,
            "data": data
        }))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _app_row_to_task_like(row: Any) -> Dict:
    """把 app_crawl_tasks 的一行转成与 list_tasks 元素结构一致，便于合并排序。"""
    if hasattr(row, "keys"):
        d = dict(row)
    else:
        d = dict(row)
    d["platforms"] = json.loads(d.get("platforms_json") or "[]")
    d.pop("platforms_json", None)
    return d


@bp.get("/dashboard/recent-tasks-merged")
def api_dashboard_recent_tasks_merged():
    """首页最近任务（合并云端+手机端两表，取前5条，不影响原 recent-tasks）"""
    try:
        from flask import make_response
        from .auth import current_user

        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])
        now = time.time()

        cache = _RECENT_TASKS_MERGED_CACHE.get(user_id)
        if cache and now - cache.get("ts", 0) <= _DASHBOARD_CACHE_TTL:
            formatted_tasks = cache.get("data", [])
        else:
            # 云端：最多 10 条
            desktop = list_tasks(limit=10, user_id=user_id)
            for t in desktop:
                t["exec_source"] = "电脑端"
            # 手机端：查 app_crawl_tasks，最多 10 条
            app_rows = []
            try:
                app_rows = db.execute(
                    "SELECT task_id, created_at, hotel_name, platforms_json, status FROM app_crawl_tasks WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, 10),
                    sqlite_name=_APP_TASKS_DB,
                )
            except Exception:
                app_rows = []
            app_tasks = []
            for r in (app_rows or []):
                t = _app_row_to_task_like(r)
                t["exec_source"] = "手机端"
                app_tasks.append(t)
            # 合并按 created_at 降序取前 5
            merged = desktop + app_tasks
            merged.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
            merged = merged[:5]

            platform_map = {"meituan": "美团", "ctrip": "携程", "fliggy": "飞猪", "gaode": "高德"}
            status_map = {"success": "已完成", "running": "爬取中", "queued": "等待中", "failed": "失败", "cancelled": "已取消"}
            formatted_tasks = []
            for task in merged:
                platforms = task.get("platforms", [])
                platform_labels = [platform_map.get(p, p) for p in platforms]
                platform_str = "全部平台" if len(platform_labels) == 4 else "、".join(platform_labels)
                created_at = task.get("created_at", "")
                time_str = _format_relative_time(created_at)
                status_code = task.get("status", "")
                status = status_map.get(status_code, status_code)
                formatted_tasks.append({
                    "task_id": task.get("task_id"),
                    "hotel_name": task.get("hotel_name", ""),
                    "platforms": platform_str,
                    "time": time_str,
                    "status": status,
                    "status_code": status_code,
                    "exec_source": task.get("exec_source", "电脑端"),
                })
            _RECENT_TASKS_MERGED_CACHE[user_id] = {"ts": now, "data": formatted_tasks}

        response = make_response(jsonify({"success": True, "data": formatted_tasks}))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/dashboard/trend-merged")
def api_dashboard_trend_merged():
    """首页数据趋势（合并云端+手机端两表完成数，最近7天，不影响原 trend）"""
    try:
        from flask import make_response
        from .auth import current_user
        from datetime import datetime, timedelta

        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])
        now = time.time()

        cache = _TREND_MERGED_CACHE.get(user_id)
        if cache and now - cache.get("ts", 0) <= _DASHBOARD_CACHE_TTL:
            data = cache.get("data", {})
        else:
            today = datetime.now()
            dates: List[str] = []
            data_counts: List[int] = []
            for i in range(6, -1, -1):
                date = today - timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                dates.append(date_str)
                start_time = f"{date_str} 00:00:00"
                end_time = f"{date_str} 23:59:59"
                count = 0
                # 云端：crawl_tasks 该日完成数
                conn = db.get_connection("crawl_tasks.sqlite3")
                try:
                    cursor = conn.cursor()
                    if db.config["db_type"] == "mysql":
                        cursor.execute(
                            "SELECT COUNT(*) as cnt FROM crawl_tasks WHERE user_id = %s AND user_id IS NOT NULL AND DATE(created_at) = %s AND status = 'success'",
                            (user_id, date_str),
                        )
                    else:
                        cursor.execute(
                            "SELECT COUNT(*) as cnt FROM crawl_tasks WHERE user_id = ? AND user_id IS NOT NULL AND created_at >= ? AND created_at < ? AND status = 'success'",
                            (user_id, start_time, end_time),
                        )
                    row = cursor.fetchone()
                    if row:
                        count += (row.get("cnt", 0) if isinstance(row, dict) else row[0]) or 0
                except Exception:
                    pass
                finally:
                    conn.close()
                # 手机端：app_crawl_tasks 该日完成数
                try:
                    if db.config["db_type"] == "mysql":
                        row = db.query_one(
                            "SELECT COUNT(*) as cnt FROM app_crawl_tasks WHERE user_id = ? AND DATE(created_at) = ? AND status = 'success'",
                            (user_id, date_str),
                            sqlite_name=_APP_TASKS_DB,
                        )
                    else:
                        row = db.query_one(
                            "SELECT COUNT(*) as cnt FROM app_crawl_tasks WHERE user_id = ? AND created_at >= ? AND created_at < ? AND status = 'success'",
                            (user_id, start_time, end_time),
                            sqlite_name=_APP_TASKS_DB,
                        )
                    if row:
                        count += int(row.get("cnt", 0) or 0)
                except Exception:
                    pass
                data_counts.append(count)
            labels = [f"{int(d.split('-')[1])}/{int(d.split('-')[2])}" for d in dates]
            data = {"labels": labels, "values": data_counts}
            _TREND_MERGED_CACHE[user_id] = {"ts": now, "data": data}

        response = make_response(jsonify({"success": True, "data": data}))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


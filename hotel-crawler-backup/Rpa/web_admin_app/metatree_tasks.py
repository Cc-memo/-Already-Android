import json
import os
import sqlite3
import threading
import uuid
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from .constants import DATABASE_DIR, METATREE_ROOT, METATREE_TASK_DB


bp = Blueprint("metatree", __name__, url_prefix="/api/metatree")

METATREE_AVAILABLE = False
METATREE_IMPORT_ERROR: Optional[str] = None
metatree_crawl_hotel = None


def _now_str() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_metatree_task_db():
    os.makedirs(DATABASE_DIR, exist_ok=True)
    conn = sqlite3.connect(METATREE_TASK_DB)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metatree_tasks (
                task_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                hotel_name TEXT NOT NULL,
                platforms_json TEXT NOT NULL,
                use_graph INTEGER NOT NULL,
                username TEXT,
                error TEXT,
                result_json TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def try_import_metatree():
    global METATREE_AVAILABLE, METATREE_IMPORT_ERROR, metatree_crawl_hotel
    METATREE_AVAILABLE = False
    METATREE_IMPORT_ERROR = None
    metatree_crawl_hotel = None

    try:
        if os.path.isdir(METATREE_ROOT):
            import sys

            sys.path.insert(0, METATREE_ROOT)
            from crawler.main import crawl_hotel as _crawl_hotel  # type: ignore

            metatree_crawl_hotel = _crawl_hotel
            METATREE_AVAILABLE = True
        else:
            METATREE_IMPORT_ERROR = f"未找到 metatree 目录: {METATREE_ROOT}"
    except Exception as e:
        METATREE_IMPORT_ERROR = str(e)


def create_task(hotel_name: str, platforms: List[str], use_graph: bool, username: Optional[str]) -> Dict:
    task_id = str(uuid.uuid4())
    now = _now_str()

    conn = sqlite3.connect(METATREE_TASK_DB)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO metatree_tasks
                (task_id, created_at, updated_at, status, hotel_name, platforms_json, use_graph, username, error, result_json)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                now,
                now,
                "queued",
                hotel_name,
                json.dumps(platforms, ensure_ascii=False),
                1 if use_graph else 0,
                username,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return get_task(task_id)  # type: ignore


def update_task(task_id: str, **fields) -> None:
    allowed = {"updated_at", "status", "error", "result_json"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now_str()
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    params = list(updates.values()) + [task_id]

    conn = sqlite3.connect(METATREE_TASK_DB)
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE metatree_tasks SET {set_clause} WHERE task_id = ?", params)
        conn.commit()
    finally:
        conn.close()


def get_task(task_id: str) -> Optional[Dict]:
    conn = sqlite3.connect(METATREE_TASK_DB)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM metatree_tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        task = dict(row)
        task["platforms"] = json.loads(task.pop("platforms_json") or "[]")
        task["use_graph"] = bool(task.get("use_graph"))
        if task.get("result_json"):
            try:
                task["result"] = json.loads(task["result_json"])
            except Exception:
                task["result"] = None
        else:
            task["result"] = None
        task.pop("result_json", None)
        return task
    finally:
        conn.close()


def list_tasks(limit: int = 50, username: Optional[str] = None) -> List[Dict]:
    conn = sqlite3.connect(METATREE_TASK_DB)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if username:
            cursor.execute("SELECT * FROM metatree_tasks WHERE username = ? ORDER BY created_at DESC LIMIT ?", (username, limit))
        else:
            cursor.execute("SELECT * FROM metatree_tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        tasks: List[Dict] = []
        for row in rows:
            task = dict(row)
            task["platforms"] = json.loads(task.pop("platforms_json") or "[]")
            task["use_graph"] = bool(task.get("use_graph"))
            task.pop("result_json", None)
            tasks.append(task)
        return tasks
    finally:
        conn.close()


def _run_task(task_id: str, hotel_name: str, platforms: List[str], use_graph: bool, username: Optional[str], password: Optional[str]):
    if not METATREE_AVAILABLE or not metatree_crawl_hotel:
        update_task(task_id, status="failed", error=METATREE_IMPORT_ERROR or "metatree 不可用")
        return

    update_task(task_id, status="running", error=None)

    try:
        result = metatree_crawl_hotel(  # type: ignore[misc]
            hotel_name=hotel_name,
            platforms=platforms,
            username=username,
            password=password,
            need_detail=True,
            use_graph=use_graph,
        )
        update_task(
            task_id,
            status="success",
            result_json=json.dumps(result, ensure_ascii=False),
            error=None,
        )
    except Exception as e:
        update_task(task_id, status="failed", error=str(e))


@bp.get("/health")
def health():
    return jsonify(
        {
            "success": True,
            "data": {
                "available": METATREE_AVAILABLE,
                "metatree_root": METATREE_ROOT,
                "import_error": METATREE_IMPORT_ERROR,
            },
        }
    )


@bp.get("/tasks")
def api_list_tasks():
    try:
        from .auth import current_user
        
        # 获取当前登录用户
        user = current_user()
        username = user["username"] if user else None
        
        limit = int(request.args.get("limit", 50))
        tasks = list_tasks(limit=limit, username=username)
        return jsonify({"success": True, "data": tasks, "total": len(tasks)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/tasks")
def api_create_task():
    try:
        if not METATREE_AVAILABLE:
            return (
                jsonify({"success": False, "error": f"metatree 不可用: {METATREE_IMPORT_ERROR or 'unknown'}"}),
                400,
            )

        from .auth import current_user
        
        # 获取当前登录用户
        user = current_user()
        current_username = user["username"] if user else None

        data: Dict[str, Any] = request.get_json(force=True) or {}
        hotel_name = (data.get("hotel_name") or "").strip()
        platforms = data.get("platforms") or []
        use_graph = bool(data.get("use_graph", True))
        # 使用当前登录用户的username，而不是请求中的username（账户隔离）
        username = current_username or (data.get("username") or "").strip() or None
        password = (data.get("password") or "") or None

        if not hotel_name:
            return jsonify({"success": False, "error": "hotel_name 不能为空"}), 400
        if not isinstance(platforms, list) or not platforms:
            return jsonify({"success": False, "error": "platforms 必须是非空数组"}), 400

        allowed_platforms = {"meituan", "ctrip", "fliggy", "gaode"}
        platforms = [p for p in platforms if p in allowed_platforms]
        if not platforms:
            return jsonify({"success": False, "error": "platforms 无有效平台（meituan/ctrip/fliggy/gaode）"}), 400

        task = create_task(hotel_name=hotel_name, platforms=platforms, use_graph=use_graph, username=username)
        th = threading.Thread(
            target=_run_task,
            args=(task["task_id"], hotel_name, platforms, use_graph, username, password),
            daemon=True,
        )
        th.start()
        return jsonify({"success": True, "data": task})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/tasks/<task_id>")
def api_get_task(task_id: str):
    try:
        from .auth import current_user
        
        # 获取当前登录用户
        user = current_user()
        username = user["username"] if user else None
        
        task = get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        
        # 检查任务是否属于当前用户（账户隔离）
        if username and task.get("username") and task.get("username") != username:
            return jsonify({"success": False, "error": "无权访问此任务"}), 403
        
        return jsonify({"success": True, "data": task})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


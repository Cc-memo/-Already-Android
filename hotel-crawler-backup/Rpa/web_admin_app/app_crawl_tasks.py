# -*- coding: utf-8 -*-
"""
手机端任务：独立表 app_crawl_tasks、app_hotel_search_results，不影响原有 crawl_tasks。
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from .db import db

bp = Blueprint("app_crawl_tasks", __name__, url_prefix="/api/app-crawl-tasks")

APP_DB_NAME = "app_crawl_tasks.sqlite3"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_app_crawl_task_db():
    """初始化 app_crawl_tasks 表"""
    sql_sqlite = """
        CREATE TABLE IF NOT EXISTS app_crawl_tasks (
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
            user_id INTEGER,
            platform TEXT NOT NULL DEFAULT 'ctrip'
        )
    """
    sql_mysql = """
        CREATE TABLE IF NOT EXISTS app_crawl_tasks (
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
            user_id INT,
            platform VARCHAR(20) NOT NULL DEFAULT 'ctrip'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    conn = db.get_connection(APP_DB_NAME)
    try:
        cursor = conn.cursor()
        if db.config["db_type"] == "mysql":
            cursor.execute(sql_mysql)
            # 为已存在的表补列（兼容旧表或手动建表）
            for col, spec in [
                ("user_id", "INT"),
                ("platforms_json", "TEXT"),
                ("check_in", "VARCHAR(20)"),
                ("check_out", "VARCHAR(20)"),
                ("started_at", "VARCHAR(30)"),
                ("finished_at", "VARCHAR(30)"),
                ("progress", "INT NOT NULL DEFAULT 0"),
                ("current_platform", "VARCHAR(50)"),
                ("error", "TEXT"),
                ("results_json", "LONGTEXT"),
                ("platform", "VARCHAR(20) NOT NULL DEFAULT 'ctrip'"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE app_crawl_tasks ADD COLUMN {col} {spec}")
                except Exception:
                    pass
        else:
            cursor.execute(sql_sqlite)
            for col, spec in [
                ("user_id", "INTEGER"),
                ("platforms_json", "TEXT"),
                ("check_in", "TEXT"),
                ("check_out", "TEXT"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE app_crawl_tasks ADD COLUMN {col} {spec}")
                except Exception:
                    pass
        conn.commit()
    finally:
        conn.close()


def init_app_hotel_search_results_db():
    """初始化 app_hotel_search_results 表（存手机端任务的爬取结果）"""
    sql_sqlite = """
        CREATE TABLE IF NOT EXISTS app_hotel_search_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            results_json TEXT,
            created_at TEXT NOT NULL
        )
    """
    sql_mysql = """
        CREATE TABLE IF NOT EXISTS app_hotel_search_results (
            id INT AUTO_INCREMENT PRIMARY KEY,
            task_id VARCHAR(50) NOT NULL,
            results_json LONGTEXT,
            created_at VARCHAR(30) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    conn = db.get_connection(APP_DB_NAME)
    try:
        cursor = conn.cursor()
        if db.config["db_type"] == "mysql":
            cursor.execute(sql_mysql)
            # 兼容旧表：若表已存在但缺列，则逐列追加（列已存在则忽略）
            for col, col_def in [
                ("task_id", "VARCHAR(50) NOT NULL DEFAULT ''"),
                ("results_json", "LONGTEXT"),
                ("created_at", "VARCHAR(30) NOT NULL DEFAULT ''"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE app_hotel_search_results ADD COLUMN {col} {col_def}")
                    conn.commit()
                except Exception:
                    conn.rollback()
        else:
            cursor.execute(sql_sqlite)
            for col, col_def in [
                ("task_id", "TEXT NOT NULL DEFAULT ''"),
                ("results_json", "TEXT"),
                ("created_at", "TEXT NOT NULL DEFAULT ''"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE app_hotel_search_results ADD COLUMN {col} {col_def}")
                    conn.commit()
                except Exception:
                    conn.rollback()
        conn.commit()
    finally:
        conn.close()


def _row_to_task(row: Any) -> Dict:
    if hasattr(row, "keys"):
        d = dict(row)
    else:
        d = dict(row)
    d["platforms"] = json.loads(d.get("platforms_json") or "[]")
    d.pop("platforms_json", None)
    return d


# ---------- 需登录接口 ----------


@bp.post("")
def api_create():
    """创建手机端任务，body: hotels[], platforms[], location, check_in?, check_out?"""
    try:
        from .auth import current_user
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])

        data = request.get_json(force=True) or {}
        location = (data.get("location") or "").strip() or "上海"
        check_in = (data.get("check_in") or "").strip() or None
        check_out = (data.get("check_out") or "").strip() or None
        platforms = data.get("platforms") or []
        hotels = data.get("hotels") or []

        if not isinstance(hotels, list) or not hotels:
            return jsonify({"success": False, "error": "hotels 必须是非空数组"}), 400
        if not isinstance(platforms, list) or not platforms:
            return jsonify({"success": False, "error": "platforms 必须是非空数组"}), 400
        allowed = {"meituan", "ctrip", "fliggy", "gaode"}
        platforms = [p for p in platforms if str(p).strip().lower() in allowed]
        if not platforms:
            return jsonify({"success": False, "error": "platforms 无有效平台"}), 400

        now = _now_str()
        created = []
        for h in hotels:
            hotel_name = (str(h) or "").strip()
            if not hotel_name:
                continue
            task_id = str(uuid.uuid4())
            platforms_json = json.dumps(platforms, ensure_ascii=False)
            platform_first = (platforms[0] if platforms else "ctrip").strip().lower()
            db.execute(
                """INSERT INTO app_crawl_tasks
                   (task_id, created_at, updated_at, started_at, finished_at, status, hotel_name, location, check_in, check_out, platforms_json, progress, current_platform, error, results_json, user_id, platform)
                   VALUES (?, ?, ?, NULL, NULL, 'queued', ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, ?, ?)""",
                (task_id, now, now, hotel_name, location, check_in, check_out, platforms_json, user_id, platform_first),
                sqlite_name=APP_DB_NAME,
            )
            created.append({
                "task_id": task_id,
                "hotel_name": hotel_name,
                "location": location,
                "platforms": platforms,
                "status": "queued",
                "created_at": now,
            })
        return jsonify({"success": True, "data": created, "total": len(created)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("")
def api_list():
    """任务列表，当前用户"""
    try:
        from .auth import current_user
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])
        limit = int(request.args.get("limit", 50))

        rows = db.execute(
            "SELECT * FROM app_crawl_tasks WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
            sqlite_name=APP_DB_NAME,
        )
        tasks = [_row_to_task(r) for r in rows]
        return jsonify({"success": True, "data": tasks, "total": len(tasks)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ---------- 无需登录：给 scheduler 领任务 / 上报（必须写在 /<task_id> 之前） ----------


@bp.get("/claim")
def api_claim():
    """领一条 status=queued 的任务，原子更新为 running 并返回"""
    try:
        platform = (request.args.get("platform") or "").strip() or None
        conn = db.get_connection(APP_DB_NAME)
        try:
            cursor = conn.cursor()
            is_mysql = db.config["db_type"] == "mysql"
            ph = "%s" if is_mysql else "?"
            now = _now_str()
            where = "status = 'queued'"
            params = []
            if platform:
                where += " AND platforms_json LIKE " + ph
                params.append(f"%{platform}%")
            if is_mysql:
                conn.autocommit(False)
                try:
                    cursor.execute(
                        f"SELECT task_id FROM app_crawl_tasks WHERE {where} ORDER BY created_at ASC LIMIT 1 FOR UPDATE",
                        tuple(params),
                    )
                    row = cursor.fetchone()
                    if not row:
                        conn.rollback()
                        return jsonify({"success": True, "task": None})
                    task_id = row["task_id"] if isinstance(row, dict) else row[0]
                    cursor.execute(
                        "UPDATE app_crawl_tasks SET status = 'running', updated_at = %s, started_at = %s WHERE task_id = %s",
                        (now, now, task_id),
                    )
                    cursor.execute("SELECT * FROM app_crawl_tasks WHERE task_id = %s", (task_id,))
                    row = cursor.fetchone()
                    conn.commit()
                finally:
                    conn.autocommit(True)
            else:
                cursor.execute(f"SELECT * FROM app_crawl_tasks WHERE {where} ORDER BY created_at ASC LIMIT 1", tuple(params))
                row = cursor.fetchone()
                if not row:
                    return jsonify({"success": True, "task": None})
                row = dict(row)
                task_id = row["task_id"]
                cursor.execute(
                    "UPDATE app_crawl_tasks SET status = 'running', updated_at = ?, started_at = ? WHERE task_id = ?",
                    (now, now, task_id),
                )
                conn.commit()
                cursor.execute("SELECT * FROM app_crawl_tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                row = dict(row) if row else None

            if not row:
                return jsonify({"success": True, "task": None})
            task = _row_to_task(row)
            platforms = task.get("platforms") or []
            task["platform"] = (platforms[0] if platforms else "ctrip").lower()
            return jsonify({"success": True, "task": task})
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/report")
def api_report():
    """上报结果，body: task_id, success, result?, error?"""
    try:
        data = request.get_json(force=True) or {}
        task_id = (data.get("task_id") or "").strip()
        success = data.get("success", True)
        result = data.get("result")
        error_msg = (data.get("error") or "").strip()
        if not task_id:
            return jsonify({"success": False, "error": "缺少 task_id"}), 400
        now = _now_str()
        status = "success" if success else "failed"
        results_json = json.dumps(result, ensure_ascii=False) if result is not None else None

        db.execute(
            "UPDATE app_crawl_tasks SET status = ?, updated_at = ?, finished_at = ?, results_json = ?, error = ? WHERE task_id = ?",
            (status, now, now, results_json, error_msg or None, task_id),
            sqlite_name=APP_DB_NAME,
        )
        # 仅在有结果时写入 app_hotel_search_results（失败时 result 可能为 None，部分库不允许 results_json 为 NULL）
        if results_json is not None:
            try:
                db.execute(
                    "INSERT INTO app_hotel_search_results (task_id, results_json, created_at) VALUES (?, ?, ?)",
                    (task_id, results_json, now),
                    sqlite_name=APP_DB_NAME,
                )
            except Exception as e:
                msg = str(e).lower()
                # 兼容历史 MySQL 结果表（含 app_name/task_type/hotel_name/room_details_json 等必填列）
                if ("app_name" in msg) or ("task_type" in msg) or ("room_details_json" in msg):
                    task_row = db.query_one(
                        "SELECT hotel_name, location FROM app_crawl_tasks WHERE task_id = ?",
                        (task_id,),
                        sqlite_name=APP_DB_NAME,
                    )
                    hotel_name = ""
                    city = None
                    if task_row:
                        hotel_name = (getattr(task_row, "hotel_name", None) or (task_row.get("hotel_name") if hasattr(task_row, "get") else "")) or ""
                        city = getattr(task_row, "location", None) or (task_row.get("location") if hasattr(task_row, "get") else None)
                    if not hotel_name and isinstance(result, dict):
                        hotel_name = (result.get("hotel_name") or "").strip()
                    room_details_json = "[]"
                    if isinstance(result, dict):
                        if isinstance(result.get("room_details"), (list, dict)):
                            room_details_json = json.dumps(result.get("room_details"), ensure_ascii=False)
                        elif isinstance(result.get("data"), (list, dict)):
                            room_details_json = json.dumps(result.get("data"), ensure_ascii=False)
                    db.execute(
                        "INSERT INTO app_hotel_search_results (created_at, app_name, task_type, city, hotel_name, room_details_json, raw_response, status, error_message, results_json, task_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            now,
                            "mobile",
                            "app_crawl",
                            city,
                            hotel_name or "unknown",
                            room_details_json,
                            results_json,
                            status,
                            error_msg or None,
                            results_json,
                            task_id,
                        ),
                        sqlite_name=APP_DB_NAME,
                    )
                else:
                    raise
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ---------- 需登录 ----------


@bp.delete("/<task_id>")
def api_delete(task_id: str):
    """删除任务（仅当前用户），并删除关联结果数据"""
    try:
        from .auth import current_user
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])

        row = db.query_one(
            "SELECT task_id FROM app_crawl_tasks WHERE task_id = ? AND user_id = ?",
            (task_id, user_id),
            sqlite_name=APP_DB_NAME,
        )
        if not row:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        db.execute(
            "DELETE FROM app_hotel_search_results WHERE task_id = ?",
            (task_id,),
            sqlite_name=APP_DB_NAME,
        )
        db.execute(
            "DELETE FROM app_crawl_tasks WHERE task_id = ? AND user_id = ?",
            (task_id, user_id),
            sqlite_name=APP_DB_NAME,
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/<task_id>")
def api_get(task_id: str):
    """任务详情"""
    try:
        from .auth import current_user
        user = current_user()
        if not user or not isinstance(user, dict) or "id" not in user:
            return jsonify({"success": False, "error": "未登录"}), 401
        user_id = int(user["id"])

        row = db.query_one("SELECT * FROM app_crawl_tasks WHERE task_id = ? AND user_id = ?", (task_id, user_id), sqlite_name=APP_DB_NAME)
        if not row:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        data = _row_to_task(row)
        # 查询该任务的上报结果（成功时写入 app_hotel_search_results）
        result_row = db.query_one(
            "SELECT results_json, created_at FROM app_hotel_search_results WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
            sqlite_name=APP_DB_NAME,
        )
        results_json_raw = None
        if result_row:
            results_json_raw = getattr(result_row, "results_json", None) or (result_row.get("results_json") if hasattr(result_row, "get") else None)
        if results_json_raw:
            try:
                data["result"] = json.loads(results_json_raw)
            except Exception:
                data["result"] = results_json_raw
            data["result_at"] = getattr(result_row, "created_at", None) or (result_row.get("created_at") if hasattr(result_row, "get") else None) if result_row else None
        else:
            data["result"] = None
            data["result_at"] = None
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

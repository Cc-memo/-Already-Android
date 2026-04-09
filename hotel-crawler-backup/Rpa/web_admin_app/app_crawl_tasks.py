# -*- coding: utf-8 -*-
"""
手机端任务：独立表 app_crawl_tasks、app_hotel_search_results，不影响原有 crawl_tasks。
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from .db import db
from .auth import require_role, ROLE_OPERATOR, ROLE_ADMIN, ROLE_SUPER_ADMIN

bp = Blueprint("app_crawl_tasks", __name__, url_prefix="/api/app-crawl-tasks")

APP_DB_NAME = "app_crawl_tasks.sqlite3"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _dt_to_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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

def init_app_crawl_cooldown_db():
    """
    初始化 app_crawl_cooldowns 表：
    - 以 (user_id, platform) 作为唯一键，记录该账号在该平台“上次上报完成时间”
    - 用于 claim 时做冷却过滤（节流）
    """
    sql_sqlite = """
        CREATE TABLE IF NOT EXISTS app_crawl_cooldowns (
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            last_reported_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, platform)
        )
    """
    sql_mysql = """
        CREATE TABLE IF NOT EXISTS app_crawl_cooldowns (
            user_id INT NOT NULL,
            platform VARCHAR(20) NOT NULL,
            last_reported_at VARCHAR(30) NOT NULL,
            updated_at VARCHAR(30) NOT NULL,
            PRIMARY KEY (user_id, platform)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    conn = db.get_connection(APP_DB_NAME)
    try:
        cursor = conn.cursor()
        if db.config["db_type"] == "mysql":
            cursor.execute(sql_mysql)
        else:
            cursor.execute(sql_sqlite)
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
            # 方案A：拆成“单平台任务”
            # 同一酒店如果选择了多个 platforms，则为每个平台创建一条独立 task，
            # 这样 scheduler 可以按 platform 轮询并对每个平台做独立冷却控制。
            for p in platforms:
                p = str(p or "").strip().lower()
                if not p:
                    continue
                task_id = str(uuid.uuid4())
                platforms_json = json.dumps([p], ensure_ascii=False)
                db.execute(
                    """INSERT INTO app_crawl_tasks
                       (task_id, created_at, updated_at, started_at, finished_at, status, hotel_name, location, check_in, check_out, platforms_json, progress, current_platform, error, results_json, user_id, platform)
                       VALUES (?, ?, ?, NULL, NULL, 'queued', ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, ?, ?)""",
                    (task_id, now, now, hotel_name, location, check_in, check_out, platforms_json, user_id, p),
                    sqlite_name=APP_DB_NAME,
                )
                created.append({
                    "task_id": task_id,
                    "hotel_name": hotel_name,
                    "location": location,
                    "platforms": [p],
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
        # 冷却（秒）：默认 120 秒 = 2 分钟
        cooldown_sec = int(request.args.get("cooldown_sec") or 0) or int(
            request.args.get("cooldown") or 0
        ) or int(
            # env 可用于全局配置
            os.environ.get("APP_CRAWL_PLATFORM_COOLDOWN_SEC", "120")
        )
        # running 超时回收（秒）：默认 15 分钟
        running_timeout_sec = int(
            os.environ.get("APP_CRAWL_RUNNING_TIMEOUT_SEC", str(15 * 60))
        )
        conn = db.get_connection(APP_DB_NAME)
        try:
            cursor = conn.cursor()
            is_mysql = db.config["db_type"] == "mysql"
            ph = "%s" if is_mysql else "?"
            now = _now_str()
            now_dt = datetime.now()

            # 0) 确保冷却表存在：云端若未重启或未初始化，避免直接 500
            cooldown_table_ok = True
            try:
                if is_mysql:
                    cursor.execute("SELECT 1 FROM app_crawl_cooldowns LIMIT 1")
                else:
                    cursor.execute("SELECT 1 FROM app_crawl_cooldowns LIMIT 1")
            except Exception:
                cooldown_table_ok = False
                try:
                    init_app_crawl_cooldown_db()
                    cooldown_table_ok = True
                except Exception:
                    cooldown_table_ok = False

            # 1) running 超时回收：started_at 过久未完成的任务回到 queued，避免“卡死”
            try:
                cutoff_dt = now_dt - timedelta(seconds=running_timeout_sec)
                cutoff = _dt_to_str(cutoff_dt)
                if is_mysql:
                    cursor.execute(
                        "UPDATE app_crawl_tasks SET status='queued', updated_at=%s, error=%s "
                        "WHERE status='running' AND started_at IS NOT NULL AND started_at < %s",
                        (now, "requeued: running timeout", cutoff),
                    )
                else:
                    cursor.execute(
                        "UPDATE app_crawl_tasks SET status='queued', updated_at=?, error=? "
                        "WHERE status='running' AND started_at IS NOT NULL AND started_at < ?",
                        (now, "requeued: running timeout", cutoff),
                    )
                conn.commit()
            except Exception:
                # 不阻塞 claim；回收失败就忽略
                pass

            # where 子句：JOIN 场景必须加表别名（避免 platform 字段歧义）
            where_plain = "status = 'queued'"
            where_t = "t.status = 'queued'"
            params = []
            if platform:
                # 任务表里同时有 platform 列与 platforms_json（历史兼容）；优先用 platform
                where_plain += f" AND (platform = {ph} OR platforms_json LIKE {ph})"
                where_t += f" AND (t.platform = {ph} OR t.platforms_json LIKE {ph})"
                params.extend([platform, f"%{platform}%"])

            # 2) 冷却过滤：根据 (user_id, platform) 的 last_reported_at 过滤掉未到点的任务
            eligible_cutoff_dt = now_dt - timedelta(seconds=cooldown_sec)
            eligible_cutoff = _dt_to_str(eligible_cutoff_dt)

            if is_mysql:
                conn.autocommit(False)
                try:
                    if cooldown_table_ok:
                        cursor.execute(f"""
                            SELECT t.task_id
                            FROM app_crawl_tasks t
                            LEFT JOIN app_crawl_cooldowns c
                              ON c.user_id = t.user_id AND c.platform = t.platform
                            WHERE {where_t}
                              AND (c.last_reported_at IS NULL OR c.last_reported_at <= %s)
                            ORDER BY t.created_at ASC
                            LIMIT 1
                            FOR UPDATE
                        """, tuple(params + [eligible_cutoff]))
                    else:
                        # 冷却表不可用则降级：按旧逻辑直接取 queued
                        cursor.execute(
                            f"SELECT task_id FROM app_crawl_tasks WHERE {where_plain} ORDER BY created_at ASC LIMIT 1 FOR UPDATE",
                            tuple(params),
                        )
                    row = cursor.fetchone()
                    if not row:
                        conn.rollback()
                        # 判断是否“队列为空”还是“被冷却挡住”
                        cursor.execute(
                            f"SELECT COUNT(1) FROM app_crawl_tasks WHERE {where_plain}",
                            tuple(params),
                        )
                        cnt_row = cursor.fetchone()
                        queued_count = 0
                        if cnt_row is not None:
                            if isinstance(cnt_row, dict):
                                # 兼容不同 driver 的列名
                                queued_count = (
                                    cnt_row.get("COUNT(1)")
                                    or cnt_row.get("count(1)")
                                    or cnt_row.get("COUNT(*)")
                                    or cnt_row.get("count(*)")
                                    or 0
                                )
                            else:
                                queued_count = (cnt_row[0] if isinstance(cnt_row, (list, tuple)) and cnt_row else 0) or 0
                        if queued_count <= 0:
                            return jsonify({"success": True, "task": None})

                        if not cooldown_table_ok:
                            # 冷却表不可用时，不返回 cooldown（避免误导）
                            return jsonify({"success": True, "task": None})

                        # 计算 next_ready_at：找一批最早的 queued 任务，对照冷却表求最小 next_ready
                        cursor.execute(
                            f"SELECT user_id, platform FROM app_crawl_tasks WHERE {where_plain} ORDER BY created_at ASC LIMIT 100",
                            tuple(params),
                        )
                        pairs = cursor.fetchall() or []
                        # 去重
                        uniq = []
                        seen = set()
                        for r in pairs:
                            uid = r.get("user_id") if isinstance(r, dict) else r[0]
                            plat = r.get("platform") if isinstance(r, dict) else r[1]
                            key = (int(uid or 0), str(plat or ""))
                            if key in seen:
                                continue
                            seen.add(key)
                            uniq.append(key)
                        next_ready_at = None
                        if uniq:
                            # 查询冷却表
                            # 逐个查（数量<=100，简单可靠）
                            for uid, plat in uniq:
                                cursor.execute(
                                    "SELECT last_reported_at FROM app_crawl_cooldowns WHERE user_id=%s AND platform=%s",
                                    (uid, plat),
                                )
                                cr = cursor.fetchone()
                                last = (cr.get("last_reported_at") if isinstance(cr, dict) else (cr[0] if cr else None)) if cr else None
                                if not last:
                                    # 没有冷却记录意味着可立即执行；但这里未选出 eligible 行，说明多半平台/字段异常，兜底 next_ready=now
                                    cand = now
                                else:
                                    try:
                                        last_dt = datetime.strptime(str(last), "%Y-%m-%d %H:%M:%S")
                                        cand = _dt_to_str(last_dt + timedelta(seconds=cooldown_sec))
                                    except Exception:
                                        cand = now
                                if (next_ready_at is None) or (cand < next_ready_at):
                                    next_ready_at = cand
                        return jsonify({"success": True, "task": None, "reason": "cooldown", "next_ready_at": next_ready_at})
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
                if cooldown_table_ok:
                    cursor.execute(f"""
                        SELECT t.*
                        FROM app_crawl_tasks t
                        LEFT JOIN app_crawl_cooldowns c
                          ON c.user_id = t.user_id AND c.platform = t.platform
                        WHERE {where_t}
                          AND (c.last_reported_at IS NULL OR c.last_reported_at <= ?)
                        ORDER BY t.created_at ASC
                        LIMIT 1
                    """, tuple(params + [eligible_cutoff]))
                else:
                    cursor.execute(
                        f"SELECT * FROM app_crawl_tasks WHERE {where_plain} ORDER BY created_at ASC LIMIT 1",
                        tuple(params),
                    )
                row = cursor.fetchone()
                if not row:
                    cursor.execute(f"SELECT COUNT(1) FROM app_crawl_tasks WHERE {where_plain}", tuple(params))
                    cnt_row = cursor.fetchone()
                    queued_count = (cnt_row[0] if cnt_row else 0) or 0
                    if queued_count <= 0:
                        return jsonify({"success": True, "task": None})

                    if not cooldown_table_ok:
                        return jsonify({"success": True, "task": None})

                    cursor.execute(
                        f"SELECT user_id, platform FROM app_crawl_tasks WHERE {where_plain} ORDER BY created_at ASC LIMIT 100",
                        tuple(params),
                    )
                    pairs = cursor.fetchall() or []
                    uniq = []
                    seen = set()
                    for r in pairs:
                        uid = r[0]
                        plat = r[1]
                        key = (int(uid or 0), str(plat or ""))
                        if key in seen:
                            continue
                        seen.add(key)
                        uniq.append(key)
                    next_ready_at = None
                    if uniq:
                        for uid, plat in uniq:
                            cursor.execute(
                                "SELECT last_reported_at FROM app_crawl_cooldowns WHERE user_id=? AND platform=?",
                                (uid, plat),
                            )
                            cr = cursor.fetchone()
                            last = (cr[0] if cr else None) if cr else None
                            if not last:
                                cand = now
                            else:
                                try:
                                    last_dt = datetime.strptime(str(last), "%Y-%m-%d %H:%M:%S")
                                    cand = _dt_to_str(last_dt + timedelta(seconds=cooldown_sec))
                                except Exception:
                                    cand = now
                            if (next_ready_at is None) or (cand < next_ready_at):
                                next_ready_at = cand
                    return jsonify({"success": True, "task": None, "reason": "cooldown", "next_ready_at": next_ready_at})

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

        # 更新冷却表：按 (user_id, platform) 记录上次上报完成时间（无论 success/failed 都更新）
        try:
            # 冷却表可能尚未初始化（云端热更新/漏重启）；兜底自动创建
            try:
                init_app_crawl_cooldown_db()
            except Exception:
                pass
            task_row = db.query_one(
                "SELECT user_id, platform FROM app_crawl_tasks WHERE task_id = ?",
                (task_id,),
                sqlite_name=APP_DB_NAME,
            )
            uid = None
            plat = None
            if task_row:
                uid = getattr(task_row, "user_id", None) or (task_row.get("user_id") if hasattr(task_row, "get") else None)
                plat = getattr(task_row, "platform", None) or (task_row.get("platform") if hasattr(task_row, "get") else None)
            if uid is not None and plat:
                # sqlite: INSERT OR REPLACE；mysql: ON DUPLICATE KEY UPDATE
                if db.config["db_type"] == "mysql":
                    db.execute(
                        "INSERT INTO app_crawl_cooldowns (user_id, platform, last_reported_at, updated_at) "
                        "VALUES (%s, %s, %s, %s) "
                        "ON DUPLICATE KEY UPDATE last_reported_at=VALUES(last_reported_at), updated_at=VALUES(updated_at)",
                        (int(uid), str(plat), now, now),
                        sqlite_name=APP_DB_NAME,
                    )
                else:
                    db.execute(
                        "INSERT OR REPLACE INTO app_crawl_cooldowns (user_id, platform, last_reported_at, updated_at) VALUES (?, ?, ?, ?)",
                        (int(uid), str(plat), now, now),
                        sqlite_name=APP_DB_NAME,
                    )
        except Exception:
            # 冷却更新失败不影响 report 主流程
            pass

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

@bp.post("/admin/clear-queued")
@require_role(ROLE_OPERATOR, ROLE_ADMIN, ROLE_SUPER_ADMIN)
def api_admin_clear_queued():
    """
    【管理员接口】清空全库 queued 任务（可选按 platform 过滤）。

    说明：
    - 用于云端调试/环境清理：claim 不按账号过滤时，历史 queued 会干扰调试
    - 仅允许 operator/admin/super_admin 调用（需登录）
    - 默认仅清 status=queued，不动 running/success/failed
    - 可选 include_running=true，一并清理 running（注意：不会停止手机端正在执行的进程，只是清理服务端记录）
    """
    try:
        platform = (request.args.get("platform") or "").strip().lower() or None
        include_running = (request.args.get("include_running") or "").strip().lower() in ("1", "true", "yes", "y")
        conn = db.get_connection(APP_DB_NAME)
        try:
            cursor = conn.cursor()
            is_mysql = db.config["db_type"] == "mysql"
            ph = "%s" if is_mysql else "?"

            statuses = ["queued"]
            if include_running:
                statuses.append("running")
            if is_mysql:
                in_ph = ",".join(["%s"] * len(statuses))
            else:
                in_ph = ",".join(["?"] * len(statuses))
            where = f"status IN ({in_ph})"
            params = []
            params.extend(statuses)
            if platform:
                where += f" AND platform = {ph}"
                params.append(platform)

            # 先统计再删除，返回 deleted_count
            if is_mysql:
                cursor.execute(f"SELECT COUNT(1) AS c FROM app_crawl_tasks WHERE {where}", tuple(params))
                row = cursor.fetchone()
                before = (row.get("c") if isinstance(row, dict) else row[0]) if row else 0
                cursor.execute(f"DELETE FROM app_crawl_tasks WHERE {where}", tuple(params))
                conn.commit()
            else:
                cursor.execute(f"SELECT COUNT(1) AS c FROM app_crawl_tasks WHERE {where}", tuple(params))
                row = cursor.fetchone()
                before = (row["c"] if isinstance(row, sqlite3.Row) else row[0]) if row else 0
                cursor.execute(f"DELETE FROM app_crawl_tasks WHERE {where}", tuple(params))
                conn.commit()

            return jsonify({"success": True, "deleted": int(before), "platform": platform, "include_running": include_running})
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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

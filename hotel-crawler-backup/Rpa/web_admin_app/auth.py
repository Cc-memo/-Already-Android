import os
from functools import wraps
from typing import Dict, Optional, List

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .constants import AUTH_DB
from .db import db

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# 角色常量
ROLE_USER = "user"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"  # 超级管理员

# 状态常量
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"


def _now_str() -> str:
    # 延迟导入避免循环
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_auth_db():
    # SQLite 建表
    sql_sqlite = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            real_name TEXT,
            email TEXT,
            phone TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            last_login_at TEXT
        )
    """
    # MySQL 建表
    sql_mysql = """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            real_name VARCHAR(100),
            email VARCHAR(255),
            phone VARCHAR(20),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at VARCHAR(30) NOT NULL,
            updated_at VARCHAR(30),
            last_login_at VARCHAR(30)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """

    conn = db.get_connection("auth.sqlite3")
    try:
        cursor = conn.cursor()
        if db.config['db_type'] == 'mysql':
            cursor.execute(sql_mysql)
        else:
            cursor.execute(sql_sqlite)
        
        # 迁移现有表：添加新字段（如果不存在）
        _migrate_user_table(cursor, conn)
        
        if db.config['db_type'] == 'sqlite':
            conn.commit()
    finally:
        conn.close()


def _migrate_user_table(cursor, conn):
    """迁移用户表，添加新字段"""
    db_type = db.config['db_type']
    
    # 需要添加的字段列表
    new_fields = [
        ('real_name', 'TEXT' if db_type == 'sqlite' else 'VARCHAR(100)'),
        ('email', 'TEXT' if db_type == 'sqlite' else 'VARCHAR(255)'),
        ('phone', 'TEXT' if db_type == 'sqlite' else 'VARCHAR(20)'),
        ('status', 'TEXT' if db_type == 'sqlite' else 'VARCHAR(20)'),
        ('updated_at', 'TEXT' if db_type == 'sqlite' else 'VARCHAR(30)'),
    ]
    
    for field_name, field_type in new_fields:
        try:
            if db_type == 'sqlite':
                # SQLite 使用 ALTER TABLE ADD COLUMN
                cursor.execute(f"ALTER TABLE users ADD COLUMN {field_name} {field_type}")
            else:
                # MySQL 检查字段是否存在
                cursor.execute(f"""
                    SELECT COUNT(*) FROM information_schema.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'users' 
                    AND COLUMN_NAME = '{field_name}'
                """)
                if cursor.fetchone()[0] == 0:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {field_name} {field_type}")
            
            if db_type == 'sqlite':
                conn.commit()
        except Exception as e:
            # 字段可能已存在，忽略错误
            pass
    
    # 为现有用户设置默认状态（兼容旧数据）
    try:
        # 检查 status 字段是否存在（通过尝试查询来判断）
        try:
            # 尝试查询 status 字段，如果字段不存在会抛出异常
            cursor.execute("SELECT status FROM users LIMIT 1")
            
            # 字段存在，更新所有 status 为 NULL 或空字符串的用户
            if db_type == 'sqlite':
                cursor.execute("UPDATE users SET status = ? WHERE status IS NULL OR status = ''", (STATUS_ACTIVE,))
            else:
                cursor.execute("UPDATE users SET status = ? WHERE status IS NULL OR status = ''", (STATUS_ACTIVE,))
            
            if db_type == 'sqlite':
                conn.commit()
        except Exception:
            # 字段不存在，跳过更新（字段会在上面的循环中添加）
            pass
    except Exception as e:
        # 如果更新失败，忽略错误
        pass


def _get_user_by_username(username: str) -> Optional[Dict]:
    row = db.query_one(
        "SELECT * FROM users WHERE username = ?",
        (username,),
        sqlite_name="auth.sqlite3"
    )
    if not row:
        return None
    # 确保返回字典类型
    if isinstance(row, dict):
        return row
    elif hasattr(row, 'keys'):
        return dict(row)
    else:
        return None


def _get_user_by_id(user_id: int) -> Optional[Dict]:
    row = db.query_one(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
        sqlite_name="auth.sqlite3"
    )
    if not row:
        return None
    # 确保返回字典类型
    if isinstance(row, dict):
        return row
    elif hasattr(row, 'keys'):
        return dict(row)
    else:
        return None


def _create_user(username: str, password: str, role: str = "user", 
                 real_name: Optional[str] = None, email: Optional[str] = None, 
                 phone: Optional[str] = None, status: str = STATUS_ACTIVE) -> Dict:
    now = _now_str()
    pwd_hash = generate_password_hash(password)

    user_id = db.execute(
        """
        INSERT INTO users (username, password_hash, role, real_name, email, phone, status, created_at, updated_at, last_login_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (username, pwd_hash, role, real_name, email, phone, status, now, now, None),
        sqlite_name="auth.sqlite3"
    )

    user = _get_user_by_id(int(user_id))
    if not user:
        raise RuntimeError("创建用户失败")
    return user


def _touch_last_login(user_id: int) -> None:
    db.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?",
        (_now_str(), user_id),
        sqlite_name="auth.sqlite3"
    )


def current_user() -> Optional[Dict]:
    uid = session.get("user_id")
    if not uid:
        return None
    return _get_user_by_id(int(uid))


def require_role(*allowed_roles):
    """角色权限装饰器，用于限制只有特定角色的用户才能访问"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"success": False, "error": "未登录"}), 401
            
            # 检查用户状态（如果status不存在，默认为active，兼容旧数据）
            user_status = user.get("status", STATUS_ACTIVE)
            if user_status and user_status != STATUS_ACTIVE:
                return jsonify({"success": False, "error": "账户已禁用"}), 403
            
            # 检查角色权限
            user_role = user.get("role", ROLE_USER)
            # 超级管理员拥有所有权限
            if user_role == ROLE_SUPER_ADMIN or user_role in allowed_roles:
                return f(*args, **kwargs)
            
            return jsonify({"success": False, "error": "权限不足"}), 403
        return decorated_function
    return decorator


def _can_manage_user(operator: Dict, target_user: Dict) -> tuple[bool, str]:
    """
    检查操作者是否可以管理目标用户
    返回: (是否可以管理, 错误信息)
    """
    operator_role = operator.get("role", ROLE_USER)
    target_role = target_user.get("role", ROLE_USER)
    
    # 超级管理员可以管理所有用户（包括其他超级管理员）
    if operator_role == ROLE_SUPER_ADMIN:
        return (True, "")
    
    # 普通管理员只能管理普通用户和操作员，不能管理管理员和超级管理员
    if operator_role == ROLE_ADMIN:
        if target_role in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            return (False, "普通管理员不能管理其他管理员")
        return (True, "")
    
    # 其他角色不能管理用户
    return (False, "权限不足，只有管理员可以管理用户")


@bp.post("/register")
def register():
    try:
        data = request.get_json(force=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        password2 = data.get("password2") or ""

        if not username:
            return jsonify({"success": False, "error": "username 不能为空"}), 400
        if len(username) < 3:
            return jsonify({"success": False, "error": "username 至少 3 位"}), 400
        if not password:
            return jsonify({"success": False, "error": "password 不能为空"}), 400
        if len(password) < 6:
            return jsonify({"success": False, "error": "password 至少 6 位"}), 400
        if password != password2:
            return jsonify({"success": False, "error": "两次密码不一致"}), 400

        if _get_user_by_username(username):
            return jsonify({"success": False, "error": "用户名已存在"}), 400

        user = _create_user(username=username, password=password, role="user")
        return jsonify(
            {
                "success": True,
                "data": {
                    "id": user["id"],
                    "username": user["username"],
                    "role": user.get("role", "user"),
                    "created_at": user.get("created_at"),
                },
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/login")
def login():
    try:
        data = request.get_json(force=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        if not username or not password:
            return jsonify({"success": False, "error": "用户名或密码不能为空"}), 400

        user = _get_user_by_username(username)
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"success": False, "error": "用户名或密码错误"}), 400

        # 检查用户状态
        user_status = user.get("status", STATUS_ACTIVE)
        if user_status != STATUS_ACTIVE:
            return jsonify({"success": False, "error": "账户已禁用，请联系管理员"}), 403

        session["user_id"] = int(user["id"])
        session["username"] = user["username"]
        session["role"] = user.get("role", ROLE_USER)
        _touch_last_login(int(user["id"]))

        return jsonify(
            {
                "success": True,
                "data": {"id": user["id"], "username": user["username"], "role": user.get("role", ROLE_USER)},
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"success": True, "data": True})


@bp.get("/me")
def me():
    user = current_user()
    if not user:
        return jsonify({"success": False, "error": "未登录"}), 401
    return jsonify(
        {
            "success": True,
            "data": {
                "id": user["id"],
                "username": user["username"],
                "real_name": user.get("real_name") or "",
                "email": user.get("email") or "",
                "phone": user.get("phone") or "",
                "role": user.get("role", "user"),
                "status": user.get("status", STATUS_ACTIVE),
                "created_at": user.get("created_at"),
                "updated_at": user.get("updated_at"),
                "last_login_at": user.get("last_login_at"),
            },
        }
    )


def require_login_for_api():
    """
    全局 API 登录检查（before_request）
    - 检查是否登录
    - 检查用户是否被禁用
    """
    path = request.path or ""
    if not path.startswith("/api/"):
        return None
    if path.startswith("/api/auth/") or path == "/api/metatree/health":
        return None
    if path in ("/api/app-crawl-tasks/claim", "/api/app-crawl-tasks/report"):
        return None

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "未登录"}), 401
    
    # 检查用户状态（每次请求都从数据库获取最新状态）
    user = _get_user_by_id(int(user_id))
    if not user:
        # 用户不存在（可能被删除），清除 session
        session.clear()
        return jsonify({"success": False, "error": "用户不存在，请重新登录"}), 401
    
    user_status = user.get("status", STATUS_ACTIVE)
    if user_status and user_status != STATUS_ACTIVE:
        # 用户被禁用，清除 session 并阻止访问
        session.clear()
        return jsonify({"success": False, "error": "账户已禁用，请联系管理员"}), 403
    
    return None


# ==================== 用户管理 API（仅管理员） ====================

def _count_admin_users(exclude_user_id: Optional[int] = None, include_super_admin: bool = True) -> int:
    """统计管理员数量（包括超级管理员）"""
    roles = [ROLE_ADMIN]
    if include_super_admin:
        roles.append(ROLE_SUPER_ADMIN)
    
    if exclude_user_id:
        placeholders = ','.join(['?'] * len(roles))
        result = db.query_one(
            f"SELECT COUNT(*) as count FROM users WHERE role IN ({placeholders}) AND id != ?",
            tuple(roles) + (exclude_user_id,),
            sqlite_name="auth.sqlite3"
        )
    else:
        placeholders = ','.join(['?'] * len(roles))
        result = db.query_one(
            f"SELECT COUNT(*) as count FROM users WHERE role IN ({placeholders})",
            tuple(roles),
            sqlite_name="auth.sqlite3"
        )
    
    if isinstance(result, dict):
        return int(result.get("count", 0))
    elif isinstance(result, (list, tuple)):
        return int(result[0])
    else:
        return 0


def _sanitize_user_data(user: Dict) -> Dict:
    """清理用户数据，移除敏感信息"""
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "real_name": user.get("real_name") or "",
        "email": user.get("email") or "",
        "phone": user.get("phone") or "",
        "role": user.get("role", ROLE_USER),
        "status": user.get("status", STATUS_ACTIVE),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "last_login_at": user.get("last_login_at"),
    }


def _get_role_display_name(role: str) -> str:
    """获取角色的显示名称"""
    role_map = {
        ROLE_USER: "普通用户",
        ROLE_OPERATOR: "操作员",
        ROLE_ADMIN: "管理员",
        ROLE_SUPER_ADMIN: "超级管理员",
    }
    return role_map.get(role, role)


@bp.get("/users")
@require_role(ROLE_ADMIN)
def list_users():
    """获取用户列表（支持筛选、分页、排序）"""
    try:
        # 获取查询参数
        keyword = request.args.get("keyword", "").strip()
        role_filter = request.args.get("role", "").strip()
        status_filter = request.args.get("status", "").strip()
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")
        
        # 构建查询条件
        conditions = []
        params = []
        
        if keyword:
            conditions.append("(username LIKE ? OR real_name LIKE ? OR email LIKE ?)")
            keyword_pattern = f"%{keyword}%"
            params.extend([keyword_pattern, keyword_pattern, keyword_pattern])
        
        if role_filter:
            conditions.append("role = ?")
            params.append(role_filter)
        
        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 排序
        allowed_sort_fields = ["id", "username", "real_name", "role", "status", "created_at", "last_login_at"]
        if sort_by not in allowed_sort_fields:
            sort_by = "created_at"
        if sort_order not in ["asc", "desc"]:
            sort_order = "desc"
        
        order_clause = f"{sort_by} {sort_order.upper()}"
        
        # 计算总数
        count_sql = f"SELECT COUNT(*) as count FROM users WHERE {where_clause}"
        count_result = db.query_one(count_sql, tuple(params), sqlite_name="auth.sqlite3")
        total = int(count_result.get("count", 0) if isinstance(count_result, dict) else count_result[0])
        
        # 分页查询
        offset = (page - 1) * page_size
        sql = f"SELECT * FROM users WHERE {where_clause} ORDER BY {order_clause} LIMIT ? OFFSET ?"
        params.extend([page_size, offset])
        
        rows = db.query_all(sql, tuple(params), sqlite_name="auth.sqlite3")
        
        # 格式化数据
        users = []
        for row in rows:
            if isinstance(row, dict):
                users.append(_sanitize_user_data(row))
            elif hasattr(row, 'keys'):
                users.append(_sanitize_user_data(dict(row)))
        
        return jsonify({
            "success": True,
            "data": {
                "users": users,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size
                }
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.get("/users/<int:user_id>")
@require_role(ROLE_ADMIN)
def get_user(user_id: int):
    """获取用户详情"""
    try:
        user = _get_user_by_id(user_id)
        if not user:
            return jsonify({"success": False, "error": "用户不存在"}), 404
        
        return jsonify({
            "success": True,
            "data": _sanitize_user_data(user)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/users")
@require_role(ROLE_ADMIN)
def create_user():
    """创建用户"""
    try:
        data = request.get_json(force=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        password2 = data.get("password2") or ""
        real_name = (data.get("real_name") or "").strip()
        email = (data.get("email") or "").strip()
        phone = (data.get("phone") or "").strip()
        role = (data.get("role") or ROLE_USER).strip()
        status = (data.get("status") or STATUS_ACTIVE).strip()
        
        # 验证必填字段
        if not username:
            return jsonify({"success": False, "error": "用户名不能为空"}), 400
        if len(username) < 3:
            return jsonify({"success": False, "error": "用户名至少3位"}), 400
        if not password:
            return jsonify({"success": False, "error": "密码不能为空"}), 400
        if len(password) < 6:
            return jsonify({"success": False, "error": "密码至少6位"}), 400
        if password != password2:
            return jsonify({"success": False, "error": "两次密码不一致"}), 400
        
        # 验证角色
        current = current_user()
        current_role = current.get("role", ROLE_USER) if current else ROLE_USER
        
        # 角色验证：只有超级管理员可以创建管理员和超级管理员
        if role not in [ROLE_USER, ROLE_OPERATOR, ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            return jsonify({"success": False, "error": "无效的角色"}), 400
        
        # 权限检查：普通管理员只能创建普通用户和操作员
        if current_role == ROLE_ADMIN and role in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            return jsonify({"success": False, "error": "普通管理员不能创建管理员或超级管理员"}), 403
        
        # 验证状态
        if status not in [STATUS_ACTIVE, STATUS_INACTIVE]:
            return jsonify({"success": False, "error": "无效的状态"}), 400
        
        # 验证邮箱格式（如果提供）
        if email and "@" not in email:
            return jsonify({"success": False, "error": "邮箱格式不正确"}), 400
        
        # 检查用户名是否已存在
        if _get_user_by_username(username):
            return jsonify({"success": False, "error": "用户名已存在"}), 400
        
        # 创建用户
        now = _now_str()
        pwd_hash = generate_password_hash(password)
        
        user_id = db.execute(
            """
            INSERT INTO users (username, password_hash, role, real_name, email, phone, status, created_at, updated_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (username, pwd_hash, role, real_name or None, email or None, phone or None, status, now, now, None),
            sqlite_name="auth.sqlite3"
        )
        
        user = _get_user_by_id(int(user_id))
        if not user:
            raise RuntimeError("创建用户失败")
        
        return jsonify({
            "success": True,
            "data": _sanitize_user_data(user)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.put("/users/<int:user_id>")
@require_role(ROLE_ADMIN)
def update_user(user_id: int):
    """更新用户信息"""
    try:
        user = _get_user_by_id(user_id)
        if not user:
            return jsonify({"success": False, "error": "用户不存在"}), 404
        
        data = request.get_json(force=True) or {}
        real_name = (data.get("real_name") or "").strip()
        email = (data.get("email") or "").strip()
        phone = (data.get("phone") or "").strip()
        role = (data.get("role") or "").strip()
        status = (data.get("status") or "").strip()
        password = data.get("password") or ""
        password2 = data.get("password2") or ""
        
        # 获取当前用户（操作者）
        current = current_user()
        current_user_id = int(current["id"]) if current else None
        
        # 权限检查：是否可以管理目标用户
        can_manage, error_msg = _can_manage_user(current, user)
        if not can_manage:
            return jsonify({"success": False, "error": error_msg}), 403
        
        # 保护规则：不能修改自己
        if user_id == current_user_id:
            # 不能禁用自己
            if status == STATUS_INACTIVE:
                return jsonify({"success": False, "error": "不能禁用自己的账户"}), 400
            # 不能降级自己（超级管理员可以降级自己，但不推荐）
            current_role = current.get("role", ROLE_USER)
            if role and role != current_role and current_role in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
                if current_role == ROLE_SUPER_ADMIN and role != ROLE_SUPER_ADMIN:
                    # 超级管理员降级自己需要特别提示
                    pass  # 允许但不推荐
                elif current_role == ROLE_ADMIN:
                    return jsonify({"success": False, "error": "不能将自己的角色降级"}), 400
        
        # 保护规则：不能删除/禁用最后一个管理员（包括超级管理员）
        if user.get("role") in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            admin_count = _count_admin_users(exclude_user_id=user_id, include_super_admin=True)
            if admin_count == 0:
                if status == STATUS_INACTIVE:
                    return jsonify({"success": False, "error": "不能禁用最后一个管理员"}), 400
                if role and role not in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
                    return jsonify({"success": False, "error": "不能删除最后一个管理员"}), 400
        
        # 验证角色
        if role and role not in [ROLE_USER, ROLE_OPERATOR, ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            return jsonify({"success": False, "error": "无效的角色"}), 400
        
        # 权限检查：普通管理员不能将用户设置为管理员或超级管理员
        current_role = current.get("role", ROLE_USER)
        if current_role == ROLE_ADMIN and role in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            return jsonify({"success": False, "error": "普通管理员不能将用户设置为管理员"}), 403
        
        # 验证状态
        if status and status not in [STATUS_ACTIVE, STATUS_INACTIVE]:
            return jsonify({"success": False, "error": "无效的状态"}), 400
        
        # 验证邮箱格式
        if email and "@" not in email:
            return jsonify({"success": False, "error": "邮箱格式不正确"}), 400
        
        # 验证密码（如果提供）
        if password:
            if len(password) < 6:
                return jsonify({"success": False, "error": "密码至少6位"}), 400
            if password != password2:
                return jsonify({"success": False, "error": "两次密码不一致"}), 400
        
        # 构建更新语句
        updates = []
        params = []
        
        if real_name is not None:
            updates.append("real_name = ?")
            params.append(real_name or None)
        
        if email is not None:
            updates.append("email = ?")
            params.append(email or None)
        
        if phone is not None:
            updates.append("phone = ?")
            params.append(phone or None)
        
        if role:
            updates.append("role = ?")
            params.append(role)
        
        if status:
            updates.append("status = ?")
            params.append(status)
        
        if password:
            updates.append("password_hash = ?")
            params.append(generate_password_hash(password))
        
        if updates:
            updates.append("updated_at = ?")
            params.append(_now_str())
            params.append(user_id)
            
            sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
            db.execute(sql, tuple(params), sqlite_name="auth.sqlite3")
        
        # 返回更新后的用户信息
        updated_user = _get_user_by_id(user_id)
        return jsonify({
            "success": True,
            "data": _sanitize_user_data(updated_user)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.delete("/users/<int:user_id>")
@require_role(ROLE_ADMIN)
def delete_user(user_id: int):
    """删除用户（软删除：设置为禁用状态）"""
    try:
        user = _get_user_by_id(user_id)
        if not user:
            return jsonify({"success": False, "error": "用户不存在"}), 404
        
        # 获取当前用户（操作者）
        current = current_user()
        current_user_id = int(current["id"]) if current else None
        
        # 权限检查：是否可以管理目标用户
        can_manage, error_msg = _can_manage_user(current, user)
        if not can_manage:
            return jsonify({"success": False, "error": error_msg}), 403
        
        # 保护规则：不能删除自己
        if user_id == current_user_id:
            return jsonify({"success": False, "error": "不能删除自己的账户"}), 400
        
        # 保护规则：不能删除最后一个管理员（包括超级管理员）
        if user.get("role") in [ROLE_ADMIN, ROLE_SUPER_ADMIN]:
            admin_count = _count_admin_users(exclude_user_id=user_id, include_super_admin=True)
            if admin_count == 0:
                return jsonify({"success": False, "error": "不能删除最后一个管理员"}), 400
        
        # 软删除：设置为禁用状态
        now = _now_str()
        db.execute(
            "UPDATE users SET status = ?, updated_at = ? WHERE id = ?",
            (STATUS_INACTIVE, now, user_id),
            sqlite_name="auth.sqlite3"
        )
        
        return jsonify({
            "success": True,
            "message": "用户已删除（已禁用）"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/users/<int:user_id>/toggle-status")
@require_role(ROLE_ADMIN)
def toggle_user_status(user_id: int):
    """切换用户状态（启用/禁用）"""
    try:
        user = _get_user_by_id(user_id)
        if not user:
            return jsonify({"success": False, "error": "用户不存在"}), 404
        
        # 获取当前用户（操作者）
        current = current_user()
        current_user_id = int(current["id"]) if current else None
        
        # 权限检查：是否可以管理目标用户
        can_manage, error_msg = _can_manage_user(current, user)
        if not can_manage:
            return jsonify({"success": False, "error": error_msg}), 403
        
        # 保护规则：不能禁用自己
        if user_id == current_user_id:
            return jsonify({"success": False, "error": "不能禁用自己的账户"}), 400
        
        # 保护规则：不能禁用最后一个管理员（包括超级管理员）
        current_status = user.get("status", STATUS_ACTIVE)
        new_status = STATUS_INACTIVE if current_status == STATUS_ACTIVE else STATUS_ACTIVE
        
        if user.get("role") in [ROLE_ADMIN, ROLE_SUPER_ADMIN] and new_status == STATUS_INACTIVE:
            admin_count = _count_admin_users(exclude_user_id=user_id, include_super_admin=True)
            if admin_count == 0:
                return jsonify({"success": False, "error": "不能禁用最后一个管理员"}), 400
        
        # 更新状态
        now = _now_str()
        db.execute(
            "UPDATE users SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, user_id),
            sqlite_name="auth.sqlite3"
        )
        
        updated_user = _get_user_by_id(user_id)
        return jsonify({
            "success": True,
            "data": _sanitize_user_data(updated_user),
            "message": f"用户已{'禁用' if new_status == STATUS_INACTIVE else '启用'}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/users/<int:user_id>/reset-password")
@require_role(ROLE_ADMIN)
def reset_user_password(user_id: int):
    """重置用户密码"""
    try:
        import secrets
        import string
        
        user = _get_user_by_id(user_id)
        if not user:
            return jsonify({"success": False, "error": "用户不存在"}), 404
        
        # 生成随机密码（12位，包含大小写字母、数字）
        alphabet = string.ascii_letters + string.digits
        new_password = ''.join(secrets.choice(alphabet) for _ in range(12))
        
        # 更新密码
        pwd_hash = generate_password_hash(new_password)
        now = _now_str()
        db.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (pwd_hash, now, user_id),
            sqlite_name="auth.sqlite3"
        )
        
        return jsonify({
            "success": True,
            "data": {
                "new_password": new_password  # 返回临时密码，管理员可以告知用户
            },
            "message": "密码已重置"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 个人设置 API（用户自己） ====================

@bp.put("/profile")
def update_profile():
    """更新当前登录用户的个人信息"""
    try:
        user = current_user()
        if not user:
            return jsonify({"success": False, "error": "未登录"}), 401
        
        data = request.get_json(force=True) or {}
        real_name = (data.get("real_name") or "").strip()
        email = (data.get("email") or "").strip()
        phone = (data.get("phone") or "").strip()
        current_password = data.get("current_password") or ""
        new_password = data.get("new_password") or ""
        confirm_password = data.get("confirm_password") or ""
        
        user_id = int(user["id"])
        updates = []
        params = []
        
        # 更新基本信息
        if real_name is not None:
            updates.append("real_name = ?")
            params.append(real_name or None)
        
        if email is not None:
            # 验证邮箱格式
            if email and "@" not in email:
                return jsonify({"success": False, "error": "邮箱格式不正确"}), 400
            updates.append("email = ?")
            params.append(email or None)
        
        if phone is not None:
            updates.append("phone = ?")
            params.append(phone or None)
        
        # 修改密码
        if new_password:
            if not current_password:
                return jsonify({"success": False, "error": "修改密码需要提供当前密码"}), 400
            
            # 验证当前密码
            if not check_password_hash(user["password_hash"], current_password):
                return jsonify({"success": False, "error": "当前密码错误"}), 400
            
            if len(new_password) < 8:
                return jsonify({"success": False, "error": "新密码长度至少8位"}), 400
            
            # 密码强度验证（建议包含字母、数字和特殊字符）
            import re
            has_lower = bool(re.search(r'[a-z]', new_password))
            has_upper = bool(re.search(r'[A-Z]', new_password))
            has_number = bool(re.search(r'[0-9]', new_password))
            has_special = bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', new_password))
            
            # 至少包含字母和数字（不强求特殊字符，但建议）
            if not (has_lower or has_upper) or not has_number:
                return jsonify({"success": False, "error": "密码应包含字母和数字"}), 400
            
            if new_password != confirm_password:
                return jsonify({"success": False, "error": "两次输入的新密码不一致"}), 400
            
            updates.append("password_hash = ?")
            params.append(generate_password_hash(new_password))
        
        # 执行更新
        if updates:
            updates.append("updated_at = ?")
            params.append(_now_str())
            params.append(user_id)
            
            sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
            db.execute(sql, tuple(params), sqlite_name="auth.sqlite3")
        
        # 返回更新后的用户信息
        updated_user = _get_user_by_id(user_id)
        return jsonify({
            "success": True,
            "data": {
                "id": updated_user["id"],
                "username": updated_user["username"],
                "real_name": updated_user.get("real_name") or "",
                "email": updated_user.get("email") or "",
                "phone": updated_user.get("phone") or "",
                "role": updated_user.get("role", "user"),
                "updated_at": updated_user.get("updated_at"),
            },
            "message": "个人信息已更新"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


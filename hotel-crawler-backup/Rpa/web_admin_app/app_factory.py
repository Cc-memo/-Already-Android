import os

from flask import Flask
from flask_cors import CORS

from . import auth
from .auth import require_login_for_api
from .crawl_tasks import bp as crawl_tasks_bp, init_crawl_task_db
from .app_crawl_tasks import bp as app_crawl_tasks_bp, init_app_crawl_task_db, init_app_hotel_search_results_db
from .metatree_tasks import bp as metatree_bp, init_metatree_task_db, try_import_metatree
from .rpa_routes import bp as rpa_bp
from .settings import bp as settings_bp, init_settings_db
from .ui import bp as ui_bp
from database.db_utils import init_database


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    app.config["JSON_AS_ASCII"] = False
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True
    app.secret_key = os.getenv("WEB_ADMIN_SECRET_KEY", "dev-secret-key-change-me")

    @app.before_request
    def _guard():
        rv = require_login_for_api()
        if rv is not None:
            return rv
        return None

    # 注册蓝图
    app.register_blueprint(ui_bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(metatree_bp)
    app.register_blueprint(crawl_tasks_bp)
    app.register_blueprint(app_crawl_tasks_bp)
    app.register_blueprint(rpa_bp)
    app.register_blueprint(settings_bp)

    # 初始化数据库（auth / metatree_tasks / settings）
    auth.init_auth_db()
    init_metatree_task_db()
    init_crawl_task_db()
    init_app_crawl_task_db()
    init_app_hotel_search_results_db()
    init_settings_db()
    # 初始化业务数据库（search_records/room_data），兼容原 Rpa API
    try:
        init_database()
    except Exception:
        # 不阻塞启动：例如 MySQL 配置不对
        pass

    # 尝试加载 metatree（不阻塞启动）
    try_import_metatree()

    return app


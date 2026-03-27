import os

from flask import Blueprint, Response, abort, redirect, send_from_directory, session

from .constants import METATREE_PROTOTYPES_DIR, UI_OVERRIDES_DIR


bp = Blueprint("ui", __name__)


@bp.get("/")
def index():
    if os.path.isdir(METATREE_PROTOTYPES_DIR):
        return redirect("/ui/login.html")
    return abort(404)


@bp.get("/ui/")
def ui_index():
    if not os.path.isdir(METATREE_PROTOTYPES_DIR):
        abort(404)
    return redirect("/ui/login.html")


@bp.get("/ui/logout")
def ui_logout():
    session.clear()
    return redirect("/ui/login.html")


@bp.get("/ui/<path:filename>")
def ui_files(filename: str):
    if not os.path.isdir(METATREE_PROTOTYPES_DIR):
        abort(404)

    allowed_ext = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".map"}
    _, ext = os.path.splitext(filename.lower())
    if ext and ext not in allowed_ext:
        abort(404)

    public_files = {"login.html", "register.html"}
    if filename.lower().endswith(".html") and filename.lower() not in public_files:
        if not session.get("user_id"):
            return redirect("/ui/login.html")

    override_path = os.path.join(UI_OVERRIDES_DIR, filename)
    if os.path.isfile(override_path):
        response = send_from_directory(UI_OVERRIDES_DIR, filename)
        # 为静态资源添加无缓存头，防止浏览器缓存旧 JS
        if filename.lower().endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # 对特定原型页注入JS（不改 prototypes 文件）
    inject_map = {
        "dashboard.html": "/ui/inject/dashboard.js",
        "crawl-tasks.html": "/ui/inject/crawl_tasks.js",
        "task_detail.html": "/ui/inject/task_detail.js",
        "data_export.html": "/ui/inject/data_export.js",
    }
    if filename in inject_map and filename.lower().endswith(".html"):
        source_path = os.path.join(METATREE_PROTOTYPES_DIR, filename)
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                html = f.read()

            inject_src = inject_map[filename]
            js_name = inject_src.split("/")[-1]
            js_path = os.path.join(UI_OVERRIDES_DIR, "inject", js_name)
            ts = int(os.path.getmtime(js_path)) if os.path.exists(js_path) else 0

            tag = f'\n<script src="{inject_src}?v={ts}"></script>\n'
            idx = html.lower().rfind("</body>")
            if idx != -1:
                html = html[:idx] + tag + html[idx:]
            else:
                html = html + tag

            response = Response(html, mimetype="text/html; charset=utf-8")
            # 为 HTML 页面也添加无缓存头
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        except Exception:
            # 回退到静态托管
            pass

    return send_from_directory(METATREE_PROTOTYPES_DIR, filename)


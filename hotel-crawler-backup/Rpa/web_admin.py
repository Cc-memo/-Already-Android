# -*- coding: utf-8 -*-
"""
Web 管理平台启动入口（薄启动器）

- UI：托管 metatree/prototypes（/ui/*），并允许用 Rpa/ui_overrides 覆盖少量页面（登录/注册等）
- API：在 Rpa/web_admin_app/ 下按模块拆分（auth、metatree_tasks、rpa_routes）

启动方式：
  - 双击 start_web_admin.bat
  - 或在 Rpa 目录执行：python web_admin.py
"""

import sys

from web_admin_app import create_app


# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")


def main():
    app = create_app()
    print("=" * 60)
    print("  🚀 酒店信息爬取及管理平台（Web Admin）")
    print("=" * 60)
    print("  访问地址: http://localhost:5000/ui/login.html")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()


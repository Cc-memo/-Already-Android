import os


def project_root() -> str:
    # Rpa/web_admin_app -> Rpa
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PROJECT_ROOT = project_root()

ORDERS_FILE = os.path.join(PROJECT_ROOT, "orders", "orders.json")
MEITUAN_DATA_FILE = os.path.join(PROJECT_ROOT, "meituan", "meituan_hotel.json")
XIECHENG_DATA_FILE = os.path.join(PROJECT_ROOT, "xiecheng", "hotel_data.json")
PRICE_COMPARISON_REPORT = os.path.join(PROJECT_ROOT, "price_comparison_report.md")

DATABASE_DIR = os.path.join(PROJECT_ROOT, "database")

AUTH_DB = os.path.join(DATABASE_DIR, "auth.sqlite3")
METATREE_TASK_DB = os.path.join(DATABASE_DIR, "metatree_tasks.sqlite3")
CRAWL_TASK_DB = os.path.join(DATABASE_DIR, "crawl_tasks.sqlite3")

METATREE_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, "..", "metatree"))
METATREE_PROTOTYPES_DIR = os.path.join(METATREE_ROOT, "prototypes")
UI_OVERRIDES_DIR = os.path.join(PROJECT_ROOT, "ui_overrides")


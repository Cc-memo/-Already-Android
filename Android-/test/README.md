# 手机端测试

本目录为手机端两个页面的前端文件，需配合 Web Admin 的 app 接口使用。

## 文件

- **mobile_create.html**：手机端创建任务页（填写酒店、城市、平台，提交后写入 `app_crawl_tasks` 表）
- **mobile_task_list.html**：手机端任务列表页（展示 `app_crawl_tasks` 列表，可查看状态与结果）
- **app_scheduler.py**：本地领任务脚本，轮询领任务 → 按 platform 执行 3.py / Meituan/meituan_extract.py → 上报结果
- **clear_all_queued_admin.py**：管理员清空全库 `queued`（云端多人环境用，需 operator/admin 权限，需后端支持对应接口）
- **config.py**：配置 `BASE_URL`（默认 `http://localhost:5000`）、`POLL_INTERVAL`（默认 30 秒）

## 使用

1. 启动 Web Admin（`hotel-crawler-backup/Rpa` 下 `python web_admin.py`），确保已登录。
2. 在「手机端 - 创建任务」页（或 `/ui/mobile_create.html`）创建任务。
3. 在 **Android-** 项目根目录下运行领任务脚本：
   ```bash
   python test/app_scheduler.py
   ```
   脚本会轮询领任务，领到后按 platform 执行携程 3.py 或美团 meituan_extract.py，结果写入 1.json / Meituan/1.json 后上报。

   若云端存在大量历史 queued 任务，影响手机端调试，可用管理员脚本清空全库 queued（需后端支持接口 + 管理员权限）：
   ```bash
   python test/clear_all_queued_admin.py
   # 同时清理 running（清理“执行中”残留；注意不会停止手机端进程）
   python test/clear_all_queued_admin.py --include-running
   python test/clear_all_queued_admin.py --platform meituan
   ```
4. 在「手机端 - 任务列表」页可查看任务状态与结果。

## 接口（需先部署后端）

- `POST /api/app-crawl-tasks`：创建任务（需登录）
- `GET /api/app-crawl-tasks`：任务列表（需登录）
- `GET /api/app-crawl-tasks/<task_id>`：任务详情（需登录）
- `GET /api/app-crawl-tasks/claim`：领任务（scheduler 用，无需登录）
- `POST /api/app-crawl-tasks/report`：上报结果（无需登录）

结果数据写入 `app_hotel_search_results` 表。

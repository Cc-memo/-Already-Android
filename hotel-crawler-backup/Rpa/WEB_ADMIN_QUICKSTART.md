# Web管理平台 - 快速开始

## 简介

Web管理平台为酒店爬虫系统提供了一个可视化的管理界面，方便查看和管理订单、监控价格、查看比价报告等。

## 快速启动

### 1. 安装依赖

确保已安装Flask和flask-cors：

```bash
pip install flask flask-cors
```

> 建议直接安装本项目依赖：

```bash
pip install -r requirements.txt
```

### 2. 启动服务

**Windows:**
```bash
# 方式1: 双击运行
start_web_admin.bat

# 方式2: 命令行运行
cd Rpa
python web_admin.py
```

**Linux/Mac:**
```bash
python3 web_admin.py
```

### 3. 访问管理平台

在浏览器中打开：

```
http://localhost:5000
```

首次使用请先注册：打开 `http://localhost:5000/ui/register.html` 注册账号，然后回到 `login.html` 登录。

## 新增：Metatree 任务中心（统一管理页）

当前管理平台已集成 `../metatree`（相对 `Rpa` 目录）中的爬虫能力：

- UI 页面入口：`/ui/login.html`（直接托管 `metatree/prototypes`）
- 原型页之间的跳转（例如 `dashboard.html`、`create_task.html`）保持不改动即可工作
- API：
  - `GET /api/metatree/health`（检查是否成功加载 metatree）
  - `POST /api/metatree/tasks`（创建并后台执行）
  - `GET /api/metatree/tasks`（列表）
  - `GET /api/metatree/tasks/<task_id>`（详情/结果）
- 任务落库：`Rpa/database/metatree_tasks.sqlite3`

### metatree 依赖与 ChromeDriver 配置（Windows）

metatree 的 Selenium 需要正确的 ChromeDriver 路径，否则任务会失败。

优先推荐用环境变量覆盖：

```powershell
$env:CHROME_DRIVER_PATH="D:\path\to\chromedriver.exe"
python web_admin.py
```

也可以直接修改 metatree 的配置文件：`metatree/crawler/config/settings.py` 里的 `CRAWLER_CONFIG['selenium']['driver_path']`。

### 本机测试注意：避免清理掉你正在使用的 Chrome

为了避免脚本启动时“误杀”你正在使用的浏览器，本项目默认只会清理 `chromedriver.exe`。

- 如你确实需要连 `chrome.exe` 一并清理（不推荐），请显式设置：

```powershell
$env:KILL_CHROME_PROCESS="1"
```

## 功能模块

### 📊 数据概览
- 总订单数、总利润统计
- 订单状态分布图表
- 平台分布图表
- 近7天订单统计

### 🛒 订单管理
- 查看所有订单
- 按状态筛选订单
- 查看订单详情（酒店、客人、价格、利润等）
- 支持订单状态更新

### 🔍 价格监控
- 查看搜索历史记录
- 按平台筛选（携程、美团）
- 按日期范围筛选
- 查看每次搜索的房型详情

### ⚖️ 比价报告
- 查看最新的比价分析报告
- 支持刷新报告内容

### ⚙️ 系统配置
- 查看数据库配置信息
- 查看数据库类型和连接信息

## 界面预览

管理平台采用现代化的设计风格，包含：

- **侧边栏导航** - 快速切换功能模块
- **数据卡片** - 直观展示关键指标
- **数据表格** - 清晰展示订单和搜索记录
- **图表展示** - 可视化数据分布
- **模态框** - 查看详细信息

## 常见问题

### Q: 启动后无法访问？

A: 检查以下几点：
1. 确保端口5000未被占用
2. 检查防火墙设置
3. 尝试使用 `http://127.0.0.1:5000`

### Q: 订单数据不显示？

A: 确保：
1. `orders/orders.json` 文件存在
2. 文件格式正确（JSON格式）
3. 文件有读取权限

### Q: 搜索记录不显示？

A: 确保：
1. 数据库已初始化（运行过 `database/setup_mysql.py` 或使用SQLite）
2. 数据库配置正确（`database/db_config.json`）
3. 数据库中有搜索记录数据

### Q: 比价报告为空？

A: 确保：
1. 已运行过比价程序（`price_comparison.py`）
2. `price_comparison_report.md` 文件存在

## 技术说明

- **后端框架**: Flask (Python)
- **前端技术**: HTML5 + CSS3 + JavaScript (原生)
- **数据存储**: 
  - 订单数据: JSON文件 (`orders/orders.json`)
  - 搜索记录: SQLite/MySQL数据库
  - 比价报告: Markdown文件

## 开发扩展

如需扩展功能，可以：

1. **添加新的API接口** - 在 `web_admin.py` 中添加路由
2. **添加新的页面** - 在 `templates/index.html` 中添加页面
3. **添加前端逻辑** - 在 `static/js/app.js` 中添加JavaScript代码
4. **自定义样式** - 在 `static/css/style.css` 中添加CSS样式

## 更多信息

详细文档请参考：`web_admin/README.md`

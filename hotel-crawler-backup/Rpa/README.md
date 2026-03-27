# 酒店爬虫系统

## 快速开始

### 1. 服务器环境准备（在Xshell中执行）

```bash
# 安装基础软件
sudo yum install -y python3 python3-pip git mariadb-server chromium
sudo systemctl start mariadb
sudo systemctl enable mariadb
sudo mkdir -p /opt/hotel-crawler
```

### 2. 本地部署（Windows）

编辑 `deploy.bat`，配置服务器IP：
```batch
set SERVER_HOST=8.153.81.55
```

运行部署：
```cmd
deploy.bat
```

### 3. 配置数据库（在Xshell中）

```bash
ssh root@8.153.81.55
cd /opt/hotel-crawler
python3 setup_mysql.py
```

## 详细文档

- `README_DEPLOY.md` - 完整部署指南
- `README_DB.md` - 数据库配置说明
- `Xshell使用说明.md` - Xshell使用指南
- `SSH使用说明.md` - SSH连接说明
- `部署文件说明.md` - 部署文件清单

## 项目结构

- `api_server.py` - API服务
- `search.py` - 搜索主程序
- `meituan/` - 美团爬虫
- `xiecheng/` - 携程爬虫
- `feizhu/` - 飞猪爬虫


# -*- coding: utf-8 -*-
"""
MySQL数据库配置助手
帮助用户配置本地MySQL连接
"""

import os
import json

CONFIG_FILE = "db_config.json"
CONFIG_EXAMPLE = "db_config.json.example"

def create_mysql_config():
    """交互式创建MySQL配置文件"""
    print("=" * 50)
    print("MySQL数据库配置助手")
    print("=" * 50)
    print()
    
    print("请输入MySQL连接信息（直接回车使用默认值）：")
    print()
    
    # 获取配置信息
    host = input("MySQL主机地址 [localhost]: ").strip() or "localhost"
    port = input("MySQL端口 [3306]: ").strip() or "3306"
    user = input("MySQL用户名 [root]: ").strip() or "root"
    password = input("MySQL密码: ").strip()
    database = input("数据库名称 [hotel_data]: ").strip() or "hotel_data"
    
    # 创建配置
    config = {
        "db_type": "mysql",
        "mysql": {
            "host": host,
            "port": int(port),
            "user": user,
            "password": password,
            "database": database,
            "charset": "utf8mb4"
        }
    }
    
    # 保存配置文件
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print()
    print("✓ 配置文件已创建: db_config.json")
    print()
    print("配置信息：")
    print(f"  主机: {host}")
    print(f"  端口: {port}")
    print(f"  用户: {user}")
    print(f"  数据库: {database}")
    print()
    
    # 测试连接并创建数据库
    print("正在测试数据库连接...")
    try:
        import pymysql
        
        # 先连接到MySQL服务器（不指定数据库）
        conn = pymysql.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # 检查数据库是否存在
        cursor.execute("SHOW DATABASES LIKE %s", (database,))
        result = cursor.fetchone()
        
        if not result:
            # 数据库不存在，创建它
            print(f"数据库 '{database}' 不存在，正在创建...")
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
            print(f"✓ 数据库 '{database}' 创建成功！")
        else:
            print(f"✓ 数据库 '{database}' 已存在")
        
        cursor.close()
        conn.close()
        
        # 再次连接，这次指定数据库
        conn = pymysql.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        conn.close()
        print("✓ 数据库连接成功！")
        print()
        print("现在可以运行爬虫脚本，数据将保存到MySQL数据库。")
        
    except ImportError:
        print("⚠️  未安装pymysql，请先安装：")
        print("   pip install pymysql")
        print()
        print("安装后，配置会自动生效。")
        
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        print()
        print("请检查：")
        print("  1. MySQL服务是否已启动")
        print("  2. 用户名和密码是否正确")
        print("  3. 端口是否正确")
        print("  4. 用户是否有创建数据库的权限")


if __name__ == "__main__":
    create_mysql_config()


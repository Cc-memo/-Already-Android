# -*- coding: utf-8 -*-
"""
测试云数据库连接
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_utils import load_config, init_database

def test_connection():
    """测试数据库连接"""
    print("=" * 60)
    print("正在测试云数据库连接...")
    print("=" * 60)
    print()
    
    try:
        config = load_config()
        mysql_config = config['mysql']
        
        print(f"连接信息：")
        print(f"  主机: {mysql_config['host']}")
        print(f"  端口: {mysql_config['port']}")
        print(f"  用户: {mysql_config['user']}")
        print(f"  数据库: {mysql_config['database']}")
        print(f"  连接超时: {mysql_config.get('connect_timeout', 10)}秒")
        print(f"  读取超时: {mysql_config.get('read_timeout', 30)}秒")
        print(f"  写入超时: {mysql_config.get('write_timeout', 30)}秒")
        
        # SSL配置
        ssl_enabled = mysql_config.get('ssl', {}).get('enabled', False)
        ssl_disabled = mysql_config.get('ssl_disabled', False)
        if ssl_enabled:
            print(f"  SSL: 已启用")
        elif ssl_disabled:
            print(f"  SSL: 已禁用")
        else:
            print(f"  SSL: 使用默认设置")
        print()
        
        # 测试连接并初始化
        print("正在连接数据库...")
        import time
        start_time = time.time()
        init_database()
        elapsed = time.time() - start_time
        print()
        print("=" * 60)
        print(f"[✓] 连接成功！数据库表已初始化（耗时 {elapsed:.2f} 秒）")
        print("=" * 60)
        
    except ImportError as e:
        print(f"\n[✗] 错误: {e}")
        print("请先安装 pymysql: pip install pymysql")
        return False
    except Exception as e:
        error_msg = str(e)
        print(f"\n[✗] 连接失败: {error_msg}")
        print()
        print("=" * 60)
        print("排查建议：")
        print("=" * 60)
        
        # 根据错误类型给出具体建议
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            print("1. ⏱️  连接超时问题：")
            print("   - 检查云服务器安全组是否开放了MySQL端口（通常是3306）")
            print("   - 检查云数据库白名单是否添加了服务器IP")
            print("   - 尝试增加 connect_timeout 配置值")
            print("   - 检查网络连接是否正常：ping 数据库主机")
        elif "access denied" in error_msg.lower() or "authentication" in error_msg.lower():
            print("1. 🔐 认证失败：")
            print("   - 检查用户名和密码是否正确")
            print("   - 检查用户是否有访问该数据库的权限")
            print("   - 检查用户是否允许从该IP连接")
        elif "unknown host" in error_msg.lower() or "name resolution" in error_msg.lower():
            print("1. 🌐 DNS解析失败：")
            print("   - 检查数据库主机地址是否正确")
            print("   - 尝试使用IP地址而不是域名")
        elif "ssl" in error_msg.lower():
            print("1. 🔒 SSL配置问题：")
            print("   - 如果云数据库要求SSL，请在配置中启用 ssl.enabled = true")
            print("   - 如果云数据库不支持SSL，设置 ssl_disabled = true")
            print("   - 检查SSL证书路径是否正确")
        else:
            print("1. 📋 通用检查项：")
            print("   - 检查配置文件 db_config.json 是否存在且格式正确")
            print("   - 检查数据库服务是否正在运行")
            print("   - 检查端口是否正确（默认3306）")
        
        print()
        print("2. 📝 配置文件位置：")
        print(f"   {os.path.join(os.path.dirname(__file__), 'db_config.json')}")
        print()
        print("3. 🔧 环境变量方式（可选）：")
        print("   export DB_TYPE=mysql")
        print("   export DB_HOST=your-db-host.com")
        print("   export DB_PORT=3306")
        print("   export DB_USER=your_username")
        print("   export DB_PASSWORD=your_password")
        print("   export DB_NAME=hotel_data")
        print()
        print("4. 🧪 测试网络连接：")
        print(f"   telnet {mysql_config['host']} {mysql_config['port']}")
        print(f"   或: nc -zv {mysql_config['host']} {mysql_config['port']}")
        print()
        return False
    
    return True

if __name__ == "__main__":
    test_connection()


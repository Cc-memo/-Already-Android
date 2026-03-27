#!/bin/bash
# 开发环境设置脚本

echo "=========================================="
echo "酒店信息爬虫系统 - 开发环境设置"
echo "=========================================="

# 检查Python版本
echo "1. 检查Python版本..."
python3 --version

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "2. 创建Python虚拟环境..."
    python3 -m venv venv
    echo "✓ 虚拟环境创建成功"
else
    echo "2. 虚拟环境已存在，跳过创建"
fi

# 激活虚拟环境
echo "3. 激活虚拟环境..."
source venv/bin/activate

# 升级pip
echo "4. 升级pip..."
pip install --upgrade pip setuptools wheel

# 安装依赖
echo "5. 安装项目依赖..."
pip install -r requirements.txt

# 创建必要的目录
echo "6. 创建必要的目录..."
mkdir -p logs
mkdir -p data
mkdir -p crawler/core
mkdir -p crawler/spiders
mkdir -p crawler/utils
mkdir -p crawler/models
mkdir -p crawler/api
mkdir -p crawler/config
mkdir -p tests

# 创建.env文件（如果不存在）
if [ ! -f ".env" ]; then
    echo "7. 创建.env配置文件..."
    cp .env.example .env
    echo "✓ .env文件已创建，请根据实际情况修改配置"
else
    echo "7. .env文件已存在，跳过创建"
fi

echo ""
echo "=========================================="
echo "开发环境设置完成！"
echo "=========================================="
echo ""
echo "使用说明："
echo "1. 激活虚拟环境: source venv/bin/activate"
echo "2. 运行爬虫: python crawler/main.py --hotel '酒店名称'"
echo "3. 运行测试: python -m pytest tests/"
echo "4. 退出虚拟环境: deactivate"
echo ""


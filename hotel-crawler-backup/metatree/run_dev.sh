#!/bin/bash
# 开发环境启动脚本

# 激活虚拟环境
source venv/bin/activate

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ]; then
    echo "错误: 虚拟环境激活失败"
    exit 1
fi

echo "=========================================="
echo "开发环境已激活"
echo "Python版本: $(python --version)"
echo "虚拟环境: $VIRTUAL_ENV"
echo "=========================================="
echo ""

# 执行传入的命令
if [ $# -eq 0 ]; then
    echo "可用命令:"
    echo "  python crawler/main.py --hotel '酒店名称'  # 运行爬虫"
    echo "  python -m pytest tests/                   # 运行测试"
    echo "  python -c 'from crawler.spiders.meituan_spider import MeituanSpider; print(\"OK\")'  # 测试导入"
    echo ""
    echo "或者直接运行: ./run_dev.sh <命令>"
    echo "例如: ./run_dev.sh python crawler/main.py --hotel '北京饭店'"
else
    exec "$@"
fi


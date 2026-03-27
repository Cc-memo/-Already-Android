# 酒店信息爬虫系统

## 项目结构

```
crawler/
├── core/                    # 核心可复用模块
│   ├── browser.py          # 浏览器管理模块
│   ├── auth.py             # 登录认证模块
│   ├── search.py           # 搜索模块
│   └── extractor.py        # 数据提取模块
├── spiders/                # 各平台爬虫
│   ├── meituan_spider.py   # 美团爬虫
│   ├── ctrip_spider.py     # 携程爬虫
│   ├── fliggy_spider.py    # 飞猪爬虫
│   └── gaode_spider.py     # 高德爬虫
├── models/                 # 数据模型
│   └── hotel_model.py      # 酒店数据模型
├── utils/                  # 工具模块
│   ├── logger.py           # 日志工具
│   └── helpers.py          # 辅助函数
├── config/                 # 配置模块
│   └── settings.py         # 配置文件
└── main.py                 # 主程序入口

tests/                      # 测试文件
├── test_meituan_spider.py
├── test_ctrip_spider.py
├── test_fliggy_spider.py
└── test_gaode_spider.py
```

## 核心模块说明

### 1. BrowserManager (browser.py)
浏览器管理核心模块，提供：
- 浏览器初始化和关闭
- 页面打开和等待
- 元素查找和操作
- 页面滚动
- JavaScript执行

### 2. AuthManager (auth.py)
登录认证核心模块，提供：
- 通用登录流程
- 登录状态检查
- 退出登录

### 3. SearchManager (search.py)
搜索核心模块，提供：
- 通过酒店名称搜索
- 通过地址搜索
- 等待搜索结果
- 滚动加载更多

### 4. DataExtractor (extractor.py)
数据提取核心模块，提供：
- 文本提取
- 属性提取
- 价格/评分/点评数解析
- 联系方式提取（电话、邮箱）
- 房型信息提取

## 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=password
MYSQL_DATABASE=hotel_crawler

REDIS_HOST=localhost
REDIS_PORT=6379
```

### 3. 运行爬虫

#### 命令行方式

```bash
# 爬取单个酒店（所有平台）
python crawler/main.py --hotel "北京饭店"

# 指定平台
python crawler/main.py --hotel "北京饭店" --platforms meituan ctrip

# 需要登录
python crawler/main.py --hotel "北京饭店" --username "your_username" --password "your_password"

# 只爬列表页，不爬详情
python crawler/main.py --hotel "北京饭店" --no-detail

# 保存结果到文件
python crawler/main.py --hotel "北京饭店" --output results.json
```

#### Python代码方式

```python
from crawler.main import crawl_hotel

# 爬取酒店
results = crawl_hotel(
    hotel_name="北京饭店",
    platforms=['meituan', 'ctrip'],
    username='your_username',  # 可选
    password='your_password',  # 可选
    need_detail=True
)

# 结果格式
# {
#     'meituan': [酒店数据列表],
#     'ctrip': [酒店数据列表],
#     ...
# }
```

#### 使用单个平台爬虫

```python
from crawler.spiders.meituan_spider import MeituanSpider

with MeituanSpider(username='user', password='pass') as spider:
    # 登录
    spider.login()
    
    # 搜索酒店
    hotels = spider.search_hotel("北京饭店")
    
    # 获取详情
    for hotel in hotels:
        detail = spider.get_hotel_detail(hotel['hotel_url'])
        print(detail)
```

## 数据字段说明

### 酒店列表页字段
- `hotel_name`: 酒店名称
- `star_level`: 星级
- `rating_score`: 评分
- `review_count`: 点评数量
- `min_price`: 最低价格
- `address`: 地址
- `hotel_url`: 酒店详情页URL
- `platform`: 平台名称

### 酒店详情页字段（额外）
- `opening_date`: 开业时间
- `room_types`: 房型列表（包含房型名称、价格、库存）
- `phone`: 联系电话 ⭐新增
- `email`: 邮箱 ⭐新增
- `website`: 官网 ⭐新增
- `region`: 区域（城市-区县）

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定平台测试
python -m pytest tests/test_meituan_spider.py

# 带详细输出
python -m pytest tests/ -v
```

## 注意事项

1. **Chrome驱动**: 确保已安装Chrome浏览器和对应版本的ChromeDriver
2. **反爬措施**: 各平台可能有反爬机制，建议：
   - 设置合理的请求间隔
   - 使用代理IP（如需要）
   - 轮换User-Agent
   - 模拟真实用户行为
3. **登录凭据**: 某些平台可能需要登录才能查看详情，请提供有效的登录凭据
4. **选择器更新**: 各平台的页面结构可能变化，需要及时更新选择器

## 扩展开发

### 添加新平台

1. 在 `crawler/spiders/` 创建新的爬虫文件
2. 继承或参考现有爬虫的结构
3. 实现 `search_hotel()` 和 `get_hotel_detail()` 方法
4. 在 `main.py` 中注册新平台

### 自定义数据提取

在 `DataExtractor` 类中添加新的提取方法，或在各平台爬虫中重写提取逻辑。

## 许可证

MIT License


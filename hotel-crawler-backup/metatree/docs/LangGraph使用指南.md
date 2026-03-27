# LangGraph爬取架构使用指南

## 概述

本系统采用LangGraph框架构建爬取流程，将复杂的爬取任务分解为多个角色（Agent）协作完成。每个平台拥有独立的流程图，通过状态机管理爬取流程。

## 架构特点

- **模块化设计**：每个角色职责单一，易于测试和维护
- **流程可视化**：LangGraph提供流程可视化，便于理解和调试
- **状态管理**：通过状态机管理爬取流程，支持暂停、恢复、重试
- **平台隔离**：每个平台独立流程，互不干扰
- **可扩展性**：新增平台只需定义新的流程图

## 角色说明

### 1. 网址获取角色 (URLFetcherAgent)
- 从配置文件获取平台URL
- 构建搜索URL和详情页URL
- 验证URL有效性

### 2. 登入角色 (LoginAgent)
- 检测是否需要登录
- 执行登录流程
- 验证登录状态

### 3. 定位角色 (LocatorAgent)
- 定位搜索输入框
- 定位搜索按钮
- 定位结果列表容器

### 4. 酒店查找角色 (SearchAgent)
- 输入酒店名称
- 执行搜索操作
- 等待搜索结果加载

### 5. 数据提取角色 (ExtractorAgent)
- 提取酒店列表数据
- 提取酒店详情数据
- 数据清洗和格式化

### 6. 内容校验角色 (ValidatorAgent)
- 校验数据完整性
- 校验数据格式
- 生成校验报告

### 7. 错误处理角色 (ErrorHandlerAgent)
- 捕获和处理异常
- 决定重试或跳过
- 生成错误报告

## 使用方式

### 方式一：使用命令行

```bash
# 使用LangGraph流程（默认）
python -m crawler.main --hotel "北京饭店" --platforms meituan ctrip

# 使用传统爬虫
python -m crawler.main --hotel "北京饭店" --platforms meituan --no-graph
```

### 方式二：使用Python API

```python
from crawler.main import crawl_hotel_with_graph

# 使用LangGraph流程爬取单个平台
result = crawl_hotel_with_graph(
    hotel_name="北京饭店",
    platform="meituan",
    username="your_username",  # 可选
    password="your_password"   # 可选
)

print(f"状态: {result['status']}")
print(f"数据条数: {len(result['hotel_data'])}")
print(f"当前节点: {result['current_node']}")
print(f"已访问节点: {result['visited_nodes']}")
```

### 方式三：批量爬取

```python
from crawler.main import crawl_hotel

# 爬取多个平台
results = crawl_hotel(
    hotel_name="北京饭店",
    platforms=['meituan', 'ctrip', 'fliggy', 'gaode'],
    username="your_username",
    password="your_password",
    use_graph=True  # 使用LangGraph流程
)

for platform, hotels in results.items():
    print(f"{platform}: {len(hotels)} 条数据")
```

## 流程监控

### 查看流程状态

```python
result = crawl_hotel_with_graph(
    hotel_name="北京饭店",
    platform="meituan"
)

# 查看当前节点
print(f"当前节点: {result['current_node']}")

# 查看已访问节点
print(f"已访问节点: {result['visited_nodes']}")

# 查看日志
for log in result['logs']:
    print(log)
```

### 查看错误信息

```python
if result['status'] == 'failed':
    print(f"错误数: {result['error_count']}")
    for error in result['error_messages']:
        print(f"错误: {error}")
```

## 配置说明

### XPath配置

每个平台的XPath配置在`crawler/config/settings.py`中，支持通过环境变量动态调整：

```python
PLATFORM_CONFIG = {
    'meituan': {
        'search': {
            'input_xpath': '//input[@name="keyword"]',
            'button_xpath': '//button[contains(@class, "search")]',
        },
        'extraction': {
            'hotel_list_xpath': '//div[contains(@class, "hotel-item")]',
            'hotel_name_xpath': './/div[contains(@class, "hotel-name")]',
        }
    }
}
```

### 环境变量配置

```bash
# 飞猪平台XPath配置
FLIGGY_SEARCH_INPUT_XPATH=//input[@name="keyword"]
FLIGGY_HOTEL_LIST_XPATH=//div[contains(@class, "hotel-item")]
```

## 流程图

### 标准流程

```
START
  ↓
fetch_urls (网址获取)
  ↓
login? (是否需要登录)
  ├─ 是 → login (登入)
  └─ 否 → locate_elements (定位元素)
  ↓
locate_elements (定位元素)
  ↓
search_hotel (酒店查找)
  ↓
extract_data (数据提取)
  ↓
validate_content (内容校验)
  ↓
END
```

### 错误处理流程

```
任何节点出错
  ↓
handle_error (错误处理)
  ↓
retry? (是否重试)
  ├─ 是 → 回到fetch_urls重试
  └─ 否 → END (任务失败)
```

## 扩展开发

### 新增平台

1. 在`crawler/config/settings.py`中添加平台配置
2. 在`crawler/graph/graphs.py`中创建平台流程图（如需要自定义）
3. 在`get_graph_for_platform`函数中注册

### 新增角色

1. 在`crawler/graph/agents.py`中创建角色类，继承`BaseAgent`
2. 实现`_execute`方法
3. 在流程图中添加节点

### 自定义流程

```python
from crawler.graph import StateGraph, CrawlState
from crawler.graph.agents import URLFetcherAgent, SearchAgent

def create_custom_graph():
    workflow = StateGraph(CrawlState)
    
    # 添加节点
    workflow.add_node("fetch_urls", URLFetcherAgent().execute)
    workflow.add_node("search_hotel", SearchAgent().execute)
    
    # 设置入口和边
    workflow.set_entry_point("fetch_urls")
    workflow.add_edge("fetch_urls", "search_hotel")
    workflow.add_edge("search_hotel", END)
    
    return workflow.compile()
```

## 调试技巧

### 1. 查看流程状态

```python
result = crawl_hotel_with_graph(...)
print(json.dumps(result, indent=2, ensure_ascii=False))
```

### 2. 查看日志

```python
for log in result['logs']:
    print(log)
```

### 3. 使用非无头模式

在`BrowserManager`初始化时设置`headless=False`：

```python
from crawler.core.browser import BrowserManager
browser = BrowserManager(headless=False)
```

### 4. 保存流程可视化

```python
from crawler.graph import get_graph_for_platform

graph = get_graph_for_platform("meituan")
# LangGraph支持导出为图片
graph.get_graph().draw_mermaid_png(output_file_path="meituan_flow.png")
```

## 常见问题

### Q1: 流程卡在某个节点？

**A:** 检查该节点的日志，可能是：
- XPath选择器失效
- 页面加载超时
- 需要登录但未提供凭证

### Q2: 如何跳过某个节点？

**A:** 修改流程图，添加条件边，或在该节点的`_execute`方法中直接返回。

### Q3: 如何增加重试次数？

**A:** 在创建`CrawlState`时设置`max_retries`参数：

```python
state = CrawlState(
    task_id="...",
    hotel_name="...",
    platform="...",
    max_retries=5  # 默认3次
)
```

## 性能优化

### 1. 并发执行

每个平台独立流程，可以并行执行：

```python
from concurrent.futures import ThreadPoolExecutor

platforms = ['meituan', 'ctrip', 'fliggy', 'gaode']
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(crawl_hotel_with_graph, "北京饭店", p): p
        for p in platforms
    }
    results = {futures[f]: f.result() for f in futures}
```

### 2. 缓存配置

URL和XPath配置可以缓存，减少重复读取。

## 参考文档

- [技术架构文档](./技术架构文档.md)
- [XPath配置说明](./XPath配置说明.md)
- [LangGraph官方文档](https://langchain-ai.github.io/langgraph/)


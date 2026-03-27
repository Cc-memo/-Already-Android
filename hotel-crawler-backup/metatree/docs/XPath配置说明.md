# XPath和用户操作配置说明

## 概述

爬虫系统支持通过环境变量或配置文件动态调整XPath选择器和用户操作逻辑，无需修改代码即可适应网页结构变化。

## 配置方式

### 方式一：环境变量配置

在`.env`文件或系统环境变量中设置：

```bash
# 飞猪平台XPath配置示例
FLIGGY_SEARCH_INPUT_XPATH=//input[@name="keyword" or contains(@placeholder, "酒店")]
FLIGGY_SEARCH_BUTTON_XPATH=//button[contains(@class, "search-btn")]
FLIGGY_HOTEL_LIST_XPATH=//div[contains(@class, "hotel-item") or @data-hotel-id]
FLIGGY_HOTEL_NAME_XPATH=.//div[contains(@class, "hotel-name")] | .//h3
FLIGGY_HOTEL_PRICE_XPATH=.//div[contains(@class, "price")] | .//span[contains(@class, "price")]
FLIGGY_HOTEL_RATING_XPATH=.//div[contains(@class, "rating")] | .//span[contains(@class, "score")]
FLIGGY_HOTEL_ADDRESS_XPATH=.//div[contains(@class, "address")] | .//span[contains(@class, "location")]
FLIGGY_HOTEL_LINK_XPATH=.//a[@href]

# 登录相关XPath
FLIGGY_LOGIN_URL=https://www.fliggy.com/login
FLIGGY_USERNAME_XPATH=//input[@name="username" or @type="text"]
FLIGGY_PASSWORD_XPATH=//input[@type="password"]
FLIGGY_SUBMIT_XPATH=//button[contains(@class, "login-btn") or contains(text(), "登录")]
FLIGGY_SUCCESS_XPATH=//div[contains(@class, "user")]

# 页面识别标识
FLIGGY_LOGIN_INDICATOR_1=//div[contains(@class, "login")]
FLIGGY_LOGIN_INDICATOR_2=//input[@type="password"]
FLIGGY_LOGIN_INDICATOR_3=//button[contains(text(), "登录")]
FLIGGY_RESULT_INDICATOR_1=//div[contains(@class, "hotel-list")]
FLIGGY_RESULT_INDICATOR_2=//div[contains(@class, "hotel-item")]
FLIGGY_RESULT_INDICATOR_3=//div[@data-hotel-id]
```

### 方式二：直接修改配置文件

编辑`crawler/config/settings.py`中的`PLATFORM_CONFIG`，修改对应平台的配置项。

## 配置项说明

### 1. 搜索相关配置 (`search`)

```python
'search': {
    'input_xpath': '//input[@name="keyword"]',  # 搜索输入框XPath
    'button_xpath': '//button[contains(@class, "search")]',  # 搜索按钮XPath
    'use_enter': True,  # 是否使用回车键搜索
    'input_delay': 0.5,  # 输入后等待时间（秒）
    'click_delay': 0.3,  # 点击后等待时间（秒）
}
```

### 2. 登录相关配置 (`login`)

```python
'login': {
    'login_url': 'https://www.fliggy.com/login',  # 登录页面URL
    'username_xpath': '//input[@name="username"]',  # 用户名输入框XPath
    'password_xpath': '//input[@type="password"]',  # 密码输入框XPath
    'submit_xpath': '//button[contains(text(), "登录")]',  # 提交按钮XPath
    'success_xpath': '//div[contains(@class, "user")]',  # 登录成功标识XPath
}
```

### 3. 页面识别配置 (`page_detection`)

```python
'page_detection': {
    'login_indicators': [  # 登录页面标识列表
        '//div[contains(@class, "login")]',
        '//input[@type="password"]',
        '//button[contains(text(), "登录")]',
    ],
    'result_indicators': [  # 结果页面标识列表
        '//div[contains(@class, "hotel-list")]',
        '//div[contains(@class, "hotel-item")]',
        '//div[@data-hotel-id]',
    ],
}
```

### 4. 数据提取配置 (`extraction`)

```python
'extraction': {
    'hotel_list_xpath': '//div[contains(@class, "hotel-item")]',  # 酒店列表容器XPath
    'hotel_name_xpath': './/div[contains(@class, "hotel-name")] | .//h3',  # 酒店名称XPath
    'hotel_price_xpath': './/div[contains(@class, "price")]',  # 价格XPath
    'hotel_rating_xpath': './/div[contains(@class, "rating")]',  # 评分XPath
    'hotel_address_xpath': './/div[contains(@class, "address")]',  # 地址XPath
    'hotel_link_xpath': './/a[@href]',  # 链接XPath
}
```

### 5. 用户操作配置 (`user_actions`)

```python
'user_actions': {
    'simulate_human': True,  # 是否模拟人类操作
    'mouse_move_offset': (-5, 5),  # 鼠标移动偏移范围（像素）
    'typing_delay_range': (0.05, 0.15),  # 打字延迟范围（秒）
    'click_delay_range': (0.5, 1.0),  # 点击后延迟范围（秒）
    'scroll_before_click': True,  # 点击前是否滚动到元素
}
```

## XPath编写技巧

### 1. 使用属性选择器

```xpath
//input[@name="keyword"]  # 精确匹配name属性
//input[contains(@class, "search")]  # 包含某个class
//div[@data-hotel-id]  # 匹配data属性
```

### 2. 使用文本内容

```xpath
//button[contains(text(), "搜索")]  # 按钮文本包含"搜索"
//div[text()="登录"]  # 精确匹配文本
```

### 3. 使用逻辑运算符

```xpath
//input[@name="username" or @type="text"]  # OR逻辑
//div[contains(@class, "hotel") and @data-id]  # AND逻辑
```

### 4. 使用相对路径

```xpath
.//div[contains(@class, "hotel-name")]  # 从当前元素查找
//div[@class="container"]//div[@class="item"]  # 嵌套查找
```

### 5. 使用通配符

```xpath
//div[contains(@class, "hotel")]  # 包含"hotel"的class
//*[@data-hotel-id]  # 任意标签，有data-hotel-id属性
```

## 调试XPath

### 1. 在浏览器控制台测试

打开浏览器开发者工具（F12），在Console中输入：

```javascript
// 测试XPath
$x('//div[contains(@class, "hotel-item")]')
```

### 2. 使用浏览器扩展

推荐使用Chrome扩展：
- XPath Helper
- SelectorsHub
- ChroPath

### 3. 查看爬虫日志

爬虫会记录XPath查找结果，查看日志文件了解哪些XPath有效：

```bash
tail -f logs/crawler.log | grep "XPath"
```

## 常见问题

### Q1: XPath找不到元素怎么办？

**A:** 
1. 检查元素是否在iframe中，需要先切换iframe
2. 检查元素是否动态加载，需要等待元素出现
3. 使用更通用的选择器，如`contains(@class, "hotel")`
4. 添加多个备选XPath到配置中

### Q2: 如何适应网页结构变化？

**A:**
1. 定期检查网页结构，更新XPath配置
2. 使用环境变量，方便快速调整
3. 配置多个备选标识，提高容错性

### Q3: 模拟人类操作太慢怎么办？

**A:**
调整`user_actions`配置：
```python
'user_actions': {
    'simulate_human': False,  # 关闭模拟人类操作
    'typing_delay_range': (0.01, 0.05),  # 减少延迟
    'click_delay_range': (0.1, 0.3),  # 减少延迟
}
```

### Q4: 如何添加新的页面识别标识？

**A:**
在`page_detection`中添加新的标识：
```python
'result_indicators': [
    '//div[contains(@class, "hotel-list")]',
    '//div[contains(@class, "hotel-item")]',
    '//div[@data-hotel-id]',
    '//div[contains(@class, "new-indicator")]',  # 新增标识
]
```

## 配置示例

### 完整配置示例（飞猪平台）

```python
'fliggy': {
    'base_url': 'https://www.fliggy.com',
    'search_url': 'https://www.fliggy.com/s/hotel',
    'search': {
        'input_xpath': '//input[@name="keyword" or contains(@placeholder, "酒店")]',
        'button_xpath': '//button[contains(@class, "search")]',
        'use_enter': True,
    },
    'login': {
        'login_url': 'https://www.fliggy.com/login',
        'username_xpath': '//input[@name="username"]',
        'password_xpath': '//input[@type="password"]',
        'submit_xpath': '//button[contains(text(), "登录")]',
    },
    'page_detection': {
        'login_indicators': [
            '//div[contains(@class, "login")]',
            '//input[@type="password"]',
        ],
        'result_indicators': [
            '//div[contains(@class, "hotel-list")]',
            '//div[contains(@class, "hotel-item")]',
        ],
    },
    'extraction': {
        'hotel_list_xpath': '//div[contains(@class, "hotel-item")]',
        'hotel_name_xpath': './/div[contains(@class, "hotel-name")]',
        'hotel_price_xpath': './/div[contains(@class, "price")]',
    },
    'user_actions': {
        'simulate_human': True,
        'typing_delay_range': (0.05, 0.15),
        'click_delay_range': (0.5, 1.0),
    },
}
```

## 最佳实践

1. **使用环境变量**：便于不同环境使用不同配置
2. **配置多个备选**：提高容错性
3. **定期更新**：网页结构变化时及时更新XPath
4. **测试验证**：修改配置后先测试，确保有效
5. **记录日志**：保留配置变更记录，便于排查问题


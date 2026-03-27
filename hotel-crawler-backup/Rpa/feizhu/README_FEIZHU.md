# 飞猪酒店房型数据爬取工具

## 功能说明

自动化爬取飞猪（Fliggy）平台的酒店房型数据，包括：
- 房型名称
- 价格信息
- 其他备注信息

## 文件说明

- `feizhu_rpa.py` - 主爬虫脚本
- `cookies.py` - 登录态管理工具（可选，用于飞猪首页）
- `feizhu_hotel_cookies.py` - 飞猪酒店后台登录Cookies管理工具（使用Playwright）
- `feizhu_cookies.pkl` - 保存的Cookies文件（首次登录后自动生成）
- `feizhu_hotel_cookies.pkl` - 飞猪酒店后台保存的Cookies文件
- `feizhu_hotel.json` - 爬取结果保存文件
- `config.yaml` - 配置文件（需要从 config.yaml.example 复制）

## 安装依赖

### 飞猪酒店后台登录工具（feizhu_hotel_cookies.py）
```bash
pip install playwright pyyaml
playwright install chromium
```

### 爬虫工具（feizhu_rpa.py）
```bash
pip install selenium webdriver-manager
```

## 使用方法

### 飞猪酒店后台登录（保存Cookies）

如果你需要在飞猪酒店后台（https://hotel.fliggy.com/ebooking/）登录并保存登录态：

```bash
cd feizhu
python feizhu_hotel_cookies.py
```

或者测试已保存的Cookies是否有效：

```bash
python feizhu_hotel_cookies.py test
```

**使用说明：**
1. 首次运行会打开浏览器并访问飞猪酒店登录页面
2. 在浏览器中完成登录（可能需要扫码或输入账号密码）
3. 登录成功后，按回车保存Cookies
4. 下次运行会自动使用保存的Cookies，无需重复登录

**配置文件：**
- 可以创建 `config.yaml` 文件（从 `config.yaml.example` 复制）来自定义浏览器设置
- 如果不创建配置文件，会使用默认设置和URL

### 基本使用（爬虫）

```bash
cd feizhu
python feizhu_rpa.py
```

运行后会提示输入：
```
请输入: 地址关键词,酒店关键词（默认为 杭州,西湖）：
```

例如：
- `杭州,西湖` - 搜索杭州西湖附近的酒店
- `上海,外滩` - 搜索上海外滩附近的酒店
- `北京,天安门` - 搜索北京天安门附近的酒店

### 登录态说明

脚本使用**本地Chromium用户数据 + Cookies文件**双重保持登录态：

1. **本地用户数据目录**：
   - 路径：`C:\Users\武sir\AppData\Local\Chromium\User Data`
   - 如果你在Chromium浏览器中登录过飞猪，会自动使用该登录态

2. **Cookies文件**：
   - 首次运行时，如果页面需要登录，手动登录后会自动保存
   - 下次运行会自动加载保存的Cookies

## 工作流程

1. **启动浏览器** - 使用本地Chromium，加载用户数据和Cookies
2. **访问飞猪首页** - https://www.fliggy.com/?_er_static=true
3. **输入目的地** - 根据你输入的地址关键词
4. **选择日期** - 默认明天入住，住1晚（可在代码中修改）
5. **输入酒店关键词** - 搜索特定酒店或区域
6. **点击搜索** - 自动搜索并点击第一个酒店
7. **获取房型数据** - 提取房型名称、价格等信息
8. **保存结果** - 保存到 `feizhu_hotel.json`

## 日期选择说明

飞猪使用的是复杂的日期选择组件（antd DatePicker），脚本会自动：
- 点击日期选择器
- 选择明天作为入住日期
- 选择后天作为离店日期

如需修改日期，在 `run()` 函数调用时传入参数：

```python
run("杭州", "西湖", check_in_days=2, nights=3)
# check_in_days=2 表示后天入住
# nights=3 表示住3晚
```

## XPath说明

根据你提供的信息，脚本使用了以下XPath：

| 元素 | XPath |
|------|-------|
| 地址输入框 | `//*[@id="J_HomeContainer"]/div/div[1]/div[1]/div[1]/div/div/div[2]/div[1]/div[2]/input` |
| 关键词输入框 | `//*[@id="J_HomeContainer"]/div/div[1]/div[1]/div[1]/div/div/div[2]/div[2]/input` |
| 日期选择器 | `//div[contains(@class,"domestic_RangePicker_show")]` |

## 输出示例

```json
{
  "搜索时间": "2025-12-18 12:00:00",
  "地址": "杭州",
  "酒店关键词": "西湖",
  "入住日期": "2025-12-19",
  "离店日期": "2025-12-20",
  "房型总数": 5,
  "房型列表": [
    {
      "房型名称": "豪华大床房",
      "价格": "¥588",
      "备注": "含早餐 | 免费取消"
    },
    {
      "房型名称": "标准双床房",
      "价格": "¥468",
      "备注": "不含早 | 不可取消"
    }
  ]
}
```

## 注意事项

1. **浏览器要求**
   - 需要Chromium浏览器（路径：`D:\yingyong\tool\chrome-win\chrome.exe`）
   - 首次运行前请确保关闭所有Chromium窗口

2. **网络要求**
   - 需要稳定的网络连接
   - 飞猪页面加载较慢，请耐心等待

3. **反爬虫**
   - 脚本已添加反检测措施（模拟人工操作、随机延迟等）
   - 建议不要频繁运行，避免被检测

4. **页面结构变化**
   - 如果飞猪更新了页面结构，XPath可能失效
   - 需要重新定位元素并更新脚本

## 常见问题

### 1. 日期选择失败
**原因**：飞猪的日期选择器是动态加载的，可能需要更长等待时间

**解决**：
- 手动选择日期后继续运行
- 或在代码中增加等待时间

### 2. 未找到酒店列表
**原因**：搜索结果页面结构可能变化

**解决**：
- 使用浏览器开发者工具查看实际元素
- 更新 `hotel_item_xpaths` 中的XPath

### 3. 登录态丢失
**原因**：Cookies过期或被清除

**解决**：
- 删除 `feizhu_cookies.pkl` 文件
- 重新运行脚本并手动登录

## 技术栈

- **Selenium** - 浏览器自动化
- **ChromeDriver** - Chrome浏览器驱动（通过webdriver-manager自动管理）
- **Python 3.x** - 开发语言

## 与其他平台对比

| 平台 | 登录方式 | 页面类型 | 难点 |
|------|----------|----------|------|
| 美团 | Cookies | H5移动端 | 需要手机端页面 |
| 携程 | 本地用户数据 | PC端 | 反爬虫较严格 |
| **飞猪** | **本地数据+Cookies** | **PC端** | **复杂日期选择器** |

## 更新日志

### v1.0.0 (2025-12-18)
- 初始版本
- 支持地址和关键词搜索
- 支持日期选择
- 支持房型数据提取
- 支持Cookies保存和加载

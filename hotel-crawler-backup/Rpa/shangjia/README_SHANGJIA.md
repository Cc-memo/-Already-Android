# 代理通自动上架RPA工具

使用 Python + Playwright 实现的代理通后台自动上架工具。

## 📋 功能特点

- ✅ 支持批量上架多个酒店
- ✅ 支持多渠道选择（Trip、Qunar、B2B等）
- ✅ 支持多房型批量操作
- ✅ 支持日期范围选择
- ✅ 支持价格、库存、开关房等操作
- ✅ 自动截图记录操作过程
- ✅ 完整的日志记录
- ✅ 支持Cookies保存登录态

## 🚀 快速开始

### 1. 安装依赖

```bash
# 安装Python依赖
pip install playwright pyyaml

# 安装Playwright浏览器
playwright install chromium
```

### 2. 配置参数

编辑 `config.yaml` 文件，填写你的登录信息和任务参数：

```yaml
login:
  url: "https://你的代理通后台地址"
  username: "你的用户名"
  password: "你的密码"

task:
  hotels:
    - "你的酒店名称"
  channels:
    - "Trip"
    - "Qunar"
  room_types:
    - "大床房"
    - "双床房"
  date_start: "2025-01-01"
  date_end: "2025-12-31"
  action: "price"
  value: 968
```

### 3. 首次登录并保存Cookies（重要！）

**首次使用必须先运行登录工具保存Cookies**，这样后续运行就不需要每次都登录了：

```bash
# 运行登录工具（交互式）
python shangjia_cookies.py
```

操作步骤：
1. 工具会自动打开浏览器
2. 如果检测到已保存的Cookies，会先加载
3. 在浏览器中完成登录操作
4. 登录成功后，按回车保存Cookies
5. Cookies会保存到 `shangjia_cookies.pkl` 文件

**测试Cookies是否有效**：
```bash
python shangjia_cookies.py test
```

这会打开浏览器，加载Cookies，并测试是否仍然有效。

### 4. 使用 Playwright Codegen 录制选择器

**这是最关键的一步！** 你需要手动操作一次，让 Playwright 帮你生成选择器。

#### 步骤：

1. **启动录制器**：
```bash
playwright codegen "https://你的代理通后台地址"
```

2. **手动操作一遍完整流程**：
   - 登录
   - 导航到日历/房态管理页面
   - 选择酒店
   - 选择房型
   - 点击"批量修改"按钮
   - 填写日期范围
   - 选择渠道
   - 填写价格/库存等
   - 点击确认提交

3. **复制生成的选择器**：
   - Playwright 会生成类似这样的代码：
   ```python
   page.click('button:has-text("批量修改")')
   page.fill('input[name="date_start"]', '2025-01-01')
   ```
   - 将这些选择器复制到 `shangjia_rpa.py` 中对应的 TODO 位置

4. **替换 TODO 标记的代码**：
   - 在 `shangjia_rpa.py` 中找到所有 `TODO:` 标记
   - 用录制得到的选择器替换示例代码

### 5. 填入选择器

将录制得到的选择器填入 `shangjia_rpa.py` 中所有 `TODO:` 标记的位置。

### 6. 运行RPA脚本

```bash
python shangjia_rpa.py
```

**工作流程**：
- 首次运行：如果没有Cookies，会自动执行登录并保存
- 后续运行：自动加载Cookies，如果有效则跳过登录，直接执行任务
- Cookies失效：自动检测到失效后，会重新执行登录并更新Cookies

## 📁 项目结构

```
shangjia/
├── config.yaml              # 配置文件（登录信息、任务参数）
├── shangjia_rpa.py          # 主RPA脚本
├── shangjia_cookies.py      # Cookies管理工具（独立工具）
├── shangjia_cookies.pkl     # 保存的Cookies（自动生成）
├── screenshots/             # 截图目录（自动生成）
│   ├── login_success.png
│   ├── calendar_page.png
│   └── ...
└── README_SHANGJIA.md       # 本说明文档
```

## 🔧 模块说明

脚本采用模块化设计，每个函数负责一个独立的功能：

### 核心函数

1. **`login()`** - 登录代理通后台
2. **`goto_calendar_page()`** - 导航到日历/房态管理页面
3. **`select_hotel(hotel_name)`** - 选择门店/酒店
4. **`select_room_types(room_types)`** - 选择房型（可多选）
5. **`open_batch_modal()`** - 打开批量修改弹窗
6. **`fill_batch_form(params)`** - 填写批量修改表单
7. **`submit_and_verify()`** - 提交表单并验证结果
8. **`_take_screenshot(name)`** - 截图保存（自动调用）

### 辅助函数

- `_wait_and_click()` - 等待元素并点击（带重试）
- `_wait_and_fill()` - 等待输入框并填写
- `_wait_and_select()` - 等待下拉框并选择
- `_random_sleep()` - 随机等待（模拟人工操作）
- `_save_cookies()` / `_load_cookies()` - Cookies管理

## 📝 配置说明

### 登录配置

```yaml
login:
  url: "后台地址"
  username: "用户名"
  password: "密码"
  use_cookies: true  # 是否使用Cookies保存登录态
```

### 任务配置

```yaml
task:
  hotels:           # 酒店列表（支持多个）
    - "酒店1"
    - "酒店2"
  
  channels:          # 渠道（可多选）
    - "Trip"
    - "Qunar"
    - "B2B"
  
  room_types:       # 房型（可多选）
    - "大床房"
    - "双床房"
  
  date_start: "2025-01-01"  # 开始日期
  date_end: "2025-12-31"    # 结束日期
  
  weekdays: []      # 星期筛选（空=全选）
  
  action: "price"   # 操作类型: price/inventory/open_close
  value: 968        # 操作值（价格/库存数量/true-false）
```

### 浏览器配置

```yaml
browser:
  headless: false   # true=无头模式（不显示浏览器）
  slow_mo: 500      # 操作延迟（毫秒）
  timeout: 30000    # 超时时间（毫秒）
```

## 🎯 使用流程

### 第一次使用（需要录制选择器）

1. ✅ 安装依赖
2. ✅ 配置 `config.yaml`
3. ✅ 运行 `playwright codegen` 录制一次操作
4. ✅ 将选择器填入 `shangjia_rpa.py` 的 TODO 位置
5. ✅ 运行脚本测试

### 日常使用

1. ✅ 修改 `config.yaml` 中的任务参数
2. ✅ 运行 `python shangjia_rpa.py`
3. ✅ 查看日志和截图确认结果

## 🔍 调试技巧

### 1. 查看截图

所有关键步骤都会自动截图，保存在 `screenshots/` 目录：
- `login_success.png` - 登录成功
- `calendar_page.png` - 日历页面
- `batch_modal_opened.png` - 弹窗打开
- `failed_*.png` - 失败时的截图

### 2. 查看日志

日志文件：`shangjia_rpa.log`

日志级别可以在 `config.yaml` 中设置：
```yaml
logging:
  log_level: "DEBUG"  # DEBUG/INFO/WARNING/ERROR
```

### 3. 使用非无头模式

在 `config.yaml` 中设置：
```yaml
browser:
  headless: false  # 显示浏览器，方便观察操作过程
```

### 4. 慢速模式

增加操作延迟，方便观察：
```yaml
browser:
  slow_mo: 1000  # 每个操作延迟1秒
```

## ⚠️ 注意事项

1. **选择器稳定性**：
   - 优先使用稳定的选择器（如 `name`、`id`）
   - 避免使用易变的类名或XPath
   - 如果页面结构变化，需要重新录制

2. **Cookies管理**：
   - 首次登录后会自动保存Cookies
   - 下次运行会自动加载，可能无需重新登录
   - 如果登录失效，删除 `shangjia_cookies.pkl` 重新登录

3. **错误处理**：
   - 脚本包含重试机制
   - 失败时会自动截图
   - 查看截图和日志定位问题

4. **批量操作**：
   - 脚本会遍历所有配置的酒店
   - 每个酒店独立处理，一个失败不影响其他

## 🐛 常见问题

### Q: 选择器找不到元素？

A: 
1. 检查页面是否已加载完成
2. 使用 `playwright codegen` 重新录制
3. 查看截图确认页面状态
4. 尝试更通用的选择器（如 `text=` 选择器）

### Q: 登录后Cookies失效？

A: 
1. **方法1（推荐）**：运行 `python shangjia_cookies.py` 重新登录并保存
2. **方法2**：删除 `shangjia_cookies.pkl` 文件，然后运行RPA脚本会自动重新登录
3. **测试Cookies**：运行 `python shangjia_cookies.py test` 检查Cookies是否有效

### Q: 如何只处理一个酒店？

A: 在 `config.yaml` 中只配置一个酒店：
```yaml
task:
  hotels:
    - "单个酒店名称"
```

### Q: 如何修改操作类型？

A: 在 `config.yaml` 中修改：
```yaml
task:
  action: "inventory"  # 改为库存操作
  value: 2              # 库存数量
```

## 📚 参考资源

- [Playwright 官方文档](https://playwright.dev/python/)
- [Playwright Codegen 使用指南](https://playwright.dev/python/docs/codegen)
- [YAML 配置文件格式](https://yaml.org/)

## 💡 优化建议

1. **选择器优化**：
   - 使用 `data-testid` 等测试属性（如果页面有）
   - 使用相对选择器而非绝对XPath

2. **性能优化**：
   - 减少不必要的等待时间
   - 批量操作时考虑并行处理

3. **稳定性提升**：
   - 增加更多重试机制
   - 添加更详细的错误处理

4. **功能扩展**：
   - 支持Excel批量导入任务
   - 支持定时任务
   - 支持邮件通知

## 🔐 Cookies管理说明

### 独立Cookies工具的优势

- **职责分离**：Cookies管理独立于RPA主流程
- **灵活使用**：可以单独运行进行登录和测试
- **易于维护**：Cookies相关逻辑集中在一个文件

### Cookies工具使用

**登录并保存Cookies**：
```bash
python shangjia_cookies.py
```

**测试Cookies有效性**：
```bash
python shangjia_cookies.py test
```

### RPA脚本中的Cookies流程

1. **启动时**：自动尝试加载已保存的Cookies
2. **验证**：检查Cookies是否仍然有效（访问登录后页面）
3. **决策**：
   - Cookies有效 → 跳过登录，直接执行任务
   - Cookies无效/不存在 → 执行登录，保存新Cookies
4. **保存**：登录成功后自动保存Cookies供下次使用

---

**提示**：
1. 首次使用请先运行 `python shangjia_cookies.py` 登录并保存Cookies
2. 然后使用 `playwright codegen` 录制一次，获取准确的选择器
3. 将选择器填入 `shangjia_rpa.py` 后即可正常使用


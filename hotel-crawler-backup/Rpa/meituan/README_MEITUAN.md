# 美团酒店RPA使用说明

## 🚀 快速开始

### 第一步：登录并保存登录态

首次使用需要先登录：

```powershell
python meituan_cookies.py
```

按提示在浏览器中完成登录，登录态会保存到 `meituan_h5_cookies.pkl` 文件。

### 第二步：运行爬虫

```powershell
python meituan_rpa.py
```

会自动加载已保存的登录态，无需重复登录。

## 📝 详细说明

### 登录工具 (meituan_cookies.py)

- **功能**：登录美团H5页面并保存Cookies
- **使用**：
  ```powershell
  python meituan_cookies.py         # 登录并保存
  python meituan_cookies.py test    # 测试保存的Cookies是否有效
  ```

### 主程序 (meituan_rpa.py)

- **功能**：自动搜索酒店并获取房型信息
- **输入**：地址关键词 + 酒店关键词
- **输出**：`meituan_hotel.json` (包含所有房型信息)

## 🔧 常见问题

### 1. 登录态失效怎么办？

重新运行登录工具：
```powershell
python meituan_cookies.py
```

### 2. 为什么每次都要登录？

确保：
- 使用登录工具保存了Cookies
- `meituan_h5_cookies.pkl` 文件存在
- 运行主程序前关闭所有 Chromium/Chrome 窗口

### 3. Cookies保存在哪里？

保存在当前目录的 `meituan_h5_cookies.pkl` 文件中

## 📂 文件说明

- `meituan_rpa.py` - 主程序（爬取房型）
- `meituan_cookies.py` - 登录工具（保存登录态）
- `meituan_h5_cookies.pkl` - 保存的Cookies文件
- `meituan_hotel.json` - 输出的房型数据


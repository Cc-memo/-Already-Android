# 飞猪自动爬取（手机端全流程）

自动打开飞猪、搜索写死酒店、进入详情，触发 Fiddler 抓包落盘到 `Android-/json/in/`。

## 依赖

```bash
pip install -r requirements.txt
# 首次使用在手机连 USB 时执行一次
python -m uiautomator2 init
```

## 前置条件

- 手机 USB 连接电脑，开启 USB 调试
- PC 上 Fiddler 已开启，手机代理指向 Fiddler，且 CustomRules 已配置自动保存 `mtop.trip.hotel.hotel.module.detail` 响应到 `Android-/json/in/`
- 飞猪已安装（包名 `com.taobao.trip`）

## 运行

在项目根目录（mobile）或本目录执行：

```bash
# 从项目根
python Android-/Feizhu/feizhu_auto_crawl.py

# 或进入本目录
cd Android-/Feizhu
python feizhu_auto_crawl.py
```

## 写死参数

在 `feizhu_auto_crawl.py` 顶部修改：

- `HOTEL_NAME`: 要搜索的酒店名（如 `杭州西湖国宾馆`）
- `FLIGGY_PACKAGE`: 飞猪包名（默认 `com.taobao.trip`）
- `WAIT_*`: 各步等待秒数，网络慢可适当加大

## 后续解析

抓包完成后，本脚本会自动调用项目根目录下 `scripts/feizhu_task_export.py`，
把 `Android-/json/in/feizhu_detail_*.json` 转成套餐数据，并输出到 `Android-/json/out/`：

```bash
# 输出文件默认使用 overwrite：Android-/json/out/hotel_data.json
```

## 元素定位

若界面改版导致点击失败，可 dump 当前界面查看可用的 resource-id / text：

```bash
python -c "import uiautomator2 as u2; u2.connect().dump('hierarchy.xml')"
# 当前目录会生成 hierarchy.xml，用编辑器搜索「搜索」「酒店」等关键字
```

再在 `feizhu_auto_crawl.py` 里调整 `d(text=...)` / `d(resourceId=...)` 等选择器。

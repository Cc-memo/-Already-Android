# -*- coding: utf-8 -*-
"""
最小化 Selenium 启动自检脚本（Windows 友好）

用法（PowerShell）：
  # 方式1：最稳，手动指定 chromedriver.exe
  $env:CHROME_DRIVER_PATH="C:\path\to\chromedriver.exe"
  python .\Rpa\test_browser.py

  # 方式2：让 webdriver-manager 自动下载（需要能联网）
  $env:USE_WDM="1"
  python .\Rpa\test_browser.py
"""

import os
import platform

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def _pick_chrome_bin() -> str | None:
    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin and os.path.exists(chrome_bin):
        return chrome_bin

    if platform.system() != "Windows":
        return None

    candidates = [
        os.path.join(os.getenv("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.getenv("PROGRAMFILES", ""), "Chromium", "Application", "chrome.exe"),
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Chromium", "Application", "chrome.exe"),
        r"D:\yingyong\tool\chrome-win\chrome.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def main():
    chrome_options = Options()
    chrome_bin = _pick_chrome_bin()
    if chrome_bin:
        chrome_options.binary_location = chrome_bin
        print(f"使用浏览器: {chrome_bin}")
    else:
        print("使用系统默认 Chrome（未指定 CHROME_BIN）")

    chrome_driver_path = os.getenv("CHROME_DRIVER_PATH")
    if chrome_driver_path and not os.path.exists(chrome_driver_path):
        raise FileNotFoundError(f"CHROME_DRIVER_PATH 指向的文件不存在: {chrome_driver_path}")

    if chrome_driver_path:
        print(f"使用 CHROME_DRIVER_PATH: {chrome_driver_path}")
        service = Service(executable_path=chrome_driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        # 优先 webdriver-manager（如可用 + 允许），否则交给 Selenium Manager
        use_wdm = os.getenv("USE_WDM", "0") == "1"
        if use_wdm:
            from webdriver_manager.chrome import ChromeDriverManager
            try:
                from webdriver_manager.core.os_manager import ChromeType
            except Exception:
                ChromeType = None  # type: ignore

            is_chromium = bool(chrome_bin) and any(k in chrome_bin.lower() for k in ("chromium", "chrome-win"))
            print("使用 webdriver-manager 自动获取 ChromeDriver...")
            if is_chromium and ChromeType is not None:
                service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
            else:
                service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            print("使用 Selenium Manager 自动获取驱动（可能受网络/权限影响）...")
            driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get("https://example.com/")
        print("✅ 启动成功，已打开 example.com")
        print("标题:", driver.title)
        input("按回车关闭浏览器...")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()


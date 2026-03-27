@echo off
chcp 65001 >nul
echo ========================================
echo 代理通RPA工具 - 环境安装脚本
echo ========================================
echo.

echo [1/3] 安装Python依赖...
pip install playwright pyyaml
if errorlevel 1 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)

echo.
echo [2/3] 安装Playwright浏览器...
playwright install chromium
if errorlevel 1 (
    echo ❌ 浏览器安装失败
    pause
    exit /b 1
)

echo.
echo [3/3] 检查配置文件...
if not exist "config.yaml" (
    echo ⚠️  配置文件 config.yaml 不存在
    echo    请复制 config.yaml.example 并修改配置
) else (
    echo ✓ 配置文件已存在
)

echo.
echo ========================================
echo ✓ 安装完成！
echo ========================================
echo.
echo 下一步：
echo 1. 编辑 config.yaml 填写登录信息和任务参数
echo 2. 运行: playwright codegen "你的后台地址" 录制选择器
echo 3. 将选择器填入 shangjia_rpa.py 的 TODO 位置
echo 4. 运行: python shangjia_rpa.py
echo.
pause


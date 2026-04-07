# 手机端任务调度：设置云 Web Admin 地址、激活 conda 环境 work、启动 app_scheduler
# 用法：在 PowerShell 中执行  .\run_scheduler.ps1
# 若提示无法加载脚本，可先执行：Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
$ErrorActionPreference = 'Stop'

$env:APP_SCHEDULER_BASE_URL = 'http://8.153.81.55:5000'

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error 'conda not in PATH; add condabin to PATH or use Anaconda Prompt.'
    exit 1
}

(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression
conda activate work

Set-Location $PSScriptRoot
python test\app_scheduler.py

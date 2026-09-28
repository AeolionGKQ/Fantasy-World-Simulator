@echo off
setlocal
chcp 65001 >nul
title Fantasy Simulator

set "PROJECT_DIR=%~dp0"
set "WEB_DIR=%PROJECT_DIR%apps\web"
set "PYTHON_EXE=%PROJECT_DIR%runtime\python\python.exe"
set "SERVER_FILE=%PROJECT_DIR%apps\api\server.py"
set "APP_URL=http://127.0.0.1:8000"

if not exist "%PYTHON_EXE%" (
  echo [错误] 未找到项目自带的 Python 运行时：
  echo %PYTHON_EXE%
  pause
  exit /b 1
)

if not exist "%WEB_DIR%\dist\index.html" (
  echo [提示] 正在构建网页前端...
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [错误] 前端尚未构建，且系统中没有 npm。请安装 Node.js 后重试。
    pause
    exit /b 1
  )
  pushd "%WEB_DIR%"
  if not exist "node_modules" call npm install
  if errorlevel 1 goto :build_failed
  call npm run build
  if errorlevel 1 goto :build_failed
  popd
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='%APP_URL%/api/health'; try { $h=Invoke-RestMethod -Uri $u -TimeoutSec 1; if ($h.status -eq 'ok' -and $h.app_id -eq 'fantasy-simulator' -and $h.api_version -eq '1') { exit 0 }; exit 2 } catch { exit 1 }" >nul 2>nul
if errorlevel 2 (
  echo [错误] 端口 8000 已被其他服务占用。请关闭该服务后重试。
  pause
  exit /b 1
)
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',8000); exit 0 } catch { exit 1 } finally { $c.Dispose() }" >nul 2>nul
  if not errorlevel 1 (
    echo [错误] 端口 8000 已被其他服务占用，且健康标识不匹配。请关闭该服务后重试。
    pause
    exit /b 1
  )
  echo [启动] Fantasy Simulator 后端服务...
  start "Fantasy Simulator Server" /D "%PROJECT_DIR%" "%PYTHON_EXE%" "%SERVER_FILE%" --host 127.0.0.1 --port 8000
)

echo [等待] 正在确认服务可用...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='%APP_URL%/api/health'; 1..40 | ForEach-Object { try { $h=Invoke-RestMethod -Uri $u -TimeoutSec 1; if ($h.status -eq 'ok' -and $h.app_id -eq 'fantasy-simulator' -and $h.api_version -eq '1') { exit 0 } } catch {}; Start-Sleep -Milliseconds 250 }; exit 1"
if errorlevel 1 (
  echo [错误] 服务未能在 10 秒内启动。请查看“Fantasy Simulator Server”窗口中的信息。
  pause
  exit /b 1
)

echo [完成] 正在打开浏览器：%APP_URL%
start "" "%APP_URL%"
exit /b 0

:build_failed
popd
echo [错误] 网页前端构建失败，请检查上方日志。
pause
exit /b 1

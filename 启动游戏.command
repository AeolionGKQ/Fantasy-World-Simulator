#!/bin/bash
# Fantasy Simulator launcher for macOS: finds Python 3.9+, starts the game server and opens the
# browser. Closing this Terminal window stops the game. Written for the bash 3.2 that macOS ships.

cd "$(dirname "$0")" || exit 1

fail() {
  echo "[错误] $1"
  echo
  read -r -p "按回车键关闭窗口…" _
  exit 1
}

healthy() {
  curl -fsS --max-time 1 "$APP_URL/api/health" 2>/dev/null | grep -Eq '"app_id": ?"fantasy-simulator"'
}

if [ ! -f "apps/api/server.py" ] || [ ! -f "apps/web/dist/index.html" ]; then
  fail "游戏文件不完整，请重新解压下载的压缩包后再试。"
fi

# Python 3.9 or newer: Homebrew, the python.org installer, whatever is on PATH, then the system one.
PYTHON=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3 /usr/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  fail "没有找到 Python 3.9 或更高版本。请从 https://www.python.org/downloads/ 安装 Python 3 后再双击本文件。"
fi

# The game already running on a port from 8000 on is reused; otherwise the first free port is used.
read -r LAUNCH_MODE PORT <<EOF
$("$PYTHON" apps/api/launch_port.py)
EOF
APP_URL="http://127.0.0.1:$PORT"
case "$LAUNCH_MODE" in
  running)
    echo "[完成] 游戏已经在运行，正在打开浏览器：$APP_URL"
    open "$APP_URL"
    exit 0
    ;;
  free) ;;
  *) fail "端口 8000 至 8099 都已被占用，无法启动服务。请关闭部分程序后重试。" ;;
esac
if [ "$PORT" != "8000" ]; then
  echo "[提示] 端口 8000 已被占用，本次改用端口 $PORT。"
fi

echo "[启动] Fantasy Simulator 后端服务（$("$PYTHON" -V 2>&1)）"
"$PYTHON" apps/api/server.py --host 127.0.0.1 --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT INT TERM HUP

echo "[等待] 正在确认服务可用…"
for _ in $(seq 1 60); do
  healthy && break
  kill -0 "$SERVER_PID" 2>/dev/null || fail "服务启动失败，请查看上方的错误信息。"
  sleep 0.25
done
healthy || fail "服务未能在 15 秒内启动，请查看上方的错误信息。"

echo "[完成] 正在打开浏览器：$APP_URL"
open "$APP_URL"
echo
echo "游戏正在运行。关闭这个窗口或按 Control+C 即可停止服务。"
wait "$SERVER_PID"

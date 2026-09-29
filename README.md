# Fantasy Simulator

基于 LLM GM 的单人文字 RPG。当前已落地第一阶段：多存档、模型设置、13 步角色创建、角色候选生成与确认、JSON 导入导出及游戏起点页面。

## 启动

Windows 11 下双击根目录的 `启动游戏.bat`。脚本会使用项目自带的 Python 运行时启动服务，等待健康检查通过，然后打开 `http://127.0.0.1:8000`。

首次从源码启动时，如果 `apps/web/dist` 不存在，脚本会调用本机 Node.js/npm 安装已锁定的前端依赖并完成构建。当前仓库已包含构建产物，日常启动不依赖 Node.js。

关闭名为 `Fantasy Simulator Server` 的终端窗口即可停止后端。游戏数据保存在 `apps/api/.data`，存档也可在界面中导出为 JSON。API Key 在 Windows 上使用当前用户的 DPAPI 加密后写入 `secrets.dat`，不会以明文写入数据文件；非 Windows 或 DPAPI 失败时只保存在当前进程内存，重启后需要重新输入。

设置页的“测试连接”会在基础连接成功后，以最小聊天请求探测模型服务能否控制思考，因此可能产生少量费用。探测覆盖七种兼容参数：`enable_thinking`、`thinking.type`、`reasoning_effort`、`chat_template_kwargs.enable_thinking`、`reasoning.enabled`、`reasoning.effort` 和 `thinking_config.thinking_budget`。能力按 Base URL、模型和探测配置版本缓存；未测试或不支持关闭时，开关保持开启并禁用，表示模型使用服务默认行为或不受应用控制。只有探测到可控策略后才能保存开启/关闭偏好。

## 开发与测试

```powershell
cd "D:\Fantasy Simulator\apps\web"
npm run dev
npm run test
npm run build

& "D:\Fantasy Simulator\runtime\python\python.exe" -m unittest discover -s "D:\Fantasy Simulator\apps\api\tests" -v
```

前端开发服务器默认将 `/api` 转发至 `127.0.0.1:8000`。直接运行后端：

```powershell
& "D:\Fantasy Simulator\runtime\python\python.exe" "D:\Fantasy Simulator\apps\api\server.py"
```

## 当前边界

角色确认后进入第一阶段游戏壳。玩家行动、正式 GM 回合、战斗、成长和长期记忆将在后续阶段实现。

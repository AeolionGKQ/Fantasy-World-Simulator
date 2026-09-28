# Fantasy World Simulator

一个由 LLM 担任 GM 的本地单人文字 RPG。应用把完整世界设定、程序维护的权威状态和模型叙事组合起来，让玩家创建角色并在多个彼此隔离的存档中进行长篇冒险。

项目目前面向 Windows 11 x64，包含可直接运行的 Windows Python 3.14 嵌入式运行时和已构建前端。

## 已实现功能

- 多存档创建、切换、导入、导出与乐观并发保护。
- OpenAI-compatible 模型设置、最长 300 秒请求超时、最多 16 个并发请求。
- 七种常见模型思考控制参数的能力探测与有界回退。
- Response Format 默认关闭；用户开启时发起一次最小探测，不支持时自动保持关闭。
- 13 步角色创建，以及由模型提出、程序校验的初始属性和资源。
- 正式 GM 回合、2 至 3 个建议选项、自由行动、干涉命运和最新节点重塑。
- HP、MP、SP、ST，CON、INT、CHA，EXP、突破与战力规则。
- 背包、货币、任务、纪事、长期记忆、故事弧、羁绊和固定七项声望。
- 地区引导任务按地点动态注入，完成后从任务上下文和任务栏移除。
- 大型存档导入、内容版本快照，以及未知内容版本的显式信任流程。

## 快速开始

1. 克隆或下载本仓库。
2. 双击根目录的 `启动游戏.bat`。
3. 等待浏览器打开 `http://127.0.0.1:8000`。
4. 在设置页填写自己的 OpenAI-compatible API Base URL、模型名称和 API Key，然后测试连接。

正常游玩不需要另行安装 Python 或 Node.js。启动脚本只监听 `127.0.0.1`，不会向局域网开放服务。关闭标题为 `Fantasy Simulator Server` 的窗口即可停止后端。

如果端口 8000 已被占用，启动脚本会停止并提示关闭冲突服务。如果 `apps/web/dist/index.html` 缺失，脚本会尝试使用本机 npm 恢复前端构建。

## 模型兼容性

应用使用 OpenAI-compatible `/models` 与 `/chat/completions` 接口。

- 正式游戏会将六份规则原文和八份世界设定原文完整发送给用户配置的模型服务，并按当前位置附加地区任务内容。
- 应用不手动限制模型最大上下文长度。模型服务报告上下文超限时，本次任务保持原状态并提示更换长上下文模型，不会静默删减设定。
- Response Format 默认关闭。尝试开启时会发送一次很小的 `response_format: {"type":"json_object"}` 请求，可能产生少量费用；只有探测成功后才能保存开启状态。
- 思考控制支持 `enable_thinking`、`thinking.type`、`reasoning_effort`、`chat_template_kwargs.enable_thinking`、`reasoning.enabled`、`reasoning.effort` 和 `thinking_config.thinking_budget`。不同模型和网关的支持情况可能不同。
- 模型只提出叙事与状态变更。所有结果都要通过本地严格 JSON 契约和规则裁决后才会写入存档。

建议选择上下文足够长、能稳定输出严格 JSON 的模型。模型调用和能力探测可能产生服务商费用。

## 数据与安全

运行数据位于 `apps/api/.data/`，包括本地 SQLite 存档、模型设置和内容版本快照。

API Key 不写入 SQLite 或导出存档。在 Windows 上，密钥使用当前用户的 DPAPI 加密并保存为 `apps/api/.data/secrets.dat`；DPAPI 不可用时只保存在当前进程内存。`.gitignore` 已排除 `.data/`、`secrets.dat`、数据库、环境变量、日志和导出存档。

不要提交、分享或上传以下内容：

- `apps/api/.data/`
- `secrets.dat` 或 `secrets.json`
- `.env`、私钥和证书
- 包含私人角色或剧情的存档导出文件

导入携带未知规则或世界设定版本的存档时，应用会展示文档清单和哈希，只有用户明确确认后才会安装该内容版本。

## 架构

```text
apps/web                 React + TypeScript + Vite 前端
apps/api                 Python 标准库 HTTP 服务与 SQLite 权威状态
apps/api/content         GM 输出契约、协议和 JSON Schema
runtime/python           Windows Python 3.14 嵌入式运行时
docs                     实现规划与架构背景
根目录世界/规则文档     运行时读取并注入模型的权威内容
```

后端使用 `ThreadingHTTPServer`、`sqlite3` 和 `urllib.request`，没有 pip 第三方依赖。生产环境由后端直接提供 `apps/web/dist` 中的 SPA。

## 开发

前端开发需要 Node.js 和 npm。当前版本使用 React 19、TypeScript 5.9 和 Vite 8，依赖版本锁定在 `package-lock.json`。

```powershell
# 在仓库根目录
Set-Location .\apps\web
npm ci
npm run dev
```

前端开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。另开一个 PowerShell 窗口启动后端：

```powershell
# 在仓库根目录
& ".\runtime\python\python.exe" ".\apps\api\server.py"
```

## 测试与构建

```powershell
# 后端
& ".\runtime\python\python.exe" -m unittest discover -s ".\apps\api\tests" -v

# 前端
Set-Location .\apps\web
npm ci
npm test
npm run build
```

当前自动化测试覆盖内容原文完整性、模型兼容、并发幂等、状态裁决、地区任务、重塑、导入导出和前后端 DTO。真实模型效果仍取决于具体服务商和模型质量。

## 世界设定与许可证

六份规则、八份世界正典和地区引导主线位于仓库根目录。它们既是公开设定文档，也是应用运行时必需的内容源；删除或重命名会导致服务无法正确构建模型上下文。

项目使用仓库根目录的 Apache License 2.0。嵌入式 Python 的许可证保留在 `runtime/python/LICENSE.txt`；随前端构建分发的组件及其他第三方说明见 `THIRD_PARTY_NOTICES.md`，依赖版本记录在 `apps/web/package-lock.json`。

## 当前边界

当前版本聚焦本地单人游戏，不包含账户系统、云同步、多人协作、语音或图片生成。应用会把角色状态、剧情历史和公开世界设定发送到用户选择的模型 API，请只配置你信任的服务商。
